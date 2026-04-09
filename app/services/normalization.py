from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


_WHITESPACE_RE = re.compile(r"\s+")
_TIME_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b")
_DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b")
_NAME_SEPARATORS = {"-", "'", "’"}
_RELATIVE_DATE_WORDS = {
    "сегодня",
    "завтра",
    "послезавтра",
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
    "неделе",
    "неделя",
}


@dataclass(slots=True)
class ValidatedDatetime:
    value: datetime | None
    error: str | None = None


def normalize_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()


def clean_full_name(value: str | None) -> str | None:
    cleaned = normalize_whitespace(value)
    if not cleaned:
        return None

    if any(char.isdigit() for char in cleaned):
        return None

    parts = cleaned.split(" ")
    if len(parts) < 2:
        return None

    if any(not _is_valid_name_part(part) for part in parts):
        return None

    return cleaned


def _is_valid_name_part(value: str) -> bool:
    if not value:
        return False

    if value[0] in _NAME_SEPARATORS or value[-1] in _NAME_SEPARATORS:
        return False

    if any(
        left in _NAME_SEPARATORS and right in _NAME_SEPARATORS
        for left, right in zip(value, value[1:])
    ):
        return False

    letters_only = "".join(char for char in value if char not in _NAME_SEPARATORS)
    return len(letters_only) >= 2 and letters_only.isalpha()


def normalize_phone_number(value: str | None) -> str | None:
    if not value:
        return None

    digits = "".join(char for char in value if char.isdigit())
    if len(digits) == 10:
        digits = f"7{digits}"
    elif len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"

    if len(digits) != 11 or not digits.startswith("7"):
        return None

    return f"+{digits}"


def validate_preferred_datetime(
    value: str | None,
    timezone_name: str,
    *,
    now: datetime | None = None,
) -> ValidatedDatetime:
    if not value:
        return ValidatedDatetime(value=None, error="missing")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ValidatedDatetime(value=None, error="invalid")

    timezone = ZoneInfo(timezone_name)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    else:
        parsed = parsed.astimezone(timezone)

    current_local = now.astimezone(timezone) if now is not None else datetime.now(timezone)
    if parsed <= current_local:
        return ValidatedDatetime(value=None, error="past")

    return ValidatedDatetime(value=parsed.astimezone(UTC))


def format_booking_datetime(value: str | None, timezone_name: str) -> str:
    validated = validate_preferred_datetime(value, timezone_name)
    if validated.value is None:
        return normalize_whitespace(value) or "Не указано"

    localized = validated.value.astimezone(ZoneInfo(timezone_name))
    return localized.strftime("%d.%m.%Y %H:%M")


def build_datetime_clarification_question(value: str | None) -> str:
    cleaned = normalize_whitespace(value).lower()
    has_time = bool(_TIME_RE.search(cleaned))
    has_date = bool(_DATE_RE.search(cleaned)) or any(
        token in cleaned for token in _RELATIVE_DATE_WORDS
    )

    if any(token in cleaned for token in {"утром", "с утра"}):
        return (
            "Уточните, пожалуйста, точное время утром. "
            "Например: завтра в 10:00."
        )
    if any(token in cleaned for token in {"днем", "днём", "после обеда"}):
        return (
            "Уточните, пожалуйста, точное время днем. "
            "Например: в пятницу в 14:30."
        )
    if "вечером" in cleaned:
        return (
            "Уточните, пожалуйста, точное время вечером. "
            "Например: сегодня в 18:00."
        )
    if has_date and not has_time:
        return (
            "Уточните, пожалуйста, точное время. "
            "Например: 12 апреля в 15:30."
        )
    if has_time and not has_date:
        return (
            "Уточните, пожалуйста, дату приема. "
            "Например: 12 апреля в 15:30."
        )

    return (
        "Уточните, пожалуйста, удобные дату и время полностью. "
        "Например: 12 апреля в 15:30."
    )
