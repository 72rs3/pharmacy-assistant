from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# --------------------
# Pharmacy
# --------------------


class PharmacyBase(BaseModel):
    name: str
    status: str = "PENDING"
    branding_details: Optional[str] = None
    operating_hours: Optional[str] = None
    support_cod: bool = True


class PharmacyCreate(PharmacyBase):
    # domain is optional – may be configured later
    domain: Optional[str] = None


class Pharmacy(PharmacyBase):
    id: int
    domain: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# --------------------
# Medicine
# --------------------


class MedicineBase(BaseModel):
    name: str
    category: Optional[str] = None
    price: float
    stock_level: int
    prescription_required: bool = False
    dosage: Optional[str] = None
    side_effects: Optional[str] = None


class MedicineCreate(MedicineBase):
    pharmacy_id: Optional[int] = None


class Medicine(MedicineBase):
    id: int
    pharmacy_id: int

    model_config = ConfigDict(from_attributes=True)


# --------------------
# Orders
# --------------------


class OrderItemBase(BaseModel):
    medicine_id: int
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
    medicine_id: int
    quantity: int


class CustomerOrderCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_address: str
    customer_notes: str | None = None
    items: List[CustomerOrderItemCreate]


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


class PrescriptionReviewIn(BaseModel):
    status: str  # APPROVED / REJECTED


# --------------------
# Appointments
# --------------------


class AppointmentBase(BaseModel):
    customer_id: str
    type: str
    scheduled_time: datetime
    status: str = "PENDING"
    vaccine_name: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    pharmacy_id: int


class Appointment(AppointmentBase):
    id: int
    pharmacy_id: int

    model_config = ConfigDict(from_attributes=True)


class CustomerAppointmentCreate(BaseModel):
    customer_name: str
    customer_phone: str
    type: str
    scheduled_time: datetime
    vaccine_name: str | None = None


class CustomerAppointmentOut(BaseModel):
    id: int
    type: str
    scheduled_time: datetime
    status: str
    vaccine_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CustomerAppointmentCreated(CustomerAppointmentOut):
    tracking_code: str


# --------------------
# AI Interaction & Logs
# --------------------


class AIInteractionBase(BaseModel):
    customer_query: str
    ai_response: str
    confidence_score: float
    escalated_to_human: bool = False


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
