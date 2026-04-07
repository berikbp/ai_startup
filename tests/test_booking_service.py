from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest import IsolatedAsyncioTestCase

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import Booking, Clinic, Patient
from app.services.booking_service import create_booking


class BookingServiceTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.slug = f"test-clinic-{uuid.uuid4().hex[:8]}"

        async with SessionLocal() as session:
            clinic = Clinic(
                name="Booking Service Test Clinic",
                slug=self.slug,
                timezone="Asia/Almaty",
                phone_number="+77001234567",
            )
            session.add(clinic)
            await session.flush()

            patient = Patient(
                clinic_id=clinic.id,
                telegram_user_id=10_000_000 + int(uuid.uuid4().hex[:6], 16),
                telegram_username="booking_service_test",
                full_name="Test Patient",
                phone_number="+77001234567",
            )
            session.add(patient)
            await session.commit()

            self.clinic_id = clinic.id
            self.patient_id = patient.id

    async def asyncTearDown(self) -> None:
        async with SessionLocal() as session:
            await session.execute(delete(Booking).where(Booking.clinic_id == self.clinic_id))
            await session.execute(delete(Patient).where(Patient.id == self.patient_id))
            await session.execute(delete(Clinic).where(Clinic.id == self.clinic_id))
            await session.commit()

    async def test_duplicate_booking_returns_existing_record(self) -> None:
        preferred_datetime = datetime.now(UTC) + timedelta(days=1)

        async with SessionLocal() as session:
            clinic = await session.get(Clinic, self.clinic_id)
            patient = await session.get(Patient, self.patient_id)
            if clinic is None or patient is None:
                self.fail("Fixture rows were not created.")

            first_result = await create_booking(
                session,
                clinic=clinic,
                patient=patient,
                service_type="Консультация стоматолога",
                preferred_datetime_at=preferred_datetime,
                preferred_datetime_text="завтра в 15:30",
                duplicate_window_seconds=300,
            )
            await session.commit()

        async with SessionLocal() as session:
            clinic = await session.get(Clinic, self.clinic_id)
            patient = await session.get(Patient, self.patient_id)
            if clinic is None or patient is None:
                self.fail("Fixture rows were not available for the duplicate check.")

            duplicate_result = await create_booking(
                session,
                clinic=clinic,
                patient=patient,
                service_type="Консультация стоматолога",
                preferred_datetime_at=preferred_datetime,
                preferred_datetime_text="завтра в 15:30",
                duplicate_window_seconds=300,
            )

        self.assertFalse(first_result.is_duplicate)
        self.assertTrue(duplicate_result.is_duplicate)
        self.assertEqual(first_result.booking.id, duplicate_result.booking.id)
