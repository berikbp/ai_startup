from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, HTTPException, Request, status

from app.config import Settings
from app.db import SessionLocal
from app.services.clinic_service import get_clinic_by_slug


router = APIRouter()


@router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/webhook/{clinic_slug}", status_code=status.HTTP_200_OK)
async def telegram_webhook(clinic_slug: str, request: Request) -> dict[str, bool]:
    settings: Settings = request.app.state.settings
    bot: Bot | None = request.app.state.telegram_bot
    dispatcher: Dispatcher = request.app.state.dispatcher

    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot is not configured.",
        )

    secret_header = request.headers.get("x-telegram-bot-api-secret-token")
    if settings.telegram_webhook_secret and secret_header != settings.telegram_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret.",
        )

    async with SessionLocal() as session:
        clinic = await get_clinic_by_slug(session, clinic_slug)

    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found.",
        )

    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dispatcher.feed_update(
        bot,
        update,
        clinic=clinic,
        settings=settings,
        openai_service=request.app.state.openai_service,
    )
    return {"ok": True}
