from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.bot.dispatcher import build_dispatcher
from app.config import get_settings
from app.logging_utils import configure_logging
from app.owner.router import router as owner_router
from app.services.bot_registry import BotRegistry
from app.services.crypto_service import CryptoService
from app.services.idempotency_service import TelegramUpdateIdempotencyService
from app.services.openai_service import OpenAIExtractionService
from app.services.redis_service import RedisService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    redis_service = RedisService(settings)
    dispatcher = build_dispatcher(
        storage=redis_service.create_fsm_storage(),
        events_isolation=redis_service.create_event_isolation(),
    )
    openai_service = OpenAIExtractionService(settings)
    bot_registry = BotRegistry()
    crypto_service = CryptoService(settings)
    idempotency_service = TelegramUpdateIdempotencyService(settings, redis_service.client)

    app.state.settings = settings
    app.state.redis_service = redis_service
    app.state.dispatcher = dispatcher
    app.state.openai_service = openai_service
    app.state.bot_registry = bot_registry
    app.state.crypto_service = crypto_service
    app.state.idempotency_service = idempotency_service

    try:
        yield
    finally:
        await bot_registry.close()
        await openai_service.close()
        await redis_service.close()


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
