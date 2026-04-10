import asyncio

from app.config import get_settings
from app.db import SessionLocal
from app.services.clinic_service import ensure_test_clinic
from app.services.crypto_service import CryptoService
from app.services.telegram_config_service import get_clinic_telegram_config


async def seed() -> None:
    settings = get_settings()
    crypto_service = CryptoService(settings)
    async with SessionLocal() as session:
        clinic = await ensure_test_clinic(session, settings)
        config = await get_clinic_telegram_config(session, clinic.id)

    config_status = "no telegram config"
    if config is not None:
        try:
            bot_token = crypto_service.decrypt(config.bot_token_encrypted)
        except ValueError:
            bot_token = "[invalid encrypted token]"
        config_status = (
            f"telegram config present (username=@{config.bot_username or 'unknown'}, "
            f"active={config.is_active}, token={bot_token[:8]}...)"
        )

    print(f"Seeded clinic '{clinic.name}' (slug={clinic.slug}, phone={clinic.phone_number}, timezone={clinic.timezone}, {config_status})")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
