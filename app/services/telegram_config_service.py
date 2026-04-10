from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
import logging

from aiogram import Dispatcher
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramUnauthorizedError,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import Settings
from app.logging_utils import structured_event
from app.models import Clinic, ClinicTelegramConfig
from app.services.bot_registry import BotRegistry
from app.services.crypto_service import CryptoService
from app.services.normalization import normalize_whitespace


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TelegramConnectionStatus:
    label: str
    tone: str
    detail: str


async def get_clinic_telegram_config(
    session: AsyncSession,
    clinic_id: uuid.UUID,
) -> ClinicTelegramConfig | None:
    statement = select(ClinicTelegramConfig).where(ClinicTelegramConfig.clinic_id == clinic_id)
    result = await session.execute(statement)
    return result.scalars().first()


def decrypt_bot_token(config: ClinicTelegramConfig, crypto_service: CryptoService) -> str:
    return crypto_service.decrypt(config.bot_token_encrypted)


def describe_telegram_connection(
    config: ClinicTelegramConfig | None,
) -> TelegramConnectionStatus:
    if config is None:
        return TelegramConnectionStatus(
            label="Не подключен",
            tone="pending",
            detail="Добавьте токен Telegram-бота в настройках клиники.",
        )

    if config.is_active and not config.last_error:
        detail = "Webhook активен."
        if config.bot_username:
            detail = f"Webhook активен для @{config.bot_username}."
        return TelegramConnectionStatus(
            label="Подключен",
            tone="confirmed",
            detail=detail,
        )

    if config.last_error:
        return TelegramConnectionStatus(
            label="Есть ошибка",
            tone="cancelled",
            detail=config.last_error,
        )

    detail = "Токен сохранен, но подключение еще не завершено."
    if config.bot_username:
        detail = f"Токен проверен для @{config.bot_username}, но webhook еще не активен."
    return TelegramConnectionStatus(
        label="Токен сохранен",
        tone="pending",
        detail=detail,
    )


async def configure_clinic_telegram_bot(
    session: AsyncSession,
    *,
    clinic: Clinic,
    bot_token: str,
    settings: Settings,
    crypto_service: CryptoService,
    bot_registry: BotRegistry,
    dispatcher: Dispatcher,
) -> ClinicTelegramConfig:
    normalized_token = normalize_whitespace(bot_token)
    if not normalized_token:
        raise ValueError("Укажите токен Telegram-бота.")

    existing = await get_clinic_telegram_config(session, clinic.id)
    bot = await bot_registry.get_bot(clinic_id=clinic.id, token=normalized_token)

    try:
        me = await bot.get_me()
    except (TelegramUnauthorizedError, TelegramBadRequest) as exc:
        logger.warning(
            structured_event(
                "telegram_bot_token_rejected",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
            )
        )
        await bot_registry.invalidate(clinic.id)
        raise ValueError("Telegram отклонил токен бота. Проверьте значение и попробуйте снова.") from exc
    except (TelegramAPIError, TelegramNetworkError) as exc:
        logger.exception(
            structured_event(
                "telegram_bot_token_validation_failed",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
            )
        )
        await bot_registry.invalidate(clinic.id)
        raise RuntimeError("Не удалось проверить токен у Telegram. Повторите попытку позже.") from exc

    webhook_secret = existing.webhook_secret if existing is not None else secrets.token_urlsafe(24)
    webhook_url = settings.build_telegram_webhook_url(clinic.slug)
    is_active = False
    last_error: str | None = None
    last_webhook_registered_at: datetime | None = None

    if webhook_url is None:
        logger.info(
            structured_event(
                "telegram_webhook_registration_skipped",
                clinic_id=clinic.id,
                clinic_slug=clinic.slug,
                reason="missing_base_url",
            )
        )
        last_error = "Токен сохранен, но TELEGRAM_WEBHOOK_BASE_URL не настроен."
    else:
        try:
            await bot.set_webhook(
                url=webhook_url,
                secret_token=webhook_secret,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
        except (TelegramAPIError, TelegramNetworkError):
            logger.exception(
                structured_event(
                    "telegram_webhook_registration_failed",
                    clinic_id=clinic.id,
                    clinic_slug=clinic.slug,
                    bot_username=me.username,
                )
            )
            last_error = "Токен сохранен, но Telegram не подтвердил webhook."
        else:
            is_active = True
            last_webhook_registered_at = datetime.now(UTC)
            logger.info(
                structured_event(
                    "telegram_webhook_registered",
                    clinic_id=clinic.id,
                    clinic_slug=clinic.slug,
                    bot_username=me.username,
                )
            )

    encrypted_token = crypto_service.encrypt(normalized_token)
    config = existing or ClinicTelegramConfig(
        clinic_id=clinic.id,
        bot_token_encrypted=encrypted_token,
        webhook_secret=webhook_secret,
    )
    config.bot_token_encrypted = encrypted_token
    config.bot_username = me.username
    config.webhook_secret = webhook_secret
    config.is_active = is_active
    config.last_webhook_registered_at = last_webhook_registered_at
    config.last_error = last_error
    session.add(config)
    await session.flush()
    return config
