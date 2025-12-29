from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.ai.provider_factory import get_ai_provider
from app.ai import rag_service
from app.ai.intent import get_customer_chat_id
from app.ai.safety import detect_risk, safe_response
from app.ai import session_memory
from app.ai.tri_model_router import route_intent
from app.ai.tool_executor import build_tool_context
from app.ai.generator import generate_answer
from app.config.rag import get_rag_config
from app.auth.deps import require_admin, require_approved_owner
from app.db import get_db
from app.deps import get_active_public_pharmacy_id


router = APIRouter(prefix="/ai", tags=["AI"])


def _get_customer_chat_id(chat_id: str | None = Header(None, alias="X-Chat-ID")) -> str:
    return get_customer_chat_id(chat_id)


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
    session_id = (payload.session_id or "").strip() or session_memory.new_session_id()

    try:
        get_ai_provider()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI provider is not configured: {exc}",
        ) from exc

    try:
        rag_service.ensure_pharmacy_playbook(db, pharmacy_id)
        db.commit()
        is_risky, reason = detect_risk(message)
        if is_risky:
            pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
            answer = safe_response(pharmacy, reason)
            interaction = models.AIInteraction(
                customer_id=customer_id,
                customer_query=message,
                ai_response=answer,
                confidence_score=0.0,
                escalated_to_human=True,
                created_at=datetime.utcnow(),
                pharmacy_id=pharmacy_id,
            )
            db.add(interaction)
            db.commit()
            db.refresh(interaction)
            session_memory.append_turns(db, pharmacy_id, session_id, message, interaction.ai_response)
            _log(db, pharmacy_id, "chat", f"chat_id={customer_id} confidence=0.00 escalated=True rag_top_k=0 retrieved_chunks=[]")
            _log(db, pharmacy_id, "escalation", f"interaction_id={interaction.id} chat_id={customer_id}")
            db.commit()
            return schemas.AIChatOut(
                interaction_id=interaction.id,
                customer_id=customer_id,
                session_id=session_id,
                answer=interaction.ai_response,
                citations=[],
                cards=[],
                actions=[],
                quick_replies=[],
                confidence_score=interaction.confidence_score,
                escalated_to_human=interaction.escalated_to_human,
                intent="RISKY_MEDICAL",
                created_at=interaction.created_at,
                data_last_updated_at=None,
                indexed_at=None,
            )
        turns = session_memory.load_turns(db, pharmacy_id, session_id)
        memory_context = session_memory.user_context(turns)
        router = await route_intent(message, pharmacy_id=pharmacy_id, session_id=session_id)
        tool_ctx, citations, actions, immediate_answer = await build_tool_context(
            db,
            pharmacy_id=pharmacy_id,
            router=router,
            session_id=session_id,
            turns=turns,
        )
        gen = await generate_answer(
            tool_context=tool_ctx,
            user_message=message,
            router_confidence=float(router.confidence or 0.0),
        )
        answer = immediate_answer or gen.answer
        # Keep existing action list from tools unless generator provided actions.
        if gen.actions:
            actions = [
                schemas.AIAction(
                    type=a.type,
                    label=a.label,
                    medicine_id=(int(a.payload.get("medicine_id")) if isinstance(a.payload, dict) and a.payload.get("medicine_id") else None),
                    payload=a.payload,
                )
                for a in gen.actions
            ]
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    interaction = models.AIInteraction(
        customer_id=customer_id,
        customer_query=message,
        ai_response=answer,
        confidence_score=float(gen.confidence if gen.answer else 0.0),
        escalated_to_human=bool(tool_ctx.escalated or gen.escalated),
        created_at=datetime.utcnow(),
        pharmacy_id=pharmacy_id,
    )
    db.add(interaction)
    db.flush()
    chunk_log = ",".join(f"{c.get('chunk_id',0)}:source" for c in (tool_ctx.citations or []))
    action_log = ",".join(sorted({a.type for a in (actions or []) if a and a.type}))
    _log(
        db,
        pharmacy_id,
        "chat",
        (
            f"chat_id={customer_id} confidence={float(gen.confidence if gen.answer else 0.0):.2f} escalated={bool(tool_ctx.escalated or gen.escalated)} "
            f"router_intent={router.intent} router_conf={router.confidence:.2f} "
            f"rag_top_k={int(get_rag_config().top_k)} retrieved_chunks=[{chunk_log}] actions=[{action_log}]"
        ),
    )
    if interaction.escalated_to_human:
        _log(db, pharmacy_id, "escalation", f"interaction_id={interaction.id} chat_id={customer_id}")
    db.commit()
    db.refresh(interaction)
    session_memory.append_turns(db, pharmacy_id, session_id, message, interaction.ai_response)

    return schemas.AIChatOut(
        interaction_id=interaction.id,
        customer_id=customer_id,
        session_id=session_id,
        answer=interaction.ai_response,
        citations=[schemas.AICitation(**c) for c in (tool_ctx.citations or [])] if tool_ctx.citations else citations,
        cards=(tool_ctx.cards or []),
        actions=actions,
        quick_replies=(gen.quick_replies or tool_ctx.quick_replies or []),
        confidence_score=interaction.confidence_score,
        escalated_to_human=interaction.escalated_to_human,
        intent=tool_ctx.intent,
        created_at=interaction.created_at,
        data_last_updated_at=tool_ctx.data_last_updated_at,
        indexed_at=tool_ctx.indexed_at,
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
    current_user: models.User = Depends(require_approved_owner),
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
    current_user: models.User = Depends(require_approved_owner),
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
    current_user: models.User = Depends(require_approved_owner),
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
