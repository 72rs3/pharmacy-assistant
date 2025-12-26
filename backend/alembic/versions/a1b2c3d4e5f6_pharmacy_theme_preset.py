"""pharmacy theme preset.

Revision ID: a1b2c3d4e5f6
Revises: 8192a3b4c5d6
Create Date: 2025-12-26
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "8192a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pharmacies", sa.Column("theme_preset", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("pharmacies", "theme_preset")
