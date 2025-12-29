"""Add RAG freshness fields."""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("data_updated_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "document_chunks",
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "products",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.alter_column("documents", "version", server_default=None)
    op.alter_column("document_chunks", "version", server_default=None)
    op.alter_column("products", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_column("products", "updated_at")
    op.drop_column("document_chunks", "version")
    op.drop_column("document_chunks", "indexed_at")
    op.drop_column("documents", "version")
    op.drop_column("documents", "indexed_at")
    op.drop_column("documents", "data_updated_at")
