"""Add chat sessions metadata and chat messages table."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "aa1b2c3d4e5f"
down_revision = "f8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(sa.Column("user_session_id", sa.String(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"))
        batch_op.add_column(sa.Column("last_activity_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
        batch_op.create_index("ix_chat_sessions_user_session_id", ["user_session_id"])
        batch_op.create_index("ix_chat_sessions_status", ["status"])

    op.execute("UPDATE chat_sessions SET last_activity_at = COALESCE(updated_at, NOW())")

    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.alter_column("user_session_id", server_default=None)
        batch_op.alter_column("status", server_default=None)
        batch_op.alter_column("last_activity_at", server_default=None)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id"), nullable=False),
        sa.Column("sender_type", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_chat_messages_id", "chat_messages", ["id"])
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])
    op.alter_column("chat_messages", "created_at", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_index("ix_chat_sessions_status")
        batch_op.drop_index("ix_chat_sessions_user_session_id")
        batch_op.drop_column("last_activity_at")
        batch_op.drop_column("status")
        batch_op.drop_column("user_session_id")

