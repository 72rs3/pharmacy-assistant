from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.deps import require_approved_owner, require_pharmacy_owner
from app.db import get_db
from app.deps import get_active_public_pharmacy_id, get_current_pharmacy_id
from app.utils.validation import validate_e164_phone

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def _require_customer_tracking_code(
    tracking_code: str | None = Header(None, alias="X-Customer-ID"),
) -> str:
    if not tracking_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Customer-ID tracking code",
        )
    return tracking_code


@router.post("", response_model=schemas.CustomerAppointmentCreated)
def create_customer_appointment(
    payload: schemas.CustomerAppointmentCreate,
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
):
    tracking_code = secrets.token_urlsafe(12)
    appt = models.Appointment(
        customer_id=tracking_code,
        customer_name=payload.customer_name.strip(),
        customer_phone=validate_e164_phone(payload.customer_phone, "customer"),
        type=payload.type.strip(),
        scheduled_time=payload.scheduled_time,
        status="PENDING",
        vaccine_name=(payload.vaccine_name.strip() if payload.vaccine_name else None),
        pharmacy_id=tenant_pharmacy_id,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return schemas.CustomerAppointmentCreated(
        id=appt.id,
        type=appt.type,
        scheduled_time=appt.scheduled_time,
        status=appt.status,
        vaccine_name=appt.vaccine_name,
        tracking_code=tracking_code,
    )


@router.get("/my", response_model=list[schemas.CustomerAppointmentOut])
def list_customer_appointments(
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    tracking_code: str = Depends(_require_customer_tracking_code),
):
    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.pharmacy_id == tenant_pharmacy_id,
            models.Appointment.customer_id == tracking_code,
        )
        .order_by(models.Appointment.scheduled_time.desc())
        .all()
    )


@router.get("/owner", response_model=list[schemas.Appointment])
def list_owner_appointments(
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Appointment)
        .filter(models.Appointment.pharmacy_id == current_user.pharmacy_id)
        .order_by(models.Appointment.scheduled_time.desc())
        .all()
    )


@router.post("/{appointment_id}/status", response_model=schemas.Appointment)
def update_appointment_status(
    appointment_id: int,
    status_in: schemas.AppointmentStatusIn,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_current_pharmacy_id),
    _=Depends(require_pharmacy_owner),
):
    appointment = (
        db.query(models.Appointment)
        .filter(models.Appointment.id == appointment_id, models.Appointment.pharmacy_id == pharmacy_id)
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    if status_in.status not in {"PENDING", "CONFIRMED", "CANCELLED", "COMPLETED"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    appointment.status = status_in.status
    db.commit()
    db.refresh(appointment)
    return appointment


@router.patch("/{appointment_id}", response_model=schemas.Appointment)
def update_appointment(
    appointment_id: int,
    payload: schemas.AppointmentUpdateIn,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_current_pharmacy_id),
    _=Depends(require_pharmacy_owner),
):
    appointment = (
        db.query(models.Appointment)
        .filter(models.Appointment.id == appointment_id, models.Appointment.pharmacy_id == pharmacy_id)
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    data = payload.model_dump(exclude_unset=True)
    status_value = data.get("status")
    if status_value is not None:
        if status_value not in {"PENDING", "CONFIRMED", "CANCELLED", "COMPLETED"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
        appointment.status = status_value

    if "scheduled_time" in data and data["scheduled_time"] is not None:
        appointment.scheduled_time = data["scheduled_time"]

    db.commit()
    db.refresh(appointment)
    return appointment
