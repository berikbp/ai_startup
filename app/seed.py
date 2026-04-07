import asyncio

from app.config import get_settings
from app.db import SessionLocal
from app.services.clinic_service import ensure_test_clinic


async def seed() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        clinic = await ensure_test_clinic(session, settings)

    print(
        f"Seeded clinic '{clinic.name}' "
        f"(slug={clinic.slug}, phone={clinic.phone_number}, timezone={clinic.timezone})"
    )


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
