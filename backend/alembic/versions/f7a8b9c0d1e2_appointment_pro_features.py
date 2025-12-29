"""Add appointment settings, audits, reminders, and customer email/no-show."""

from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("customer_email", sa.String(), nullable=True))
    op.add_column("appointments", sa.Column("no_show", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("appointments", sa.Column("no_show_marked_at", sa.DateTime(), nullable=True))
    op.alter_column("appointments", "no_show", server_default=None)

    op.create_table(
        "appointment_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=False, unique=True),
        sa.Column("slot_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("buffer_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
        sa.Column("weekly_hours_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_appointment_settings_pharmacy_id", "appointment_settings", ["pharmacy_id"])
    op.alter_column("appointment_settings", "slot_minutes", server_default=None)
    op.alter_column("appointment_settings", "buffer_minutes", server_default=None)
    op.alter_column("appointment_settings", "timezone", server_default=None)
    op.alter_column("appointment_settings", "weekly_hours_json", server_default=None)
    op.alter_column("appointment_settings", "created_at", server_default=None)
    op.alter_column("appointment_settings", "updated_at", server_default=None)

    op.create_table(
        "appointment_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("old_values_json", sa.Text(), nullable=True),
        sa.Column("new_values_json", sa.Text(), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_appointment_audits_appointment_id", "appointment_audits", ["appointment_id"])

    op.create_table(
        "appointment_reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("channel", sa.String(), nullable=False, server_default="EMAIL"),
        sa.Column("template", sa.String(), nullable=False, server_default="24h"),
        sa.Column("send_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_appointment_reminders_appointment_id", "appointment_reminders", ["appointment_id"])
    op.create_index("ix_appointment_reminders_send_at", "appointment_reminders", ["send_at"])
    op.alter_column("appointment_reminders", "channel", server_default=None)
    op.alter_column("appointment_reminders", "template", server_default=None)
    op.alter_column("appointment_reminders", "status", server_default=None)
    op.alter_column("appointment_reminders", "created_at", server_default=None)
    op.alter_column("appointment_reminders", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_appointment_reminders_send_at", table_name="appointment_reminders")
    op.drop_index("ix_appointment_reminders_appointment_id", table_name="appointment_reminders")
    op.drop_table("appointment_reminders")

    op.drop_index("ix_appointment_audits_appointment_id", table_name="appointment_audits")
    op.drop_table("appointment_audits")

    op.drop_index("ix_appointment_settings_pharmacy_id", table_name="appointment_settings")
    op.drop_table("appointment_settings")

    op.drop_column("appointments", "no_show_marked_at")
    op.drop_column("appointments", "no_show")
    op.drop_column("appointments", "customer_email")
