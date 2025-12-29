"""Add updated_at fields for citations."""

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pharmacies",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "medicines",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "documents",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "document_chunks",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.alter_column("pharmacies", "updated_at", server_default=None)
    op.alter_column("medicines", "updated_at", server_default=None)
    op.alter_column("documents", "updated_at", server_default=None)
    op.alter_column("document_chunks", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_column("document_chunks", "updated_at")
    op.drop_column("documents", "updated_at")
    op.drop_column("medicines", "updated_at")
    op.drop_column("pharmacies", "updated_at")
