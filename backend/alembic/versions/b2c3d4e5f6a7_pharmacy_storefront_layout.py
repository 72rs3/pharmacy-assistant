"""pharmacy storefront layout.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-12-26
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pharmacies", sa.Column("storefront_layout", sa.String(), nullable=True))
    op.add_column("pharmacies", sa.Column("contact_email", sa.String(), nullable=True))
    op.add_column("pharmacies", sa.Column("contact_phone", sa.String(), nullable=True))
    op.add_column("pharmacies", sa.Column("contact_address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pharmacies", "contact_address")
    op.drop_column("pharmacies", "contact_phone")
    op.drop_column("pharmacies", "contact_email")
    op.drop_column("pharmacies", "storefront_layout")
