from __future__ import annotations

import os
import secrets
from datetime import datetime
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.deps import require_approved_owner
from app.db import get_db
from app.deps import get_active_public_pharmacy_id
from app.utils.file_storage import load_prescription_file, save_prescription_upload

router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])

MAX_UPLOAD_BYTES = int(os.getenv("PRESCRIPTION_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"}


def _validate_order(db: Session, order_id: int, tenant_pharmacy_id: int) -> models.Order:
    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_id, models.Order.pharmacy_id == tenant_pharmacy_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _is_allowed_file(file: UploadFile) -> bool:
    ctype = (file.content_type or "").lower()
    if ctype in ALLOWED_CONTENT_TYPES:
        return True
    # Fallback to extension checks when the browser doesn't send a content type.
    name = (file.filename or "").lower()
    return name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf"))


async def _read_limited_upload(file: UploadFile) -> bytes:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        max_mb = max(1, MAX_UPLOAD_BYTES // (1024 * 1024))
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is too large. Maximum size is {max_mb} MB.",
        )
    return content


def _attachment_header(filename: str) -> str:
    safe_fallback = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in filename) or "prescription"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{safe_fallback}\"; filename*=UTF-8''{encoded}"


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
        content = await _read_limited_upload(file)
        stored = save_prescription_upload(file, content, token=token, pharmacy_id=tenant_pharmacy_id)

        created.append(
            models.Prescription(
                file_path=stored.location,
                original_filename=stored.original_filename,
                content_type=stored.content_type,
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
        content = await _read_limited_upload(file)
        stored = save_prescription_upload(file, content, token=token, pharmacy_id=tenant_pharmacy_id)
        created.append(
            models.Prescription(
                file_path=stored.location,
                original_filename=stored.original_filename,
                content_type=stored.content_type,
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

    loaded = load_prescription_file(
        prescription.file_path or "",
        original_filename=prescription.original_filename,
        content_type=prescription.content_type,
    )
    return Response(
        content=loaded.body,
        media_type=loaded.content_type,
        headers={"Content-Disposition": _attachment_header(loaded.filename)},
    )
