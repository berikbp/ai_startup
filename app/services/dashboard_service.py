from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Booking, BookingStatus, Message, MessageRole, Patient
from app.services.normalization import normalize_whitespace


@dataclass(slots=True)
class BookingListItem:
    booking_id: uuid.UUID
    patient_name: str
    patient_phone: str
    service_type: str
    preferred_datetime: str
    status: str
    created_at: str


@dataclass(slots=True)
class BookingListResult:
    items: list[BookingListItem]
    counts: dict[str, int]


@dataclass(slots=True)
class ConversationItem:
    role: str
    content: str
    created_at: str


@dataclass(slots=True)
class BookingDetailResult:
    booking_id: uuid.UUID
    patient_name: str
    patient_phone: str
    service_type: str
    preferred_datetime: str
    preferred_datetime_raw: str
    status: str
    created_at: str
    updated_at: str
    messages: list[ConversationItem]


async def list_bookings(
    session: AsyncSession,
    *,
    clinic_id: uuid.UUID,
    clinic_timezone: str,
    status_filter: str | None = None,
    search_query: str | None = None,
) -> BookingListResult:
    statement = (
        select(Booking, Patient)
        .join(Patient, Booking.patient_id == Patient.id)
        .where(Booking.clinic_id == clinic_id)
    )

    if status_filter:
        try:
            status = BookingStatus(status_filter)
        except ValueError:
            status = None
        if status is not None:
            statement = statement.where(Booking.status == status)

    normalized_search = normalize_whitespace(search_query)
    if normalized_search:
        pattern = f"%{normalized_search}%"
        statement = statement.where(
            or_(
                Booking.service_type.ilike(pattern),
                Patient.full_name.ilike(pattern),
                Patient.phone_number.ilike(pattern),
            )
        )

    statement = statement.order_by(Booking.created_at.desc())
    result = await session.execute(statement)

    items = [
        BookingListItem(
            booking_id=booking.id,
            patient_name=patient.full_name or "Не указано",
            patient_phone=patient.phone_number or "Не указано",
            service_type=booking.service_type,
            preferred_datetime=_format_preferred_datetime(booking, clinic_timezone),
            status=_status_value(booking.status),
            created_at=_format_local_datetime(booking.created_at, clinic_timezone),
        )
        for booking, patient in result.all()
    ]

    count_statement = (
        select(Booking.status, func.count())
        .where(Booking.clinic_id == clinic_id)
        .group_by(Booking.status)
    )
    counts_result = await session.execute(count_statement)
    counts = {status.value: 0 for status in BookingStatus}
    for status, raw_count in counts_result.all():
        key = status.value if isinstance(status, BookingStatus) else str(status)
        counts[key] = int(raw_count)

    return BookingListResult(items=items, counts=counts)


async def get_booking_detail(
    session: AsyncSession,
    *,
    clinic_id: uuid.UUID,
    clinic_timezone: str,
    booking_id: uuid.UUID,
) -> BookingDetailResult | None:
    statement = (
        select(Booking, Patient)
        .join(Patient, Booking.patient_id == Patient.id)
        .where(
            Booking.id == booking_id,
            Booking.clinic_id == clinic_id,
        )
    )
    result = await session.execute(statement)
    row = result.first()
    if row is None:
        return None

    booking, patient = row

    messages_statement = (
        select(Message)
        .where(
            Message.clinic_id == clinic_id,
            Message.patient_id == patient.id,
        )
        .order_by(Message.created_at.asc())
    )
    messages_result = await session.execute(messages_statement)
    messages = [
        ConversationItem(
            role="Пациент" if message.role == MessageRole.user else "Бот",
            content=message.content,
            created_at=_format_local_datetime(message.created_at, clinic_timezone),
        )
        for message in messages_result.scalars()
    ]

    return BookingDetailResult(
        booking_id=booking.id,
        patient_name=patient.full_name or "Не указано",
        patient_phone=patient.phone_number or "Не указано",
        service_type=booking.service_type,
        preferred_datetime=_format_preferred_datetime(booking, clinic_timezone),
        preferred_datetime_raw=booking.preferred_datetime_text or "Не указано",
        status=_status_value(booking.status),
        created_at=_format_local_datetime(booking.created_at, clinic_timezone),
        updated_at=_format_local_datetime(booking.updated_at, clinic_timezone),
        messages=messages,
    )


async def update_booking_status(
    session: AsyncSession,
    *,
    clinic_id: uuid.UUID,
    booking_id: uuid.UUID,
    new_status: str,
) -> Booking | None:
    try:
        target_status = BookingStatus(new_status)
    except ValueError:
        return None

    booking = await session.get(Booking, booking_id)
    if booking is None or booking.clinic_id != clinic_id:
        return None

    current_status = booking.status if isinstance(booking.status, BookingStatus) else BookingStatus(booking.status)

    allowed_transitions = {
        BookingStatus.pending: {BookingStatus.confirmed, BookingStatus.cancelled},
        BookingStatus.confirmed: {BookingStatus.cancelled},
        BookingStatus.cancelled: {BookingStatus.pending},
    }

    if target_status == current_status:
        return booking

    if target_status not in allowed_transitions.get(current_status, set()):
        return None

    booking.status = target_status
    await session.flush()
    return booking


def _format_preferred_datetime(booking: Booking, clinic_timezone: str) -> str:
    if booking.preferred_datetime_at is not None:
        return _format_local_datetime(booking.preferred_datetime_at, clinic_timezone)
    return booking.preferred_datetime_text or "Не указано"


def _format_local_datetime(value: datetime, timezone_name: str) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    localized = value.astimezone(ZoneInfo(timezone_name))
    return localized.strftime("%d.%m.%Y %H:%M")


def _status_value(value: BookingStatus | str) -> str:
    return value.value if isinstance(value, BookingStatus) else str(value)
