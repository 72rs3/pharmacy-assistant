"""cart items

Revision ID: f9c0d1e2f3a4
Revises: f8b9c0d1e2f3
Create Date: 2026-01-03 11:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f9c0d1e2f3a4"
down_revision = "f8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cart_items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("pharmacy_id", sa.Integer(), nullable=False),
        sa.Column("medicine_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["medicine_id"], ["medicines.id"]),
        sa.ForeignKeyConstraint(["pharmacy_id"], ["pharmacies.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    )
    op.create_index("ix_cart_items_id", "cart_items", ["id"])
    op.create_index("ix_cart_items_session_id", "cart_items", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_cart_items_session_id", table_name="cart_items")
    op.drop_index("ix_cart_items_id", table_name="cart_items")
    op.drop_table("cart_items")
