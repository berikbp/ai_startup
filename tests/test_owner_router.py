from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlmodel import select


os.environ["APP_ENV"] = "development"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["AUTH_SECRET_KEY"] = "owner-test-secret"
os.environ["TELEGRAM_TOKEN_ENCRYPTION_KEY"] = "owner-test-encryption-secret"
os.environ["DATABASE_DISABLE_POOLING"] = "1"


from app.config import get_settings
from app.db import SessionLocal, engine
from app.main import create_app
from app.models import (
    Booking,
    BookingSource,
    BookingStatus,
    Clinic,
    ClinicTelegramConfig,
    ClinicUser,
    Message,
    MessageRole,
    Patient,
)


class OwnerRouterTests(TestCase):
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

    def test_protected_dashboard_redirects_anonymous_user(self) -> None:
        self._open_client()
        response = self.client.get("/owner/dashboard", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/owner/login")

    def test_owner_registration_creates_session_and_dashboard_access(self) -> None:
        self._open_client()
        response = self._register_owner()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/owner/dashboard")

        dashboard_response = self.client.get("/owner/dashboard")

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("Заявки клиники", dashboard_response.text)
        self.assertIn("owner@example.com", dashboard_response.text)
        self.assertIn("Owner Test Clinic", dashboard_response.text)
        self.assertIn("Не подключен", dashboard_response.text)

    def test_registration_rejects_duplicate_clinic_slug(self) -> None:
        self._open_client()
        first_response = self._register_owner()
        self.assertEqual(first_response.status_code, 303)

        self._logout_owner()
        second_response = self._post_with_csrf(
            form_page="/owner/register",
            path="/owner/register",
            data=self._owner_registration_payload(
                email="second-owner@example.com",
                clinic_name="Second Clinic",
                clinic_slug="owner-test-clinic",
            ),
            follow_redirects=False,
        )

        self.assertEqual(second_response.status_code, 400)
        self.assertIn("Клиника с таким slug уже существует.", second_response.text)

    def test_login_rejects_invalid_password(self) -> None:
        self._open_client()
        self._register_owner()
        self._logout_owner()

        response = self._post_with_csrf(
            form_page="/owner/login",
            path="/owner/login",
            data={
                "email": "owner@example.com",
                "password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Неверный email или пароль.", response.text)

    def test_dashboard_only_shows_bookings_for_owner_clinic(self) -> None:
        self._open_client()
        self._register_owner()
        owner_clinic = asyncio.run(self._get_owner_clinic("owner@example.com"))
        asyncio.run(self._create_booking_for_clinic(clinic_id=owner_clinic.id, patient_name="Visible Patient"))
        asyncio.run(self._create_secondary_clinic_booking(patient_name="Hidden Patient"))
        asyncio.run(engine.dispose())

        response = self.client.get("/owner/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Visible Patient", response.text)
        self.assertNotIn("Hidden Patient", response.text)

    def test_booking_detail_renders_messages_and_status_updates(self) -> None:
        self._open_client()
        self._register_owner()
        owner_clinic = asyncio.run(self._get_owner_clinic("owner@example.com"))
        booking_id = asyncio.run(
            self._create_booking_for_clinic(clinic_id=owner_clinic.id, patient_name="Detail Patient")
        )
        asyncio.run(engine.dispose())

        detail_response = self.client.get(f"/owner/bookings/{booking_id}")

        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("История диалога", detail_response.text)
        self.assertIn("Здравствуйте, хочу записаться", detail_response.text)
        self.assertIn("Detail Patient", detail_response.text)

        update_response = self._post_with_csrf(
            form_page=f"/owner/bookings/{booking_id}",
            path=f"/owner/bookings/{booking_id}/status",
            data={"status": "confirmed"},
            follow_redirects=True,
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertIn("Подтверждена", update_response.text)

    def test_settings_page_persists_telegram_config(self) -> None:
        self._open_client()
        self._register_owner()

        async def fake_configure(
            session,
            *,
            clinic,
            bot_token,
            settings,
            crypto_service,
            bot_registry,
            dispatcher,
        ):
            config = ClinicTelegramConfig(
                clinic_id=clinic.id,
                bot_token_encrypted=crypto_service.encrypt(bot_token),
                bot_username="phase4_bot",
                webhook_secret="phase4-secret",
                is_active=True,
                last_webhook_registered_at=datetime.now(UTC),
                last_error=None,
            )
            session.add(config)
            await session.flush()
            return config

        with patch("app.owner.router.configure_clinic_telegram_bot", side_effect=fake_configure):
            response = self._post_with_csrf(
                form_page="/owner/settings",
                path="/owner/settings/telegram",
                data={"bot_token": "123456:TEST-TOKEN"},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/owner/settings?saved=1")

        settings_response = self.client.get("/owner/settings?saved=1")
        self.assertEqual(settings_response.status_code, 200)
        self.assertIn("@phase4_bot", settings_response.text)
        self.assertIn("Подключен", settings_response.text)

        dashboard_response = self.client.get("/owner/dashboard")
        self.assertIn("Подключен", dashboard_response.text)

    def test_registration_rejects_missing_csrf_token(self) -> None:
        self._open_client()

        response = self.client.post(
            "/owner/register",
            data=self._owner_registration_payload(),
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("CSRF validation failed.", response.text)

    def test_status_update_rejects_invalid_csrf_token(self) -> None:
        self._open_client()
        self._register_owner()
        owner_clinic = asyncio.run(self._get_owner_clinic("owner@example.com"))
        booking_id = asyncio.run(
            self._create_booking_for_clinic(clinic_id=owner_clinic.id, patient_name="Protected Patient")
        )
        asyncio.run(engine.dispose())

        self._get_csrf_token(f"/owner/bookings/{booking_id}")
        response = self.client.post(
            f"/owner/bookings/{booking_id}/status",
            data={"status": "confirmed", "csrf_token": "invalid-token"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 403)

        detail_response = self.client.get(f"/owner/bookings/{booking_id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("Ожидает", detail_response.text)

    def _owner_registration_payload(
        self,
        *,
        email: str = "owner@example.com",
        clinic_name: str = "Owner Test Clinic",
        clinic_slug: str = "owner-test-clinic",
        clinic_phone: str = "+77001234567",
        clinic_timezone: str = "Asia/Almaty",
    ) -> dict[str, str]:
        return {
            "clinic_name": clinic_name,
            "clinic_slug": clinic_slug,
            "clinic_phone": clinic_phone,
            "clinic_timezone": clinic_timezone,
            "email": email,
            "password": "owner-pass-123",
            "password_confirm": "owner-pass-123",
        }

    def _register_owner(self) -> Response:
        return self._post_with_csrf(
            form_page="/owner/register",
            path="/owner/register",
            data=self._owner_registration_payload(),
            follow_redirects=False,
        )

    def _open_client(self) -> None:
        self.client = TestClient(create_app())
        self.client.__enter__()

    def _logout_owner(self) -> Response:
        return self._post_with_csrf(
            form_page="/owner/dashboard",
            path="/owner/logout",
            data={},
            follow_redirects=False,
        )

    def _get_csrf_token(self, path: str) -> str:
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        token = self.client.cookies.get(get_settings().auth_csrf_cookie_name)
        if not token:
            raise AssertionError("CSRF cookie was not issued.")
        return token

    def _post_with_csrf(
        self,
        *,
        form_page: str,
        path: str,
        data: dict[str, str],
        follow_redirects: bool = False,
    ) -> Response:
        token = self._get_csrf_token(form_page)
        payload = dict(data)
        payload["csrf_token"] = token
        return self.client.post(path, data=payload, follow_redirects=follow_redirects)

    async def _reset_database(self) -> None:
        async with SessionLocal() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Booking))
            await session.execute(delete(Patient))
            await session.execute(delete(ClinicTelegramConfig))
            await session.execute(delete(ClinicUser))
            await session.execute(delete(Clinic))
            await session.commit()

    async def _get_owner_clinic(self, email: str) -> Clinic:
        async with SessionLocal() as session:
            statement = select(Clinic).join(ClinicUser).where(ClinicUser.email == email)
            result = await session.execute(statement)
            clinic = result.scalars().first()
            if clinic is None:
                raise AssertionError("Owner clinic was not created.")
            return clinic

    async def _create_booking_for_clinic(self, *, clinic_id: uuid.UUID, patient_name: str) -> uuid.UUID:
        async with SessionLocal() as session:
            clinic = await session.get(Clinic, clinic_id)
            if clinic is None:
                raise AssertionError("Clinic fixture is missing.")

            patient = Patient(
                clinic_id=clinic.id,
                telegram_user_id=10_000_000 + int(uuid.uuid4().hex[:6], 16),
                telegram_username="owner_router_test",
                full_name=patient_name,
                phone_number="+77001234567",
            )
            session.add(patient)
            await session.flush()

            booking = Booking(
                clinic_id=clinic.id,
                patient_id=patient.id,
                service_type="Консультация стоматолога",
                preferred_datetime_at=datetime.now(UTC) + timedelta(days=1),
                preferred_datetime_text="завтра в 14:00",
                status=BookingStatus.pending,
                source=BookingSource.telegram,
            )
            session.add(booking)
            await session.flush()

            session.add(
                Message(
                    clinic_id=clinic.id,
                    patient_id=patient.id,
                    booking_id=booking.id,
                    role=MessageRole.user,
                    content="Здравствуйте, хочу записаться",
                )
            )
            session.add(
                Message(
                    clinic_id=clinic.id,
                    patient_id=patient.id,
                    booking_id=booking.id,
                    role=MessageRole.assistant,
                    content="Проверьте, пожалуйста, заявку",
                )
            )
            await session.commit()
            return booking.id

    async def _create_secondary_clinic_booking(self, *, patient_name: str) -> uuid.UUID:
        async with SessionLocal() as session:
            clinic = Clinic(
                name="Secondary Clinic",
                slug=f"secondary-owner-clinic-{uuid.uuid4().hex[:8]}",
                timezone="Asia/Almaty",
                phone_number="+77009998877",
            )
            session.add(clinic)
            await session.flush()

            patient = Patient(
                clinic_id=clinic.id,
                telegram_user_id=20_000_000 + int(uuid.uuid4().hex[:6], 16),
                telegram_username="secondary_test_user",
                full_name=patient_name,
                phone_number="+77009998877",
            )
            session.add(patient)
            await session.flush()

            booking = Booking(
                clinic_id=clinic.id,
                patient_id=patient.id,
                service_type="УЗИ",
                preferred_datetime_at=datetime.now(UTC) + timedelta(days=2),
                preferred_datetime_text="послезавтра в 09:00",
                status=BookingStatus.pending,
                source=BookingSource.telegram,
            )
            session.add(booking)
            await session.commit()
            return booking.id
