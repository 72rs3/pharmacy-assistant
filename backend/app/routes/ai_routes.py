from __future__ import annotations

import secrets
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.ai.provider_factory import get_ai_provider
from app.ai import rag_service
from app.auth.deps import require_admin, require_owner
from app.db import get_db
from app.deps import get_active_public_pharmacy_id


router = APIRouter(prefix="/ai", tags=["AI"])


def _get_customer_chat_id(chat_id: str | None = Header(None, alias="X-Chat-ID")) -> str:
    if chat_id and chat_id.strip():
        return chat_id.strip()
    return secrets.token_urlsafe(12)


def _log(db: Session, pharmacy_id: int, log_type: str, details: str) -> None:
    db.add(models.AILog(log_type=log_type, details=details, pharmacy_id=pharmacy_id))


@router.post("/chat", response_model=schemas.AIChatOut)
async def chat(
    payload: schemas.AIChatIn,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    customer_id: str = Depends(_get_customer_chat_id),
):
    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required")

    try:
        get_ai_provider()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI provider is not configured: {exc}",
        ) from exc

    try:
        answer, confidence, escalated, chunks = await rag_service.answer(db, pharmacy_id, customer_id, message)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    citations = [
        schemas.AICitation(
            doc_id=int(c.document_id),
            chunk_id=int(c.id),
            snippet=((c.content or "").replace("\n", " ").strip()[:160]),
        )
        for c in chunks
        if c.content
    ]

    interaction = models.AIInteraction(
        customer_id=customer_id,
        customer_query=message,
        ai_response=answer,
        confidence_score=float(confidence),
        escalated_to_human=bool(escalated),
        created_at=datetime.utcnow(),
        pharmacy_id=pharmacy_id,
    )
    db.add(interaction)
    db.flush()
    chunk_log = ",".join(f"{c.id}:{c.score:.2f}" for c in chunks)
    _log(
        db,
        pharmacy_id,
        "chat",
        (
            f"chat_id={customer_id} confidence={confidence:.2f} escalated={bool(escalated)} "
            f"rag_top_k={int(os.getenv('RAG_TOP_K','6'))} retrieved_chunks=[{chunk_log}]"
        ),
    )
    if interaction.escalated_to_human:
        _log(db, pharmacy_id, "escalation", f"interaction_id={interaction.id} chat_id={customer_id}")
    db.commit()
    db.refresh(interaction)

    return schemas.AIChatOut(
        interaction_id=interaction.id,
        customer_id=customer_id,
        answer=interaction.ai_response,
        citations=citations,
        confidence_score=interaction.confidence_score,
        escalated_to_human=interaction.escalated_to_human,
        created_at=interaction.created_at,
    )


@router.get("/chat/my", response_model=list[schemas.AIInteraction])
def my_chat_history(
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    customer_id: str = Depends(_get_customer_chat_id),
):
    return (
        db.query(models.AIInteraction)
        .filter(models.AIInteraction.pharmacy_id == pharmacy_id, models.AIInteraction.customer_id == customer_id)
        .order_by(models.AIInteraction.created_at.asc())
        .all()
    )


@router.post("/rag/reindex")
async def reindex_pharmacy(
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        get_ai_provider()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI provider is not configured: {exc}",
        ) from exc

    try:
        chunks = await rag_service.upsert_medicine_index(db, current_user.pharmacy_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    _log(db, current_user.pharmacy_id, "reindex", f"chunks={chunks}")
    db.commit()
    return {"ok": True, "chunks": chunks}


@router.get("/escalations/owner", response_model=list[schemas.AIInteraction])
def list_owner_escalations(
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.AIInteraction)
        .filter(
            models.AIInteraction.pharmacy_id == current_user.pharmacy_id,
            models.AIInteraction.escalated_to_human.is_(True),
            models.AIInteraction.owner_reply.is_(None),
        )
        .order_by(models.AIInteraction.created_at.desc())
        .all()
    )


@router.post("/escalations/{interaction_id}/reply", response_model=schemas.AIInteraction)
def reply_to_escalation(
    interaction_id: int,
    payload: schemas.AIEscalationReplyIn,
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    reply = (payload.reply or "").strip()
    if not reply:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reply is required")

    interaction = (
        db.query(models.AIInteraction)
        .filter(
            models.AIInteraction.id == interaction_id,
            models.AIInteraction.pharmacy_id == current_user.pharmacy_id,
        )
        .first()
    )
    if not interaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction not found")

    interaction.owner_reply = reply
    interaction.owner_replied_at = datetime.utcnow()
    interaction.owner_id = current_user.id
    _log(db, current_user.pharmacy_id, "owner_reply", f"interaction_id={interaction_id} owner_id={current_user.id}")
    db.commit()
    db.refresh(interaction)
    return interaction


@router.get("/admin/logs", response_model=list[schemas.AILog])
def list_admin_logs(
    _: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = 200,
):
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be between 1 and 1000")
    return db.query(models.AILog).order_by(models.AILog.timestamp.desc()).limit(limit).all()
