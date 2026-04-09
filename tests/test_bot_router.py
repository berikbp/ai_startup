from __future__ import annotations

import uuid
from unittest import IsolatedAsyncioTestCase

from sqlmodel import select

from app.bot.router import _reply_and_log
from app.db import SessionLocal, engine
from app.models import Clinic, Message, MessageRole, Patient


class _SentMessage:
    def __init__(self, message_id: int):
        self.message_id = message_id


class _ReplyMessage:
    def __init__(self, *, sent_message_id: int | None = None, should_fail: bool = False):
        self._sent_message_id = sent_message_id
        self._should_fail = should_fail

    async def answer(self, text: str, reply_markup=None) -> _SentMessage:
        if self._should_fail:
            raise RuntimeError("telegram send failed")
        return _SentMessage(self._sent_message_id or 0)


class ReplyAndLogTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.slug = f"router-test-clinic-{uuid.uuid4().hex[:8]}"
        await engine.dispose()

        async with SessionLocal() as session:
            clinic = Clinic(
                name="Router Test Clinic",
                slug=self.slug,
                timezone="Asia/Almaty",
                phone_number="+77001234567",
            )
            session.add(clinic)
            await session.flush()

            patient = Patient(
                clinic_id=clinic.id,
                telegram_user_id=20_000_000 + int(uuid.uuid4().hex[:6], 16),
                telegram_username="router_test_user",
                full_name="Test Patient",
                phone_number="+77001234567",
            )
            session.add(patient)
            await session.commit()

            self.clinic_id = clinic.id
            self.patient_id = patient.id

    async def asyncTearDown(self) -> None:
        async with SessionLocal() as session:
            statement = select(Message).where(Message.patient_id == self.patient_id)
            result = await session.execute(statement)
            for message in result.scalars():
                await session.delete(message)

            patient = await session.get(Patient, self.patient_id)
            if patient is not None:
                await session.delete(patient)

            clinic = await session.get(Clinic, self.clinic_id)
            if clinic is not None:
                await session.delete(clinic)

            await session.commit()

        await engine.dispose()

    async def test_reply_and_log_persists_message_before_send(self) -> None:
        async with SessionLocal() as session:
            clinic = await session.get(Clinic, self.clinic_id)
            patient = await session.get(Patient, self.patient_id)
            if clinic is None or patient is None:
                self.fail("Fixture rows were not created.")

            with self.assertRaises(RuntimeError):
                await _reply_and_log(
                    session,
                    message=_ReplyMessage(should_fail=True),
                    clinic=clinic,
                    patient=patient,
                    text="Тестовое сообщение",
                )

        async with SessionLocal() as session:
            statement = select(Message).where(
                Message.patient_id == self.patient_id,
                Message.role == MessageRole.assistant,
            )
            result = await session.execute(statement)
            persisted_message = result.scalars().one()

        self.assertEqual(persisted_message.content, "Тестовое сообщение")
        self.assertIsNone(persisted_message.telegram_message_id)

    async def test_reply_and_log_updates_telegram_message_id_after_send(self) -> None:
        async with SessionLocal() as session:
            clinic = await session.get(Clinic, self.clinic_id)
            patient = await session.get(Patient, self.patient_id)
            if clinic is None or patient is None:
                self.fail("Fixture rows were not created.")

            await _reply_and_log(
                session,
                message=_ReplyMessage(sent_message_id=321),
                clinic=clinic,
                patient=patient,
                text="Подтверждение",
            )

        async with SessionLocal() as session:
            statement = select(Message).where(
                Message.patient_id == self.patient_id,
                Message.role == MessageRole.assistant,
            )
            result = await session.execute(statement)
            persisted_message = result.scalars().one()

        self.assertEqual(persisted_message.content, "Подтверждение")
        self.assertEqual(persisted_message.telegram_message_id, 321)
