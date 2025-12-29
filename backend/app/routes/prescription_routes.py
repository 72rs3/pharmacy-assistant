from __future__ import annotations

import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.deps import require_approved_owner
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


def _write_upload(file: UploadFile, *, token: str) -> Path:
    original = file.filename or "upload"
    safe_name = original.replace("/", "_").replace("\\", "_")
    dest = UPLOAD_DIR / f"{token}_{safe_name}"
    return dest


def _is_allowed_file(file: UploadFile) -> bool:
    ctype = (file.content_type or "").lower()
    if ctype.startswith("image/"):
        return True
    if ctype == "application/pdf":
        return True
    # Fallback to extension checks when the browser doesn't send a content type.
    name = (file.filename or "").lower()
    return name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf"))


@router.post("/draft", response_model=list[schemas.PrescriptionDraftOut])
async def upload_prescription_draft(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
):
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

    created: list[models.Prescription] = []
    for file in files:
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file")
        if not _is_allowed_file(file):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only images and PDF files are supported",
            )
        token = secrets.token_urlsafe(16)
        dest = _write_upload(file, token=token)
        content = await file.read()
        dest.write_bytes(content)

        created.append(
            models.Prescription(
                file_path=str(dest),
                original_filename=file.filename,
                content_type=file.content_type,
                status="DRAFT",
                draft_token=token,
                pharmacy_id=tenant_pharmacy_id,
                order_id=None,
            )
        )

    for item in created:
        db.add(item)
    db.add(
        models.AILog(
            log_type="action_executed",
            details=f"action=upload_prescription_draft files={len(created)}",
            pharmacy_id=tenant_pharmacy_id,
            timestamp=datetime.utcnow(),
        )
    )
    db.commit()
    for item in created:
        db.refresh(item)
    return [schemas.PrescriptionDraftOut.model_validate(item) for item in created]


@router.post("/upload", response_model=list[schemas.PrescriptionStatusOut])
async def upload_prescription(
    order_id: int = Form(...),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
):
    _validate_order(db, order_id, tenant_pharmacy_id)
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

    created: list[models.Prescription] = []
    for file in files:
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file")
        if not _is_allowed_file(file):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only images and PDF files are supported",
            )
        token = secrets.token_urlsafe(16)
        dest = _write_upload(file, token=token)
        content = await file.read()
        dest.write_bytes(content)
        created.append(
            models.Prescription(
                file_path=str(dest),
                original_filename=file.filename,
                content_type=file.content_type,
                status="PENDING",
                draft_token=None,
                pharmacy_id=tenant_pharmacy_id,
                order_id=order_id,
            )
        )

    for item in created:
        db.add(item)
    db.add(
        models.AILog(
            log_type="action_executed",
            details=f"action=upload_prescription order_id={int(order_id)} files={len(created)}",
            pharmacy_id=tenant_pharmacy_id,
            timestamp=datetime.utcnow(),
        )
    )
    db.commit()
    for item in created:
        db.refresh(item)
    return [schemas.PrescriptionStatusOut.model_validate(item) for item in created]


@router.get("/owner", response_model=List[schemas.Prescription])
def list_prescriptions_owner(
    current_user: models.User = Depends(require_approved_owner),
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
    current_user: models.User = Depends(require_approved_owner),
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
    db.add(
        models.AILog(
            log_type="action_executed",
            details=f"action=review_prescription prescription_id={int(prescription_id)} status={review.status}",
            pharmacy_id=current_user.pharmacy_id,
            timestamp=datetime.utcnow(),
        )
    )
    db.commit()
    db.refresh(prescription)
    return prescription


@router.get("/owner/{prescription_id}/file")
def download_prescription_file(
    prescription_id: int,
    current_user: models.User = Depends(require_approved_owner),
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

    file_path = Path(prescription.file_path or "")
    try:
        resolved = file_path.resolve(strict=True)
        upload_root = UPLOAD_DIR.resolve(strict=False)
        if upload_root not in resolved.parents and resolved != upload_root:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from exc

    filename = prescription.original_filename or resolved.name
    media_type = prescription.content_type or "application/octet-stream"
    return FileResponse(path=str(resolved), media_type=media_type, filename=filename)
