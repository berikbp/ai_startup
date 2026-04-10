from __future__ import annotations

import asyncio
import os
import uuid
from unittest import TestCase

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi.testclient import TestClient
from sqlalchemy import delete


os.environ["APP_ENV"] = "development"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["AUTH_SECRET_KEY"] = "webhook-test-secret"
os.environ["TELEGRAM_TOKEN_ENCRYPTION_KEY"] = "webhook-test-encryption-secret"
os.environ["DATABASE_DISABLE_POOLING"] = "1"


from app.config import get_settings
from app.db import SessionLocal, engine
from app.main import create_app
from app.models import Booking, Clinic, ClinicTelegramConfig, ClinicUser, Message, Patient
from app.services.crypto_service import CryptoService


class _FakeBotRegistry:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.calls: list[tuple[uuid.UUID, str]] = []

    async def get_bot(self, *, clinic_id: uuid.UUID, token: str) -> Bot:
        self.calls.append((clinic_id, token))
        return self.bot

    async def invalidate(self, clinic_id: uuid.UUID) -> None:
        return None

    async def close(self) -> None:
        await self.bot.session.close()


class _FakeIdempotencyService:
    def __init__(self) -> None:
        self._seen: set[tuple[uuid.UUID, int]] = set()

    async def mark_if_new(
        self,
        *,
        clinic_id: uuid.UUID,
        clinic_slug: str,
        update_id: int,
    ) -> bool:
        key = (clinic_id, update_id)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    async def release(self, *, clinic_id: uuid.UUID, update_id: int) -> None:
        self._seen.discard((clinic_id, update_id))


class WebhookMultiClinicTests(TestCase):
    def setUp(self) -> None:
        asyncio.run(self._reset_database())
        asyncio.run(engine.dispose())
        get_settings.cache_clear()
        self.client: TestClient | None = None

    def tearDown(self) -> None:
        if self.client is not None:
            self.client.__exit__(None, None, None)
        asyncio.run(engine.dispose())
        asyncio.run(self._reset_database())
        asyncio.run(engine.dispose())

    def test_webhook_uses_clinic_specific_secret_and_token(self) -> None:
        clinic_id = asyncio.run(
            self._create_clinic_with_config(
                slug="clinic-one",
                webhook_secret="secret-one",
                bot_token="111111:BOT-ONE",
            )
        )
        asyncio.run(
            self._create_clinic_with_config(
                slug="clinic-two",
                webhook_secret="secret-two",
                bot_token="222222:BOT-TWO",
            )
        )

        self._open_client()
        fake_bot = Bot(
            token="999999:FAKE",
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        fake_registry = _FakeBotRegistry(fake_bot)
        self.client.app.state.bot_registry = fake_registry
        self.client.app.state.idempotency_service = _FakeIdempotencyService()

        feed_calls: list[str] = []

        async def fake_feed_update(bot, update, **kwargs):
            feed_calls.append(kwargs["clinic"].slug)

        self.client.app.state.dispatcher.feed_update = fake_feed_update

        response = self.client.post(
            "/webhook/clinic-one",
            headers={"x-telegram-bot-api-secret-token": "secret-one"},
            json=self._telegram_update_payload(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(feed_calls, ["clinic-one"])
        self.assertEqual(fake_registry.calls, [(clinic_id, "111111:BOT-ONE")])

    def test_webhook_rejects_wrong_secret(self) -> None:
        asyncio.run(
            self._create_clinic_with_config(
                slug="clinic-secure",
                webhook_secret="expected-secret",
                bot_token="333333:BOT-THREE",
            )
        )

        self._open_client()
        fake_bot = Bot(
            token="999999:FAKE",
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        fake_registry = _FakeBotRegistry(fake_bot)
        self.client.app.state.bot_registry = fake_registry
        self.client.app.state.idempotency_service = _FakeIdempotencyService()

        response = self.client.post(
            "/webhook/clinic-secure",
            headers={"x-telegram-bot-api-secret-token": "wrong-secret"},
            json=self._telegram_update_payload(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(fake_registry.calls, [])

    def test_webhook_short_circuits_duplicate_update_id(self) -> None:
        clinic_id = asyncio.run(
            self._create_clinic_with_config(
                slug="clinic-duplicate",
                webhook_secret="duplicate-secret",
                bot_token="444444:BOT-FOUR",
            )
        )

        self._open_client()
        fake_bot = Bot(
            token="999999:FAKE",
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        fake_registry = _FakeBotRegistry(fake_bot)
        self.client.app.state.bot_registry = fake_registry
        self.client.app.state.idempotency_service = _FakeIdempotencyService()

        feed_calls: list[str] = []

        async def fake_feed_update(bot, update, **kwargs):
            feed_calls.append(kwargs["clinic"].slug)

        self.client.app.state.dispatcher.feed_update = fake_feed_update

        first_response = self.client.post(
            "/webhook/clinic-duplicate",
            headers={"x-telegram-bot-api-secret-token": "duplicate-secret"},
            json=self._telegram_update_payload(),
        )
        second_response = self.client.post(
            "/webhook/clinic-duplicate",
            headers={"x-telegram-bot-api-secret-token": "duplicate-secret"},
            json=self._telegram_update_payload(),
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(feed_calls, ["clinic-duplicate"])
        self.assertEqual(
            fake_registry.calls,
            [
                (clinic_id, "444444:BOT-FOUR"),
                (clinic_id, "444444:BOT-FOUR"),
            ],
        )

    def _open_client(self) -> None:
        self.client = TestClient(create_app())
        self.client.__enter__()

    async def _reset_database(self) -> None:
        async with SessionLocal() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Booking))
            await session.execute(delete(Patient))
            await session.execute(delete(ClinicTelegramConfig))
            await session.execute(delete(ClinicUser))
            await session.execute(delete(Clinic))
            await session.commit()

    async def _create_clinic_with_config(
        self,
        *,
        slug: str,
        webhook_secret: str,
        bot_token: str,
    ) -> uuid.UUID:
        settings = get_settings()
        crypto_service = CryptoService(settings)
        async with SessionLocal() as session:
            clinic = Clinic(
                name=f"Clinic {slug}",
                slug=slug,
                timezone="Asia/Almaty",
                phone_number="+77001234567",
            )
            session.add(clinic)
            await session.flush()

            session.add(
                ClinicTelegramConfig(
                    clinic_id=clinic.id,
                    bot_token_encrypted=crypto_service.encrypt(bot_token),
                    bot_username=f"{slug}_bot",
                    webhook_secret=webhook_secret,
                    is_active=True,
                    last_error=None,
                )
            )
            await session.commit()
            return clinic.id

    def _telegram_update_payload(self) -> dict[str, object]:
        return {
            "update_id": 1000,
            "message": {
                "message_id": 1,
                "date": 1_710_000_000,
                "chat": {"id": 99, "type": "private"},
                "from": {
                    "id": 123456789,
                    "is_bot": False,
                    "first_name": "Test",
                },
                "text": "/start",
            },
        }
