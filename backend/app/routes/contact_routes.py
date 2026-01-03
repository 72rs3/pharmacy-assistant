from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.deps import require_approved_owner
from app.db import get_db
from app.deps import get_active_public_pharmacy_id


router = APIRouter(prefix="/contact", tags=["Contact"])


@router.post("/messages", response_model=schemas.ContactMessageOut)
def create_contact_message(
    payload: schemas.ContactMessageCreate,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_active_public_pharmacy_id),
):
    name = (payload.name or "").strip()
    email = str(payload.email).strip()
    subject = (payload.subject or "").strip()
    message = (payload.message or "").strip()
    phone = (payload.phone or "").strip() or None

    if not name or not email or not subject or not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing required fields")

    row = models.ContactMessage(
        pharmacy_id=pharmacy_id,
        status="NEW",
        name=name,
        email=email,
        phone=phone,
        subject=subject,
        message=message,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/owner/messages", response_model=list[schemas.ContactMessageSummary])
def list_owner_contact_messages(
    status_filter: str = "NEW",
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.ContactMessage)
        .filter(models.ContactMessage.pharmacy_id == current_user.pharmacy_id)
        .order_by(models.ContactMessage.created_at.desc())
    )
    if status_filter and status_filter != "ALL":
        q = q.filter(models.ContactMessage.status == status_filter)
    return q.limit(200).all()


@router.get("/owner/messages/{message_id}", response_model=schemas.ContactMessageOut)
def get_owner_contact_message(
    message_id: int,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    row = (
        db.query(models.ContactMessage)
        .filter(
            models.ContactMessage.id == message_id,
            models.ContactMessage.pharmacy_id == current_user.pharmacy_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return row


@router.post("/owner/messages/{message_id}/reply", response_model=schemas.ContactMessageOut)
def reply_owner_contact_message(
    message_id: int,
    payload: schemas.ContactMessageReplyIn,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    row = (
        db.query(models.ContactMessage)
        .filter(
            models.ContactMessage.id == message_id,
            models.ContactMessage.pharmacy_id == current_user.pharmacy_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    reply_text = (payload.reply_text or "").strip()
    if not reply_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reply is required")
    row.reply_text = reply_text
    row.replied_at = datetime.utcnow()
    row.status = "CLOSED"
    row.handled_by_user_id = current_user.id
    db.commit()
    db.refresh(row)
    return row


@router.post("/owner/messages/{message_id}/status", response_model=schemas.ContactMessageOut)
def update_owner_contact_message_status(
    message_id: int,
    payload: schemas.ContactMessageStatusUpdateIn,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    row = (
        db.query(models.ContactMessage)
        .filter(
            models.ContactMessage.id == message_id,
            models.ContactMessage.pharmacy_id == current_user.pharmacy_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    row.status = payload.status
    row.handled_by_user_id = current_user.id
    db.commit()
    db.refresh(row)
    return row
