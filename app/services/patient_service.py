from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Clinic, Patient
from app.services.normalization import clean_full_name, normalize_phone_number


async def upsert_patient(
    session: AsyncSession,
    *,
    clinic: Clinic,
    telegram_user_id: int,
    telegram_username: str | None = None,
    full_name: str | None = None,
    phone_number: str | None = None,
) -> Patient:
    statement = select(Patient).where(
        Patient.clinic_id == clinic.id,
        Patient.telegram_user_id == telegram_user_id,
    )
    result = await session.execute(statement)
    patient = result.scalars().first()

    cleaned_name = clean_full_name(full_name)
    cleaned_phone = normalize_phone_number(phone_number)

    if patient is None:
        patient = Patient(
            clinic_id=clinic.id,
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            full_name=cleaned_name,
            phone_number=cleaned_phone,
        )
        session.add(patient)
        await session.flush()
        return patient

    if telegram_username:
        patient.telegram_username = telegram_username
    if cleaned_name:
        patient.full_name = cleaned_name
    if cleaned_phone:
        patient.phone_number = cleaned_phone

    await session.flush()
    return patient
