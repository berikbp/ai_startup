from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.bot.dispatcher import build_dispatcher
from app.config import get_settings
from app.db import SessionLocal
from app.owner.router import router as owner_router
from app.services.clinic_service import ensure_test_clinic
from app.services.openai_service import OpenAIExtractionService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    dispatcher = build_dispatcher()
    openai_service = OpenAIExtractionService(settings)

    app.state.settings = settings
    app.state.dispatcher = dispatcher
    app.state.openai_service = openai_service
    app.state.telegram_bot = None

    async with SessionLocal() as session:
        await ensure_test_clinic(session, settings)

    if settings.telegram_enabled:
        bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        app.state.telegram_bot = bot

        if settings.telegram_webhook_url is not None:
            await bot.set_webhook(
                url=settings.telegram_webhook_url,
                secret_token=settings.telegram_webhook_secret,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )

    try:
        yield
    finally:
        if app.state.telegram_bot is not None:
            await app.state.telegram_bot.session.close()
        await openai_service.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(api_router)
    app.include_router(owner_router)

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


app = create_app()
