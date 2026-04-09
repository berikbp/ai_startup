from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import TestCase

from app.services.normalization import (
    build_datetime_clarification_question,
    clean_full_name,
    normalize_phone_number,
    validate_preferred_datetime,
)


class NormalizationTests(TestCase):
    def test_normalize_phone_number_variants(self) -> None:
        self.assertEqual(normalize_phone_number("87001234567"), "+77001234567")
        self.assertEqual(normalize_phone_number("+7 700 123 45 67"), "+77001234567")
        self.assertEqual(normalize_phone_number("7(700)1234567"), "+77001234567")

    def test_invalid_phone_number_returns_none(self) -> None:
        self.assertIsNone(normalize_phone_number("12345"))

    def test_clean_full_name_accepts_multi_part_names(self) -> None:
        self.assertEqual(clean_full_name("  Анна   Иванова  "), "Анна Иванова")
        self.assertEqual(clean_full_name("Jean-Pierre O'Connor"), "Jean-Pierre O'Connor")

    def test_clean_full_name_rejects_incomplete_or_invalid_names(self) -> None:
        self.assertIsNone(clean_full_name("Иван"))
        self.assertIsNone(clean_full_name("Ок"))
        self.assertIsNone(clean_full_name("Анна 123"))
        self.assertIsNone(clean_full_name("!!! !!!"))

    def test_validate_preferred_datetime_accepts_future_values(self) -> None:
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        validated = validate_preferred_datetime(
            future,
            "Asia/Almaty",
            now=datetime.now(UTC),
        )
        self.assertIsNotNone(validated.value)
        self.assertIsNone(validated.error)

    def test_validate_preferred_datetime_rejects_past_values(self) -> None:
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        validated = validate_preferred_datetime(
            past,
            "Asia/Almaty",
            now=datetime.now(UTC),
        )
        self.assertIsNone(validated.value)
        self.assertEqual(validated.error, "past")

    def test_ambiguous_morning_text_asks_for_specific_time(self) -> None:
        question = build_datetime_clarification_question("завтра утром")
        self.assertIn("точное время", question)
