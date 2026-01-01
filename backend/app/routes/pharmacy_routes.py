import re

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.auth.deps import require_admin, require_owner
from app.ai.intent import get_customer_chat_id, route_intent
from app.ai import session_memory
from app.chat_sessions import ESCALATION_SYSTEM_MESSAGE, add_message, get_or_create_session
from app.ai import rag_service
from app.ai.safety import detect_risk
from app.deps import get_active_public_pharmacy
from .. import crud, schemas
from ..db import get_db
from app.utils.validation import validate_e164_phone, validate_email

router = APIRouter(prefix="/pharmacies", tags=["Pharmacies"])


_HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")
_THEME_PRESETS = {"classic", "fresh", "minimal", "glass", "neumorph"}
_LAYOUT_PRESETS = {"classic", "breeze", "studio", "market"}


def _normalize_hex(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if not _HEX_COLOR_RE.match(raw):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid color (expected hex like #7CB342)",
        )
    return raw if raw.startswith("#") else f"#{raw}"

@router.post("/", response_model=schemas.Pharmacy)
def create_pharmacy(
    pharmacy: schemas.PharmacyCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    if pharmacy.contact_email is not None:
        pharmacy.contact_email = validate_email(pharmacy.contact_email, "contact")
    if pharmacy.contact_phone is not None:
        pharmacy.contact_phone = validate_e164_phone(pharmacy.contact_phone, "contact")
    return crud.create_pharmacy(db=db, pharmacy=pharmacy)

@router.get("/", response_model=list[schemas.Pharmacy])
def list_pharmacies(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return crud.get_pharmacies(db, active_only=True)

@router.get("/me", response_model=schemas.Pharmacy)
def my_pharmacy(
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    pharmacy = (
        db.query(models.Pharmacy)
        .filter(models.Pharmacy.id == current_user.pharmacy_id)
        .first()
    )
    if not pharmacy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pharmacy not found")
    return pharmacy


@router.patch("/me", response_model=schemas.Pharmacy)
def update_my_pharmacy(
    payload: schemas.PharmacyUpdate,
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    pharmacy = (
        db.query(models.Pharmacy)
        .filter(models.Pharmacy.id == current_user.pharmacy_id)
        .first()
    )
    if not pharmacy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pharmacy not found")

    data = payload.model_dump(exclude_unset=True)

    for key in ("primary_color", "primary_color_600", "accent_color"):
        if key in data:
            data[key] = _normalize_hex(data[key])

    for key, value in list(data.items()):
        if isinstance(value, str) and not value.strip():
            data[key] = None

    if "theme_preset" in data and data["theme_preset"] is not None:
        preset = str(data["theme_preset"]).strip().lower()
        if preset not in _THEME_PRESETS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid theme preset",
            )
        data["theme_preset"] = preset

    if "contact_email" in data and data["contact_email"] is not None:
        data["contact_email"] = validate_email(data["contact_email"], "contact")
    if "contact_phone" in data and data["contact_phone"] is not None:
        data["contact_phone"] = validate_e164_phone(data["contact_phone"], "contact")

    if "storefront_layout" in data and data["storefront_layout"] is not None:
        layout = str(data["storefront_layout"]).strip().lower()
        if layout not in _LAYOUT_PRESETS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid storefront layout",
            )
        data["storefront_layout"] = layout

    for key, value in data.items():
        setattr(pharmacy, key, value)

    db.commit()
    db.refresh(pharmacy)
    return pharmacy


@router.get("/current", response_model=schemas.Pharmacy)
def get_current_public_pharmacy(
    pharmacy: models.Pharmacy = Depends(get_active_public_pharmacy),
):
    return pharmacy


@router.get("/admin", response_model=list[schemas.Pharmacy])
def list_all_pharmacies(
    status: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return crud.get_pharmacies(db, active_only=False, status=status)


@router.get("/{pharmacy_id}/rag/status")
def rag_status(
    pharmacy_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    docs = (
        db.query(models.Document)
        .filter(models.Document.pharmacy_id == pharmacy_id)
        .all()
    )
    chunks_count = (
        db.query(models.DocumentChunk)
        .filter(models.DocumentChunk.pharmacy_id == pharmacy_id)
        .count()
    )
    last_indexed_at = max((doc.indexed_at for doc in docs if doc.indexed_at), default=None)
    source_counts: dict[str, int] = {}
    for doc in docs:
        source_counts[doc.source_type] = source_counts.get(doc.source_type, 0) + 1
    return {
        "pharmacy_id": pharmacy_id,
        "last_indexed_at": last_indexed_at,
        "document_count": len(docs),
        "document_counts_by_source": source_counts,
        "chunk_count": chunks_count,
    }


@router.post("/{pharmacy_id}/approve", response_model=schemas.Pharmacy)
def approve_pharmacy(
    pharmacy_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    pharmacy = crud.approve_pharmacy(db, pharmacy_id=pharmacy_id)
    rag_service.ensure_pharmacy_playbook(db, pharmacy.id)
    db.commit()
    db.refresh(pharmacy)
    return pharmacy


@router.post("/{pharmacy_id}/ai/chat", response_model=schemas.AIChatOut)
async def chat_for_pharmacy(
    pharmacy_id: int,
    payload: schemas.AIChatIn,
    db: Session = Depends(get_db),
    chat_id: str | None = Header(None, alias="X-Chat-ID"),
    _=Depends(require_admin),
):
    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required")
    requested_session_id = (payload.session_id or "").strip() or None

    customer_id = get_customer_chat_id(chat_id)
    session = get_or_create_session(db, pharmacy_id, customer_id, requested_session_id)
    session_id = session.session_id
    system_message: str | None = None
    add_message(db, session, "USER", message)
    rag_service.ensure_pharmacy_playbook(db, pharmacy_id)
    db.commit()
    is_risky, reason = detect_risk(message)
    if is_risky:
        answer = "A pharmacist will reply shortly. If this is urgent, please seek medical care."
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
        session.status = "ESCALATED"
        system_message = ESCALATION_SYSTEM_MESSAGE
        add_message(db, session, "SYSTEM", system_message, {"kind": "escalation", "reason": reason})
        add_message(db, session, "AI", interaction.ai_response, {"intent": "MEDICAL_ADVICE_RISK"})
        session_memory.append_turns(db, pharmacy_id, session_id, message, interaction.ai_response)
        return schemas.AIChatOut(
            interaction_id=interaction.id,
            customer_id=customer_id,
            session_id=session_id,
            answer=interaction.ai_response,
            citations=[],
            confidence_score=interaction.confidence_score,
            escalated_to_human=interaction.escalated_to_human,
            intent="MEDICAL_ADVICE_RISK",
            created_at=interaction.created_at,
            data_last_updated_at=None,
            indexed_at=None,
            system_message=system_message,
        )
    turns = session_memory.load_turns(db, pharmacy_id, session_id)
    memory_context = session_memory.user_context(turns)
    intent_result = await route_intent(
        db,
        pharmacy_id,
        customer_id,
        message,
        memory_context=memory_context,
    )

    escalated = bool(intent_result.escalated) or intent_result.intent in {"MEDICAL_ADVICE_RISK", "RISKY_MEDICAL"}
    answer = intent_result.answer
    if escalated:
        answer = "A pharmacist will reply shortly. If this is urgent, please seek medical care."

    interaction = models.AIInteraction(
        customer_id=customer_id,
        customer_query=message,
        ai_response=answer,
        confidence_score=float(intent_result.confidence),
        escalated_to_human=escalated,
        created_at=datetime.utcnow(),
        pharmacy_id=pharmacy_id,
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)
    if interaction.escalated_to_human:
        session.status = "ESCALATED"
        system_message = ESCALATION_SYSTEM_MESSAGE
        add_message(db, session, "SYSTEM", system_message, {"kind": "escalation"})
    add_message(db, session, "AI", interaction.ai_response, {"intent": intent_result.intent})
    session_memory.append_turns(db, pharmacy_id, session_id, message, interaction.ai_response)

    return schemas.AIChatOut(
        interaction_id=interaction.id,
        customer_id=customer_id,
        session_id=session_id,
        answer=interaction.ai_response,
        citations=intent_result.citations,
        confidence_score=interaction.confidence_score,
        escalated_to_human=interaction.escalated_to_human,
        intent=intent_result.intent,
        created_at=interaction.created_at,
        data_last_updated_at=intent_result.data_last_updated_at,
        indexed_at=intent_result.indexed_at,
        system_message=system_message,
    )
