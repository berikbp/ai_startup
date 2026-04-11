from __future__ import annotations

from app.models import Clinic
from app.services.normalization import format_booking_datetime


def start_message(clinic: Clinic) -> str:
    return (
        f"Здравствуйте! Я помогу оставить заявку на запись в {clinic.name}.\n\n"
        "На какую услугу вы хотите записаться?"
    )


def ask_service_retry() -> str:
    return (
        "Напишите, пожалуйста, на какую услугу вы хотите записаться. "
        "Например: консультация терапевта или УЗИ."
    )


def ask_datetime() -> str:
    return "Укажите, пожалуйста, удобные дату и время для записи."


def ask_name() -> str:
    return "Как вас зовут? Напишите, пожалуйста, имя и фамилию."


def ask_name_retry() -> str:
    return "Напишите, пожалуйста, ваше имя и фамилию."


def ask_phone() -> str:
    return (
        "Укажите, пожалуйста, номер телефона. Можно нажать кнопку ниже "
        "или отправить номер текстом в формате +77001234567."
    )


def phone_invalid() -> str:
    return (
        "Не получилось распознать номер. Отправьте, пожалуйста, номер "
        "в формате +77001234567 или нажмите кнопку ниже."
    )


def contact_owner_required() -> str:
    return "Пожалуйста, отправьте свой номер телефона или напишите его текстом."


def confirmation_summary(
    *,
    clinic: Clinic,
    service_type: str,
    preferred_datetime_iso: str,
    full_name: str,
    phone_number: str,
) -> str:
    return (
        "Проверьте, пожалуйста, заявку:\n"
        f"Услуга: {service_type}\n"
        f"Дата и время: {format_booking_datetime(preferred_datetime_iso, clinic.timezone)}\n"
        f"Имя: {full_name}\n"
        f"Телефон: {phone_number}\n\n"
        "Всё верно?"
    )


def receipt_message(clinic: Clinic) -> str:
    return (
        f"Спасибо! Заявка принята. {clinic.name} свяжется с вами по телефону, "
        "чтобы подтвердить время приема."
    )


def duplicate_message(clinic: Clinic) -> str:
    return (
        "Такую заявку мы уже получили совсем недавно. "
        f"{clinic.name} свяжется с вами по телефону, чтобы подтвердить детали."
    )


def booking_restart_message() -> str:
    return "Хорошо, начнем заново. На какую услугу вы хотите записаться?"


def confirmation_retry() -> str:
    return "Пожалуйста, выберите: подтвердить заявку или начать заново."


def off_topic_redirect() -> str:
    return (
        "Я помогаю с записью и вопросами по услугам клиники. "
        "Давайте продолжим оформление заявки."
    )


def off_topic_phone_fallback(clinic: Clinic) -> str:
    return (
        "Если удобнее, позвоните, пожалуйста, в клинику "
        f"по номеру {clinic.phone_number or 'клиники'}. "
        "Я могу продолжить запись здесь, когда будете готовы."
    )


def medical_advice_refusal() -> str:
    return (
        "Я не могу давать медицинские рекомендации. "
        "Могу помочь оставить заявку на консультацию врача."
    )


def openai_fallback(clinic: Clinic) -> str:
    return (
        "Сейчас не получается обработать сообщение автоматически. "
        f"Попробуйте еще раз чуть позже или позвоните в клинику по номеру {clinic.phone_number or 'клиники'}."
    )


def future_datetime_required() -> str:
    return (
        "Нужны, пожалуйста, будущие дата и время. "
        "Напишите удобный вариант, например: 12.04 в 15:30."
    )


def non_text_retry(prompt: str) -> str:
    return f"Пожалуйста, отправьте ответ текстом.\n\n{prompt}"


def cancel_no_pending_booking() -> str:
    return "У вас нет активных заявок для отмены."


def cancel_confirmation(
    *,
    clinic: Clinic,
    service_type: str,
    preferred_datetime_iso: str | None,
    preferred_datetime_text: str | None,
) -> str:
    if preferred_datetime_iso:
        dt_str = format_booking_datetime(preferred_datetime_iso, clinic.timezone)
    else:
        dt_str = preferred_datetime_text or "не указано"
    return (
        "Найдена заявка:\n"
        f"Услуга: {service_type}\n"
        f"Дата и время: {dt_str}\n\n"
        "Вы хотите отменить эту заявку?"
    )


def cancel_success() -> str:
    return "Заявка отменена. Если захотите записаться снова, напишите /start."


def cancel_aborted() -> str:
    return "Хорошо, заявка сохранена. Если нужна помощь, напишите /start."
