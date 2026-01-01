from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
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

    return (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session.id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )
