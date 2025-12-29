"""Products catalog + order items support product_id.

Revision ID: 708192a3b4c5
Revises: 6f708192a3b4
Create Date: 2025-12-25
"""

from alembic import op
import sqlalchemy as sa


revision = "708192a3b4c5"
down_revision = "6f708192a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("stock_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=False),
    )
    op.create_index("ix_products_id", "products", ["id"])
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_pharmacy_id", "products", ["pharmacy_id"])

    with op.batch_alter_table("order_items") as batch_op:
        batch_op.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        batch_op.alter_column("medicine_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_foreign_key("fk_order_items_product_id_products", "products", ["product_id"], ["id"])
        batch_op.create_index("ix_order_items_product_id", ["product_id"])


def downgrade() -> None:
    with op.batch_alter_table("order_items") as batch_op:
        batch_op.drop_index("ix_order_items_product_id")
        batch_op.drop_constraint("fk_order_items_product_id_products", type_="foreignkey")
        batch_op.drop_column("product_id")
        batch_op.alter_column("medicine_id", existing_type=sa.Integer(), nullable=False)

    op.drop_index("ix_products_pharmacy_id", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_index("ix_products_id", table_name="products")
    op.drop_table("products")

