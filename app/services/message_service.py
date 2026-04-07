from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Clinic, Message, MessageRole, Patient
from app.services.normalization import normalize_whitespace


async def log_message(
    session: AsyncSession,
    *,
    clinic: Clinic,
    patient: Patient,
    role: MessageRole,
    content: str,
    telegram_message_id: int | None = None,
    booking_id: uuid.UUID | None = None,
) -> Message:
    message = Message(
        clinic_id=clinic.id,
        patient_id=patient.id,
        booking_id=booking_id,
        role=role,
        content=normalize_whitespace(content) or "[empty]",
        telegram_message_id=telegram_message_id,
    )
    session.add(message)
    await session.flush()
    return message


async def log_user_message(
    session: AsyncSession,
    *,
    clinic: Clinic,
    patient: Patient,
    content: str,
    telegram_message_id: int | None = None,
) -> Message:
    return await log_message(
        session,
        clinic=clinic,
        patient=patient,
        role=MessageRole.user,
        content=content,
        telegram_message_id=telegram_message_id,
    )


async def log_assistant_message(
    session: AsyncSession,
    *,
    clinic: Clinic,
    patient: Patient,
    content: str,
    telegram_message_id: int | None = None,
    booking_id: uuid.UUID | None = None,
) -> Message:
    return await log_message(
        session,
        clinic=clinic,
        patient=patient,
        role=MessageRole.assistant,
        content=content,
        telegram_message_id=telegram_message_id,
        booking_id=booking_id,
    )
