from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin(SQLModel):
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"onupdate": utc_now},
    )


class BookingStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"


class BookingSource(str, Enum):
    telegram = "telegram"


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"


class Clinic(TimestampMixin, table=True):
    __tablename__ = "clinic"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    timezone: str = Field(default="Asia/Almaty")
    phone_number: str | None = None


class ClinicUser(TimestampMixin, table=True):
    __tablename__ = "clinic_user"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    clinic_id: uuid.UUID = Field(foreign_key="clinic.id", index=True, nullable=False)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    is_active: bool = Field(default=True, nullable=False)
    is_verified: bool = Field(default=False, nullable=False)


class Patient(TimestampMixin, table=True):
    __tablename__ = "patient"

    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "telegram_user_id",
            name="uq_patient_clinic_telegram_user",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    clinic_id: uuid.UUID = Field(foreign_key="clinic.id", index=True, nullable=False)
    telegram_user_id: int = Field(nullable=False)
    telegram_username: str | None = None
    full_name: str | None = None
    phone_number: str | None = None


class Booking(TimestampMixin, table=True):
    __tablename__ = "booking"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    clinic_id: uuid.UUID = Field(foreign_key="clinic.id", index=True, nullable=False)
    patient_id: uuid.UUID = Field(foreign_key="patient.id", index=True, nullable=False)
    service_type: str
    preferred_datetime_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    preferred_datetime_text: str | None = None
    status: BookingStatus = Field(
        default=BookingStatus.pending,
        nullable=False,
        sa_type=String(),
    )
    source: BookingSource = Field(
        default=BookingSource.telegram,
        nullable=False,
        sa_type=String(),
    )


class Message(SQLModel, table=True):
    __tablename__ = "message"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    clinic_id: uuid.UUID = Field(foreign_key="clinic.id", index=True, nullable=False)
    patient_id: uuid.UUID = Field(foreign_key="patient.id", index=True, nullable=False)
    booking_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="booking.id",
        index=True,
    )
    role: MessageRole = Field(nullable=False, sa_type=String())
    content: str
    telegram_message_id: int | None = None
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
