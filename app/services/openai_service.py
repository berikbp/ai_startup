from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel

from app.config import Settings
from app.logging_utils import structured_event
from app.models import Clinic


logger = logging.getLogger(__name__)


class ExtractionResult(BaseModel):
    service_type: str | None = None
    preferred_datetime_iso: str | None = None
    preferred_datetime_text: str | None = None
    datetime_confidence: Literal["high", "low", "none"] = "none"
    patient_name: str | None = None
    phone_number: str | None = None
    off_topic: bool = False
    medical_advice_request: bool = False
    needs_clarification: bool = False
    clarification_question: str | None = None


class OpenAIServiceError(RuntimeError):
    pass


class OpenAIExtractionService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: AsyncOpenAI | None = None
        if settings.openai_enabled:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def extract(
        self,
        *,
        step: str,
        clinic: Clinic,
        user_message: str,
        collected_fields: dict[str, str | None],
        missing_fields: list[str],
    ) -> ExtractionResult:
        if self._client is None:
            logger.warning(
                structured_event(
                    "openai_extraction_unavailable",
                    clinic_id=clinic.id,
                    clinic_slug=clinic.slug,
                    step=step,
                    reason="not_configured",
                )
            )
            raise OpenAIServiceError("OpenAI is not configured.")

        timezone_name = clinic.timezone or self._settings.clinic_timezone_default
        current_local_datetime = datetime.now(ZoneInfo(timezone_name)).isoformat()
        instructions = self._build_instructions(
            step=step,
            clinic=clinic,
            timezone_name=timezone_name,
            current_local_datetime=current_local_datetime,
            collected_fields=collected_fields,
            missing_fields=missing_fields,
        )

        try:
            response = await self._client.responses.create(
                model=self._settings.openai_model,
                instructions=instructions,
                input=user_message,
                parallel_tool_calls=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "booking_extraction",
                        "strict": True,
                        "schema": self._schema(),
                    }
                },
            )
        except (APIConnectionError, APIError, APITimeoutError, RateLimitError) as exc:
            logger.exception(
                structured_event(
                    "openai_extraction_failed",
                    clinic_id=clinic.id,
                    clinic_slug=clinic.slug,
                    step=step,
                    reason="request_failed",
                )
            )
            raise OpenAIServiceError("OpenAI request failed.") from exc

        output_text = getattr(response, "output_text", None)
        if not output_text:
            logger.warning(
                structured_event(
                    "openai_extraction_failed",
                    clinic_id=clinic.id,
                    clinic_slug=clinic.slug,
                    step=step,
                    reason="empty_response",
                )
            )
            raise OpenAIServiceError("OpenAI returned an empty response.")

        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as exc:
            logger.warning(
                structured_event(
                    "openai_extraction_failed",
                    clinic_id=clinic.id,
                    clinic_slug=clinic.slug,
                    step=step,
                    reason="invalid_json",
                )
            )
            raise OpenAIServiceError("OpenAI returned invalid JSON.") from exc

        return ExtractionResult.model_validate(payload)

    def _build_instructions(
        self,
        *,
        step: str,
        clinic: Clinic,
        timezone_name: str,
        current_local_datetime: str,
        collected_fields: dict[str, str | None],
        missing_fields: list[str],
    ) -> str:
        clinic_phone = clinic.phone_number or "не указан"
        return (
            "You extract structured fields for a Russian-language Telegram booking flow.\n"
            f"Clinic name: {clinic.name}\n"
            f"Clinic phone number: {clinic_phone}\n"
            f"Clinic timezone: {timezone_name}\n"
            f"Current Almaty-local reference datetime: {current_local_datetime}\n"
            f"Active step: {step}\n"
            f"Already collected fields: {json.dumps(collected_fields, ensure_ascii=False)}\n"
            f"Missing fields: {json.dumps(missing_fields, ensure_ascii=False)}\n"
            "Restrictions:\n"
            "- stay on booking and clinic-service topics only\n"
            "- refuse medical advice\n"
            "- ask a clarifying question for ambiguous time expressions\n"
            "- never confirm appointment availability\n"
            "- for WAITING_DATETIME, set preferred_datetime_iso only when the time is specific enough\n"
            "- if time is ambiguous, set needs_clarification=true and write a short Russian clarification_question\n"
            "- for WAITING_SERVICE, extract a service_type only if the user names a clinic service or consultation\n"
            "- for WAITING_NAME, extract only a human full name\n"
            "- for WAITING_PHONE, extract only a phone candidate\n"
            "- off_topic should be true only for clearly unrelated topics\n"
            "- medical_advice_request should be true for diagnosis, treatment, symptoms, medication, or triage advice requests\n"
        )

    def _schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "service_type": {"type": ["string", "null"]},
                "preferred_datetime_iso": {"type": ["string", "null"]},
                "preferred_datetime_text": {"type": ["string", "null"]},
                "datetime_confidence": {
                    "type": "string",
                    "enum": ["high", "low", "none"],
                },
                "patient_name": {"type": ["string", "null"]},
                "phone_number": {"type": ["string", "null"]},
                "off_topic": {"type": "boolean"},
                "medical_advice_request": {"type": "boolean"},
                "needs_clarification": {"type": "boolean"},
                "clarification_question": {"type": ["string", "null"]},
            },
            "required": [
                "service_type",
                "preferred_datetime_iso",
                "preferred_datetime_text",
                "datetime_confidence",
                "patient_name",
                "phone_number",
                "off_topic",
                "medical_advice_request",
                "needs_clarification",
                "clarification_question",
            ],
        }
