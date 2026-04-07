from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.dispatcher import build_dispatcher
from app.config import get_settings
from app.db import SessionLocal
from app.services.clinic_service import ensure_test_clinic
from app.services.openai_service import OpenAIExtractionService


async def run_polling() -> None:
    settings = get_settings()
    if not settings.telegram_enabled:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")

    dispatcher = build_dispatcher()
    openai_service = OpenAIExtractionService(settings)
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    async with SessionLocal() as session:
        clinic = await ensure_test_clinic(session, settings)

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


def main() -> None:
    asyncio.run(run_polling())


if __name__ == "__main__":
    main()
