from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import copy
from app.bot.keyboards import confirmation_keyboard, phone_request_keyboard, remove_keyboard
from app.bot.states import BookingStates
from app.config import Settings
from app.db import SessionLocal
from app.models import Clinic, Patient
from app.services.booking_service import create_booking
from app.services.message_service import log_assistant_message, log_user_message
from app.services.normalization import (
    build_datetime_clarification_question,
    clean_full_name,
    normalize_phone_number,
    normalize_whitespace,
    validate_preferred_datetime,
)
from app.services.openai_service import (
    ExtractionResult,
    OpenAIExtractionService,
    OpenAIServiceError,
)
from app.services.patient_service import upsert_patient

YES_CHOICES = {
    "да",
    "да, всё верно",
    "да, все верно",
    "всё верно",
    "все верно",
}
NO_CHOICES = {
    "нет",
    "нет, начать заново",
    "начать заново",
    "заново",
}


def _state_prompt(state_name: str | None) -> str:
    mapping = {
        BookingStates.WAITING_SERVICE.state: copy.ask_service_retry(),
        BookingStates.WAITING_DATETIME.state: copy.ask_datetime(),
        BookingStates.WAITING_NAME.state: copy.ask_name_retry(),
        BookingStates.WAITING_PHONE.state: copy.ask_phone(),
        BookingStates.CONFIRMING.state: copy.confirmation_retry(),
    }
    return mapping.get(state_name, copy.ask_service_retry())


def _message_content(message: Message) -> str:
    if message.text:
        return message.text
    if message.contact:
        return f"[contact] {message.contact.phone_number}"
    return f"[{message.content_type}]"


def _collected_fields(data: dict[str, Any]) -> dict[str, str | None]:
    return {
        "service_type": data.get("service_type"),
        "preferred_datetime_text": data.get("preferred_datetime_text"),
        "patient_name": data.get("full_name"),
        "phone_number": data.get("phone_number"),
    }


def _missing_fields(data: dict[str, Any]) -> list[str]:
    missing = []
    if not data.get("service_type"):
        missing.append("service_type")
    if not data.get("preferred_datetime_iso"):
        missing.append("preferred_datetime")
    if not data.get("full_name"):
        missing.append("full_name")
    if not data.get("phone_number"):
        missing.append("phone_number")
    return missing


async def _load_patient(
    session: AsyncSession,
    *,
    clinic: Clinic,
    message: Message,
    state_data: dict[str, Any],
) -> Patient:
    if message.from_user is None:
        raise RuntimeError("Telegram user is missing from the update.")

    return await upsert_patient(
        session,
        clinic=clinic,
        telegram_user_id=message.from_user.id,
        telegram_username=message.from_user.username,
        full_name=state_data.get("full_name"),
        phone_number=state_data.get("phone_number"),
    )


async def _reply_and_log(
    session: AsyncSession,
    *,
    message: Message,
    clinic: Clinic,
    patient: Patient,
    text: str,
    reply_markup: Any | None = None,
    booking_id: Any | None = None,
) -> None:
    assistant_message = await log_assistant_message(
        session,
        clinic=clinic,
        patient=patient,
        content=text,
        booking_id=booking_id,
    )
    await session.commit()

    sent = await message.answer(text, reply_markup=reply_markup)
    assistant_message.telegram_message_id = sent.message_id

    try:
        await session.commit()
    except Exception:
        await session.rollback()


async def _extract_with_typing(
    *,
    message: Message,
    clinic: Clinic,
    settings: Settings,
    openai_service: OpenAIExtractionService,
    step: str,
    state_data: dict[str, Any],
) -> ExtractionResult:
    async with ChatActionSender.typing(
        chat_id=message.chat.id,
        bot=message.bot,
        interval=settings.typing_interval_seconds,
    ):
        return await openai_service.extract(
            step=step,
            clinic=clinic,
            user_message=message.text or "",
            collected_fields=_collected_fields(state_data),
            missing_fields=_missing_fields(state_data),
        )


async def _handle_non_booking_signals(
    *,
    session: AsyncSession,
    message: Message,
    state: FSMContext,
    clinic: Clinic,
    patient: Patient,
    extraction: ExtractionResult,
    redirect_prompt: str,
    reply_markup: Any | None = None,
) -> bool:
    current_data = await state.get_data()
    off_topic_count = int(current_data.get("off_topic_count", 0))

    if extraction.medical_advice_request:
        await state.update_data(off_topic_count=0)
        await _reply_and_log(
            session,
            message=message,
            clinic=clinic,
            patient=patient,
            text=f"{copy.medical_advice_refusal()}\n\n{redirect_prompt}",
            reply_markup=reply_markup,
        )
        return True

    if extraction.off_topic:
        off_topic_count += 1
        await state.update_data(off_topic_count=off_topic_count)

        response_text = (
            copy.off_topic_phone_fallback(clinic)
            if off_topic_count >= 2
            else f"{copy.off_topic_redirect()}\n\n{redirect_prompt}"
        )
        await _reply_and_log(
            session,
            message=message,
            clinic=clinic,
            patient=patient,
            text=response_text,
            reply_markup=reply_markup,
        )
        return True

    await state.update_data(off_topic_count=0)
    return False


async def _restart_flow(
    *,
    session: AsyncSession,
    message: Message,
    state: FSMContext,
    clinic: Clinic,
    patient: Patient,
    text: str | None = None,
) -> None:
    await state.clear()
    await state.set_state(BookingStates.WAITING_SERVICE)
    await state.set_data({"off_topic_count": 0})
    await _reply_and_log(
        session,
        message=message,
        clinic=clinic,
        patient=patient,
        text=text or copy.start_message(clinic),
        reply_markup=remove_keyboard(),
    )


async def handle_start(
    message: Message,
    state: FSMContext,
    clinic: Clinic,
) -> None:
    async with SessionLocal() as session:
        patient = await _load_patient(
            session,
            clinic=clinic,
            message=message,
            state_data={},
        )
        await log_user_message(
            session,
            clinic=clinic,
            patient=patient,
            content=_message_content(message),
            telegram_message_id=message.message_id,
        )
        await _restart_flow(
            session=session,
            message=message,
            state=state,
            clinic=clinic,
            patient=patient,
        )
        await session.commit()


async def handle_message_without_state(
    message: Message,
    state: FSMContext,
    clinic: Clinic,
) -> None:
    async with SessionLocal() as session:
        patient = await _load_patient(
            session,
            clinic=clinic,
            message=message,
            state_data={},
        )
        await log_user_message(
            session,
            clinic=clinic,
            patient=patient,
            content=_message_content(message),
            telegram_message_id=message.message_id,
        )
        await _restart_flow(
            session=session,
            message=message,
            state=state,
            clinic=clinic,
            patient=patient,
        )
        await session.commit()


async def handle_service_message(
    message: Message,
    state: FSMContext,
    clinic: Clinic,
    settings: Settings,
    openai_service: OpenAIExtractionService,
) -> None:
    state_data = await state.get_data()
    async with SessionLocal() as session:
        patient = await _load_patient(
            session,
            clinic=clinic,
            message=message,
            state_data=state_data,
        )
        await log_user_message(
            session,
            clinic=clinic,
            patient=patient,
            content=_message_content(message),
            telegram_message_id=message.message_id,
        )

        try:
            extraction = await _extract_with_typing(
                message=message,
                clinic=clinic,
                settings=settings,
                openai_service=openai_service,
                step=BookingStates.WAITING_SERVICE.state,
                state_data=state_data,
            )
        except OpenAIServiceError:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.openai_fallback(clinic),
            )
            await session.commit()
            return

        if await _handle_non_booking_signals(
            session=session,
            message=message,
            state=state,
            clinic=clinic,
            patient=patient,
            extraction=extraction,
            redirect_prompt=copy.ask_service_retry(),
        ):
            await session.commit()
            return

        service_type = normalize_whitespace(extraction.service_type)
        if not service_type:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.ask_service_retry(),
            )
            await session.commit()
            return

        await state.update_data(service_type=service_type, off_topic_count=0)
        await state.set_state(BookingStates.WAITING_DATETIME)
        await _reply_and_log(
            session,
            message=message,
            clinic=clinic,
            patient=patient,
            text=copy.ask_datetime(),
        )
        await session.commit()


async def handle_datetime_message(
    message: Message,
    state: FSMContext,
    clinic: Clinic,
    settings: Settings,
    openai_service: OpenAIExtractionService,
) -> None:
    state_data = await state.get_data()
    async with SessionLocal() as session:
        patient = await _load_patient(
            session,
            clinic=clinic,
            message=message,
            state_data=state_data,
        )
        await log_user_message(
            session,
            clinic=clinic,
            patient=patient,
            content=_message_content(message),
            telegram_message_id=message.message_id,
        )

        try:
            extraction = await _extract_with_typing(
                message=message,
                clinic=clinic,
                settings=settings,
                openai_service=openai_service,
                step=BookingStates.WAITING_DATETIME.state,
                state_data=state_data,
            )
        except OpenAIServiceError:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.openai_fallback(clinic),
            )
            await session.commit()
            return

        if await _handle_non_booking_signals(
            session=session,
            message=message,
            state=state,
            clinic=clinic,
            patient=patient,
            extraction=extraction,
            redirect_prompt=copy.ask_datetime(),
        ):
            await session.commit()
            return

        datetime_text = normalize_whitespace(
            extraction.preferred_datetime_text or message.text,
        )
        validated = validate_preferred_datetime(
            extraction.preferred_datetime_iso,
            clinic.timezone,
        )

        if (
            extraction.needs_clarification
            or extraction.datetime_confidence != "high"
            or validated.error == "missing"
        ):
            clarification_question = (
                extraction.clarification_question
                or build_datetime_clarification_question(datetime_text)
            )
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=clarification_question,
            )
            await session.commit()
            return

        if validated.error == "past":
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.future_datetime_required(),
            )
            await session.commit()
            return

        if validated.value is None:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=build_datetime_clarification_question(datetime_text),
            )
            await session.commit()
            return

        await state.update_data(
            preferred_datetime_iso=validated.value.isoformat(),
            preferred_datetime_text=datetime_text,
            off_topic_count=0,
        )
        await state.set_state(BookingStates.WAITING_NAME)
        await _reply_and_log(
            session,
            message=message,
            clinic=clinic,
            patient=patient,
            text=copy.ask_name(),
        )
        await session.commit()


async def handle_name_message(
    message: Message,
    state: FSMContext,
    clinic: Clinic,
    settings: Settings,
    openai_service: OpenAIExtractionService,
) -> None:
    state_data = await state.get_data()
    async with SessionLocal() as session:
        patient = await _load_patient(
            session,
            clinic=clinic,
            message=message,
            state_data=state_data,
        )
        await log_user_message(
            session,
            clinic=clinic,
            patient=patient,
            content=_message_content(message),
            telegram_message_id=message.message_id,
        )

        try:
            extraction = await _extract_with_typing(
                message=message,
                clinic=clinic,
                settings=settings,
                openai_service=openai_service,
                step=BookingStates.WAITING_NAME.state,
                state_data=state_data,
            )
        except OpenAIServiceError:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.openai_fallback(clinic),
            )
            await session.commit()
            return

        if await _handle_non_booking_signals(
            session=session,
            message=message,
            state=state,
            clinic=clinic,
            patient=patient,
            extraction=extraction,
            redirect_prompt=copy.ask_name_retry(),
        ):
            await session.commit()
            return

        full_name = clean_full_name(extraction.patient_name or message.text)
        if not full_name:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.ask_name_retry(),
            )
            await session.commit()
            return

        await upsert_patient(
            session,
            clinic=clinic,
            telegram_user_id=message.from_user.id,
            telegram_username=message.from_user.username,
            full_name=full_name,
            phone_number=state_data.get("phone_number"),
        )
        await state.update_data(full_name=full_name, off_topic_count=0)
        await state.set_state(BookingStates.WAITING_PHONE)
        await _reply_and_log(
            session,
            message=message,
            clinic=clinic,
            patient=patient,
            text=copy.ask_phone(),
            reply_markup=phone_request_keyboard(),
        )
        await session.commit()


async def handle_phone_contact(
    message: Message,
    state: FSMContext,
    clinic: Clinic,
) -> None:
    state_data = await state.get_data()
    async with SessionLocal() as session:
        patient = await _load_patient(
            session,
            clinic=clinic,
            message=message,
            state_data=state_data,
        )
        await log_user_message(
            session,
            clinic=clinic,
            patient=patient,
            content=_message_content(message),
            telegram_message_id=message.message_id,
        )

        if message.from_user is None or message.contact is None:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.phone_invalid(),
                reply_markup=phone_request_keyboard(),
            )
            await session.commit()
            return

        if message.contact.user_id not in {None, message.from_user.id}:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.contact_owner_required(),
                reply_markup=phone_request_keyboard(),
            )
            await session.commit()
            return

        phone_number = normalize_phone_number(message.contact.phone_number)
        if phone_number is None:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.phone_invalid(),
                reply_markup=phone_request_keyboard(),
            )
            await session.commit()
            return

        await upsert_patient(
            session,
            clinic=clinic,
            telegram_user_id=message.from_user.id,
            telegram_username=message.from_user.username,
            full_name=state_data.get("full_name"),
            phone_number=phone_number,
        )
        await state.update_data(phone_number=phone_number, off_topic_count=0)
        await state.set_state(BookingStates.CONFIRMING)

        refreshed_data = await state.get_data()
        await _reply_and_log(
            session,
            message=message,
            clinic=clinic,
            patient=patient,
            text=copy.confirmation_summary(
                clinic=clinic,
                service_type=refreshed_data["service_type"],
                preferred_datetime_iso=refreshed_data["preferred_datetime_iso"],
                full_name=refreshed_data["full_name"],
                phone_number=phone_number,
            ),
            reply_markup=confirmation_keyboard(),
        )
        await session.commit()


async def handle_phone_message(
    message: Message,
    state: FSMContext,
    clinic: Clinic,
    settings: Settings,
    openai_service: OpenAIExtractionService,
) -> None:
    state_data = await state.get_data()
    async with SessionLocal() as session:
        patient = await _load_patient(
            session,
            clinic=clinic,
            message=message,
            state_data=state_data,
        )
        await log_user_message(
            session,
            clinic=clinic,
            patient=patient,
            content=_message_content(message),
            telegram_message_id=message.message_id,
        )

        try:
            extraction = await _extract_with_typing(
                message=message,
                clinic=clinic,
                settings=settings,
                openai_service=openai_service,
                step=BookingStates.WAITING_PHONE.state,
                state_data=state_data,
            )
        except OpenAIServiceError:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.openai_fallback(clinic),
                reply_markup=phone_request_keyboard(),
            )
            await session.commit()
            return

        if await _handle_non_booking_signals(
            session=session,
            message=message,
            state=state,
            clinic=clinic,
            patient=patient,
            extraction=extraction,
            redirect_prompt=copy.ask_phone(),
            reply_markup=phone_request_keyboard(),
        ):
            await session.commit()
            return

        phone_number = normalize_phone_number(extraction.phone_number or message.text)
        if phone_number is None:
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=copy.phone_invalid(),
                reply_markup=phone_request_keyboard(),
            )
            await session.commit()
            return

        await upsert_patient(
            session,
            clinic=clinic,
            telegram_user_id=message.from_user.id,
            telegram_username=message.from_user.username,
            full_name=state_data.get("full_name"),
            phone_number=phone_number,
        )
        await state.update_data(phone_number=phone_number, off_topic_count=0)
        await state.set_state(BookingStates.CONFIRMING)

        refreshed_data = await state.get_data()
        await _reply_and_log(
            session,
            message=message,
            clinic=clinic,
            patient=patient,
            text=copy.confirmation_summary(
                clinic=clinic,
                service_type=refreshed_data["service_type"],
                preferred_datetime_iso=refreshed_data["preferred_datetime_iso"],
                full_name=refreshed_data["full_name"],
                phone_number=phone_number,
            ),
            reply_markup=confirmation_keyboard(),
        )
        await session.commit()


async def handle_confirmation_message(
    message: Message,
    state: FSMContext,
    clinic: Clinic,
    settings: Settings,
) -> None:
    state_data = await state.get_data()
    async with SessionLocal() as session:
        patient = await _load_patient(
            session,
            clinic=clinic,
            message=message,
            state_data=state_data,
        )
        await log_user_message(
            session,
            clinic=clinic,
            patient=patient,
            content=_message_content(message),
            telegram_message_id=message.message_id,
        )

        decision = normalize_whitespace(message.text).lower()
        if decision in YES_CHOICES:
            validated = validate_preferred_datetime(
                state_data.get("preferred_datetime_iso"),
                clinic.timezone,
            )
            if validated.value is None:
                await state.set_state(BookingStates.WAITING_DATETIME)
                await _reply_and_log(
                    session,
                    message=message,
                    clinic=clinic,
                    patient=patient,
                    text=copy.ask_datetime(),
                    reply_markup=remove_keyboard(),
                )
                await session.commit()
                return

            await upsert_patient(
                session,
                clinic=clinic,
                telegram_user_id=message.from_user.id,
                telegram_username=message.from_user.username,
                full_name=state_data.get("full_name"),
                phone_number=state_data.get("phone_number"),
            )
            result = await create_booking(
                session,
                clinic=clinic,
                patient=patient,
                service_type=state_data["service_type"],
                preferred_datetime_at=validated.value,
                preferred_datetime_text=state_data["preferred_datetime_text"],
                duplicate_window_seconds=settings.booking_duplicate_window_seconds,
            )
            await state.clear()
            await _reply_and_log(
                session,
                message=message,
                clinic=clinic,
                patient=patient,
                text=(
                    copy.duplicate_message(clinic)
                    if result.is_duplicate
                    else copy.receipt_message(clinic)
                ),
                reply_markup=remove_keyboard(),
                booking_id=result.booking.id,
            )
            await session.commit()
            return

        if decision in NO_CHOICES:
            await _restart_flow(
                session=session,
                message=message,
                state=state,
                clinic=clinic,
                patient=patient,
                text=copy.booking_restart_message(),
            )
            await session.commit()
            return

        await _reply_and_log(
            session,
            message=message,
            clinic=clinic,
            patient=patient,
            text=copy.confirmation_retry(),
            reply_markup=confirmation_keyboard(),
        )
        await session.commit()


async def handle_non_text_message(
    message: Message,
    state: FSMContext,
    clinic: Clinic,
) -> None:
    state_data = await state.get_data()
    async with SessionLocal() as session:
        patient = await _load_patient(
            session,
            clinic=clinic,
            message=message,
            state_data=state_data,
        )
        await log_user_message(
            session,
            clinic=clinic,
            patient=patient,
            content=_message_content(message),
            telegram_message_id=message.message_id,
        )

        state_name = await state.get_state()
        prompt = _state_prompt(state_name)
        reply_markup: Any | None = None
        if state_name == BookingStates.WAITING_PHONE.state:
            reply_markup = phone_request_keyboard()
        elif state_name == BookingStates.CONFIRMING.state:
            reply_markup = confirmation_keyboard()

        await _reply_and_log(
            session,
            message=message,
            clinic=clinic,
            patient=patient,
            text=copy.non_text_retry(prompt),
            reply_markup=reply_markup,
        )
        await session.commit()


def build_router() -> Router:
    router = Router()
    router.message.register(handle_start, CommandStart())
    router.message.register(handle_message_without_state, StateFilter(None), F.text)
    router.message.register(handle_service_message, BookingStates.WAITING_SERVICE, F.text)
    router.message.register(handle_datetime_message, BookingStates.WAITING_DATETIME, F.text)
    router.message.register(handle_name_message, BookingStates.WAITING_NAME, F.text)
    router.message.register(handle_phone_contact, BookingStates.WAITING_PHONE, F.contact)
    router.message.register(handle_phone_message, BookingStates.WAITING_PHONE, F.text)
    router.message.register(handle_confirmation_message, BookingStates.CONFIRMING, F.text)
    router.message.register(
        handle_non_text_message,
        BookingStates.WAITING_SERVICE,
        BookingStates.WAITING_DATETIME,
        BookingStates.WAITING_NAME,
        BookingStates.WAITING_PHONE,
        BookingStates.CONFIRMING,
    )
    return router
