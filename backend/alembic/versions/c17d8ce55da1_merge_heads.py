"""merge heads

Revision ID: c17d8ce55da1
Revises: cc3d4e5f6a7b, f9c0d1e2f3a4
Create Date: 2026-01-06 20:11:42.098802

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'c17d8ce55da1'
down_revision = ('cc3d4e5f6a7b', 'f9c0d1e2f3a4')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

