from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.dispatcher import build_dispatcher
from app.config import get_settings
from app.db import SessionLocal
from app.logging_utils import configure_logging
from app.services.clinic_service import ensure_test_clinic
from app.services.crypto_service import CryptoService
from app.services.openai_service import OpenAIExtractionService
from app.services.redis_service import RedisService
from app.services.telegram_config_service import decrypt_bot_token, get_clinic_telegram_config


async def run_polling() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    redis_service = RedisService(settings)
    dispatcher = build_dispatcher(
        storage=redis_service.create_fsm_storage(),
        events_isolation=redis_service.create_event_isolation(),
    )
    openai_service = OpenAIExtractionService(settings)
    crypto_service = CryptoService(settings)

    async with SessionLocal() as session:
        clinic = await ensure_test_clinic(session, settings)
        config = await get_clinic_telegram_config(session, clinic.id)

    bot_token = settings.telegram_bot_token
    if not bot_token and config is not None:
        bot_token = decrypt_bot_token(config, crypto_service)

    if not bot_token:
        raise RuntimeError("No Telegram bot token is configured for local polling.")

    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    await bot.delete_webhook(drop_pending_updates=False)

    try:
        await dispatcher.start_polling(
            bot,
            clinic=clinic,
            settings=settings,
            openai_service=openai_service,
        )
    finally:
        await openai_service.close()
        await bot.session.close()
        await redis_service.close()


def main() -> None:
    asyncio.run(run_polling())


if __name__ == "__main__":
    main()
