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
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+asyncpg://ai_startup:ai_startup@localhost:5434/ai_startup"
    )
    database_disable_pooling: bool = False
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "ai-startup"
    telegram_bot_token: str = ""
    telegram_webhook_base_url: str = ""
    telegram_webhook_secret: str = "local-dev-secret"
    telegram_token_encryption_key: str = ""
    telegram_fsm_state_ttl_seconds: int = 86400
    telegram_fsm_data_ttl_seconds: int = 86400
    telegram_update_idempotency_ttl_seconds: int = 86400
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
    auth_secret_key: str = "change-me-local-auth-secret"
    auth_cookie_name: str = "owner_session"
    auth_session_max_age_seconds: int = 604800
    auth_csrf_cookie_name: str = "owner_csrf"
    auth_csrf_max_age_seconds: int = 604800

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("telegram_webhook_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_api_key)

    def build_telegram_webhook_url(self, clinic_slug: str) -> str | None:
        if not self.telegram_webhook_base_url:
            return None
        return f"{self.telegram_webhook_base_url}/webhook/{clinic_slug}"

    @property
    def telegram_webhook_url(self) -> str | None:
        return self.build_telegram_webhook_url(self.test_clinic_slug)

    @property
    def resolved_test_clinic_phone_number(self) -> str:
        return self.test_clinic_phone or self.test_clinic_phone_number

    @property
    def resolved_clinic_timezone(self) -> str:
        return self.test_clinic_timezone or self.clinic_timezone_default

    @property
    def resolved_telegram_token_encryption_key(self) -> str:
        return self.telegram_token_encryption_key or self.auth_secret_key


def _load_loose_env_file() -> dict[str, str]:
    env_path = Path(".env")
    if not env_path.exists():
        return {}

    mapping = {
        "APP_NAME": "app_name",
        "APP_ENV": "app_env",
        "APP_HOST": "app_host",
        "APP_PORT": "app_port",
        "LOG_LEVEL": "log_level",
        "DATABASE_URL": "database_url",
        "DATABASE_DISABLE_POOLING": "database_disable_pooling",
        "REDIS_URL": "redis_url",
        "REDIS_KEY_PREFIX": "redis_key_prefix",
        "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
        "TELEGRAM_WEBHOOK_BASE_URL": "telegram_webhook_base_url",
        "TELEGRAM_WEBHOOK_SECRET": "telegram_webhook_secret",
        "TELEGRAM_TOKEN_ENCRYPTION_KEY": "telegram_token_encryption_key",
        "TELEGRAM_FSM_STATE_TTL_SECONDS": "telegram_fsm_state_ttl_seconds",
        "TELEGRAM_FSM_DATA_TTL_SECONDS": "telegram_fsm_data_ttl_seconds",
        "TELEGRAM_UPDATE_IDEMPOTENCY_TTL_SECONDS": "telegram_update_idempotency_ttl_seconds",
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
        "AUTH_SECRET_KEY": "auth_secret_key",
        "AUTH_COOKIE_NAME": "auth_cookie_name",
        "AUTH_SESSION_MAX_AGE_SECONDS": "auth_session_max_age_seconds",
        "AUTH_CSRF_COOKIE_NAME": "auth_csrf_cookie_name",
        "AUTH_CSRF_MAX_AGE_SECONDS": "auth_csrf_max_age_seconds",
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
