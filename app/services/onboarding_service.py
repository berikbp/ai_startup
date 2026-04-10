from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Clinic, ClinicUser
from app.services.auth_service import create_owner_user
from app.services.clinic_service import get_clinic_by_slug
from app.services.normalization import (
    generate_clinic_slug,
    normalize_clinic_slug,
    normalize_phone_number,
    normalize_whitespace,
)


async def create_clinic_with_owner(
    session: AsyncSession,
    *,
    clinic_name: str,
    clinic_slug: str | None,
    clinic_phone: str | None,
    clinic_timezone: str | None,
    owner_email: str,
    owner_password: str,
) -> tuple[Clinic, ClinicUser]:
    normalized_name = normalize_whitespace(clinic_name)
    if not normalized_name:
        raise ValueError("Укажите название клиники.")

    normalized_slug = normalize_clinic_slug(clinic_slug) or generate_clinic_slug(normalized_name)
    if not normalized_slug:
        raise ValueError("Укажите корректный slug клиники.")

    existing_clinic = await get_clinic_by_slug(session, normalized_slug)
    if existing_clinic is not None:
        raise ValueError("Клиника с таким slug уже существует.")

    normalized_timezone = normalize_whitespace(clinic_timezone) or "Asia/Almaty"
    try:
        ZoneInfo(normalized_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Укажите корректный timezone, например Asia/Almaty.") from exc

    normalized_phone = normalize_whitespace(clinic_phone)
    if normalized_phone:
        normalized_phone = normalize_phone_number(normalized_phone)
        if normalized_phone is None:
            raise ValueError("Укажите телефон клиники в формате +77001234567.")
    else:
        normalized_phone = None

    clinic = Clinic(
        name=normalized_name,
        slug=normalized_slug,
        timezone=normalized_timezone,
        phone_number=normalized_phone,
    )
    session.add(clinic)
    await session.flush()

    owner = await create_owner_user(
        session,
        clinic=clinic,
        email=owner_email,
        password=owner_password,
    )
    return clinic, owner
