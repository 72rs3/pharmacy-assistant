from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# --------------------
# Pharmacy
# --------------------


class PharmacyBase(BaseModel):
    name: str
    status: str = "PENDING"
    branding_details: Optional[str] = None
    operating_hours: Optional[str] = None
    support_cod: bool = True
    logo_url: Optional[str] = None
    hero_image_url: Optional[str] = None
    primary_color: Optional[str] = None
    primary_color_600: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: Optional[str] = None
    theme_preset: Optional[str] = None
    storefront_layout: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_address: Optional[str] = None


class PharmacyCreate(PharmacyBase):
    # domain is optional – may be configured later
    domain: Optional[str] = None


class Pharmacy(PharmacyBase):
    id: int
    domain: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class PharmacyUpdate(BaseModel):
    branding_details: Optional[str] = None
    operating_hours: Optional[str] = None
    support_cod: Optional[bool] = None
    logo_url: Optional[str] = None
    hero_image_url: Optional[str] = None
    primary_color: Optional[str] = None
    primary_color_600: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: Optional[str] = None
    theme_preset: Optional[str] = None
    storefront_layout: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_address: Optional[str] = None


# --------------------
# Medicine
# --------------------


class MedicineBase(BaseModel):
    name: str
    category: Optional[str] = None
    price: float
    stock_level: int
    expiry_date: Optional[date] = None
    prescription_required: bool = False
    dosage: Optional[str] = None
    side_effects: Optional[str] = None


class MedicineCreate(MedicineBase):
    pharmacy_id: Optional[int] = None


class MedicineUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock_level: Optional[int] = None
    expiry_date: Optional[date] = None
    prescription_required: Optional[bool] = None
    dosage: Optional[str] = None
    side_effects: Optional[str] = None


class MedicineStockIn(BaseModel):
    quantity_delta: int
    expiry_date: Optional[date] = None


class MedicineBulkItem(BaseModel):
    name: str
    dosage: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock_delta: int = 0
    expiry_date: Optional[date] = None
    prescription_required: Optional[bool] = None
    side_effects: Optional[str] = None


class MedicineBulkImportIn(BaseModel):
    items: list[MedicineBulkItem]
    update_fields: bool = False


class MedicineBulkImportError(BaseModel):
    row: int
    message: str


class MedicineBulkImportOut(BaseModel):
    created: int
    updated: int
    stock_in: int
    errors: list[MedicineBulkImportError] = []


class Medicine(MedicineBase):
    id: int
    pharmacy_id: int

    model_config = ConfigDict(from_attributes=True)


# --------------------
# Product (Shop)
# --------------------


class ProductBase(BaseModel):
    name: str
    category: Optional[str] = None
    price: float
    stock_level: int
    description: Optional[str] = None
    image_url: Optional[str] = None


class ProductCreate(ProductBase):
    pharmacy_id: Optional[int] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock_level: Optional[int] = None
    description: Optional[str] = None
    image_url: Optional[str] = None


class Product(ProductBase):
    id: int
    pharmacy_id: int

    model_config = ConfigDict(from_attributes=True)


class ProductBulkItem(BaseModel):
    name: str
    category: Optional[str] = None
    price: Optional[float] = None
    stock_level: Optional[int] = None
    description: Optional[str] = None
    image_url: Optional[str] = None


class ProductBulkImportIn(BaseModel):
    items: list[ProductBulkItem]
    update_fields: bool = False


class ProductBulkImportError(BaseModel):
    row: int
    message: str


class ProductBulkImportOut(BaseModel):
    created: int
    updated: int
    errors: list[ProductBulkImportError] = []


# --------------------
# Orders
# --------------------


class OrderItemBase(BaseModel):
    medicine_id: int | None = None
    product_id: int | None = None
    quantity: int
    unit_price: float


class OrderItemCreate(OrderItemBase):
    order_id: Optional[int] = None


class OrderItem(OrderItemBase):
    id: int
    order_id: int

    model_config = ConfigDict(from_attributes=True)


class OrderBase(BaseModel):
    customer_id: str
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_address: str | None = None
    customer_notes: str | None = None
    status: str = "PENDING"
    payment_method: str = "COD"
    payment_status: str = "UNPAID"
    delivery_person_id: Optional[str] = None


class OrderCreate(OrderBase):
    pharmacy_id: int
    items: List[OrderItemBase]


class Order(OrderBase):
    id: int
    pharmacy_id: int
    order_date: datetime | None = None
    items: List[OrderItem] = []

    model_config = ConfigDict(from_attributes=True)


class CustomerOrderItemCreate(BaseModel):
    medicine_id: int | None = None
    product_id: int | None = None
    quantity: int


class CustomerOrderCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_address: str
    customer_notes: str | None = None
    items: List[CustomerOrderItemCreate]
    draft_prescription_tokens: list[str] | None = None


class CustomerRxOrderCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_address: str
    customer_notes: str | None = None
    medicine_id: int
    quantity: int = 1
    draft_prescription_tokens: list[str]


class CustomerOrderCreated(BaseModel):
    order_id: int
    tracking_code: str
    status: str
    payment_method: str
    payment_status: str
    order_date: datetime
    requires_prescription: bool


class CustomerOrderSummary(BaseModel):
    id: int
    status: str
    payment_method: str
    payment_status: str
    order_date: datetime

    model_config = ConfigDict(from_attributes=True)


# --------------------
# Prescriptions
# --------------------


class PrescriptionMedicineBase(BaseModel):
    medicine_id: int
    dosage: Optional[str] = None
    quantity: int
    notes: Optional[str] = None


class PrescriptionMedicineCreate(PrescriptionMedicineBase):
    prescription_id: Optional[int] = None


class PrescriptionMedicine(PrescriptionMedicineBase):
    id: int
    prescription_id: int

    model_config = ConfigDict(from_attributes=True)


class PrescriptionBase(BaseModel):
    file_path: str
    status: str = "PENDING"


class PrescriptionCreate(PrescriptionBase):
    order_id: int
    reviewer_id: Optional[int] = None
    medicines: List[PrescriptionMedicineBase] = []


class Prescription(PrescriptionBase):
    id: int
    order_id: int
    reviewer_id: Optional[int] = None
    original_filename: Optional[str] = None
    content_type: Optional[str] = None
    medicines: List[PrescriptionMedicine] = []
    upload_date: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PrescriptionStatusOut(BaseModel):
    id: int
    status: str
    upload_date: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PrescriptionDraftOut(BaseModel):
    id: int
    draft_token: str
    status: str
    upload_date: datetime | None = None
    original_filename: str | None = None
    content_type: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PrescriptionReviewIn(BaseModel):
    status: str  # APPROVED / REJECTED


class AppointmentStatusIn(BaseModel):
    status: str  # PENDING / CONFIRMED / CANCELLED / COMPLETED


# --------------------
# Appointments
# --------------------


class AppointmentBase(BaseModel):
    customer_id: str
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    type: str
    scheduled_time: datetime
    status: str = "PENDING"
    vaccine_name: Optional[str] = None
    no_show: bool = False
    no_show_marked_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AppointmentCreate(AppointmentBase):
    pharmacy_id: int


class Appointment(AppointmentBase):
    id: int
    pharmacy_id: int

    model_config = ConfigDict(from_attributes=True)


class CustomerAppointmentCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    type: str
    scheduled_time: datetime
    vaccine_name: str | None = None


class CustomerAppointmentOut(BaseModel):
    id: int
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    type: str
    scheduled_time: datetime
    status: str
    vaccine_name: str | None = None
    no_show: bool = False
    no_show_marked_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CustomerAppointmentCreated(CustomerAppointmentOut):
    tracking_code: str


class AppointmentUpdateIn(BaseModel):
    status: str | None = None  # PENDING / CONFIRMED / CANCELLED / COMPLETED
    scheduled_time: datetime | None = None


class AppointmentSettingsBase(BaseModel):
    slot_minutes: int = 15
    buffer_minutes: int = 0
    timezone: str = "UTC"
    weekly_hours_json: str = "{}"
    no_show_minutes: int = 30
    locale: str = "en"


class AppointmentSettingsUpdate(AppointmentSettingsBase):
    pass


class AppointmentSettings(AppointmentSettingsBase):
    id: int
    pharmacy_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentAudit(BaseModel):
    id: int
    appointment_id: int
    action: str
    old_values_json: str | None = None
    new_values_json: str | None = None
    changed_by_user_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentReminder(BaseModel):
    id: int
    appointment_id: int
    channel: str
    template: str
    send_at: datetime
    sent_at: datetime | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentPublicUpdate(BaseModel):
    scheduled_time: datetime | None = None
    cancel: bool = False


class AppointmentReminderPreviewOut(BaseModel):
    subject: str
    html: str


# --------------------
# AI Interaction & Logs
# --------------------


class AIInteractionBase(BaseModel):
    customer_id: str | None = None
    customer_query: str
    ai_response: str
    confidence_score: float
    escalated_to_human: bool = False
    created_at: datetime | None = None
    owner_reply: str | None = None
    owner_replied_at: datetime | None = None
    owner_id: int | None = None


class AIInteractionCreate(AIInteractionBase):
    pharmacy_id: int


class AIInteraction(AIInteractionBase):
    id: int
    pharmacy_id: int

    model_config = ConfigDict(from_attributes=True)


class AILogBase(BaseModel):
    log_type: str
    details: str


class AILogCreate(AILogBase):
    pharmacy_id: int


class AILog(AILogBase):
    id: int
    pharmacy_id: int

    model_config = ConfigDict(from_attributes=True)


# --------------------
# AI Chat (API)
# --------------------


class AIChatIn(BaseModel):
    message: str
    session_id: str | None = None


class AICitation(BaseModel):
    source_type: str
    title: str
    doc_id: int
    chunk_id: int
    preview: str
    last_updated_at: datetime | None = None
    score: float | None = None


class AIAction(BaseModel):
    type: str  # add_to_cart | upload_prescription | request_notify
    label: str | None = None
    medicine_id: int | None = None
    payload: dict | None = None


class MedicineCard(BaseModel):
    medicine_id: int
    name: str
    dosage: str | None = None
    category: str | None = None
    rx: bool
    price: float | None = None
    stock: int
    updated_at: datetime | None = None
    indexed_at: datetime | None = None


class AIChatOut(BaseModel):
    interaction_id: int
    customer_id: str
    session_id: str
    answer: str
    citations: list[AICitation] = []
    cards: list[MedicineCard] = []
    actions: list[AIAction] = []
    quick_replies: list[str] = []
    confidence_score: float
    escalated_to_human: bool
    intent: str
    created_at: datetime
    data_last_updated_at: datetime | None = None
    indexed_at: datetime | None = None
    system_message: str | None = None


class AIEscalationReplyIn(BaseModel):
    reply: str


class ChatMessageOut(BaseModel):
    id: int
    session_id: int
    sender_type: str
    text: str
    created_at: datetime
    meta: dict | None = Field(default=None, serialization_alias="metadata")

    model_config = ConfigDict(from_attributes=True)


class ChatSessionSummary(BaseModel):
    id: int
    session_id: str
    user_session_id: str
    status: str
    last_activity_at: datetime
    intake_data: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatSessionEscalateIn(BaseModel):
    customer_name: str
    customer_phone: str
    age_range: str
    main_concern: str
    how_long: str
    current_medications: str | None = None
    allergies: str | None = None


class ChatSessionReplyIn(BaseModel):
    text: str


class ChatSessionMessageIn(BaseModel):
    text: str
