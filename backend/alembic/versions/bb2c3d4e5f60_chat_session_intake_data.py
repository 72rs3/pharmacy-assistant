"""Add intake_data to chat sessions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "bb2c3d4e5f60"
down_revision = "aa1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_sessions", sa.Column("intake_data", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_sessions", "intake_data")

