import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ai-startup"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = (
        "postgresql+asyncpg://ai_startup:ai_startup@localhost:5434/ai_startup"
    )
    telegram_bot_token: str = ""
    telegram_webhook_base_url: str = ""
    telegram_webhook_secret: str = "local-dev-secret"
    test_clinic_slug: str = "test-clinic"
    test_clinic_name: str = "Тестовая клиника"
    test_clinic_phone: str = ""
    test_clinic_phone_number: str = Field(
        default="+77001234567",
        validation_alias=AliasChoices("TEST_CLINIC_PHONE_NUMBER", "TEST_CLINIC_PHONE"),
    )
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 20.0
    test_clinic_timezone: str = ""
    clinic_timezone_default: str = Field(
        default="Asia/Almaty",
        validation_alias=AliasChoices("CLINIC_TIMEZONE_DEFAULT", "TEST_CLINIC_TIMEZONE"),
    )
    typing_interval_seconds: float = 4.0
    booking_duplicate_window_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("telegram_webhook_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def telegram_webhook_url(self) -> str | None:
        if not self.telegram_webhook_base_url:
            return None
        return f"{self.telegram_webhook_base_url}/webhook/{self.test_clinic_slug}"

    @property
    def resolved_test_clinic_phone_number(self) -> str:
        return self.test_clinic_phone or self.test_clinic_phone_number

    @property
    def resolved_clinic_timezone(self) -> str:
        return self.test_clinic_timezone or self.clinic_timezone_default


def _load_loose_env_file() -> dict[str, str]:
    env_path = Path(".env")
    if not env_path.exists():
        return {}

    mapping = {
        "APP_NAME": "app_name",
        "APP_ENV": "app_env",
        "APP_HOST": "app_host",
        "APP_PORT": "app_port",
        "DATABASE_URL": "database_url",
        "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
        "TELEGRAM_WEBHOOK_BASE_URL": "telegram_webhook_base_url",
        "TELEGRAM_WEBHOOK_SECRET": "telegram_webhook_secret",
        "TEST_CLINIC_SLUG": "test_clinic_slug",
        "TEST_CLINIC_NAME": "test_clinic_name",
        "TEST_CLINIC_PHONE": "test_clinic_phone",
        "TEST_CLINIC_PHONE_NUMBER": "test_clinic_phone_number",
        "TEST_CLINIC_TIMEZONE": "test_clinic_timezone",
        "CLINIC_TIMEZONE_DEFAULT": "clinic_timezone_default",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_MODEL": "openai_model",
        "OPENAI_TIMEOUT_SECONDS": "openai_timeout_seconds",
        "TYPING_INTERVAL_SECONDS": "typing_interval_seconds",
        "BOOKING_DUPLICATE_WINDOW_SECONDS": "booking_duplicate_window_seconds",
    }

    overrides: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        env_name, value = line.split("=", 1)
        env_name = env_name.strip()
        value = value.strip()
        field_name = mapping.get(env_name)
        if field_name is None or os.getenv(env_name) is not None:
            continue
        overrides[field_name] = value

    return overrides


@lru_cache
def get_settings() -> Settings:
    return Settings(**_load_loose_env_file())
