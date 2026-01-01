from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models
from app.ai import session_memory


SESSION_TIMEOUT_MINUTES = int(os.getenv("CHAT_SESSION_TIMEOUT_MINUTES", "10"))
ESCALATION_SYSTEM_MESSAGE = "Escalated to pharmacist"


def is_session_expired(session: models.ChatSession) -> bool:
    if not session.last_activity_at:
        return False
    return datetime.utcnow() - session.last_activity_at > timedelta(minutes=SESSION_TIMEOUT_MINUTES)


def get_or_create_session(
    db: Session,
    pharmacy_id: int,
    user_session_id: str,
    session_id: str | None,
) -> models.ChatSession:
    session: models.ChatSession | None = None
    if session_id:
        session = (
            db.query(models.ChatSession)
            .filter(
                models.ChatSession.pharmacy_id == pharmacy_id,
                models.ChatSession.session_id == session_id,
            )
            .first()
        )
        if session and session.user_session_id and session.user_session_id != user_session_id:
            session = None
        if session and is_session_expired(session):
            session.status = "CLOSED"
            session = None
        if session and not session.user_session_id:
            session.user_session_id = user_session_id

    if not session:
        session = (
            db.query(models.ChatSession)
            .filter(
                models.ChatSession.pharmacy_id == pharmacy_id,
                models.ChatSession.user_session_id == user_session_id,
                models.ChatSession.status.in_(["ACTIVE", "ESCALATED"]),
            )
            .order_by(models.ChatSession.last_activity_at.desc())
            .first()
        )
        if session and is_session_expired(session):
            session.status = "CLOSED"
            session = None
        if session and not session.user_session_id:
            session.user_session_id = user_session_id

    if not session:
        session = models.ChatSession(
            pharmacy_id=pharmacy_id,
            session_id=session_memory.new_session_id(),
            user_session_id=user_session_id,
            status="ACTIVE",
            last_activity_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=SESSION_TIMEOUT_MINUTES),
        )
        db.add(session)
        db.flush()
    else:
        session.last_activity_at = datetime.utcnow()

    return session


def add_message(
    db: Session,
    session: models.ChatSession,
    sender_type: str,
    text: str,
    metadata: dict | None = None,
) -> models.ChatMessage:
    message = models.ChatMessage(
        session_id=session.id,
        sender_type=sender_type,
        text=text,
        meta=metadata,
    )
    db.add(message)
    return message
