"""AI chat escalation fields.

Revision ID: 3c4d5e6f7081
Revises: 2b3c4d5e6f70
Create Date: 2025-12-21
"""

from alembic import op
import sqlalchemy as sa


revision = "3c4d5e6f7081"
down_revision = "2b3c4d5e6f70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_interactions") as batch_op:
        batch_op.add_column(sa.Column("customer_id", sa.String(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch_op.add_column(sa.Column("owner_reply", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("owner_replied_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_ai_interactions_customer_id", ["customer_id"])

    with op.batch_alter_table("ai_interactions") as batch_op:
        batch_op.alter_column("customer_id", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("ai_interactions") as batch_op:
        batch_op.drop_index("ix_ai_interactions_customer_id")
        batch_op.drop_column("owner_id")
        batch_op.drop_column("owner_replied_at")
        batch_op.drop_column("owner_reply")
        batch_op.drop_column("created_at")
        batch_op.drop_column("customer_id")

