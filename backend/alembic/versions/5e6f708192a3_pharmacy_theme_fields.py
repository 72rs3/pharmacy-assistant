"""pharmacy theme fields.

Revision ID: 5e6f708192a3
Revises: 4d5e6f708192
Create Date: 2025-12-24
"""

from alembic import op
import sqlalchemy as sa


revision = "5e6f708192a3"
down_revision = "4d5e6f708192"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pharmacies", sa.Column("logo_url", sa.String(), nullable=True))
    op.add_column("pharmacies", sa.Column("hero_image_url", sa.String(), nullable=True))
    op.add_column("pharmacies", sa.Column("primary_color", sa.String(), nullable=True))
    op.add_column("pharmacies", sa.Column("primary_color_600", sa.String(), nullable=True))
    op.add_column("pharmacies", sa.Column("accent_color", sa.String(), nullable=True))
    op.add_column("pharmacies", sa.Column("font_family", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("pharmacies", "font_family")
    op.drop_column("pharmacies", "accent_color")
    op.drop_column("pharmacies", "primary_color_600")
    op.drop_column("pharmacies", "primary_color")
    op.drop_column("pharmacies", "hero_image_url")
    op.drop_column("pharmacies", "logo_url")
