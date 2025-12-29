"""initial schema

Revision ID: 1a2b3c4d5e6f
Revises:
Create Date: 2025-12-17

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "1a2b3c4d5e6f"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pharmacies",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("branding_details", sa.Text(), nullable=True),
        sa.Column("operating_hours", sa.String(), nullable=True),
        sa.Column("support_cod", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_pharmacies_id", "pharmacies", ["id"])
    op.create_index("ix_pharmacies_name", "pharmacies", ["name"], unique=True)
    op.create_index("ix_pharmacies_domain", "pharmacies", ["domain"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False, server_default="OWNER"),
        sa.Column("contact_info", sa.Text(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=True),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "medicines",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("stock_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prescription_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dosage", sa.String(), nullable=True),
        sa.Column("side_effects", sa.Text(), nullable=True),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=False),
    )
    op.create_index("ix_medicines_id", "medicines", ["id"])
    op.create_index("ix_medicines_name", "medicines", ["name"])
    op.create_index("ix_medicines_category", "medicines", ["category"])
    op.create_index("ix_medicines_pharmacy_id", "medicines", ["pharmacy_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("payment_method", sa.String(), nullable=False, server_default="COD"),
        sa.Column("payment_status", sa.String(), nullable=False, server_default="UNPAID"),
        sa.Column("delivery_person_id", sa.String(), nullable=True),
        sa.Column("order_date", sa.DateTime(), nullable=False),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=False),
    )
    op.create_index("ix_orders_id", "orders", ["id"])
    op.create_index("ix_orders_pharmacy_id", "orders", ["pharmacy_id"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("medicine_id", sa.Integer(), sa.ForeignKey("medicines.id"), nullable=False),
    )
    op.create_index("ix_order_items_id", "order_items", ["id"])
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_medicine_id", "order_items", ["medicine_id"])

    op.create_table(
        "prescriptions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("upload_date", sa.DateTime(), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_prescriptions_id", "prescriptions", ["id"])
    op.create_index("ix_prescriptions_order_id", "prescriptions", ["order_id"])

    op.create_table(
        "prescription_medicines",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("dosage", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "prescription_id",
            sa.Integer(),
            sa.ForeignKey("prescriptions.id"),
            nullable=False,
        ),
        sa.Column(
            "medicine_id",
            sa.Integer(),
            sa.ForeignKey("medicines.id"),
            nullable=False,
        ),
    )
    op.create_index("ix_prescription_medicines_id", "prescription_medicines", ["id"])
    op.create_index(
        "ix_prescription_medicines_prescription_id",
        "prescription_medicines",
        ["prescription_id"],
    )
    op.create_index(
        "ix_prescription_medicines_medicine_id",
        "prescription_medicines",
        ["medicine_id"],
    )

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("scheduled_time", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("vaccine_name", sa.String(), nullable=True),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=False),
    )
    op.create_index("ix_appointments_id", "appointments", ["id"])
    op.create_index("ix_appointments_pharmacy_id", "appointments", ["pharmacy_id"])

    op.create_table(
        "ai_interactions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("customer_query", sa.Text(), nullable=False),
        sa.Column("ai_response", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column(
            "escalated_to_human",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=False),
    )
    op.create_index("ix_ai_interactions_id", "ai_interactions", ["id"])
    op.create_index("ix_ai_interactions_pharmacy_id", "ai_interactions", ["pharmacy_id"])

    op.create_table(
        "ai_logs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("log_type", sa.String(), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=False),
    )
    op.create_index("ix_ai_logs_id", "ai_logs", ["id"])
    op.create_index("ix_ai_logs_pharmacy_id", "ai_logs", ["pharmacy_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_logs_pharmacy_id", table_name="ai_logs")
    op.drop_index("ix_ai_logs_id", table_name="ai_logs")
    op.drop_table("ai_logs")

    op.drop_index("ix_ai_interactions_pharmacy_id", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_id", table_name="ai_interactions")
    op.drop_table("ai_interactions")

    op.drop_index("ix_appointments_pharmacy_id", table_name="appointments")
    op.drop_index("ix_appointments_id", table_name="appointments")
    op.drop_table("appointments")

    op.drop_index(
        "ix_prescription_medicines_medicine_id",
        table_name="prescription_medicines",
    )
    op.drop_index(
        "ix_prescription_medicines_prescription_id",
        table_name="prescription_medicines",
    )
    op.drop_index("ix_prescription_medicines_id", table_name="prescription_medicines")
    op.drop_table("prescription_medicines")

    op.drop_index("ix_prescriptions_order_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_id", table_name="prescriptions")
    op.drop_table("prescriptions")

    op.drop_index("ix_order_items_medicine_id", table_name="order_items")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_index("ix_order_items_id", table_name="order_items")
    op.drop_table("order_items")

    op.drop_index("ix_orders_pharmacy_id", table_name="orders")
    op.drop_index("ix_orders_id", table_name="orders")
    op.drop_table("orders")

    op.drop_index("ix_medicines_pharmacy_id", table_name="medicines")
    op.drop_index("ix_medicines_category", table_name="medicines")
    op.drop_index("ix_medicines_name", table_name="medicines")
    op.drop_index("ix_medicines_id", table_name="medicines")
    op.drop_table("medicines")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_pharmacies_domain", table_name="pharmacies")
    op.drop_index("ix_pharmacies_name", table_name="pharmacies")
    op.drop_index("ix_pharmacies_id", table_name="pharmacies")
    op.drop_table("pharmacies")

