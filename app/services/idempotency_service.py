from __future__ import annotations

import logging
import uuid

from redis.asyncio import Redis

from app.config import Settings
from app.logging_utils import structured_event


logger = logging.getLogger(__name__)


class TelegramUpdateIdempotencyService:
    def __init__(self, settings: Settings, redis: Redis) -> None:
        self._redis = redis
        self._key_prefix = f"{settings.redis_key_prefix}:telegram-update"
        self._ttl_seconds = settings.telegram_update_idempotency_ttl_seconds

    async def mark_if_new(
        self,
        *,
        clinic_id: uuid.UUID,
        clinic_slug: str,
        update_id: int,
    ) -> bool:
        redis_key = f"{self._key_prefix}:{clinic_id}:{update_id}"
        created = await self._redis.set(redis_key, "1", ex=self._ttl_seconds, nx=True)
        is_new = bool(created)
        if not is_new:
            logger.info(
                structured_event(
                    "telegram_webhook_duplicate_suppressed",
                    clinic_id=clinic_id,
                    clinic_slug=clinic_slug,
                    update_id=update_id,
                )
            )
        return is_new

    async def release(self, *, clinic_id: uuid.UUID, update_id: int) -> None:
        redis_key = f"{self._key_prefix}:{clinic_id}:{update_id}"
        await self._redis.delete(redis_key)
