from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from datetime import datetime

from app import models, schemas
from app.chat_sessions import ESCALATION_SYSTEM_MESSAGE, add_message, close_session_if_expired
from app.ai.intent import get_customer_chat_id
from app.db import get_db
from app.deps import get_active_public_pharmacy_id


router = APIRouter(prefix="/chat", tags=["Chat"])


def _get_customer_chat_id(chat_id: str | None = Header(None, alias="X-Chat-ID")) -> str:
    return get_customer_chat_id(chat_id)


@router.get("/sessions/{session_id}/messages", response_model=list[schemas.ChatMessageOut])
def get_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    customer_id: str = Depends(_get_customer_chat_id),
):
    session = (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.pharmacy_id == pharmacy_id,
            models.ChatSession.session_id == session_id,
        )
        .first()
    )
    if not session or session.user_session_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    close_session_if_expired(db, session)

    return (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session.id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )


@router.post("/sessions/{session_id}/escalate")
def escalate_session(
    session_id: str,
    payload: schemas.ChatSessionEscalateIn,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    customer_id: str = Depends(_get_customer_chat_id),
):
    session = (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.pharmacy_id == pharmacy_id,
            models.ChatSession.session_id == session_id,
        )
        .first()
    )
    if not session or session.user_session_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if close_session_if_expired(db, session):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Session expired")

    main_concern = (payload.main_concern or "").strip()
    if not main_concern or len(main_concern) > 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Main concern must be 1-200 characters")

    customer_name = (payload.customer_name or "").strip()
    customer_phone = (payload.customer_phone or "").strip()
    if not customer_name or len(customer_name) > 80:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name is required")
    if not customer_phone or len(customer_phone) > 32:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone is required")

    session.intake_data = {
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "age_range": payload.age_range,
        "main_concern": main_concern,
        "how_long": payload.how_long,
        "current_medications": (payload.current_medications or "").strip() or None,
        "allergies": (payload.allergies or "").strip() or None,
    }
    session.status = "ESCALATED"
    session.last_activity_at = datetime.utcnow()
    add_message(db, session, "SYSTEM", ESCALATION_SYSTEM_MESSAGE, {"kind": "escalation", "source": "customer"})
    db.commit()

    return {"ok": True, "status": session.status, "system_message": ESCALATION_SYSTEM_MESSAGE}


@router.post("/sessions/{session_id}/messages", response_model=schemas.ChatMessageOut)
def post_session_message(
    session_id: str,
    payload: schemas.ChatSessionMessageIn,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    customer_id: str = Depends(_get_customer_chat_id),
):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required")

    session = (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.pharmacy_id == pharmacy_id,
            models.ChatSession.session_id == session_id,
        )
        .first()
    )
    if not session or session.user_session_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if close_session_if_expired(db, session) or session.status == "CLOSED":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Session is closed")

    session.last_activity_at = datetime.utcnow()
    message = add_message(db, session, "USER", text)
    db.commit()
    db.refresh(message)
    return message
