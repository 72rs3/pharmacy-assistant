from __future__ import annotations

import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.deps import require_owner
from app.db import BACKEND_DIR, get_db
from app.deps import get_active_public_pharmacy_id

router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])

UPLOAD_DIR = Path(os.getenv("PRESCRIPTION_UPLOAD_DIR", BACKEND_DIR / "uploads" / "prescriptions"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _validate_order(db: Session, order_id: int, tenant_pharmacy_id: int) -> models.Order:
    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_id, models.Order.pharmacy_id == tenant_pharmacy_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.post("/upload", response_model=schemas.PrescriptionStatusOut)
async def upload_prescription(
    order_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
):
    _validate_order(db, order_id, tenant_pharmacy_id)

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file")

    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    dest = UPLOAD_DIR / safe_name
    content = await file.read()
    dest.write_bytes(content)

    prescription = models.Prescription(
        file_path=str(dest),
        original_filename=file.filename,
        content_type=file.content_type,
        status="PENDING",
        order_id=order_id,
    )
    db.add(prescription)
    db.commit()
    db.refresh(prescription)
    return schemas.PrescriptionStatusOut.model_validate(prescription)


@router.get("/owner", response_model=List[schemas.Prescription])
def list_prescriptions_owner(
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Prescription)
        .join(models.Order, models.Prescription.order_id == models.Order.id)
        .filter(models.Order.pharmacy_id == current_user.pharmacy_id)
        .order_by(models.Prescription.upload_date.desc())
        .all()
    )


@router.post("/{prescription_id}/review", response_model=schemas.Prescription)
def review_prescription(
    prescription_id: int,
    review: schemas.PrescriptionReviewIn,
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    prescription = (
        db.query(models.Prescription)
        .join(models.Order, models.Prescription.order_id == models.Order.id)
        .filter(
            models.Prescription.id == prescription_id,
            models.Order.pharmacy_id == current_user.pharmacy_id,
        )
        .first()
    )
    if not prescription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")

    if review.status not in {"APPROVED", "REJECTED"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")

    prescription.status = review.status
    prescription.reviewer_id = current_user.id
    db.commit()
    db.refresh(prescription)
    return prescription
