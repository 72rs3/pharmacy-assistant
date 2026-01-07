from __future__ import annotations

import difflib
from dataclasses import dataclass
from datetime import datetime
import re
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
    multi_query: bool = False


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


_MULTI_MED_SPLIT_RE = re.compile(r"\s*(?:,|/|&|\+|\band\b|\bw\b|\bwith\b|\bplus\b)\s*", re.IGNORECASE)
_MED_QUERY_PREFIX_RE = re.compile(
    r"^\s*(?:do\s+you\s+have|do\s+u\s+have|do\s+we\s+have|i\s+need|need|looking\s+for|search\s+for|search|find)\s+",
    re.IGNORECASE,
)


def _clean_medicine_query(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    text = _MED_QUERY_PREFIX_RE.sub("", text).strip()
    text = re.sub(r"[^\w\s\-/+&]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _split_medicine_queries(query: str, *, limit: int = 10) -> list[str]:
    cleaned = _clean_medicine_query(query)
    if not cleaned:
        return []
    parts = [p.strip() for p in _MULTI_MED_SPLIT_RE.split(cleaned) if p.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
        if len(out) >= limit:
            break
    return out


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


def _update_last_items_state(turns: list[dict] | None, items: list[dict[str, Any]], *, kind: str) -> None:
    if not turns or not items:
        return
    recent: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        key = f"{kind}:{name.lower()}"
        if key in seen:
            continue
        seen.add(key)
        recent.append({"name": name, "dosage": item.get("dosage") or None, "type": kind})
        if len(recent) >= 3:
            break
    if recent:
        session_memory.set_state(turns, "last_medicines", {"items": recent})


def _update_last_search_results(turns: list[dict] | None, items: list[dict[str, Any]], *, kind: str) -> None:
    if not turns or not items:
        return
    stored: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        item_id = item.get("id")
        key = f"{kind}:{item_id}"
        if key in seen:
            continue
        seen.add(key)
        stored.append(
            {
                "type": kind,
                "id": int(item_id) if item_id is not None else None,
                "name": name,
            }
        )
        if len(stored) >= 10:
            break
    if stored:
        session_memory.set_state(turns, "last_search_results", {"items": stored})


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

    # Avoid corrupted/garbled canned Arabic greetings and keep UX consistent across locales.
    if router.intent == "GREETING" and router.language == "ar":
        immediate_answer = "مرحباً! كيف يمكنني مساعدتك اليوم؟"
        citations = [_system_citation("greeting", "Canned greeting")]
        ctx = ToolContext(
            intent="GREETING",
            language=router.language,
            found=False,
            items=[],
            suggestions=[],
            citations=[c.model_dump() for c in citations],
            cards=[],
            quick_replies=_default_quick_replies(),
        )
        return ctx, citations, actions, immediate_answer

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
        info: dict[str, str] = {}
        if pharmacy and pharmacy.operating_hours:
            parts.append(f"Store hours: {pharmacy.operating_hours}.")
            preview_parts.append(pharmacy.operating_hours)
            info["operating_hours"] = pharmacy.operating_hours
        if pharmacy and pharmacy.contact_phone:
            parts.append(f"Phone: {pharmacy.contact_phone}.")
            preview_parts.append(pharmacy.contact_phone)
            info["contact_phone"] = pharmacy.contact_phone
        if pharmacy and pharmacy.contact_email:
            parts.append(f"Email: {pharmacy.contact_email}.")
            preview_parts.append(pharmacy.contact_email)
            info["contact_email"] = pharmacy.contact_email
        if parts:
            citations.append(_playbook_citation(pharmacy, "hours_contact", ", ".join(preview_parts)))
            immediate_answer = " ".join(parts)
        else:
            immediate_answer = "Store hours and contact details are not available yet. Please contact the pharmacy directly."
            citations = [_system_citation("hours_contact", "Missing pharmacy contact details")]
        ctx = ToolContext(
            intent="HOURS_CONTACT",
            language=router.language,
            found=bool(parts),
            items=[info] if info else [],
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
        view_query = (router.query or "").strip().lower()
        is_view = any(word in view_query for word in ["what", "list", "show", "view", "check"])

        if is_view and session_id:
            cart_items = (
                db.query(models.CartItem)
                .filter(models.CartItem.pharmacy_id == pharmacy_id, models.CartItem.session_id == session_id)
                .all()
            )
            if cart_items:
                parts = []
                for item in cart_items:
                    qty = int(item.quantity or 0)
                    if item.medicine_id and item.medicine:
                        parts.append(f"{item.medicine.name} (Qty: {qty})")
                    elif item.product_id and item.product:
                        parts.append(f"{item.product.name} (Qty: {qty})")
                if parts:
                    immediate_answer = "You currently have " + " and ".join(parts) + " in your cart."
                else:
                    immediate_answer = "Your cart is empty."
            else:
                immediate_answer = "Your cart is empty."
            citations = [_system_citation("cart_view", f"items={len(cart_items)}")]
            ctx = ToolContext(intent="CART", language=router.language, found=bool(cart_items), items=[], suggestions=[], citations=[c.model_dump() for c in citations], cards=[], quick_replies=_default_quick_replies())
            return ctx, citations, actions, immediate_answer

        if turns:
            last_results = session_memory.get_state(turns, "last_search_results") or {}
            items = last_results.get("items") if isinstance(last_results, dict) else []
            if items:
                for item in items:
                    item_type = str(item.get("type") or "medicine")
                    item_id = int(item.get("id") or 0)
                    name = str(item.get("name") or "")
                    if not item_id:
                        continue
                    if item_type == "product":
                        actions.append(
                            schemas.AIAction(
                                type="add_to_cart",
                                label=f"Add {name} to cart",
                                medicine_id=None,
                                product_id=item_id,
                                payload={"product_id": item_id, "quantity": 1},
                            )
                        )
                    else:
                        actions.append(
                            schemas.AIAction(
                                type="add_to_cart",
                                label=f"Add {name} to cart",
                                medicine_id=item_id,
                                payload={"medicine_id": item_id, "quantity": 1},
                            )
                        )
                citations = [_system_citation("cart", "Cart actions from last search results")]
                ctx = ToolContext(intent="CART", language=router.language, found=True, items=[], suggestions=[], citations=[c.model_dump() for c in citations], cards=[], quick_replies=_default_quick_replies())
                immediate_answer = "Ready to add those to your cart."
                return ctx, citations, actions, immediate_answer

        citations = [_system_citation("cart", "Missing context")]
        ctx = ToolContext(intent="CART", language=router.language, found=False, items=[], suggestions=[], citations=[c.model_dump() for c in citations], cards=[], quick_replies=_default_quick_replies())
        immediate_answer = "Which medicine or product should I add to your cart?"
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
        tokens = _subject_tokens(q)
        found_medicines: list[models.Medicine] = []
        found_products: list[models.Product] = []

        if not tokens:
            found_medicines = medicine_sql_search(db, pharmacy_id, q, limit=5)
        else:
            for token in tokens:
                med_found = medicine_sql_search(db, pharmacy_id, token, limit=5)
                if not med_found:
                    med_found = medicine_fuzzy(db, pharmacy_id, token, limit=3)
                if med_found:
                    found_medicines.extend(med_found)
                    continue
                prod_found = product_sql_search(db, pharmacy_id, token, limit=5)
                if not prod_found:
                    prod_found = product_fuzzy(db, pharmacy_id, token, limit=3)
                found_products.extend(prod_found)

        seen_med_ids: set[int] = set()
        unique_meds: list[models.Medicine] = []
        for med in found_medicines:
            if not med:
                continue
            med_id = int(med.id)
            if med_id in seen_med_ids:
                continue
            seen_med_ids.add(med_id)
            unique_meds.append(med)
        unique_meds = unique_meds[:6]

        seen_prod_ids: set[int] = set()
        unique_products: list[models.Product] = []
        for prod in found_products:
            if not prod:
                continue
            prod_id = int(prod.id)
            if prod_id in seen_prod_ids:
                continue
            seen_prod_ids.add(prod_id)
            unique_products.append(prod)
        unique_products = unique_products[:6]

        cards: list[schemas.MedicineCard] = []
        medicine_items: list[dict[str, Any]] = []
        for med in unique_meds:
            cards.append(_medicine_card(med))
            medicine_items.append(
                {
                    "id": int(med.id),
                    "name": med.name,
                    "dosage": med.dosage,
                    "rx": bool(med.prescription_required),
                    "price": float(med.price) if med.price is not None else None,
                    "stock": int(med.stock_level or 0),
                    "updated_at": med.updated_at.isoformat() if med.updated_at else None,
                    "type": "medicine",
                }
            )

        product_items: list[dict[str, Any]] = []
        for prod in unique_products:
            product_items.append(
                {
                    "id": int(prod.id),
                    "name": prod.name,
                    "category": prod.category,
                    "price": float(prod.price) if prod.price is not None else None,
                    "stock": int(prod.stock_level or 0),
                    "image_url": prod.image_url,
                    "rx": False,
                    "dosage": None,
                    "type": "product",
                }
            )

        items: list[dict[str, Any]] = medicine_items + product_items
        suggestions: list[str] = []

        for item in medicine_items:
            stock = int(item.get("stock") or 0)
            rx = bool(item.get("rx") or False)
            mid = int(item["id"])
            name = str(item["name"])
            if stock > 0:
                actions.append(
                    schemas.AIAction(
                        type="add_to_cart",
                        label=f"Add {name}",
                        medicine_id=mid,
                        payload={
                            "medicine_id": mid,
                            "quantity": 1,
                            "requires_prescription": rx,
                        },
                    )
                )

        for item in product_items:
            stock = int(item.get("stock") or 0)
            if stock <= 0:
                continue
            pid = int(item["id"])
            name = str(item["name"])
            actions.append(
                schemas.AIAction(
                    type="add_to_cart",
                    label=f"Add {name}",
                    medicine_id=None,
                    product_id=pid,
                    payload={"product_id": pid, "quantity": 1},
                )
            )

        found = bool(items)
        immediate_answer = None
        if turns is not None and found:
            if medicine_items:
                session_memory.set_state(
                    turns,
                    "last_item",
                    {"medicine_id": int(medicine_items[0]["id"]), "name": str(medicine_items[0]["name"])},
                )
                _update_last_items_state(turns, medicine_items, kind="medicine")
                _update_last_search_results(turns, medicine_items, kind="medicine")
            if product_items:
                _update_last_search_results(turns, product_items, kind="product")
            if session_id:
                session_memory.save_turns(db, pharmacy_id, session_id, turns)

        citations = [
            _system_citation(
                "medicine_search",
                (f"medicines={len(medicine_items)} products={len(product_items)}" if found else "no matches"),
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
            data_last_updated_at=(unique_meds[0].updated_at if unique_meds else None),
        )
        return ctx, citations, actions, immediate_answer

    if router.intent == "PRODUCT_SEARCH":
        q = (router.query or "").strip() or ""
        exact = product_exact(db, pharmacy_id, q)
        matches = [exact] if exact else product_sql_search(db, pharmacy_id, q)
        suggestions: list[str] = []
        if not matches:
            suggestions = [p.name for p in product_fuzzy(db, pharmacy_id, q) if p and p.name]
            if not suggestions:
                med_exact_match = medicine_exact(db, pharmacy_id, q)
                med_matches = [med_exact_match] if med_exact_match else medicine_sql_search(db, pharmacy_id, q)
                if med_matches:
                    actions.append(schemas.AIAction(type="search_medicine", label=f"Search {med_matches[0].name}", payload={"query": str(med_matches[0].name)}))
                    cards = [_medicine_card(med_matches[0])]
                    items = [
                        {
                            "id": int(med_matches[0].id),
                            "name": med_matches[0].name,
                            "dosage": med_matches[0].dosage,
                            "rx": bool(med_matches[0].prescription_required),
                            "price": float(med_matches[0].price) if med_matches[0].price is not None else None,
                            "stock": int(med_matches[0].stock_level or 0),
                            "updated_at": med_matches[0].updated_at.isoformat() if med_matches[0].updated_at else None,
                        }
                    ]
                    citations = [_system_citation("medicine_search", f"match={items[0]['name']} stock={items[0]['stock']}")]
                    ctx = ToolContext(
                        intent="MEDICINE_SEARCH",
                        language=router.language,
                        found=True,
                        items=items,
                        suggestions=[],
                        citations=[c.model_dump() for c in citations],
                        snippets=[],
                        cards=cards,
                        quick_replies=_merge_quick_replies([f"Search {items[0]['name']}"], _default_quick_replies()),
                        data_last_updated_at=med_matches[0].updated_at,
                    )
                    immediate_answer = f"I couldn't find a product with that name, but I found this medicine: {items[0]['name']}."
                    return ctx, citations, actions, immediate_answer
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
        for item in items:
            stock = int(item.get("stock") or 0)
            if stock <= 0:
                continue
            actions.append(
                schemas.AIAction(
                    type="add_to_cart",
                    label=f"Add {item['name']} to cart",
                    medicine_id=None,
                    product_id=int(item["id"]),
                    payload={"product_id": int(item["id"]), "quantity": 1},
                )
            )
        if items:
            if len(items) == 1:
                stock = int(items[0].get("stock") or 0)
                if stock > 0:
                    immediate_answer = f"Yes, {items[0].get('name')} is available."
                else:
                    immediate_answer = f"Sorry, {items[0].get('name')} is currently out of stock."
            else:
                immediate_answer = "Here are a few products I found: " + ", ".join(str(it.get("name")) for it in items[:3]) + "."
        elif suggestions:
            immediate_answer = "I could not find an exact match. Did you mean: " + ", ".join(suggestions[:3]) + "?"
        else:
            immediate_answer = "Which product are you looking for? Please share the name."
        if turns is not None and items:
            _update_last_items_state(turns, items, kind="product")
            _update_last_search_results(turns, items, kind="product")
            if session_id:
                session_memory.save_turns(db, pharmacy_id, session_id, turns)
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
