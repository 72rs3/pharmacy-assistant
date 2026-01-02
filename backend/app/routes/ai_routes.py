from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.ai.provider_factory import get_ai_provider
from app.ai import rag_service
from app.ai.intent import get_customer_chat_id
from app.ai.safety import detect_risk
from app.ai import session_memory
from app.chat_sessions import ESCALATION_SYSTEM_MESSAGE, add_message, get_or_create_session
from app.ai.tri_model_router import route_intent
from app.ai.tool_executor import build_tool_context
from app.ai.generator import generate_answer
from app.config.rag import get_rag_config
from app.auth.deps import require_admin, require_approved_owner
from app.db import get_db
from app.deps import get_active_public_pharmacy_id


router = APIRouter(prefix="/ai", tags=["AI"])

_HEADACHE_PATTERN = re.compile(r"\b(headache|head\s*ache|migraine|head\s*pain|heache)\b", re.IGNORECASE)
_HEADACHE_REDFLAG_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(worst headache|thunderclap|sudden(ly)?|came on suddenly)\b", re.IGNORECASE), "sudden / worst-ever"),
    (re.compile(r"\b(confusion|confused|disoriented|slurred speech|seizure|faint(ing|ed)?|passed out)\b", re.IGNORECASE), "neurologic symptoms"),
    (re.compile(r"\b(vision (loss|change|changes)|blurred vision|double vision)\b", re.IGNORECASE), "vision changes"),
    (re.compile(r"\b(weakness|numbness|paralysis)\b", re.IGNORECASE), "weakness / numbness"),
    (re.compile(r"\b(head injury|hit my head|fell|accident|concussion)\b", re.IGNORECASE), "recent head injury"),
    (re.compile(r"\b(fever|stiff neck|neck stiffness|rash|photophobia|light sensitivity)\b", re.IGNORECASE), "fever / stiff neck"),
    (re.compile(r"\b(pregnant|pregnancy)\b", re.IGNORECASE), "pregnancy"),
]

_ABDOMINAL_PAIN_PATTERN = re.compile(
    r"\b(stomach pain|stomach ache|abdominal pain|belly pain|tummy ache|stomach cramps|cramps)\b",
    re.IGNORECASE,
)
_ABDOMINAL_REDFLAG_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(severe|unbearable|worst)\b", re.IGNORECASE), "severe pain"),
    (re.compile(r"\b(sudden(ly)?|came on suddenly)\b", re.IGNORECASE), "sudden onset"),
    (re.compile(r"\b(vomiting blood|blood in vomit|hematemesis)\b", re.IGNORECASE), "vomiting blood"),
    (re.compile(r"\b(blood in stool|bloody stool|black stool|tarry stool)\b", re.IGNORECASE), "blood/black stool"),
    (re.compile(r"\b(faint(ing|ed)?|passed out|confusion|unconscious)\b", re.IGNORECASE), "fainting/confusion"),
    (re.compile(r"\b(pregnant|pregnancy)\b", re.IGNORECASE), "pregnancy"),
    (re.compile(r"\b(high fever|fever|rigid abdomen|hard belly)\b", re.IGNORECASE), "fever/rigid abdomen"),
]


def _looks_like_headache(text: str) -> bool:
    return bool(_HEADACHE_PATTERN.search(text or ""))


def _headache_red_flags(text: str) -> list[str]:
    msg = text or ""
    found: list[str] = []
    for pattern, label in _HEADACHE_REDFLAG_PATTERNS:
        if pattern.search(msg):
            found.append(label)
    return found


def _looks_like_abdominal_pain(text: str) -> bool:
    return bool(_ABDOMINAL_PAIN_PATTERN.search(text or ""))


def _abdominal_red_flags(text: str) -> list[str]:
    msg = text or ""
    found: list[str] = []
    for pattern, label in _ABDOMINAL_REDFLAG_PATTERNS:
        if pattern.search(msg):
            found.append(label)
    return found


def _parse_severity_1_to_10(text: str) -> int | None:
    match = re.search(r"\b(10|[1-9])\b", (text or ""))
    if not match:
        return None
    try:
        value = int(match.group(1))
    except Exception:
        return None
    return value if 1 <= value <= 10 else None


def _parse_duration_bucket(text: str) -> str | None:
    msg = (text or "").lower()
    if any(tok in msg for tok in ["getting worse", "worse", "worsening"]):
        return ">3 days"
    if any(tok in msg for tok in ["< 1 day", "<1 day", "today", "this morning", "since morning", "hours", "hour"]):
        return "<1 day"
    if any(tok in msg for tok in ["1-3 days", "1 - 3 days", "two days", "3 days", "2 days"]):
        return "1-3 days"
    days_match = re.search(r"(\d+)\s*day", msg)
    if days_match:
        try:
            days = int(days_match.group(1))
            if days <= 0:
                return None
            if days < 1:
                return "<1 day"
            if days <= 3:
                return "1-3 days"
            return ">3 days"
        except Exception:
            return None
    if "week" in msg or "weeks" in msg:
        return ">3 days"
    return None


def _is_affirmative(text: str) -> bool:
    msg = (text or "").strip().lower()
    return msg in {"yes", "y", "yeah", "yep", "i do", "i have", "sure"} or msg.startswith("yes ")


def _is_negative(text: str) -> bool:
    msg = (text or "").strip().lower()
    return msg in {"no", "n", "nope", "not really"} or msg.startswith("no ")


def _maybe_handle_headache_triage(db: Session, pharmacy_id: int, customer_id: str, session: models.ChatSession, user_text: str):
    triage_action = schemas.AIAction(type="escalate_to_pharmacist", label="Talk to pharmacist")

    last_ai = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session.id, models.ChatMessage.sender_type == "AI")
        .order_by(models.ChatMessage.created_at.desc())
        .first()
    )
    last_intent = ""
    if last_ai and isinstance(last_ai.meta, dict):
        last_intent = str(last_ai.meta.get("intent") or "")

    is_in_flow = last_intent.startswith("HEADACHE_TRIAGE_")
    is_new_headache = _looks_like_headache(user_text)
    if not is_in_flow and not is_new_headache:
        return None

    red_flags_now = _headache_red_flags(user_text)

    def respond(text: str, *, intent: str, quick_replies: list[str] | None = None, strong: bool = False):
        interaction = models.AIInteraction(
            customer_id=customer_id,
            customer_query=user_text,
            ai_response=text,
            confidence_score=0.0,
            escalated_to_human=bool(strong),
            created_at=datetime.utcnow(),
            pharmacy_id=pharmacy_id,
        )
        db.add(interaction)
        db.commit()
        db.refresh(interaction)
        add_message(
            db,
            session,
            "AI",
            text,
            _build_ai_metadata(
                intent=intent,
                actions=[triage_action],
                cards=[],
                quick_replies=quick_replies or [],
                data_last_updated_at=None,
                indexed_at=None,
            ),
        )
        db.commit()
        return schemas.AIChatOut(
            interaction_id=interaction.id,
            customer_id=customer_id,
            session_id=session.session_id,
            answer=text,
            citations=[],
            cards=[],
            actions=[triage_action],
            quick_replies=quick_replies or [],
            confidence_score=interaction.confidence_score,
            escalated_to_human=interaction.escalated_to_human,
            intent=intent,
            created_at=interaction.created_at,
            data_last_updated_at=None,
            indexed_at=None,
            system_message=None,
        )

    if red_flags_now:
        return respond(
            (
                "Your symptoms may need urgent medical attention. "
                "Please start a pharmacist consultation now, and if this feels severe or sudden, seek emergency care."
            ),
            intent="HEADACHE_REDFLAG",
            quick_replies=["Talk to pharmacist"],
            strong=True,
        )

    if last_intent == "HEADACHE_TRIAGE_SEVERITY":
        severity = _parse_severity_1_to_10(user_text)
        if severity is None:
            return respond(
                "On a scale of 1-10, how severe is your headache right now? (1 = mild, 10 = worst)",
                intent="HEADACHE_TRIAGE_SEVERITY",
                quick_replies=["1-3 (mild)", "4-7 (moderate)", "8-10 (severe)"],
            )
        return respond(
            "How long have you had this headache?",
            intent="HEADACHE_TRIAGE_DURATION",
            quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
            strong=severity >= 8,
        )

    if last_intent == "HEADACHE_TRIAGE_DURATION":
        bucket = _parse_duration_bucket(user_text)
        if not bucket:
            return respond(
                "How long have you had this headache?",
                intent="HEADACHE_TRIAGE_DURATION",
                quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
            )
        return respond(
            (
                "Do you have any of these right now: fever, stiff neck, vision changes, confusion/fainting, "
                "weakness/numbness, or a recent head injury?"
            ),
            intent="HEADACHE_TRIAGE_REDFLAGS",
            quick_replies=["No", "Yes"],
            strong=bucket == ">3 days",
        )

    if last_intent == "HEADACHE_TRIAGE_REDFLAGS":
        has_flags = _is_affirmative(user_text) and not _is_negative(user_text)
        if has_flags:
            return respond(
                (
                    "Thanks — those symptoms can be serious. Please start a pharmacist consultation now. "
                    "If this is urgent or worsening, seek medical care immediately."
                ),
                intent="HEADACHE_REDFLAG",
                quick_replies=["Talk to pharmacist"],
                strong=True,
            )
        if not _is_negative(user_text):
            return respond(
                (
                    "Do you have any of these right now: fever, stiff neck, vision changes, confusion/fainting, "
                    "weakness/numbness, or a recent head injury?"
                ),
                intent="HEADACHE_TRIAGE_REDFLAGS",
                quick_replies=["No", "Yes"],
            )
        return respond(
            (
                "For mild headaches with no concerning symptoms: rest, drink water, and avoid bright screens. "
                "If you want, you can look for common OTC options (e.g., paracetamol) - always follow the label. "
                "If symptoms persist, worsen, or you're unsure, please talk to a pharmacist."
            ),
            intent="HEADACHE_SELFCARE",
            quick_replies=["Search panadol", "Talk to pharmacist"],
        )

    return respond(
        "On a scale of 1-10, how severe is your headache right now? (1 = mild, 10 = worst)",
        intent="HEADACHE_TRIAGE_SEVERITY",
        quick_replies=["1-3 (mild)", "4-7 (moderate)", "8-10 (severe)"],
    )


def _maybe_handle_abdominal_pain_triage(
    db: Session,
    pharmacy_id: int,
    customer_id: str,
    session: models.ChatSession,
    user_text: str,
):
    triage_action = schemas.AIAction(type="escalate_to_pharmacist", label="Talk to pharmacist")

    last_ai = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session.id, models.ChatMessage.sender_type == "AI")
        .order_by(models.ChatMessage.created_at.desc())
        .first()
    )
    last_intent = ""
    if last_ai and isinstance(last_ai.meta, dict):
        last_intent = str(last_ai.meta.get("intent") or "")

    is_in_flow = last_intent.startswith("ABDOMINAL_TRIAGE_")
    is_new = _looks_like_abdominal_pain(user_text)
    if not is_in_flow and not is_new:
        return None

    red_flags_now = _abdominal_red_flags(user_text)

    def respond(text: str, *, intent: str, quick_replies: list[str] | None = None, strong: bool = False):
        interaction = models.AIInteraction(
            customer_id=customer_id,
            customer_query=user_text,
            ai_response=text,
            confidence_score=0.0,
            escalated_to_human=bool(strong),
            created_at=datetime.utcnow(),
            pharmacy_id=pharmacy_id,
        )
        db.add(interaction)
        db.commit()
        db.refresh(interaction)
        add_message(
            db,
            session,
            "AI",
            text,
            _build_ai_metadata(
                intent=intent,
                actions=[triage_action],
                cards=[],
                quick_replies=quick_replies or [],
                data_last_updated_at=None,
                indexed_at=None,
            ),
        )
        db.commit()
        return schemas.AIChatOut(
            interaction_id=interaction.id,
            customer_id=customer_id,
            session_id=session.session_id,
            answer=text,
            citations=[],
            cards=[],
            actions=[triage_action],
            quick_replies=quick_replies or [],
            confidence_score=interaction.confidence_score,
            escalated_to_human=interaction.escalated_to_human,
            intent=intent,
            created_at=interaction.created_at,
            data_last_updated_at=None,
            indexed_at=None,
            system_message=None,
        )

    if red_flags_now:
        return respond(
            (
                "Your symptoms may need urgent medical attention. Please start a pharmacist consultation now. "
                "If you have severe pain, bleeding, fainting, or rapidly worsening symptoms, seek emergency care."
            ),
            intent="ABDOMINAL_REDFLAG",
            quick_replies=["Talk to pharmacist"],
            strong=True,
        )

    if last_intent == "ABDOMINAL_TRIAGE_SEVERITY":
        severity = _parse_severity_1_to_10(user_text)
        if severity is None:
            return respond(
                "On a scale of 1-10, how severe is your stomach/abdominal pain right now? (1 = mild, 10 = worst)",
                intent="ABDOMINAL_TRIAGE_SEVERITY",
                quick_replies=["1-3 (mild)", "4-7 (moderate)", "8-10 (severe)"],
            )
        return respond(
            "How long have you had this pain?",
            intent="ABDOMINAL_TRIAGE_DURATION",
            quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
            strong=severity >= 8,
        )

    if last_intent == "ABDOMINAL_TRIAGE_DURATION":
        bucket = _parse_duration_bucket(user_text)
        if not bucket:
            return respond(
                "How long have you had this pain?",
                intent="ABDOMINAL_TRIAGE_DURATION",
                quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
            )
        return respond(
            (
                "Any of these right now: fever, vomiting repeatedly, blood in vomit/stool, black stools, "
                "fainting/confusion, pregnancy, or severe worsening pain?"
            ),
            intent="ABDOMINAL_TRIAGE_REDFLAGS",
            quick_replies=["No", "Yes"],
            strong=bucket == ">3 days",
        )

    if last_intent == "ABDOMINAL_TRIAGE_REDFLAGS":
        has_flags = _is_affirmative(user_text) and not _is_negative(user_text)
        if has_flags:
            return respond(
                (
                    "Thanks — those symptoms can be serious. Please start a pharmacist consultation now. "
                    "If symptoms are severe or worsening, seek medical care immediately."
                ),
                intent="ABDOMINAL_REDFLAG",
                quick_replies=["Talk to pharmacist"],
                strong=True,
            )
        if not _is_negative(user_text):
            return respond(
                (
                    "Any of these right now: fever, vomiting repeatedly, blood in vomit/stool, black stools, "
                    "fainting/confusion, pregnancy, or severe worsening pain?"
                ),
                intent="ABDOMINAL_TRIAGE_REDFLAGS",
                quick_replies=["No", "Yes"],
            )
        return respond(
            (
                "For mild abdominal discomfort with no red flags: sip water, eat light foods, and rest. "
                "If symptoms persist, worsen, or you're unsure, please talk to a pharmacist."
            ),
            intent="ABDOMINAL_SELFCARE",
            quick_replies=["Talk to pharmacist"],
        )

    return respond(
        "On a scale of 1-10, how severe is your stomach/abdominal pain right now? (1 = mild, 10 = worst)",
        intent="ABDOMINAL_TRIAGE_SEVERITY",
        quick_replies=["1-3 (mild)", "4-7 (moderate)", "8-10 (severe)"],
    )


def _get_customer_chat_id(chat_id: str | None = Header(None, alias="X-Chat-ID")) -> str:
    return get_customer_chat_id(chat_id)


def _log(db: Session, pharmacy_id: int, log_type: str, details: str) -> None:
    db.add(models.AILog(log_type=log_type, details=details, pharmacy_id=pharmacy_id))


 


def _format_dt(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.isoformat()


def _build_ai_metadata(
    *,
    intent: str,
    actions: list[schemas.AIAction],
    cards: list[schemas.MedicineCard],
    quick_replies: list[str],
    data_last_updated_at: datetime | None,
    indexed_at: datetime | None,
) -> dict:
    # Important: this metadata is stored in Postgres JSONB. It must be fully JSON-serializable.
    # Pydantic `model_dump()` returns Python objects (e.g., `datetime`) by default, so use `mode="json"`.
    return {
        "intent": intent,
        "actions": [a.model_dump(mode="json") for a in actions] if actions else [],
        "cards": [c.model_dump(mode="json") for c in cards] if cards else [],
        "quick_replies": quick_replies or [],
        "data_last_updated_at": _format_dt(data_last_updated_at),
        "indexed_at": _format_dt(indexed_at),
    }

def _enforce_action_policy(tool_ctx: object, actions: list[schemas.AIAction]) -> list[schemas.AIAction]:
    intent = str(getattr(tool_ctx, "intent", "") or "")
    if intent != "MEDICINE_SEARCH":
        return actions

    med_id: int | None = None
    rx: bool | None = None
    stock: int | None = None

    cards = getattr(tool_ctx, "cards", None) or []
    if cards:
        card = cards[0]
        med_id = int(getattr(card, "medicine_id", 0) or 0) or None
        rx = bool(getattr(card, "rx", False))
        stock = int(getattr(card, "stock", 0) or 0)

    items = getattr(tool_ctx, "items", None) or []
    if items and isinstance(items[0], dict):
        item = items[0]
        med_id = med_id or (int(item.get("id") or 0) or None)
        rx = bool(item.get("rx")) if rx is None else rx
        stock = int(item.get("stock") or 0) if stock is None else stock

    def action_med_id(action: schemas.AIAction) -> int | None:
        if action.medicine_id:
            return int(action.medicine_id)
        payload = action.payload or {}
        try:
            return int(payload.get("medicine_id")) if payload.get("medicine_id") is not None else None
        except Exception:
            return None

    def dedupe(vals: list[schemas.AIAction]) -> list[schemas.AIAction]:
        seen: set[tuple[str, int | None]] = set()
        out: list[schemas.AIAction] = []
        for a in vals:
            key = (str(a.type or ""), action_med_id(a))
            if key in seen:
                continue
            seen.add(key)
            out.append(a)
        return out

    def ensure_add_to_cart_ids(vals: list[schemas.AIAction]) -> list[schemas.AIAction]:
        out: list[schemas.AIAction] = []
        for a in vals:
            if a.type == "add_to_cart" and med_id and action_med_id(a) is None:
                out.append(
                    schemas.AIAction(
                        type="add_to_cart",
                        label=a.label or "Add to cart",
                        medicine_id=med_id,
                        payload={"medicine_id": med_id, "quantity": 1},
                    )
                )
            else:
                out.append(a)
        return out

    if rx is True:
        filtered = [a for a in actions if a.type != "add_to_cart"]
        if not any(a.type == "upload_prescription" for a in filtered):
            if med_id:
                filtered.append(
                    schemas.AIAction(
                        type="upload_prescription",
                        label="Upload prescription",
                        medicine_id=med_id,
                        payload={"medicine_id": med_id},
                    )
                )
        return dedupe(filtered)

    if stock is not None and stock <= 0:
        return dedupe([a for a in actions if a.type != "add_to_cart"])

    if med_id and stock is not None and stock > 0 and not any(a.type == "add_to_cart" for a in actions):
        actions = actions + [
            schemas.AIAction(
                type="add_to_cart",
                label="Add to cart",
                medicine_id=med_id,
                payload={"medicine_id": med_id, "quantity": 1},
            )
        ]
    return dedupe(ensure_add_to_cart_ids(actions))


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
    requested_session_id = (payload.session_id or "").strip() or None

    try:
        get_ai_provider()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI provider is not configured: {exc}",
        ) from exc

    session = get_or_create_session(db, pharmacy_id, customer_id, requested_session_id)
    session_id = session.session_id
    system_message: str | None = None

    add_message(db, session, "USER", message)

    if session.status == "ESCALATED":
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
        session_memory.append_turns(db, pharmacy_id, session_id, message, answer)
        return schemas.AIChatOut(
            interaction_id=interaction.id,
            customer_id=customer_id,
            session_id=session_id,
            answer=answer,
            citations=[],
            cards=[],
            actions=[],
            quick_replies=[],
            confidence_score=0.0,
            escalated_to_human=True,
            intent="RISKY_MEDICAL",
            created_at=interaction.created_at,
            data_last_updated_at=None,
            indexed_at=None,
            system_message=None,
        )

    try:
        rag_service.ensure_pharmacy_playbook(db, pharmacy_id)
        db.commit()
        triage = _maybe_handle_headache_triage(db, pharmacy_id, customer_id, session, message)
        if triage is not None:
            session_memory.append_turns(db, pharmacy_id, session_id, message, triage.answer)
            return triage
        triage = _maybe_handle_abdominal_pain_triage(db, pharmacy_id, customer_id, session, message)
        if triage is not None:
            session_memory.append_turns(db, pharmacy_id, session_id, message, triage.answer)
            return triage
        is_risky, reason = detect_risk(message)
        if is_risky:
            answer = (
                "This may require a pharmacist. Tap 'Escalate to pharmacist' to start a consultation, "
                "or ask a general non-urgent question."
            )
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
            add_message(
                db,
                session,
                "AI",
                interaction.ai_response,
                _build_ai_metadata(
                    intent="RISKY_MEDICAL",
                    actions=[schemas.AIAction(type="escalate_to_pharmacist", label="Escalate to pharmacist")],
                    cards=[],
                    quick_replies=[],
                    data_last_updated_at=None,
                    indexed_at=None,
                ),
            )
            session_memory.append_turns(db, pharmacy_id, session_id, message, interaction.ai_response)
            _log(db, pharmacy_id, "chat", f"chat_id={customer_id} confidence=0.00 escalated=True rag_top_k=0 retrieved_chunks=[]")
            _log(db, pharmacy_id, "escalation", f"interaction_id={interaction.id} chat_id={customer_id} pending_intake=1")
            db.commit()
            return schemas.AIChatOut(
                interaction_id=interaction.id,
                customer_id=customer_id,
                session_id=session_id,
                answer=interaction.ai_response,
                citations=[],
                cards=[],
                actions=[schemas.AIAction(type="escalate_to_pharmacist", label="Escalate to pharmacist")],
                quick_replies=[],
                confidence_score=interaction.confidence_score,
                escalated_to_human=interaction.escalated_to_human,
                intent="RISKY_MEDICAL",
                created_at=interaction.created_at,
                data_last_updated_at=None,
                indexed_at=None,
                system_message=system_message,
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
        answer = (gen.answer or "").strip()
        if immediate_answer and (not answer or answer.lower().startswith("assistant temporarily unavailable")):
            answer = immediate_answer
        elif not answer:
            answer = immediate_answer or ""
        if tool_ctx.intent == "RISKY_MEDICAL" or router.intent == "RISKY_MEDICAL":
            answer = "A pharmacist will reply shortly. If this is urgent, please seek medical care."
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
        actions = _enforce_action_policy(tool_ctx, actions or [])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    escalated = bool(tool_ctx.escalated or gen.escalated)
    interaction = models.AIInteraction(
        customer_id=customer_id,
        customer_query=message,
        ai_response=answer,
        confidence_score=float(gen.confidence if gen.answer else 0.0),
        escalated_to_human=escalated,
        created_at=datetime.utcnow(),
        pharmacy_id=pharmacy_id,
    )
    db.add(interaction)
    db.flush()
    if escalated:
        session.status = "ESCALATED"
        system_message = ESCALATION_SYSTEM_MESSAGE
        add_message(db, session, "SYSTEM", system_message, {"kind": "escalation"})
    add_message(
        db,
        session,
        "AI",
        answer,
        _build_ai_metadata(
            intent=tool_ctx.intent,
            actions=actions,
            cards=tool_ctx.cards or [],
            quick_replies=(gen.quick_replies or tool_ctx.quick_replies or []),
            data_last_updated_at=tool_ctx.data_last_updated_at,
            indexed_at=tool_ctx.indexed_at,
        ),
    )
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
        system_message=system_message,
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
