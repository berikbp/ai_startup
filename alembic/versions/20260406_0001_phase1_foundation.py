"""phase 1 foundation schema

Revision ID: 20260406_0001
Revises:
Create Date: 2026-04-06 00:00:00

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260406_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clinic_slug"), "clinic", ["slug"], unique=True)

    op.create_table(
        "clinic_user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinic.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clinic_user_clinic_id"), "clinic_user", ["clinic_id"], unique=False)
    op.create_index(op.f("ix_clinic_user_email"), "clinic_user", ["email"], unique=True)

    op.create_table(
        "patient",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(), nullable=True),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("phone_number", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinic.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "clinic_id",
            "telegram_user_id",
            name="uq_patient_clinic_telegram_user",
        ),
    )
    op.create_index(op.f("ix_patient_clinic_id"), "patient", ["clinic_id"], unique=False)

    op.create_table(
        "booking",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("service_type", sa.String(), nullable=False),
        sa.Column("preferred_datetime_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preferred_datetime_text", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinic.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_booking_clinic_id"), "booking", ["clinic_id"], unique=False)
    op.create_index(op.f("ix_booking_patient_id"), "booking", ["patient_id"], unique=False)

    op.create_table(
        "message",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["booking.id"]),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinic.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_message_booking_id"), "message", ["booking_id"], unique=False)
    op.create_index(op.f("ix_message_clinic_id"), "message", ["clinic_id"], unique=False)
    op.create_index(op.f("ix_message_patient_id"), "message", ["patient_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_message_patient_id"), table_name="message")
    op.drop_index(op.f("ix_message_clinic_id"), table_name="message")
    op.drop_index(op.f("ix_message_booking_id"), table_name="message")
    op.drop_table("message")

    op.drop_index(op.f("ix_booking_patient_id"), table_name="booking")
    op.drop_index(op.f("ix_booking_clinic_id"), table_name="booking")
    op.drop_table("booking")

    op.drop_index(op.f("ix_patient_clinic_id"), table_name="patient")
    op.drop_table("patient")

    op.drop_index(op.f("ix_clinic_user_email"), table_name="clinic_user")
    op.drop_index(op.f("ix_clinic_user_clinic_id"), table_name="clinic_user")
    op.drop_table("clinic_user")

    op.drop_index(op.f("ix_clinic_slug"), table_name="clinic")
    op.drop_table("clinic")
