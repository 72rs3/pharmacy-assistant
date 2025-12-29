"""Add locale and no-show settings for appointments."""

from alembic import op
import sqlalchemy as sa


revision = "f8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointment_settings",
        sa.Column("no_show_minutes", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "appointment_settings",
        sa.Column("locale", sa.String(), nullable=False, server_default="en"),
    )
    op.alter_column("appointment_settings", "no_show_minutes", server_default=None)
    op.alter_column("appointment_settings", "locale", server_default=None)


def downgrade() -> None:
    op.drop_column("appointment_settings", "locale")
    op.drop_column("appointment_settings", "no_show_minutes")
