from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import Settings
from app.models import Clinic


async def get_clinic_by_slug(session: AsyncSession, slug: str) -> Clinic | None:
    statement = select(Clinic).where(Clinic.slug == slug)
    result = await session.execute(statement)
    return result.scalars().first()


async def ensure_test_clinic(session: AsyncSession, settings: Settings) -> Clinic:
    clinic = await get_clinic_by_slug(session, settings.test_clinic_slug)
    if clinic is None:
        clinic = Clinic(
            name=settings.test_clinic_name,
            slug=settings.test_clinic_slug,
            timezone=settings.resolved_clinic_timezone,
            phone_number=settings.resolved_test_clinic_phone_number or None,
        )
        session.add(clinic)
    else:
        clinic.name = settings.test_clinic_name
        clinic.timezone = settings.resolved_clinic_timezone
        clinic.phone_number = settings.resolved_test_clinic_phone_number or None

    await session.commit()
    await session.refresh(clinic)
    return clinic
