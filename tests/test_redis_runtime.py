from __future__ import annotations

import uuid
from unittest import IsolatedAsyncioTestCase, TestCase

from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisEventIsolation, RedisStorage

from app.config import Settings
from app.services.idempotency_service import TelegramUpdateIdempotencyService
from app.services.redis_service import RedisService


class _FakeRedis:
    def __init__(self) -> None:
        self.set_calls: list[dict[str, object]] = []
        self.delete_calls: list[str] = []
        self._values: set[str] = set()
        self.closed = False

    async def set(
        self,
        name: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        self.set_calls.append(
            {
                "name": name,
                "value": value,
                "ex": ex,
                "nx": nx,
            }
        )
        if nx and name in self._values:
            return None
        self._values.add(name)
        return True

    async def aclose(self) -> None:
        self.closed = True

    async def delete(self, name: str) -> None:
        self.delete_calls.append(name)
        self._values.discard(name)


class RedisServiceTests(TestCase):
    def test_redis_service_builds_bot_scoped_fsm_storage(self) -> None:
        fake_redis = _FakeRedis()
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            redis_key_prefix="ai-startup",
            telegram_fsm_state_ttl_seconds=111,
            telegram_fsm_data_ttl_seconds=222,
        )
        service = RedisService(settings, redis_client=fake_redis)  # type: ignore[arg-type]

        storage = service.create_fsm_storage()
        isolation = service.create_event_isolation()

        self.assertIsInstance(storage, RedisStorage)
        self.assertIsInstance(isolation, RedisEventIsolation)
        self.assertEqual(storage.state_ttl, 111)
        self.assertEqual(storage.data_ttl, 222)
        self.assertEqual(
            storage.key_builder.build(StorageKey(bot_id=7, chat_id=101, user_id=202), "state"),
            "ai-startup:fsm:7:101:202:state",
        )


class TelegramUpdateIdempotencyServiceTests(IsolatedAsyncioTestCase):
    async def test_idempotency_service_marks_new_updates_once(self) -> None:
        fake_redis = _FakeRedis()
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            redis_key_prefix="ai-startup",
            telegram_update_idempotency_ttl_seconds=600,
        )
        service = TelegramUpdateIdempotencyService(settings, fake_redis)  # type: ignore[arg-type]
        clinic_id = uuid.uuid4()

        self.assertTrue(
            await service.mark_if_new(
                clinic_id=clinic_id,
                clinic_slug="demo-clinic",
                update_id=9001,
            )
        )
        self.assertFalse(
            await service.mark_if_new(
                clinic_id=clinic_id,
                clinic_slug="demo-clinic",
                update_id=9001,
            )
        )
        self.assertEqual(
            fake_redis.set_calls[0],
            {
                "name": f"ai-startup:telegram-update:{clinic_id}:9001",
                "value": "1",
                "ex": 600,
                "nx": True,
            },
        )

    async def test_idempotency_service_can_release_marker(self) -> None:
        fake_redis = _FakeRedis()
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            redis_key_prefix="ai-startup",
            telegram_update_idempotency_ttl_seconds=600,
        )
        service = TelegramUpdateIdempotencyService(settings, fake_redis)  # type: ignore[arg-type]
        clinic_id = uuid.uuid4()

        await service.mark_if_new(
            clinic_id=clinic_id,
            clinic_slug="demo-clinic",
            update_id=1234,
        )
        await service.release(clinic_id=clinic_id, update_id=1234)

        self.assertEqual(
            fake_redis.delete_calls,
            [f"ai-startup:telegram-update:{clinic_id}:1234"],
        )
        self.assertTrue(
            await service.mark_if_new(
                clinic_id=clinic_id,
                clinic_slug="demo-clinic",
                update_id=1234,
            )
        )
