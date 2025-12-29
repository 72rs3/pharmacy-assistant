from __future__ import annotations

import difflib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import models, schemas
from app.ai import rag_service
from app.ai import session_memory
from app.ai.tri_model_router import RouterIntent
from app.config.rag import get_rag_config


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "do",
    "does",
    "for",
    "from",
    "have",
    "hello",
    "hey",
    "hi",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "please",
    "the",
    "their",
    "there",
    "this",
    "to",
    "we",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "you",
    "your",
}


@dataclass(frozen=True)
class ToolContext:
    intent: str
    language: str
    found: bool = False
    items: list[dict[str, Any]] = None  # type: ignore[assignment]
    suggestions: list[str] = None  # type: ignore[assignment]
    citations: list[dict[str, Any]] = None  # type: ignore[assignment]
    snippets: list[dict[str, Any]] = None  # type: ignore[assignment]
    cards: list[schemas.MedicineCard] = None  # type: ignore[assignment]
    quick_replies: list[str] = None  # type: ignore[assignment]
    escalated: bool = False
    data_last_updated_at: datetime | None = None
    indexed_at: datetime | None = None


def _system_citation(title: str, preview: str) -> schemas.AICitation:
    return schemas.AICitation(
        source_type="system",
        title=title,
        doc_id=0,
        chunk_id=0,
        preview=preview,
        last_updated_at=None,
        score=None,
    )


def _playbook_citation(pharmacy: models.Pharmacy | None, title: str, preview: str) -> schemas.AICitation:
    pharmacy_id = int(pharmacy.id) if pharmacy else 0
    updated_at = pharmacy.updated_at if pharmacy else None
    return schemas.AICitation(
        source_type="playbook",
        title=title,
        doc_id=pharmacy_id,
        chunk_id=0,
        preview=preview,
        last_updated_at=updated_at,
        score=None,
    )


def _medicine_card(med: models.Medicine, indexed_at: datetime | None = None) -> schemas.MedicineCard:
    return schemas.MedicineCard(
        medicine_id=int(med.id),
        name=str(med.name),
        dosage=(med.dosage or None),
        category=(getattr(med, "category", None) or None),
        rx=bool(med.prescription_required),
        price=float(med.price) if med.price is not None else None,
        stock=int(med.stock_level or 0),
        updated_at=med.updated_at,
        indexed_at=indexed_at,
    )


def _subject_tokens(text: str) -> list[str]:
    tokens = [t.lower() for t in difflib.SequenceMatcher(None, "", "").get_opcodes() if False]  # keep mypy quiet
    del tokens
    raw = (text or "").strip()
    parts = []
    for token in raw.split():
        tok = "".join(ch for ch in token if ch.isalnum()).lower()
        if not tok or tok in _STOPWORDS:
            continue
        if len(tok) < 3:
            continue
        parts.append(tok)
    return parts


def medicine_sql_search(db: Session, pharmacy_id: int, query: str, *, limit: int = 3) -> list[models.Medicine]:
    tokens = _subject_tokens(query)
    if not tokens:
        return []
    filters = [models.Medicine.name.ilike(f"%{t}%") for t in tokens]
    return (
        db.query(models.Medicine)
        .filter(models.Medicine.pharmacy_id == pharmacy_id, or_(*filters))
        .order_by(models.Medicine.name.asc())
        .limit(limit)
        .all()
    )


def medicine_exact(db: Session, pharmacy_id: int, query: str) -> models.Medicine | None:
    q = (query or "").strip()
    if not q:
        return None
    return (
        db.query(models.Medicine)
        .filter(models.Medicine.pharmacy_id == pharmacy_id, func.lower(models.Medicine.name) == q.lower())
        .first()
    )


def medicine_fuzzy(db: Session, pharmacy_id: int, query: str, *, limit: int = 3) -> list[models.Medicine]:
    tokens = _subject_tokens(query)
    if not tokens:
        return []
    needle = " ".join(tokens).lower()
    meds = db.query(models.Medicine).filter(models.Medicine.pharmacy_id == pharmacy_id).all()
    name_map = {str(med.name or "").lower(): med for med in meds if med.name}
    names = list(name_map.keys())
    close = difflib.get_close_matches(needle, names, n=limit, cutoff=0.68)
    return [name_map[name] for name in close]


def product_sql_search(db: Session, pharmacy_id: int, query: str, *, limit: int = 3) -> list[models.Product]:
    tokens = _subject_tokens(query)
    if not tokens:
        return []
    filters = [models.Product.name.ilike(f"%{t}%") for t in tokens]
    return (
        db.query(models.Product)
        .filter(models.Product.pharmacy_id == pharmacy_id, or_(*filters))
        .order_by(models.Product.name.asc())
        .limit(limit)
        .all()
    )


def product_exact(db: Session, pharmacy_id: int, query: str) -> models.Product | None:
    q = (query or "").strip()
    if not q:
        return None
    return (
        db.query(models.Product)
        .filter(models.Product.pharmacy_id == pharmacy_id, func.lower(models.Product.name) == q.lower())
        .first()
    )


def product_fuzzy(db: Session, pharmacy_id: int, query: str, *, limit: int = 3) -> list[models.Product]:
    tokens = _subject_tokens(query)
    if not tokens:
        return []
    needle = " ".join(tokens).lower()
    rows = db.query(models.Product).filter(models.Product.pharmacy_id == pharmacy_id).all()
    name_map = {str(row.name or "").lower(): row for row in rows if row.name}
    names = list(name_map.keys())
    close = difflib.get_close_matches(needle, names, n=limit, cutoff=0.68)
    return [name_map[name] for name in close]


def _default_quick_replies() -> list[str]:
    return ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"]


def _greeting_prefix(language: str) -> str:
    return (
        "مرحباً! "
        if language == "ar"
        else "Bonjour! "
        if language == "fr"
        else "Hello! "
    )


def _merge_quick_replies(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for item in group:
            val = (item or "").strip()
            key = val.lower()
            if not val or key in seen:
                continue
            seen.add(key)
            out.append(val)
    return out


async def build_tool_context(
    db: Session,
    *,
    pharmacy_id: int,
    router: RouterIntent,
    session_id: str | None,
    turns: list[dict] | None,
) -> tuple[ToolContext, list[schemas.AICitation], list[schemas.AIAction], str | None]:
    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    playbook_doc = (
        db.query(models.Document)
        .filter(
            models.Document.pharmacy_id == pharmacy_id,
            models.Document.source_type == "pharmacy",
            models.Document.source_key == "pharmacy:playbook",
        )
        .first()
    )

    citations: list[schemas.AICitation] = []
    actions: list[schemas.AIAction] = []
    immediate_answer: str | None = None

    if router.intent == "GREETING":
        immediate_answer = (
            "مرحباً! كيف يمكنني مساعدتك اليوم؟"
            if router.language == "ar"
            else "Bonjour ! Comment puis-je vous aider ?"
            if router.language == "fr"
            else "Hello! How can I assist you today?"
        )
        citations = [_system_citation("greeting", "Canned greeting")]
        ctx = ToolContext(intent="GREETING", language=router.language, found=False, items=[], suggestions=[], citations=[c.model_dump() for c in citations], cards=[], quick_replies=_default_quick_replies())
        return ctx, citations, actions, immediate_answer

    if router.intent == "HOURS_CONTACT":
        parts: list[str] = []
        preview_parts: list[str] = []
        if pharmacy and pharmacy.operating_hours:
            parts.append(f"Store hours: {pharmacy.operating_hours}.")
            preview_parts.append(pharmacy.operating_hours)
        if pharmacy and pharmacy.contact_phone:
            parts.append(f"Phone: {pharmacy.contact_phone}.")
            preview_parts.append(pharmacy.contact_phone)
        if pharmacy and pharmacy.contact_email:
            parts.append(f"Email: {pharmacy.contact_email}.")
            preview_parts.append(pharmacy.contact_email)
        if parts:
            citations.append(_playbook_citation(pharmacy, "hours_contact", ", ".join(preview_parts)))
            immediate_answer = " ".join(parts)
        ctx = ToolContext(
            intent="HOURS_CONTACT",
            language=router.language,
            found=bool(parts),
            items=[],
            suggestions=[],
            citations=[c.model_dump() for c in citations],
            cards=[],
            quick_replies=_default_quick_replies(),
            data_last_updated_at=(pharmacy.updated_at if pharmacy else None),
            indexed_at=(playbook_doc.indexed_at if playbook_doc else None),
        )
        return ctx, citations, actions, immediate_answer

    if router.intent == "SERVICES":
        cod = bool(getattr(pharmacy, "support_cod", True)) if pharmacy else True
        immediate_answer = "Delivery: available." if cod else "Delivery: not available."
        citations = [_playbook_citation(pharmacy, "services", f"cod={cod}")]
        ctx = ToolContext(
            intent="SERVICES",
            language=router.language,
            found=True,
            items=[],
            suggestions=[],
            citations=[c.model_dump() for c in citations],
            snippets=[],
            cards=[],
            quick_replies=_default_quick_replies(),
            data_last_updated_at=(pharmacy.updated_at if pharmacy else None),
            indexed_at=(playbook_doc.indexed_at if playbook_doc else None),
        )
        return ctx, citations, actions, immediate_answer

    if router.intent == "APPOINTMENT":
        actions.append(schemas.AIAction(type="book_appointment", label="Book appointment", payload={}))
        citations = [_system_citation("appointment", "Open in-chat booking form")]
        ctx = ToolContext(
            intent="APPOINTMENT",
            language=router.language,
            found=False,
            items=[],
            suggestions=[],
            citations=[c.model_dump() for c in citations],
            cards=[],
            quick_replies=_default_quick_replies(),
        )
        immediate_answer = "Sure - please fill the appointment form below."
        return ctx, citations, actions, immediate_answer

    if router.intent == "CART":
        if turns:
            last_item = session_memory.get_state(turns, "last_item") or {}
            mid = int(last_item.get("medicine_id") or 0)
            if mid > 0:
                actions.append(schemas.AIAction(type="add_to_cart", label="Add to cart", medicine_id=mid, payload={"medicine_id": mid, "quantity": 1}))
                citations = [_system_citation("cart", "Cart action available")]
                ctx = ToolContext(intent="CART", language=router.language, found=True, items=[], suggestions=[], citations=[c.model_dump() for c in citations], cards=[], quick_replies=_default_quick_replies())
                immediate_answer = "Ready to add it to your cart."
                return ctx, citations, actions, immediate_answer
        citations = [_system_citation("cart", "Missing context")]
        ctx = ToolContext(intent="CART", language=router.language, found=False, items=[], suggestions=[], citations=[c.model_dump() for c in citations], cards=[], quick_replies=_default_quick_replies())
        immediate_answer = "Which medicine should I add to your cart?"
        return ctx, citations, actions, immediate_answer

    if router.intent == "RISKY_MEDICAL":
        contact_bits = []
        if pharmacy and pharmacy.contact_phone:
            contact_bits.append(f"Phone: {pharmacy.contact_phone}")
        if pharmacy and pharmacy.contact_email:
            contact_bits.append(f"Email: {pharmacy.contact_email}")
        contact_text = f" {' '.join(contact_bits)}" if contact_bits else ""
        immediate_answer = (
            "This looks like a medical-risk question. I will escalate this to the pharmacist for review. "
            "If this is urgent, seek emergency care."
            + contact_text
        )
        ctx = ToolContext(intent="RISKY_MEDICAL", language=router.language, escalated=True, found=False, items=[], suggestions=[], citations=[], cards=[], quick_replies=_default_quick_replies())
        return ctx, [], actions, immediate_answer

    if router.intent == "MEDICINE_SEARCH":
        q = (router.query or "").strip() or ""
        exact = medicine_exact(db, pharmacy_id, q)
        matches = [exact] if exact else medicine_sql_search(db, pharmacy_id, q)
        suggestions: list[str] = []
        if not matches:
            suggestions = [m.name for m in medicine_fuzzy(db, pharmacy_id, q) if m and m.name]
            for name in suggestions:
                actions.append(schemas.AIAction(type="search_medicine", label=f"Search {name}", payload={"query": name}))
        cards: list[schemas.MedicineCard] = []
        items: list[dict[str, Any]] = []
        for med in matches[:1]:
            cards.append(_medicine_card(med))
            items.append(
                {
                    "id": int(med.id),
                    "name": med.name,
                    "dosage": med.dosage,
                    "rx": bool(med.prescription_required),
                    "price": float(med.price) if med.price is not None else None,
                    "stock": int(med.stock_level or 0),
                    "updated_at": med.updated_at.isoformat() if med.updated_at else None,
                }
            )
        found = bool(items)
        if found:
            item = items[0]
            mid = int(item["id"])
            name = str(item["name"])
            stock = int(item.get("stock") or 0)
            price = item.get("price")
            rx = bool(item.get("rx") or False)
            price_text = f" Price: {float(price):.2f}." if price is not None else ""
            if rx:
                actions.append(
                    schemas.AIAction(
                        type="upload_prescription",
                        label="Upload prescription",
                        medicine_id=mid,
                        payload={"medicine_id": mid},
                    )
                )
                immediate_answer = f"Yes, we have {name} in stock ({stock}). This medicine requires a prescription.{price_text} Would you like to upload your prescription?"
            elif stock > 0:
                actions.append(
                    schemas.AIAction(
                        type="add_to_cart",
                        label="Add to cart",
                        medicine_id=mid,
                        payload={"medicine_id": mid, "quantity": 1},
                    )
                )
                immediate_answer = f"Yes, we have {name} in stock ({stock}).{price_text} Would you like me to add it to your cart?"
            else:
                immediate_answer = f"Sorry, {name} is currently out of stock.{price_text} Do you want to search another medicine?"
        elif suggestions:
            immediate_answer = "I could not find an exact match. Did you mean: " + ", ".join(suggestions[:3]) + "?"
        else:
            immediate_answer = "Which medicine are you looking for? Please share the name (and dosage, if possible)."
        if getattr(router, "greeting", False) and immediate_answer:
            immediate_answer = _greeting_prefix(router.language) + immediate_answer
        if turns is not None and found and items:
            session_memory.set_state(turns, "last_item", {"medicine_id": int(items[0]["id"]), "name": str(items[0]["name"])})
            if session_id:
                session_memory.save_turns(db, pharmacy_id, session_id, turns)

        citations = [
            _system_citation(
                "medicine_search",
                (f"match={items[0]['name']} stock={items[0]['stock']}" if found and items else f"suggestions={','.join(suggestions[:3])}"),
            )
        ]
        ctx = ToolContext(
            intent="MEDICINE_SEARCH",
            language=router.language,
            found=found,
            items=items,
            suggestions=suggestions,
            citations=[c.model_dump() for c in citations],
            snippets=[],
            cards=cards,
            quick_replies=_merge_quick_replies(suggestions, _default_quick_replies()),
            data_last_updated_at=(matches[0].updated_at if matches else None),
        )
        return ctx, citations, actions, immediate_answer

    if router.intent == "PRODUCT_SEARCH":
        q = (router.query or "").strip() or ""
        exact = product_exact(db, pharmacy_id, q)
        matches = [exact] if exact else product_sql_search(db, pharmacy_id, q)
        suggestions: list[str] = []
        if not matches:
            suggestions = [p.name for p in product_fuzzy(db, pharmacy_id, q) if p and p.name]
        items: list[dict[str, Any]] = []
        for row in matches[:3]:
            items.append(
                {
                    "id": int(row.id),
                    "name": row.name,
                    "category": row.category,
                    "price": float(row.price) if row.price is not None else None,
                    "stock": int(row.stock_level or 0),
                    "image_url": row.image_url,
                }
            )
        citations = [_system_citation("product_search", f"items={len(items)} suggestions={len(suggestions)}")]
        ctx = ToolContext(
            intent="PRODUCT_SEARCH",
            language=router.language,
            found=bool(items),
            items=items,
            suggestions=suggestions,
            citations=[c.model_dump() for c in citations],
            snippets=[],
            cards=[],
            quick_replies=_merge_quick_replies(suggestions, _default_quick_replies()),
        )
        if items:
            if len(items) == 1:
                immediate_answer = f"Yes, we have {items[0].get('name')} in stock ({items[0].get('stock')})."
            else:
                immediate_answer = "Here are a few products I found: " + ", ".join(str(it.get("name")) for it in items[:3]) + "."
        elif suggestions:
            immediate_answer = "I could not find an exact match. Did you mean: " + ", ".join(suggestions[:3]) + "?"
        else:
            immediate_answer = "Which product are you looking for? Please share the name."
        return ctx, citations, actions, immediate_answer

    if router.intent == "UNKNOWN":
        immediate_answer = (
            "عذرًا، لم أفهم طلبك. هل يمكنك إعادة صياغته؟"
            if router.language == "ar"
            else "Désolé, je n’ai pas compris. Pouvez-vous reformuler ?"
            if router.language == "fr"
            else "I'm not sure I understood—could you rephrase?"
        )
        citations = [_system_citation("unknown", "Fallback response")]
        ctx = ToolContext(
            intent="UNKNOWN",
            language=router.language,
            found=False,
            items=[],
            suggestions=[],
            citations=[c.model_dump() for c in citations],
            snippets=[],
            cards=[],
            quick_replies=_default_quick_replies(),
        )
        return ctx, citations, actions, immediate_answer

    q = (router.query or "").strip() or ""
    chunks = await rag_service.retrieve(db, pharmacy_id, q, top_k=int(get_rag_config().top_k)) if q else []
    citations = [
        schemas.AICitation(
            source_type="rag",
            title=str(c.source or "source"),
            doc_id=int(c.document_id),
            chunk_id=int(c.id),
            preview=str(c.content or "")[:250],
            last_updated_at=None,
            score=float(c.score or 0.0),
        )
        for c in chunks
    ]
    snippets = [
        {
            "source": str(c.source or "source"),
            "doc_id": int(c.document_id),
            "chunk_id": int(c.id),
            "content": str(c.content or ""),
            "score": float(c.score or 0.0),
        }
        for c in chunks
    ]
    ctx = ToolContext(
        intent="GENERAL_RAG",
        language=router.language,
        found=bool(chunks),
        items=[],
        suggestions=[],
        citations=[c.model_dump() for c in citations],
        snippets=snippets,
        cards=[],
        quick_replies=_default_quick_replies(),
    )
    return ctx, citations, actions, None
