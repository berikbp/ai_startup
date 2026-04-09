from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest import TestCase

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlmodel import select


os.environ["APP_ENV"] = "development"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["TEST_CLINIC_SLUG"] = "owner-test-clinic"
os.environ["TEST_CLINIC_NAME"] = "Owner Test Clinic"
os.environ["TEST_CLINIC_PHONE"] = "+77001234567"
os.environ["TEST_CLINIC_TIMEZONE"] = "Asia/Almaty"
os.environ["AUTH_SECRET_KEY"] = "owner-test-secret"
os.environ["DATABASE_DISABLE_POOLING"] = "1"


from app.config import get_settings
from app.db import SessionLocal, engine
from app.main import create_app
from app.models import Booking, BookingSource, BookingStatus, Clinic, ClinicUser, Message, MessageRole, Patient


class OwnerRouterTests(TestCase):
    def setUp(self) -> None:
        asyncio.run(self._reset_primary_clinic_data())
        asyncio.run(engine.dispose())
        get_settings.cache_clear()
        self.client: TestClient | None = None

    def tearDown(self) -> None:
        if self.client is not None:
            self.client.__exit__(None, None, None)
        asyncio.run(engine.dispose())
        asyncio.run(self._reset_primary_clinic_data())
        asyncio.run(engine.dispose())

    def test_protected_dashboard_redirects_anonymous_user(self) -> None:
        self._open_client()
        response = self.client.get("/owner/dashboard", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/owner/login")

    def test_owner_registration_creates_session_and_dashboard_access(self) -> None:
        self._open_client()
        response = self.client.post(
            "/owner/register",
            data={
                "email": "owner@example.com",
                "password": "owner-pass-123",
                "password_confirm": "owner-pass-123",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/owner/dashboard")

        dashboard_response = self.client.get("/owner/dashboard")

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("Заявки клиники", dashboard_response.text)
        self.assertIn("owner@example.com", dashboard_response.text)

    def test_login_rejects_invalid_password(self) -> None:
        self._open_client()
        self._register_owner()
        self.client.post("/owner/logout", follow_redirects=False)

        response = self.client.post(
            "/owner/login",
            data={
                "email": "owner@example.com",
                "password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Неверный email или пароль.", response.text)

    def test_dashboard_only_shows_bookings_for_owner_clinic(self) -> None:
        asyncio.run(self._create_booking_for_primary_clinic(patient_name="Visible Patient"))
        asyncio.run(self._create_secondary_clinic_booking(patient_name="Hidden Patient"))
        asyncio.run(engine.dispose())

        self._open_client()
        self._register_owner()

        response = self.client.get("/owner/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Visible Patient", response.text)
        self.assertNotIn("Hidden Patient", response.text)

    def test_booking_detail_renders_messages_and_status_updates(self) -> None:
        booking_id = asyncio.run(self._create_booking_for_primary_clinic(patient_name="Detail Patient"))
        asyncio.run(engine.dispose())

        self._open_client()
        self._register_owner()

        detail_response = self.client.get(f"/owner/bookings/{booking_id}")

        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("История диалога", detail_response.text)
        self.assertIn("Здравствуйте, хочу записаться", detail_response.text)
        self.assertIn("Detail Patient", detail_response.text)

        update_response = self.client.post(
            f"/owner/bookings/{booking_id}/status",
            data={"status": "confirmed"},
            follow_redirects=True,
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertIn("Подтверждена", update_response.text)

    def _register_owner(self) -> None:
        response = self.client.post(
            "/owner/register",
            data={
                "email": "owner@example.com",
                "password": "owner-pass-123",
                "password_confirm": "owner-pass-123",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

    def _open_client(self) -> None:
        self.client = TestClient(create_app())
        self.client.__enter__()

    async def _reset_primary_clinic_data(self) -> None:
        settings = get_settings()
        async with SessionLocal() as session:
            primary_clinic = await self._get_or_create_primary_clinic(session)

            secondary_statement = select(Clinic).where(Clinic.slug.like("secondary-owner-clinic-%"))
            secondary_result = await session.execute(secondary_statement)
            secondary_clinics = list(secondary_result.scalars())

            clinic_ids = [primary_clinic.id, *(clinic.id for clinic in secondary_clinics)]

            await session.execute(delete(Message).where(Message.clinic_id.in_(clinic_ids)))
            await session.execute(delete(Booking).where(Booking.clinic_id.in_(clinic_ids)))
            await session.execute(delete(Patient).where(Patient.clinic_id.in_(clinic_ids)))
            await session.execute(delete(ClinicUser).where(ClinicUser.clinic_id.in_(clinic_ids)))

            for clinic in secondary_clinics:
                await session.delete(clinic)

            primary_clinic.name = settings.test_clinic_name
            primary_clinic.phone_number = settings.resolved_test_clinic_phone_number
            primary_clinic.timezone = settings.resolved_clinic_timezone
            await session.commit()

    async def _get_or_create_primary_clinic(self, session) -> Clinic:
        settings = get_settings()
        statement = select(Clinic).where(Clinic.slug == settings.test_clinic_slug)
        result = await session.execute(statement)
        clinic = result.scalars().first()
        if clinic is None:
            clinic = Clinic(
                name=settings.test_clinic_name,
                slug=settings.test_clinic_slug,
                timezone=settings.resolved_clinic_timezone,
                phone_number=settings.resolved_test_clinic_phone_number,
            )
            session.add(clinic)
            await session.flush()
        return clinic

    async def _create_booking_for_primary_clinic(self, *, patient_name: str) -> uuid.UUID:
        settings = get_settings()
        async with SessionLocal() as session:
            clinic = await self._get_or_create_primary_clinic(session)
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
