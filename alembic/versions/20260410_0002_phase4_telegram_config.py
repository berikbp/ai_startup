"""phase 4 clinic telegram config

Revision ID: 20260410_0002
Revises: 20260406_0001
Create Date: 2026-04-10 00:00:00

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260410_0002"
down_revision = "20260406_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic_telegram_config",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("bot_token_encrypted", sa.String(), nullable=False),
        sa.Column("bot_username", sa.String(), nullable=True),
        sa.Column("webhook_secret", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_webhook_registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinic.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "clinic_id",
            name="uq_clinic_telegram_config_clinic_id",
        ),
    )
    op.create_index(
        op.f("ix_clinic_telegram_config_clinic_id"),
        "clinic_telegram_config",
        ["clinic_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_clinic_telegram_config_webhook_secret"),
        "clinic_telegram_config",
        ["webhook_secret"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_clinic_telegram_config_webhook_secret"),
        table_name="clinic_telegram_config",
    )
    op.drop_index(
        op.f("ix_clinic_telegram_config_clinic_id"),
        table_name="clinic_telegram_config",
    )
    op.drop_table("clinic_telegram_config")
