from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.deps import require_approved_owner
from app.db import get_db


router = APIRouter(prefix="/admin/pharmacist", tags=["Pharmacist"])


@router.get("/sessions", response_model=list[schemas.ChatSessionSummary])
def list_escalated_sessions(
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
    status_filter: str = "ESCALATED",
):
    return (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.pharmacy_id == current_user.pharmacy_id,
            models.ChatSession.status == status_filter,
        )
        .order_by(models.ChatSession.last_activity_at.desc())
        .all()
    )


@router.get("/sessions/{session_id}/messages", response_model=list[schemas.ChatMessageOut])
def get_session_messages(
    session_id: str,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    session = (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.pharmacy_id == current_user.pharmacy_id,
            models.ChatSession.session_id == session_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session.id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )


@router.post("/sessions/{session_id}/reply", response_model=schemas.ChatMessageOut)
def reply_to_session(
    session_id: str,
    payload: schemas.ChatSessionReplyIn,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reply is required")

    session = (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.pharmacy_id == current_user.pharmacy_id,
            models.ChatSession.session_id == session_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session.status = "ACTIVE"
    session.last_activity_at = datetime.utcnow()
    message = models.ChatMessage(
        session_id=session.id,
        sender_type="PHARMACIST",
        text=text,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
