"""Prescription drafts for pre-order uploads.

Revision ID: 8192a3b4c5d6
Revises: 708192a3b4c5
Create Date: 2025-12-25
"""

from alembic import op
import sqlalchemy as sa


revision = "8192a3b4c5d6"
down_revision = "708192a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prescriptions") as batch_op:
        batch_op.add_column(sa.Column("draft_token", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("pharmacy_id", sa.Integer(), nullable=True))
        batch_op.alter_column("order_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_index("ix_prescriptions_draft_token", ["draft_token"], unique=True)
        batch_op.create_index("ix_prescriptions_pharmacy_id", ["pharmacy_id"])
        batch_op.create_foreign_key("fk_prescriptions_pharmacy_id_pharmacies", "pharmacies", ["pharmacy_id"], ["id"])

    # Backfill pharmacy_id for existing prescriptions from their orders.
    op.execute(
        """
        UPDATE prescriptions p
        SET pharmacy_id = o.pharmacy_id
        FROM orders o
        WHERE p.order_id = o.id AND p.pharmacy_id IS NULL
        """
    )

    with op.batch_alter_table("prescriptions") as batch_op:
        batch_op.alter_column("pharmacy_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("prescriptions") as batch_op:
        batch_op.alter_column("pharmacy_id", existing_type=sa.Integer(), nullable=True)
        batch_op.drop_constraint("fk_prescriptions_pharmacy_id_pharmacies", type_="foreignkey")
        batch_op.drop_index("ix_prescriptions_pharmacy_id")
        batch_op.drop_index("ix_prescriptions_draft_token")
        batch_op.drop_column("pharmacy_id")
        batch_op.drop_column("draft_token")
        batch_op.alter_column("order_id", existing_type=sa.Integer(), nullable=False)

