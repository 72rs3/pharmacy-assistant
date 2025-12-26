from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db import Base
from app.ai.types import Embedding


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    # Spec-aligned fields
    status = Column(String, default="PENDING", nullable=False)
    branding_details = Column(Text, nullable=True)
    operating_hours = Column(String, nullable=True)
    support_cod = Column(Boolean, default=True, nullable=False)

    # Theme / branding tokens (per-tenant UI customization)
    logo_url = Column(String, nullable=True)
    hero_image_url = Column(String, nullable=True)
    primary_color = Column(String, nullable=True)  # hex, e.g. #7CB342
    primary_color_600 = Column(String, nullable=True)  # hex, e.g. #689F38
    accent_color = Column(String, nullable=True)  # hex, e.g. #3b82f6
    font_family = Column(String, nullable=True)
    theme_preset = Column(String, nullable=True)
    storefront_layout = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    contact_address = Column(Text, nullable=True)

    # Implementation-specific fields
    domain = Column(String, unique=True, index=True, nullable=True)  # for future subdomains
    is_active = Column(Boolean, default=False, nullable=False)

    owners = relationship("User", back_populates="pharmacy")
    medicines = relationship("Medicine", back_populates="pharmacy")
    orders = relationship("Order", back_populates="pharmacy")
    appointments = relationship("Appointment", back_populates="pharmacy")
    ai_interactions = relationship("AIInteraction", back_populates="pharmacy")
    ai_logs = relationship("AILog", back_populates="pharmacy")


class User(Base):
    """
    Represents both global admins and pharmacy owners.
    Admins have is_admin=True with no pharmacy_id.
    Owners link to a Pharmacy via pharmacy_id.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # Spec-aligned fields
    username = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)
    role = Column(String, default="OWNER", nullable=False)
    contact_info = Column(Text, nullable=True)

    # Existing fields kept for compatibility with current auth flows
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)

    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=True)
    pharmacy = relationship("Pharmacy", back_populates="owners")

    reviewed_prescriptions = relationship("Prescription", back_populates="reviewer")
    handled_ai_interactions = relationship(
        "AIInteraction",
        back_populates="owner",
        foreign_keys="AIInteraction.owner_id",
    )


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    category = Column(String, index=True, nullable=True)
    price = Column(Float, nullable=False)
    stock_level = Column(Integer, nullable=False, default=0)
    expiry_date = Column(Date, nullable=True)
    prescription_required = Column(Boolean, default=False, nullable=False)
    dosage = Column(String, nullable=True)
    side_effects = Column(Text, nullable=True)

    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    pharmacy = relationship("Pharmacy", back_populates="medicines")

    order_items = relationship("OrderItem", back_populates="medicine")
    prescription_medicines = relationship("PrescriptionMedicine", back_populates="medicine")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    category = Column(String, index=True, nullable=True)
    price = Column(Float, nullable=False)
    stock_level = Column(Integer, nullable=False, default=0)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)

    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    pharmacy = relationship("Pharmacy")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    customer_address = Column(Text, nullable=True)
    customer_notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="PENDING")
    payment_method = Column(String, nullable=False, default="COD")
    payment_status = Column(String, nullable=False, default="UNPAID")
    delivery_person_id = Column(String, nullable=True)
    order_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    pharmacy = relationship("Pharmacy", back_populates="orders")

    items = relationship("OrderItem", back_populates="order")
    prescriptions = relationship("Prescription", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)

    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    order = relationship("Order", back_populates="items")

    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=True)
    medicine = relationship("Medicine", back_populates="order_items")

    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product = relationship("Product")


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    content_type = Column(String, nullable=True)
    status = Column(String, nullable=False, default="PENDING")
    upload_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Draft prescriptions are uploaded before the order is created and then attached later.
    draft_token = Column(String, unique=True, index=True, nullable=True)

    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    pharmacy = relationship("Pharmacy")

    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    order = relationship("Order", back_populates="prescriptions")

    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer = relationship("User", back_populates="reviewed_prescriptions")

    medicines = relationship("PrescriptionMedicine", back_populates="prescription")


class PrescriptionMedicine(Base):
    __tablename__ = "prescription_medicines"

    id = Column(Integer, primary_key=True, index=True)
    dosage = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)

    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=False)
    prescription = relationship("Prescription", back_populates="medicines")

    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    medicine = relationship("Medicine", back_populates="prescription_medicines")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    type = Column(String, nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    vaccine_name = Column(String, nullable=True)

    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    pharmacy = relationship("Pharmacy", back_populates="appointments")


class AIInteraction(Base):
    __tablename__ = "ai_interactions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String, nullable=False, index=True)
    customer_query = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=False)
    escalated_to_human = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    owner_reply = Column(Text, nullable=True)
    owner_replied_at = Column(DateTime, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    pharmacy = relationship("Pharmacy", back_populates="ai_interactions")
    owner = relationship(
        "User",
        back_populates="handled_ai_interactions",
        foreign_keys=[owner_id],
    )


class AILog(Base):
    __tablename__ = "ai_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    log_type = Column(String, nullable=False)
    details = Column(Text, nullable=False)

    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    pharmacy = relationship("Pharmacy", back_populates="ai_logs")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # medicine / pharmacy / faq / upload
    source_key = Column(String, nullable=True)  # e.g. medicine:{id}
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False, index=True)

    chunks = relationship("DocumentChunk", back_populates="document")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    # Default matches `text-embedding-3-small` output dimension.
    embedding = Column(Embedding(1536), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False, index=True)

    document = relationship("Document", back_populates="chunks")
