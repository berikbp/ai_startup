from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

import uuid

from app.models import Booking, BookingSource, BookingStatus, Clinic, Patient
from app.services.normalization import normalize_whitespace


@dataclass(slots=True)
class BookingCreateResult:
    booking: Booking
    is_duplicate: bool


async def find_recent_duplicate_booking(
    session: AsyncSession,
    *,
    clinic: Clinic,
    patient: Patient,
    service_type: str,
    preferred_datetime_at: datetime,
    window_seconds: int,
) -> Booking | None:
    threshold = datetime.now(UTC) - timedelta(seconds=window_seconds)
    statement = (
        select(Booking)
        .where(
            Booking.clinic_id == clinic.id,
            Booking.patient_id == patient.id,
            Booking.service_type == normalize_whitespace(service_type),
            Booking.preferred_datetime_at == preferred_datetime_at,
            Booking.created_at >= threshold,
        )
        .order_by(Booking.created_at.desc())
    )
    result = await session.execute(statement)
    return result.scalars().first()


async def create_booking(
    session: AsyncSession,
    *,
    clinic: Clinic,
    patient: Patient,
    service_type: str,
    preferred_datetime_at: datetime,
    preferred_datetime_text: str,
    duplicate_window_seconds: int,
) -> BookingCreateResult:
    duplicate = await find_recent_duplicate_booking(
        session,
        clinic=clinic,
        patient=patient,
        service_type=service_type,
        preferred_datetime_at=preferred_datetime_at,
        window_seconds=duplicate_window_seconds,
    )
    if duplicate is not None:
        return BookingCreateResult(booking=duplicate, is_duplicate=True)

    booking = Booking(
        clinic_id=clinic.id,
        patient_id=patient.id,
        service_type=normalize_whitespace(service_type),
        preferred_datetime_at=preferred_datetime_at,
        preferred_datetime_text=normalize_whitespace(preferred_datetime_text) or None,
        status=BookingStatus.pending,
        source=BookingSource.telegram,
    )
    session.add(booking)
    await session.flush()
    return BookingCreateResult(booking=booking, is_duplicate=False)


async def get_latest_pending_booking(
    session: AsyncSession,
    *,
    clinic: Clinic,
    patient: Patient,
) -> Booking | None:
    statement = (
        select(Booking)
        .where(
            Booking.clinic_id == clinic.id,
            Booking.patient_id == patient.id,
            Booking.status == BookingStatus.pending,
        )
        .order_by(Booking.created_at.desc())
    )
    result = await session.execute(statement)
    return result.scalars().first()


async def get_booking_by_id(
    session: AsyncSession,
    *,
    clinic: Clinic,
    booking_id: uuid.UUID,
) -> Booking | None:
    statement = select(Booking).where(
        Booking.id == booking_id,
        Booking.clinic_id == clinic.id,
    )
    result = await session.execute(statement)
    return result.scalars().first()


async def cancel_booking(
    session: AsyncSession,
    *,
    booking: Booking,
) -> None:
    booking.status = BookingStatus.cancelled
    session.add(booking)
    await session.flush()
