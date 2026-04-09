from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Clinic, ClinicUser
from app.services.normalization import normalize_whitespace


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
MIN_PASSWORD_LENGTH = 8


@dataclass(slots=True)
class SessionData:
    clinic_user_id: uuid.UUID
    expires_at: int


def normalize_owner_email(value: str | None) -> str | None:
    normalized = normalize_whitespace(value).lower()
    if not normalized or " " in normalized or normalized.count("@") != 1:
        return None

    local, domain = normalized.split("@", 1)
    if not local or not domain or "." not in domain:
        return None

    return normalized


def validate_password(value: str | None) -> str | None:
    password = value or ""
    if len(password) < MIN_PASSWORD_LENGTH:
        return None
    return password


def hash_password(password: str) -> str:
    validated = validate_password(password)
    if validated is None:
        raise ValueError("Password does not meet the minimum length requirement.")

    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        validated.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
        f"{_urlsafe_b64encode(salt)}${_urlsafe_b64encode(derived)}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_derived = password_hash.split("$", 5)
    except ValueError:
        return False

    if algorithm != "scrypt":
        return False

    try:
        salt = _urlsafe_b64decode(raw_salt)
        expected = _urlsafe_b64decode(raw_derived)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(derived, expected)


def create_session_token(
    *,
    clinic_user_id: uuid.UUID,
    secret_key: str,
    max_age_seconds: int,
) -> str:
    payload = {
        "sub": str(clinic_user_id),
        "exp": int(time.time()) + max_age_seconds,
    }
    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_part = _urlsafe_b64encode(raw_payload)
    signature = _sign_value(payload_part.encode("utf-8"), secret_key)
    return f"{payload_part}.{_urlsafe_b64encode(signature)}"


def verify_session_token(token: str | None, secret_key: str) -> SessionData | None:
    if not token or "." not in token:
        return None

    payload_part, signature_part = token.split(".", 1)

    try:
        signature = _urlsafe_b64decode(signature_part)
    except (ValueError, TypeError):
        return None

    expected_signature = _sign_value(payload_part.encode("utf-8"), secret_key)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(_urlsafe_b64decode(payload_part).decode("utf-8"))
        clinic_user_id = uuid.UUID(str(payload["sub"]))
        expires_at = int(payload["exp"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None

    if expires_at <= int(time.time()):
        return None

    return SessionData(clinic_user_id=clinic_user_id, expires_at=expires_at)


async def clinic_has_owner(session: AsyncSession, clinic_id: uuid.UUID) -> bool:
    statement = select(func.count()).select_from(ClinicUser).where(ClinicUser.clinic_id == clinic_id)
    result = await session.execute(statement)
    return int(result.scalar_one()) > 0


async def get_clinic_user_by_email(session: AsyncSession, email: str) -> ClinicUser | None:
    statement = select(ClinicUser).where(ClinicUser.email == email)
    result = await session.execute(statement)
    return result.scalars().first()


async def get_clinic_user_by_id(session: AsyncSession, clinic_user_id: uuid.UUID) -> ClinicUser | None:
    return await session.get(ClinicUser, clinic_user_id)


async def create_owner_user(
    session: AsyncSession,
    *,
    clinic: Clinic,
    email: str,
    password: str,
) -> ClinicUser:
    normalized_email = normalize_owner_email(email)
    if normalized_email is None:
        raise ValueError("Укажите корректный email.")

    if validate_password(password) is None:
        raise ValueError("Пароль должен содержать минимум 8 символов.")

    if await clinic_has_owner(session, clinic.id):
        raise ValueError("Регистрация уже завершена для этой клиники.")

    existing_user = await get_clinic_user_by_email(session, normalized_email)
    if existing_user is not None:
        raise ValueError("Пользователь с таким email уже существует.")

    clinic_user = ClinicUser(
        clinic_id=clinic.id,
        email=normalized_email,
        hashed_password=hash_password(password),
        is_active=True,
        is_verified=True,
    )
    session.add(clinic_user)
    await session.flush()
    return clinic_user


async def authenticate_owner(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> ClinicUser | None:
    normalized_email = normalize_owner_email(email)
    if normalized_email is None:
        return None

    clinic_user = await get_clinic_user_by_email(session, normalized_email)
    if clinic_user is None or not clinic_user.is_active:
        return None

    if not verify_password(password, clinic_user.hashed_password):
        return None

    return clinic_user


def _sign_value(value: bytes, secret_key: str) -> bytes:
    return hmac.new(secret_key.encode("utf-8"), value, digestmod=hashlib.sha256).digest()


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
