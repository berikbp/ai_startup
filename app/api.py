import logging
from json import JSONDecodeError

from aiogram import Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from redis.exceptions import RedisError

from app.config import Settings
from app.db import SessionLocal
from app.logging_utils import structured_event
from app.services.bot_registry import BotRegistry
from app.services.clinic_service import get_clinic_by_slug
from app.services.crypto_service import CryptoService
from app.services.idempotency_service import TelegramUpdateIdempotencyService
from app.services.telegram_config_service import decrypt_bot_token, get_clinic_telegram_config


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/webhook/{clinic_slug}", status_code=status.HTTP_200_OK)
async def telegram_webhook(clinic_slug: str, request: Request) -> dict[str, bool]:
    settings: Settings = request.app.state.settings
    dispatcher: Dispatcher = request.app.state.dispatcher
    bot_registry: BotRegistry = request.app.state.bot_registry
    crypto_service: CryptoService = request.app.state.crypto_service
    idempotency_service: TelegramUpdateIdempotencyService = request.app.state.idempotency_service

    async with SessionLocal() as session:
        clinic = await get_clinic_by_slug(session, clinic_slug)
        if clinic is None:
            logger.warning(
                structured_event(
                    "telegram_webhook_rejected",
                    clinic_slug=clinic_slug,
                    reason="clinic_not_found",
                )
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clinic not found.",
            )
        config = await get_clinic_telegram_config(session, clinic.id)

    if config is None:
        logger.warning(
            structured_event(
                "telegram_webhook_rejected",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                reason="bot_not_configured",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot is not configured for this clinic.",
        )

    if not config.is_active:
        logger.warning(
            structured_event(
                "telegram_webhook_rejected",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                reason="bot_not_active",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot is not active for this clinic.",
        )

    secret_header = request.headers.get("x-telegram-bot-api-secret-token")
    if secret_header != config.webhook_secret:
        logger.warning(
            structured_event(
                "telegram_webhook_rejected",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                reason="invalid_secret",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret.",
        )

    try:
        payload = await request.json()
    except (JSONDecodeError, ValueError) as exc:
        logger.warning(
            structured_event(
                "telegram_webhook_rejected",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                reason="invalid_json",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram update payload.",
        ) from exc

    if not isinstance(payload, dict):
        logger.warning(
            structured_event(
                "telegram_webhook_rejected",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                reason="payload_not_object",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram update payload.",
        )

    update_id = payload.get("update_id")
    if not isinstance(update_id, int) or isinstance(update_id, bool):
        logger.warning(
            structured_event(
                "telegram_webhook_rejected",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                reason="missing_update_id",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram update_id is required.",
        )

    try:
        bot_token = decrypt_bot_token(config, crypto_service)
    except ValueError as exc:
        logger.exception(
            structured_event(
                "telegram_webhook_token_invalid",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                update_id=update_id,
            )
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stored Telegram bot token is invalid.",
        ) from exc

    bot = await bot_registry.get_bot(clinic_id=clinic.id, token=bot_token)
    try:
        update = Update.model_validate(payload, context={"bot": bot})
    except ValidationError as exc:
        logger.warning(
            structured_event(
                "telegram_webhook_rejected",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                update_id=update_id,
                reason="payload_validation_failed",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram update payload.",
        ) from exc

    try:
        is_new_update = await idempotency_service.mark_if_new(
            clinic_id=clinic.id,
            clinic_slug=clinic.slug,
            update_id=update_id,
        )
    except RedisError as exc:
        logger.exception(
            structured_event(
                "telegram_webhook_idempotency_unavailable",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                update_id=update_id,
            )
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook idempotency is unavailable.",
        ) from exc

    if not is_new_update:
        return {"ok": True}

    logger.info(
        structured_event(
            "telegram_webhook_accepted",
            clinic_id=clinic.id,
            clinic_slug=clinic.slug,
            update_id=update_id,
        )
    )
    try:
        await dispatcher.feed_update(
            bot,
            update,
            clinic=clinic,
            settings=settings,
            openai_service=request.app.state.openai_service,
        )
    except Exception:
        await idempotency_service.release(clinic_id=clinic.id, update_id=update_id)
        logger.exception(
            structured_event(
                "telegram_webhook_dispatch_failed",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                update_id=update_id,
            )
        )
        raise
    return {"ok": True}
