"""Customer order, prescription, and appointment details.

Revision ID: 2b3c4d5e6f70
Revises: 1a2b3c4d5e6f
Create Date: 2025-12-20
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2b3c4d5e6f70"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("customer_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("customer_phone", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("customer_address", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("customer_notes", sa.Text(), nullable=True))

    with op.batch_alter_table("prescriptions") as batch_op:
        batch_op.add_column(sa.Column("original_filename", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("content_type", sa.String(), nullable=True))

    with op.batch_alter_table("appointments") as batch_op:
        batch_op.add_column(sa.Column("customer_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("customer_phone", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.drop_column("customer_phone")
        batch_op.drop_column("customer_name")

    with op.batch_alter_table("prescriptions") as batch_op:
        batch_op.drop_column("content_type")
        batch_op.drop_column("original_filename")

    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("customer_notes")
        batch_op.drop_column("customer_address")
        batch_op.drop_column("customer_phone")
        batch_op.drop_column("customer_name")

