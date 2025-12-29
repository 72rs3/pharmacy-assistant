"""medicine expiry date column.

Revision ID: 6f708192a3b4
Revises: 5e6f708192a3
Create Date: 2025-12-25
"""

from alembic import op
import sqlalchemy as sa


revision = "6f708192a3b4"
down_revision = "5e6f708192a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("medicines") as batch_op:
        batch_op.add_column(sa.Column("expiry_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("medicines") as batch_op:
        batch_op.drop_column("expiry_date")

