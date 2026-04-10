from __future__ import annotations

from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisEventIsolation, RedisStorage
from redis.asyncio import Redis

from app.config import Settings


class RedisService:
    def __init__(self, settings: Settings, *, redis_client: Redis | None = None) -> None:
        self._settings = settings
        self._redis = redis_client or Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    @property
    def client(self) -> Redis:
        return self._redis

    def create_fsm_storage(self) -> RedisStorage:
        return RedisStorage(
            redis=self._redis,
            key_builder=self._fsm_key_builder(),
            state_ttl=self._settings.telegram_fsm_state_ttl_seconds,
            data_ttl=self._settings.telegram_fsm_data_ttl_seconds,
        )

    def create_event_isolation(self) -> RedisEventIsolation:
        return RedisEventIsolation(
            redis=self._redis,
            key_builder=self._fsm_key_builder(),
        )

    async def close(self) -> None:
        await self._redis.aclose()

    def _fsm_key_builder(self) -> DefaultKeyBuilder:
        return DefaultKeyBuilder(
            prefix=f"{self._settings.redis_key_prefix}:fsm",
            with_bot_id=True,
        )
