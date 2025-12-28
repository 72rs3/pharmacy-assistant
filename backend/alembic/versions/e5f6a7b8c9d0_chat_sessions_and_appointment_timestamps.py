"""Add chat sessions and appointment timestamps."""

from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.alter_column("appointments", "updated_at", server_default=None)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("turns_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_sessions_pharmacy_id", "chat_sessions", ["pharmacy_id"])
    op.create_index("ix_chat_sessions_session_id", "chat_sessions", ["session_id"])
    op.create_index("ix_chat_sessions_expires_at", "chat_sessions", ["expires_at"])
    op.create_index("ix_chat_sessions_id", "chat_sessions", ["id"])
    op.alter_column("chat_sessions", "turns_json", server_default=None)
    op.alter_column("chat_sessions", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_id", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_expires_at", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_session_id", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_pharmacy_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_column("appointments", "updated_at")
