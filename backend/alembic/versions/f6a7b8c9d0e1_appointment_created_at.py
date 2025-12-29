"""Add appointments created_at."""

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.alter_column("appointments", "created_at", server_default=None)
    op.create_index(
        "ix_appointments_pharmacy_status_scheduled",
        "appointments",
        ["pharmacy_id", "status", "scheduled_time"],
    )
    op.create_index(
        "ix_appointments_pharmacy_status_created",
        "appointments",
        ["pharmacy_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_pharmacy_status_created", table_name="appointments")
    op.drop_index("ix_appointments_pharmacy_status_scheduled", table_name="appointments")
    op.drop_column("appointments", "created_at")

