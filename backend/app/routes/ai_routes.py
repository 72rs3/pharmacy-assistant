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
from app.chat_sessions import add_message, get_or_create_session
from app.ai.tri_model_router import RouterIntent, route_intent
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
]

_ABDOMINAL_PAIN_PATTERN = re.compile(
    r"\b(stomach pain|stomac[k]?\s*(pain|ain)|stomach\s*ain|stomach ache|stomac[k]?\s*ache|abdominal pain|belly pain|tummy ache|stomach cramps|cramps)\b",
    re.IGNORECASE,
)
_ABDOMINAL_REDFLAG_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(severe|unbearable|worst)\b", re.IGNORECASE), "severe pain"),
    (re.compile(r"\b(sudden(ly)?|came on suddenly)\b", re.IGNORECASE), "sudden onset"),
    (re.compile(r"\b(vomiting blood|blood in vomit|hematemesis)\b", re.IGNORECASE), "vomiting blood"),
    (re.compile(r"\b(blood in stool|bloody stool|black stool|tarry stool)\b", re.IGNORECASE), "blood/black stool"),
    (re.compile(r"\b(faint(ing|ed)?|passed out|confusion|unconscious)\b", re.IGNORECASE), "fainting/confusion"),
    (re.compile(r"\b(high fever|fever|rigid abdomen|hard belly)\b", re.IGNORECASE), "fever/rigid abdomen"),
]

_URGENT_REDFLAG_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(chest pain|pressure in (my )?chest)\b", re.IGNORECASE), "chest pain"),
    (re.compile(r"\b(shortness of breath|trouble breathing|can't breathe)\b", re.IGNORECASE), "breathing difficulty"),
    (re.compile(r"\b(seizure|convulsion)\b", re.IGNORECASE), "seizure"),
    (re.compile(r"\b(unconscious|not conscious)\b", re.IGNORECASE), "unconsciousness"),
    (re.compile(r"\b(faint(ing|ed)?|passed out)\b", re.IGNORECASE), "fainting"),
    (re.compile(r"\b(overdose|poison(ing)?|took too much)\b", re.IGNORECASE), "overdose/poisoning"),
    (re.compile(r"\b(anaphylaxis|throat closing|severe allergic)\b", re.IGNORECASE), "severe allergic reaction"),
    (re.compile(r"\b(face swelling|lip swelling|tongue swelling)\b", re.IGNORECASE), "possible anaphylaxis"),
    (re.compile(r"\b(heavy bleeding|bleeding a lot|won't stop bleeding)\b", re.IGNORECASE), "heavy bleeding"),
    (re.compile(r"\bbleeding\b", re.IGNORECASE), "bleeding"),
    (re.compile(r"\b(vomiting blood|blood in vomit|black stool|tarry stool|blood in stool|bloody stool)\b", re.IGNORECASE), "GI bleeding"),
    (re.compile(r"\b(pregnan(t|cy))\b.*\b(bleed|bleeding)\b|\b(bleed|bleeding)\b.*\b(pregnan(t|cy))\b", re.IGNORECASE), "pregnancy with bleeding"),
    (re.compile(r"\b(pregnan(t|cy))\b.*\b(severe|unbearable|worst)\b", re.IGNORECASE), "pregnancy with severe pain"),
]

_SEARCH_AGAIN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*another\s+medicine\s*$", re.IGNORECASE),
    re.compile(r"^\s*search\s+another\s+medicine\s*$", re.IGNORECASE),
    re.compile(r"^\s*search\s+medicine\s*$", re.IGNORECASE),
    re.compile(r"^\s*search\s+for\s+a?\s*medicine\s*$", re.IGNORECASE),
    re.compile(r"^\s*find\s+a?\s*medicine\s*$", re.IGNORECASE),
    re.compile(r"^\s*medicine\s+search\s*$", re.IGNORECASE),
    re.compile(r"^\s*search\s+(for\s+)?pain\s+relief\b.*$", re.IGNORECASE),
    re.compile(r"^\s*search\s+(for\s+)?pain\s*kill(er|ers)?\b.*$", re.IGNORECASE),
    re.compile(r"^\s*search\s+(for\s+)?antibiotic(s)?\b.*$", re.IGNORECASE),
    re.compile(r"^\s*pain\s+relief\b.*$", re.IGNORECASE),
    re.compile(r"^\s*pain\s*kill(er|ers)?\b.*$", re.IGNORECASE),
    re.compile(r"^\s*antibiotic(s)?\b.*$", re.IGNORECASE),
]

_LAST_MEDICINES_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(what|which)\b.*\b(medicine|medicines|meds)\b.*\b(asked|requested|mentioned|searched|looking)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+did\s+i\s+ask\s+for\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+meds\s+did\s+i\s+ask\s+for\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+medicines\s+did\s+i\s+ask\s+for\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+did\s+i\s+(just\s+)?look\s+at\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+did\s+i\s+(just\s+)?view\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+did\s+i\s+(just\s+)?check\b", re.IGNORECASE),
]

_MSK_PAIN_PATTERN = re.compile(
    r"\b("
    r"(hand|arm|leg|knee|ankle|foot|feet|hip|shoulder|back|wrist|elbow|neck)"
    r")\b.*\b(hurt|hurting|pain|ache|sore)\b|\b(hurt|hurting|pain|ache|sore)\b.*\b("
    r"hand|arm|leg|knee|ankle|foot|feet|hip|shoulder|back|wrist|elbow|neck"
    r")\b",
    re.IGNORECASE,
)

_DIARRHEA_PATTERN = re.compile(r"\b(diarrh(ea|oea)|dierria|loose stool|loose stools)\b", re.IGNORECASE)
_DIZZY_PATTERN = re.compile(r"\b(dizzy|dizziness|lightheaded|light-headed)\b", re.IGNORECASE)


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


def _looks_like_msk_pain(text: str) -> bool:
    msg = text or ""
    if not msg:
        return False
    # Avoid overlapping triage topics.
    if _looks_like_headache(msg) or _looks_like_abdominal_pain(msg):
        return False
    return bool(_MSK_PAIN_PATTERN.search(msg))


def _looks_like_diarrhea(text: str) -> bool:
    return bool(_DIARRHEA_PATTERN.search(text or ""))


def _looks_like_dizzy(text: str) -> bool:
    return bool(_DIZZY_PATTERN.search(text or ""))


def _urgent_red_flags(text: str) -> list[str]:
    msg = text or ""
    found: list[str] = []
    for pattern, label in _URGENT_REDFLAG_PATTERNS:
        if pattern.search(msg):
            found.append(label)
    return found


def _maybe_handle_urgent_red_flags(
    db: Session,
    pharmacy_id: int,
    customer_id: str,
    session: models.ChatSession,
    user_text: str,
):
    red_flags = _urgent_red_flags(user_text)
    if not red_flags:
        return None

    triage_action = schemas.AIAction(type="escalate_to_pharmacist", label="Talk to pharmacist")
    answer = (
        "Your message may describe an urgent situation. "
        "If you are in immediate danger or symptoms are severe/worsening, call your local emergency number now. "
        "If you can, you can also start a pharmacist consultation here for guidance."
    )
    interaction = models.AIInteraction(
        customer_id=customer_id,
        customer_query=user_text,
        ai_response=answer,
        confidence_score=0.0,
        escalated_to_human=False,
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
        answer,
        _build_ai_metadata(
            intent="URGENT_REDFLAG",
            actions=[triage_action],
            cards=[],
            quick_replies=[],
            data_last_updated_at=None,
            indexed_at=None,
        ),
    )
    db.commit()
    return schemas.AIChatOut(
        interaction_id=interaction.id,
        customer_id=customer_id,
        session_id=session.session_id,
        answer=answer,
        citations=[],
        cards=[],
        actions=[triage_action],
        quick_replies=[],
        confidence_score=interaction.confidence_score,
        escalated_to_human=False,
        intent="URGENT_REDFLAG",
        created_at=interaction.created_at,
        data_last_updated_at=None,
        indexed_at=None,
        system_message=None,
    )


def _parse_severity_1_to_10(text: str) -> int | None:
    match = re.search(r"\b(10|[1-9])\b", (text or ""))
    if not match:
        return None
    try:
        value = int(match.group(1))
    except Exception:
        return None
    return value if 1 <= value <= 10 else None


def _parse_severity_bucket(text: str) -> dict | None:
    msg = (text or "").strip().lower()
    if not msg:
        return None

    if "1-3" in msg or "1 - 3" in msg or "mild" in msg:
        return {"label": "mild", "min": 1, "max": 3, "score": 2}
    if "4-7" in msg or "4 - 7" in msg or "moderate" in msg:
        return {"label": "moderate", "min": 4, "max": 7, "score": 5}
    if "8-10" in msg or "8 - 10" in msg or "severe" in msg:
        return {"label": "severe", "min": 8, "max": 10, "score": 9}

    score = _parse_severity_1_to_10(text)
    if score is None:
        return None
    if score <= 3:
        return {"label": "mild", "min": 1, "max": 3, "score": score}
    if score <= 7:
        return {"label": "moderate", "min": 4, "max": 7, "score": score}
    return {"label": "severe", "min": 8, "max": 10, "score": score}


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


def _filter_quick_replies(actions: list[schemas.AIAction] | None, quick_replies: list[str] | None) -> list[str]:
    out = list(quick_replies or [])
    if not out:
        return []
    if actions and any((a.type or "") == "escalate_to_pharmacist" for a in actions):
        banned = {"talk to pharmacist", "escalate to pharmacist"}
        out = [qr for qr in out if str(qr or "").strip().lower() not in banned]
    return out


def _top_medicine_names(db: Session, pharmacy_id: int, limit: int = 6) -> list[str]:
    rows = (
        db.query(models.Medicine)
        .filter(models.Medicine.pharmacy_id == pharmacy_id)
        .order_by(models.Medicine.stock_level.desc().nullslast(), models.Medicine.updated_at.desc().nullslast())
        .limit(limit)
        .all()
    )
    names: list[str] = []
    for row in rows:
        name = str(getattr(row, "name", "") or "").strip()
        if not name:
            continue
        if name.lower() in {n.lower() for n in names}:
            continue
        names.append(name)
    return names


def _maybe_handle_search_again(
    db: Session,
    pharmacy_id: int,
    customer_id: str,
    session: models.ChatSession,
    user_text: str,
):
    msg = (user_text or "").strip()
    if not msg:
        return None
    if not any(p.search(msg) for p in _SEARCH_AGAIN_PATTERNS):
        return None

    suggestions = _top_medicine_names(db, pharmacy_id, limit=6)
    quick_replies = [f"Search {name}" for name in suggestions] if suggestions else []
    if not quick_replies:
        quick_replies = ["Search panadol", "Search paracetamol", "Search ibuprofen"]

    answer = "Sure - what medicine name should I search for? (Example: Panadol 500mg)"
    interaction = models.AIInteraction(
        customer_id=customer_id,
        customer_query=msg,
        ai_response=answer,
        confidence_score=0.0,
        escalated_to_human=False,
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
        answer,
        _build_ai_metadata(
            intent="MEDICINE_SEARCH_PROMPT",
            actions=[],
            cards=[],
            quick_replies=quick_replies,
            data_last_updated_at=None,
            indexed_at=None,
        ),
    )
    db.commit()
    return schemas.AIChatOut(
        interaction_id=interaction.id,
        customer_id=customer_id,
        session_id=session.session_id,
        answer=answer,
        citations=[],
        cards=[],
        actions=[],
        quick_replies=quick_replies,
        confidence_score=interaction.confidence_score,
        escalated_to_human=False,
        intent="MEDICINE_SEARCH_PROMPT",
        created_at=interaction.created_at,
        data_last_updated_at=None,
        indexed_at=None,
        system_message=None,
    )


def _maybe_handle_last_medicines(
    db: Session,
    pharmacy_id: int,
    customer_id: str,
    session: models.ChatSession,
    user_text: str,
):
    msg = (user_text or "").strip()
    if not msg:
        return None
    if not any(p.search(msg) for p in _LAST_MEDICINES_PATTERNS):
        return None

    turns = session_memory.load_turns(db, pharmacy_id, session.session_id)
    state = session_memory.get_state(turns, "last_search_results") or {}
    items = state.get("items") if isinstance(state, dict) else None
    if not items:
        state = session_memory.get_state(turns, "last_medicines") or {}
        items = state.get("items") if isinstance(state, dict) else None

    if not items:
        answer = "I don't have any recent medicine searches yet. Tell me the medicine name(s) you want."
        quick_replies = ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"]
    else:
        lines: list[str] = []
        for item in items:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            dosage = item.get("dosage")
            entry_type = str(item.get("type") or "medicine").lower()
            suffix = " (product)" if entry_type == "product" else ""
            if dosage:
                lines.append(f"- {name} ({dosage}){suffix}")
            else:
                lines.append(f"- {name}{suffix}")
        answer = "You asked about:\n" + "\n".join(lines) if lines else "I don't have any recent medicine searches yet."
        quick_replies = ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"]

    interaction = models.AIInteraction(
        customer_id=customer_id,
        customer_query=msg,
        ai_response=answer,
        confidence_score=0.0,
        escalated_to_human=False,
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
        answer,
        _build_ai_metadata(
            intent="MEDICINE_HISTORY",
            actions=[],
            cards=[],
            quick_replies=quick_replies,
            data_last_updated_at=None,
            indexed_at=None,
        ),
    )
    db.commit()
    return schemas.AIChatOut(
        interaction_id=interaction.id,
        customer_id=customer_id,
        session_id=session.session_id,
        answer=answer,
        citations=[],
        cards=[],
        actions=[],
        quick_replies=quick_replies,
        confidence_score=interaction.confidence_score,
        escalated_to_human=False,
        intent="MEDICINE_HISTORY",
        created_at=interaction.created_at,
        data_last_updated_at=None,
        indexed_at=None,
        system_message=None,
    )


def _maybe_handle_headache_triage(db: Session, pharmacy_id: int, customer_id: str, session: models.ChatSession, user_text: str):
    triage_action = schemas.AIAction(type="escalate_to_pharmacist", label="Talk to pharmacist")

    last_ai = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session.id, models.ChatMessage.sender_type == "AI")
        .order_by(models.ChatMessage.created_at.desc())
        .first()
    )
    last_intent = ""
    prior_triage: dict = {}
    if last_ai and isinstance(last_ai.meta, dict):
        last_intent = str(last_ai.meta.get("intent") or "")
        triage_blob = last_ai.meta.get("triage")
        if isinstance(triage_blob, dict):
            prior_triage = dict(triage_blob)

    is_in_flow = last_intent.startswith("HEADACHE_TRIAGE_")
    is_new_headache = _looks_like_headache(user_text)
    if not is_in_flow and not is_new_headache:
        return None

    red_flags_now = _headache_red_flags(user_text)

    def respond(text: str, *, intent: str, quick_replies: list[str] | None = None, triage: dict | None = None):
        filtered_quick_replies = _filter_quick_replies([triage_action], quick_replies)
        interaction = models.AIInteraction(
            customer_id=customer_id,
            customer_query=user_text,
            ai_response=text,
            confidence_score=0.0,
            escalated_to_human=False,
            created_at=datetime.utcnow(),
            pharmacy_id=pharmacy_id,
        )
        db.add(interaction)
        db.commit()
        db.refresh(interaction)
        meta = _build_ai_metadata(
            intent=intent,
            actions=[triage_action],
            cards=[],
            quick_replies=filtered_quick_replies,
            data_last_updated_at=None,
            indexed_at=None,
        )
        if triage:
            meta["triage"] = triage
        add_message(
            db,
            session,
            "AI",
            text,
            meta,
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
            quick_replies=filtered_quick_replies,
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
            quick_replies=[],
        )

    if last_intent == "HEADACHE_TRIAGE_SEVERITY":
        severity = _parse_severity_bucket(user_text)
        if severity is None:
            return respond(
                "On a scale of 1-10, how severe is your headache right now? (1 = mild, 10 = worst)",
                intent="HEADACHE_TRIAGE_SEVERITY",
                quick_replies=["1-3 (mild)", "4-7 (moderate)", "8-10 (severe)"],
            )
        next_triage = {**prior_triage, "topic": "headache", "severity": severity}
        return respond(
            "How long have you had this headache?",
            intent="HEADACHE_TRIAGE_DURATION",
            quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
            triage=next_triage,
        )

    if last_intent == "HEADACHE_TRIAGE_DURATION":
        bucket = _parse_duration_bucket(user_text)
        if not bucket:
            return respond(
                "How long have you had this headache?",
                intent="HEADACHE_TRIAGE_DURATION",
                quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
            )
        next_triage = {**prior_triage, "topic": "headache", "duration": bucket}
        return respond(
            (
                "Do you have any of these right now: fever, stiff neck, vision changes, confusion/fainting, "
                "weakness/numbness, or a recent head injury?"
            ),
            intent="HEADACHE_TRIAGE_REDFLAGS",
            quick_replies=["No", "Yes"],
            triage=next_triage,
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
                quick_replies=[],
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
        severity_label = ""
        severity_score: int | None = None
        triage_severity = prior_triage.get("severity") if isinstance(prior_triage, dict) else None
        if isinstance(triage_severity, dict):
            severity_label = str(triage_severity.get("label") or "")
            try:
                severity_score = int(triage_severity.get("score")) if triage_severity.get("score") is not None else None
            except Exception:
                severity_score = None
        duration_bucket = str(prior_triage.get("duration") or "")

        if severity_label == "severe" or (severity_score is not None and severity_score >= 8) or duration_bucket == ">3 days":
            return respond(
                (
                    "Because your headache is severe or has lasted longer than a couple of days, it's best to speak with a pharmacist. "
                    "In the meantime: rest, drink water, and avoid bright screens. If symptoms worsen, become sudden/severe, or you develop "
                    "new warning signs (fever, stiff neck, vision changes, fainting/confusion, weakness/numbness), seek urgent medical care."
                ),
                intent="HEADACHE_GUIDANCE_SEVERE",
                quick_replies=["Search panadol"],
            )

        if severity_label == "moderate" or (severity_score is not None and 4 <= severity_score <= 7):
            return respond(
                (
                    "For moderate headaches without warning signs: rest, drink water, and avoid triggers like bright screens. "
                    "If you'd like, you can check common OTC options (for example, paracetamol) and follow the label. "
                    "If it doesn't improve, keeps returning, or you're unsure, please talk to a pharmacist."
                ),
                intent="HEADACHE_GUIDANCE_MODERATE",
                quick_replies=["Search panadol"],
            )

        return respond(
            (
                "For mild headaches with no concerning symptoms: rest, drink water, and avoid bright screens. "
                "If you want, you can look for common OTC options (e.g., paracetamol) - always follow the label. "
                "If symptoms persist, worsen, or you're unsure, please talk to a pharmacist."
            ),
            intent="HEADACHE_SELFCARE",
            quick_replies=["Search panadol"],
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
    prior_triage: dict = {}
    if last_ai and isinstance(last_ai.meta, dict):
        last_intent = str(last_ai.meta.get("intent") or "")
        triage_blob = last_ai.meta.get("triage")
        if isinstance(triage_blob, dict):
            prior_triage = dict(triage_blob)

    is_in_flow = last_intent.startswith("ABDOMINAL_TRIAGE_")
    is_new = _looks_like_abdominal_pain(user_text)
    if not is_in_flow and not is_new:
        return None

    red_flags_now = _abdominal_red_flags(user_text)

    def respond(text: str, *, intent: str, quick_replies: list[str] | None = None, triage: dict | None = None):
        filtered_quick_replies = _filter_quick_replies([triage_action], quick_replies)
        interaction = models.AIInteraction(
            customer_id=customer_id,
            customer_query=user_text,
            ai_response=text,
            confidence_score=0.0,
            escalated_to_human=False,
            created_at=datetime.utcnow(),
            pharmacy_id=pharmacy_id,
        )
        db.add(interaction)
        db.commit()
        db.refresh(interaction)
        meta = _build_ai_metadata(
            intent=intent,
            actions=[triage_action],
            cards=[],
            quick_replies=filtered_quick_replies,
            data_last_updated_at=None,
            indexed_at=None,
        )
        if triage:
            meta["triage"] = triage
        add_message(
            db,
            session,
            "AI",
            text,
            meta,
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
            quick_replies=filtered_quick_replies,
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
            quick_replies=[],
        )

    if last_intent == "ABDOMINAL_TRIAGE_SEVERITY":
        severity = _parse_severity_bucket(user_text)
        if severity is None:
            return respond(
                "On a scale of 1-10, how severe is your stomach/abdominal pain right now? (1 = mild, 10 = worst)",
                intent="ABDOMINAL_TRIAGE_SEVERITY",
                quick_replies=["1-3 (mild)", "4-7 (moderate)", "8-10 (severe)"],
            )
        next_triage = {**prior_triage, "topic": "abdominal", "severity": severity}
        return respond(
            "How long have you had this pain?",
            intent="ABDOMINAL_TRIAGE_DURATION",
            quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
            triage=next_triage,
        )

    if last_intent == "ABDOMINAL_TRIAGE_DURATION":
        bucket = _parse_duration_bucket(user_text)
        if not bucket:
            return respond(
                "How long have you had this pain?",
                intent="ABDOMINAL_TRIAGE_DURATION",
                quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
            )
        next_triage = {**prior_triage, "topic": "abdominal", "duration": bucket}
        return respond(
            (
                "Any of these right now: fever, vomiting repeatedly, blood in vomit/stool, black stools, "
                "fainting/confusion, pregnancy, or severe worsening pain?"
            ),
            intent="ABDOMINAL_TRIAGE_REDFLAGS",
            quick_replies=["No", "Yes"],
            triage=next_triage,
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
                quick_replies=[],
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
        severity_label = ""
        severity_score: int | None = None
        triage_severity = prior_triage.get("severity") if isinstance(prior_triage, dict) else None
        if isinstance(triage_severity, dict):
            severity_label = str(triage_severity.get("label") or "")
            try:
                severity_score = int(triage_severity.get("score")) if triage_severity.get("score") is not None else None
            except Exception:
                severity_score = None
        duration_bucket = str(prior_triage.get("duration") or "")

        if severity_label == "severe" or (severity_score is not None and severity_score >= 8) or duration_bucket == ">3 days":
            return respond(
                (
                    "Because your abdominal pain is severe or has lasted more than a couple of days, it's best to speak with a pharmacist. "
                    "If symptoms worsen or you develop warning signs (fever, repeated vomiting, blood/black stools, fainting/confusion), seek urgent medical care."
                ),
                intent="ABDOMINAL_GUIDANCE_SEVERE",
                quick_replies=[],
            )

        if severity_label == "moderate" or (severity_score is not None and 4 <= severity_score <= 7):
            return respond(
                (
                    "For moderate abdominal discomfort with no warning signs: sip water, eat light foods, and rest. "
                    "If it doesn't improve, keeps returning, or you're unsure, please talk to a pharmacist."
                ),
                intent="ABDOMINAL_GUIDANCE_MODERATE",
                quick_replies=[],
            )

        return respond(
            (
                "For mild abdominal discomfort with no red flags: sip water, eat light foods, and rest. "
                "If symptoms persist, worsen, or you're unsure, please talk to a pharmacist."
            ),
            intent="ABDOMINAL_SELFCARE",
            quick_replies=[],
        )

    return respond(
        "On a scale of 1-10, how severe is your stomach/abdominal pain right now? (1 = mild, 10 = worst)",
        intent="ABDOMINAL_TRIAGE_SEVERITY",
        quick_replies=["1-3 (mild)", "4-7 (moderate)", "8-10 (severe)"],
    )


def _maybe_handle_msk_pain_triage(
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
    prior_triage: dict = {}
    if last_ai and isinstance(last_ai.meta, dict):
        last_intent = str(last_ai.meta.get("intent") or "")
        triage_blob = last_ai.meta.get("triage")
        if isinstance(triage_blob, dict):
            prior_triage = dict(triage_blob)

    is_in_flow = last_intent.startswith("MSK_TRIAGE_")
    is_new = _looks_like_msk_pain(user_text)
    if not is_in_flow and not is_new:
        return None

    def respond(text: str, *, intent: str, quick_replies: list[str] | None = None, triage: dict | None = None):
        filtered_quick_replies = _filter_quick_replies([triage_action], quick_replies)
        interaction = models.AIInteraction(
            customer_id=customer_id,
            customer_query=user_text,
            ai_response=text,
            confidence_score=0.0,
            escalated_to_human=False,
            created_at=datetime.utcnow(),
            pharmacy_id=pharmacy_id,
        )
        db.add(interaction)
        db.commit()
        db.refresh(interaction)
        meta = _build_ai_metadata(
            intent=intent,
            actions=[triage_action],
            cards=[],
            quick_replies=filtered_quick_replies,
            data_last_updated_at=None,
            indexed_at=None,
        )
        if triage:
            meta["triage"] = triage
        add_message(db, session, "AI", text, meta)
        db.commit()
        return schemas.AIChatOut(
            interaction_id=interaction.id,
            customer_id=customer_id,
            session_id=session.session_id,
            answer=text,
            citations=[],
            cards=[],
            actions=[triage_action],
            quick_replies=filtered_quick_replies,
            confidence_score=interaction.confidence_score,
            escalated_to_human=interaction.escalated_to_human,
            intent=intent,
            created_at=interaction.created_at,
            data_last_updated_at=None,
            indexed_at=None,
            system_message=None,
        )

    if last_intent == "MSK_TRIAGE_SEVERITY" or is_new:
        severity = _parse_severity_bucket(user_text) if last_intent == "MSK_TRIAGE_SEVERITY" else None
        if severity is None:
            return respond(
                "On a scale of 1-10, how severe is your pain right now? (1 = mild, 10 = worst)",
                intent="MSK_TRIAGE_SEVERITY",
                quick_replies=["1-3 (mild)", "4-7 (moderate)", "8-10 (severe)"],
                triage={**prior_triage, "topic": "msk"},
            )
        next_triage = {**prior_triage, "topic": "msk", "severity": severity}
        return respond(
            "How long have you had this pain?",
            intent="MSK_TRIAGE_DURATION",
            quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
            triage=next_triage,
        )

    if last_intent == "MSK_TRIAGE_DURATION":
        bucket = _parse_duration_bucket(user_text)
        if not bucket:
            return respond(
                "How long have you had this pain?",
                intent="MSK_TRIAGE_DURATION",
                quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
                triage=prior_triage,
            )
        next_triage = {**prior_triage, "topic": "msk", "duration": bucket}
        return respond(
            "Did this start after an injury or accident (fall/twist), or is there noticeable swelling/redness?",
            intent="MSK_TRIAGE_INJURY",
            quick_replies=["No", "Yes"],
            triage=next_triage,
        )

    if last_intent == "MSK_TRIAGE_INJURY":
        injury = _is_affirmative(user_text) and not _is_negative(user_text)
        next_triage = {**prior_triage, "topic": "msk", "injury": bool(injury)}
        return respond(
            "Any of these right now: severe swelling/deformity, inability to move or bear weight, numbness/weakness, fever, or an open wound?",
            intent="MSK_TRIAGE_REDFLAGS",
            quick_replies=["No", "Yes"],
            triage=next_triage,
        )

    if last_intent == "MSK_TRIAGE_REDFLAGS":
        has_flags = _is_affirmative(user_text) and not _is_negative(user_text)
        if has_flags:
            return respond(
                (
                    "Those symptoms can be serious. Please start a pharmacist consultation now. "
                    "If there is severe injury, uncontrolled bleeding, or you can't move the limb, seek urgent medical care."
                ),
                intent="MSK_REDFLAG",
                quick_replies=[],
                triage=prior_triage,
            )

        triage_severity = prior_triage.get("severity") if isinstance(prior_triage, dict) else None
        severity_label = str(triage_severity.get("label") or "") if isinstance(triage_severity, dict) else ""
        duration_bucket = str(prior_triage.get("duration") or "")
        injury = bool(prior_triage.get("injury")) if isinstance(prior_triage, dict) else False
        severity_score: int | None = None
        if isinstance(triage_severity, dict) and triage_severity.get("score") is not None:
            try:
                severity_score = int(triage_severity.get("score"))
            except Exception:
                severity_score = None

        if severity_label == "severe" or (severity_score is not None and severity_score >= 8) or duration_bucket == ">3 days" or injury:
            return respond(
                (
                    "Because the pain is severe, persistent, or started after an injury, it's best to speak with a pharmacist. "
                    "In the meantime: rest the area, avoid activities that worsen it, and consider cold packs for short periods. "
                    "If you choose an OTC pain reliever, follow the label and ask a pharmacist if it's safe for you."
                ),
                intent="MSK_GUIDANCE_SEVERE",
                quick_replies=["Search paracetamol"],
                triage=prior_triage,
            )
        if severity_label == "moderate" or (severity_score is not None and 4 <= severity_score <= 7):
            return respond(
                (
                    "For moderate pain with no warning signs: rest the area, avoid overuse, and consider cold packs for short periods. "
                    "If it doesn't improve, keeps returning, or you're unsure what to take, please talk to a pharmacist."
                ),
                intent="MSK_GUIDANCE_MODERATE",
                quick_replies=["Search paracetamol"],
                triage=prior_triage,
            )
        return respond(
            (
                "For mild pain with no warning signs: rest the area and avoid overuse. "
                "If it worsens or doesn't improve, please talk to a pharmacist."
            ),
            intent="MSK_GUIDANCE_MILD",
            quick_replies=["Search paracetamol"],
            triage=prior_triage,
        )

    return respond(
        "On a scale of 1-10, how severe is your pain right now? (1 = mild, 10 = worst)",
        intent="MSK_TRIAGE_SEVERITY",
        quick_replies=["1-3 (mild)", "4-7 (moderate)", "8-10 (severe)"],
        triage={**prior_triage, "topic": "msk"},
    )


def _maybe_handle_diarrhea_triage(
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
    prior_triage: dict = {}
    if last_ai and isinstance(last_ai.meta, dict):
        last_intent = str(last_ai.meta.get("intent") or "")
        triage_blob = last_ai.meta.get("triage")
        if isinstance(triage_blob, dict):
            prior_triage = dict(triage_blob)

    is_in_flow = last_intent.startswith("DIARRHEA_TRIAGE_")
    is_new = _looks_like_diarrhea(user_text)
    if not is_in_flow and not is_new:
        return None

    def respond(text: str, *, intent: str, quick_replies: list[str] | None = None, triage: dict | None = None):
        filtered_quick_replies = _filter_quick_replies([triage_action], quick_replies)
        interaction = models.AIInteraction(
            customer_id=customer_id,
            customer_query=user_text,
            ai_response=text,
            confidence_score=0.0,
            escalated_to_human=False,
            created_at=datetime.utcnow(),
            pharmacy_id=pharmacy_id,
        )
        db.add(interaction)
        db.commit()
        db.refresh(interaction)
        meta = _build_ai_metadata(
            intent=intent,
            actions=[triage_action],
            cards=[],
            quick_replies=filtered_quick_replies,
            data_last_updated_at=None,
            indexed_at=None,
        )
        if triage:
            meta["triage"] = triage
        add_message(db, session, "AI", text, meta)
        db.commit()
        return schemas.AIChatOut(
            interaction_id=interaction.id,
            customer_id=customer_id,
            session_id=session.session_id,
            answer=text,
            citations=[],
            cards=[],
            actions=[triage_action],
            quick_replies=filtered_quick_replies,
            confidence_score=interaction.confidence_score,
            escalated_to_human=interaction.escalated_to_human,
            intent=intent,
            created_at=interaction.created_at,
            data_last_updated_at=None,
            indexed_at=None,
            system_message=None,
        )

    if last_intent == "DIARRHEA_TRIAGE_DURATION" or is_new:
        bucket = _parse_duration_bucket(user_text) if last_intent == "DIARRHEA_TRIAGE_DURATION" else None
        if bucket is None:
            return respond(
                "How long have you had diarrhea?",
                intent="DIARRHEA_TRIAGE_DURATION",
                quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
                triage={**prior_triage, "topic": "diarrhea"},
            )
        next_triage = {**prior_triage, "topic": "diarrhea", "duration": bucket}
        return respond(
            "Any of these right now: blood in stool, fever, severe abdominal pain, or signs of dehydration (very thirsty, dizziness, not urinating)?",
            intent="DIARRHEA_TRIAGE_REDFLAGS",
            quick_replies=["No", "Yes"],
            triage=next_triage,
        )

    if last_intent == "DIARRHEA_TRIAGE_REDFLAGS":
        has_flags = _is_affirmative(user_text) and not _is_negative(user_text)
        if has_flags:
            return respond(
                (
                    "Those symptoms can be serious. Please start a pharmacist consultation now. "
                    "If symptoms are severe or worsening, seek urgent medical care."
                ),
                intent="DIARRHEA_REDFLAG",
                quick_replies=[],
                triage=prior_triage,
            )
        duration_bucket = str(prior_triage.get("duration") or "")
        if duration_bucket in {">3 days"}:
            return respond(
                (
                    "Because it has lasted several days, it's best to speak with a pharmacist. "
                    "Until then: drink fluids frequently (oral rehydration if available) and eat light foods. "
                    "Seek care if you develop blood in stool, high fever, or signs of dehydration."
                ),
                intent="DIARRHEA_GUIDANCE_PERSISTENT",
                quick_replies=[],
                triage=prior_triage,
            )
        return respond(
            (
                "For mild diarrhea with no warning signs: drink fluids frequently (oral rehydration if available) and eat light foods. "
                "If it worsens, doesn't improve, or you're unsure, please talk to a pharmacist."
            ),
            intent="DIARRHEA_SELFCARE",
            quick_replies=[],
            triage=prior_triage,
        )

    return respond(
        "How long have you had diarrhea?",
        intent="DIARRHEA_TRIAGE_DURATION",
        quick_replies=["<1 day", "1-3 days", ">3 days", "Getting worse"],
        triage={**prior_triage, "topic": "diarrhea"},
    )


def _maybe_handle_dizzy_triage(
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
    prior_triage: dict = {}
    if last_ai and isinstance(last_ai.meta, dict):
        last_intent = str(last_ai.meta.get("intent") or "")
        triage_blob = last_ai.meta.get("triage")
        if isinstance(triage_blob, dict):
            prior_triage = dict(triage_blob)

    is_in_flow = last_intent.startswith("DIZZY_TRIAGE_")
    is_new = _looks_like_dizzy(user_text)
    if not is_in_flow and not is_new:
        return None

    def respond(text: str, *, intent: str, quick_replies: list[str] | None = None, triage: dict | None = None):
        filtered_quick_replies = _filter_quick_replies([triage_action], quick_replies)
        interaction = models.AIInteraction(
            customer_id=customer_id,
            customer_query=user_text,
            ai_response=text,
            confidence_score=0.0,
            escalated_to_human=False,
            created_at=datetime.utcnow(),
            pharmacy_id=pharmacy_id,
        )
        db.add(interaction)
        db.commit()
        db.refresh(interaction)
        meta = _build_ai_metadata(
            intent=intent,
            actions=[triage_action],
            cards=[],
            quick_replies=filtered_quick_replies,
            data_last_updated_at=None,
            indexed_at=None,
        )
        if triage:
            meta["triage"] = triage
        add_message(db, session, "AI", text, meta)
        db.commit()
        return schemas.AIChatOut(
            interaction_id=interaction.id,
            customer_id=customer_id,
            session_id=session.session_id,
            answer=text,
            citations=[],
            cards=[],
            actions=[triage_action],
            quick_replies=filtered_quick_replies,
            confidence_score=interaction.confidence_score,
            escalated_to_human=interaction.escalated_to_human,
            intent=intent,
            created_at=interaction.created_at,
            data_last_updated_at=None,
            indexed_at=None,
            system_message=None,
        )

    if last_intent == "DIZZY_TRIAGE_REDFLAGS" or is_new:
        if last_intent != "DIZZY_TRIAGE_REDFLAGS":
            return respond(
                (
                    "Do you have any of these right now: fainting, chest pain, trouble breathing, severe headache, "
                    "confusion, weakness/numbness, or uncontrolled bleeding?"
                ),
                intent="DIZZY_TRIAGE_REDFLAGS",
                quick_replies=["No", "Yes"],
                triage={**prior_triage, "topic": "dizzy"},
            )
        has_flags = _is_affirmative(user_text) and not _is_negative(user_text)
        if has_flags:
            return respond(
                (
                    "That can be urgent. Please seek medical care immediately. "
                    "If you can, you can also start a pharmacist consultation here."
                ),
                intent="DIZZY_REDFLAG",
                quick_replies=[],
                triage=prior_triage,
            )
        return respond(
            "How long have you felt dizzy?",
            intent="DIZZY_TRIAGE_DURATION",
            quick_replies=["Just now", "<1 day", "1-3 days", ">3 days", "Getting worse"],
            triage=prior_triage,
        )

    if last_intent == "DIZZY_TRIAGE_DURATION":
        bucket = _parse_duration_bucket(user_text)
        if not bucket:
            if "just now" in (user_text or "").lower():
                bucket = "<1 day"
        if not bucket:
            return respond(
                "How long have you felt dizzy?",
                intent="DIZZY_TRIAGE_DURATION",
                quick_replies=["Just now", "<1 day", "1-3 days", ">3 days", "Getting worse"],
                triage=prior_triage,
            )
        duration_bucket = bucket
        if duration_bucket in {">3 days", "1-3 days"}:
            return respond(
                (
                    "Because it has lasted more than a day, it's best to speak with a pharmacist. "
                    "Until then: sit or lie down if you feel dizzy, drink fluids, and avoid driving. "
                    "Seek care if you develop warning signs (fainting, chest pain, trouble breathing, weakness/numbness)."
                ),
                intent="DIZZY_GUIDANCE_PERSISTENT",
                quick_replies=[],
                triage={**prior_triage, "topic": "dizzy", "duration": duration_bucket},
            )
        return respond(
            (
                "For mild dizziness with no warning signs: sit or lie down, drink fluids, and avoid driving until you feel normal. "
                "If it persists or you're unsure, please talk to a pharmacist."
            ),
            intent="DIZZY_SELFCARE",
            quick_replies=[],
            triage={**prior_triage, "topic": "dizzy", "duration": duration_bucket},
        )

    return respond(
        (
            "Do you have any of these right now: fainting, chest pain, trouble breathing, severe headache, "
            "confusion, weakness/numbness, or uncontrolled bleeding?"
        ),
        intent="DIZZY_TRIAGE_REDFLAGS",
        quick_replies=["No", "Yes"],
        triage={**prior_triage, "topic": "dizzy"},
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
    filtered_quick_replies = list(quick_replies or [])
    if actions and any((a.type or "") == "escalate_to_pharmacist" for a in actions):
        filtered_quick_replies = [
            qr
            for qr in filtered_quick_replies
            if str(qr or "").strip().lower() not in {"talk to pharmacist", "escalate to pharmacist"}
        ]
    return {
        "intent": intent,
        "actions": [a.model_dump(mode="json") for a in actions] if actions else [],
        "cards": [c.model_dump(mode="json") for c in cards] if cards else [],
        "quick_replies": filtered_quick_replies,
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
            if payload.get("medicine_id") is not None:
                return int(payload.get("medicine_id"))
            if payload.get("product_id") is not None:
                return -int(payload.get("product_id"))
            return None
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
                        payload={
                            "medicine_id": med_id,
                            "quantity": 1,
                            "requires_prescription": bool(rx),
                        },
                    )
                )
            else:
                out.append(a)
        return out

    if stock is not None and stock <= 0:
        return dedupe([a for a in actions if a.type != "add_to_cart"])

    if med_id and stock is not None and stock > 0 and not any(a.type == "add_to_cart" for a in actions):
        actions = actions + [
            schemas.AIAction(
                type="add_to_cart",
                label="Add to cart",
                medicine_id=med_id,
                payload={"medicine_id": med_id, "quantity": 1, "requires_prescription": bool(rx)},
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

    last_ai = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session.id, models.ChatMessage.sender_type == "AI")
        .order_by(models.ChatMessage.created_at.desc())
        .first()
    )
    last_ai_intent = ""
    if last_ai and isinstance(last_ai.meta, dict):
        last_ai_intent = str(last_ai.meta.get("intent") or "")

    try:
        rag_service.ensure_pharmacy_playbook(db, pharmacy_id)
        db.commit()
        triage = _maybe_handle_urgent_red_flags(db, pharmacy_id, customer_id, session, message)
        if triage is not None:
            session_memory.append_turns(db, pharmacy_id, session_id, message, triage.answer)
            return triage
        triage = _maybe_handle_last_medicines(db, pharmacy_id, customer_id, session, message)
        if triage is not None:
            session_memory.append_turns(db, pharmacy_id, session_id, message, triage.answer)
            return triage
        triage = _maybe_handle_search_again(db, pharmacy_id, customer_id, session, message)
        if triage is not None:
            session_memory.append_turns(db, pharmacy_id, session_id, message, triage.answer)
            return triage
        triage = _maybe_handle_headache_triage(db, pharmacy_id, customer_id, session, message)
        if triage is not None:
            session_memory.append_turns(db, pharmacy_id, session_id, message, triage.answer)
            return triage
        triage = _maybe_handle_abdominal_pain_triage(db, pharmacy_id, customer_id, session, message)
        if triage is not None:
            session_memory.append_turns(db, pharmacy_id, session_id, message, triage.answer)
            return triage
        triage = _maybe_handle_diarrhea_triage(db, pharmacy_id, customer_id, session, message)
        if triage is not None:
            session_memory.append_turns(db, pharmacy_id, session_id, message, triage.answer)
            return triage
        triage = _maybe_handle_dizzy_triage(db, pharmacy_id, customer_id, session, message)
        if triage is not None:
            session_memory.append_turns(db, pharmacy_id, session_id, message, triage.answer)
            return triage
        triage = _maybe_handle_msk_pain_triage(db, pharmacy_id, customer_id, session, message)
        if triage is not None:
            session_memory.append_turns(db, pharmacy_id, session_id, message, triage.answer)
            return triage
        is_risky, reason = detect_risk(message)
        if is_risky:
            answer = (
                "This may require a pharmacist. Tap 'Talk to pharmacist' to start a consultation. "
                "If symptoms are severe or urgent, seek medical care immediately."
            )
            interaction = models.AIInteraction(
                customer_id=customer_id,
                customer_query=message,
                ai_response=answer,
                confidence_score=0.0,
                escalated_to_human=False,
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
                    actions=[schemas.AIAction(type="escalate_to_pharmacist", label="Talk to pharmacist")],
                    cards=[],
                    quick_replies=[],
                    data_last_updated_at=None,
                    indexed_at=None,
                ),
            )
            session_memory.append_turns(db, pharmacy_id, session_id, message, interaction.ai_response)
            _log(db, pharmacy_id, "chat", f"chat_id={customer_id} confidence=0.00 recommended_escalation=1 rag_top_k=0 retrieved_chunks=[]")
            db.commit()
            return schemas.AIChatOut(
                interaction_id=interaction.id,
                customer_id=customer_id,
                session_id=session_id,
                answer=interaction.ai_response,
                citations=[],
                cards=[],
                actions=[schemas.AIAction(type="escalate_to_pharmacist", label="Talk to pharmacist")],
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
        if last_ai_intent == "MEDICINE_SEARCH_PROMPT":
            router = RouterIntent(
                language="en",
                intent="MEDICINE_SEARCH",
                query=message.strip(),
                greeting=False,
                confidence=0.9,
                risk="low",
                clarifying_questions=[],
            )
        else:
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
        multi_medicine = bool(getattr(tool_ctx, "multi_query", False))
        if multi_medicine and immediate_answer:
            answer = immediate_answer
        elif immediate_answer and (not answer or answer.lower().startswith("assistant temporarily unavailable")):
            answer = immediate_answer
        elif not answer:
            answer = immediate_answer or ""
        if tool_ctx.intent == "RISKY_MEDICAL" or router.intent == "RISKY_MEDICAL":
            answer = (
                "This may require a pharmacist. Tap 'Talk to pharmacist' to start a consultation. "
                "If symptoms are severe or urgent, seek medical care immediately."
            )
            actions = [schemas.AIAction(type="escalate_to_pharmacist", label="Talk to pharmacist")]
        tool_actions = actions or []
        # Prefer tool actions; only use generator actions when tool actions are empty.
        if gen.actions and not multi_medicine and not tool_actions:
            actions = [
                schemas.AIAction(
                    type=a.type,
                    label=a.label,
                    medicine_id=(
                        int(a.payload.get("medicine_id"))
                        if isinstance(a.payload, dict) and a.payload.get("medicine_id") is not None
                        else None
                    ),
                    product_id=(
                        int(a.payload.get("product_id"))
                        if isinstance(a.payload, dict) and a.payload.get("product_id") is not None
                        else None
                    ),
                    payload=a.payload,
                )
                for a in gen.actions
            ]
        else:
            actions = tool_actions
        actions = _enforce_action_policy(tool_ctx, actions or [])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    # Escalation is explicit: only the customer can start a pharmacist consultation via the intake flow.
    escalated = False
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
    quick_replies_source = tool_ctx.quick_replies or [] if multi_medicine else (gen.quick_replies or tool_ctx.quick_replies or [])
    add_message(
        db,
        session,
        "AI",
        answer,
        _build_ai_metadata(
            intent=tool_ctx.intent,
            actions=actions,
            cards=tool_ctx.cards or [],
            quick_replies=_filter_quick_replies(actions, quick_replies_source),
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
            f"chat_id={customer_id} confidence={float(gen.confidence if gen.answer else 0.0):.2f} escalated=False "
            f"router_intent={router.intent} router_conf={router.confidence:.2f} "
            f"rag_top_k={int(get_rag_config().top_k)} retrieved_chunks=[{chunk_log}] actions=[{action_log}]"
        ),
    )
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
        quick_replies=_filter_quick_replies(actions, (gen.quick_replies or tool_ctx.quick_replies or [])),
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
