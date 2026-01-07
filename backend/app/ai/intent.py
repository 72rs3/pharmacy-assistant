from __future__ import annotations

import difflib
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models, schemas
from app.ai.provider_factory import get_ai_provider
from app.ai.providers.base import ChatMessage
from app.ai import rag_service
from app.ai import session_memory
from app.ai.llm_classifier import ClassifierResult, classify_message, fallback_classify
from app.rag.hybrid import hybrid_answer
from app.utils.validation import validate_e164_phone


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


def _medicine_citation(med: models.Medicine) -> schemas.AICitation:
    preview = f"dosage={med.dosage or '-'}, stock={med.stock_level}"
    return schemas.AICitation(
        source_type="medicine",
        title=med.name,
        doc_id=int(med.id),
        chunk_id=0,
        preview=preview,
        last_updated_at=med.updated_at,
        score=None,
    )


def _product_citation(product: models.Product) -> schemas.AICitation:
    preview = f"stock={product.stock_level}"
    return schemas.AICitation(
        source_type="product",
        title=product.name,
        doc_id=int(product.id),
        chunk_id=0,
        preview=preview,
        last_updated_at=None,
        score=None,
    )


def _appointment_citation(doc: models.Document | None, preview: str) -> schemas.AICitation:
    doc_id = int(doc.id) if doc else 0
    title = doc.title if doc else "Appointments summary"
    return schemas.AICitation(
        source_type="appointment",
        title=title,
        doc_id=doc_id,
        chunk_id=0,
        preview=preview,
        last_updated_at=(doc.data_updated_at if doc else None),
        score=None,
    )


def _citations_from_chunks(
    db: Session, chunks: list[rag_service.RetrievedChunk]
) -> tuple[list[schemas.AICitation], datetime | None, datetime | None]:
    if not chunks:
        return [], None, None
    doc_ids = {int(chunk.document_id) for chunk in chunks if chunk.document_id}
    docs = db.query(models.Document).filter(models.Document.id.in_(doc_ids)).all()
    doc_map = {int(doc.id): doc for doc in docs}
    chunk_ids = {int(chunk.id) for chunk in chunks if chunk.document_id}
    chunk_rows = db.query(models.DocumentChunk).filter(models.DocumentChunk.id.in_(chunk_ids)).all()
    chunk_map = {int(row.id): row for row in chunk_rows}
    citations: list[schemas.AICitation] = []
    data_last_updated_at: datetime | None = None
    indexed_at: datetime | None = None
    for chunk in chunks:
        doc = doc_map.get(int(chunk.document_id))
        chunk_row = chunk_map.get(int(chunk.id))
        preview = (chunk.content or "").replace("\n", " ").strip()[:160]
        citations.append(
            schemas.AICitation(
                source_type=(doc.source_type if doc else "document"),
                title=(doc.title if doc else chunk.source),
                doc_id=int(chunk.document_id),
                chunk_id=int(chunk.id),
                preview=preview,
                last_updated_at=(doc.data_updated_at if doc and doc.data_updated_at else (chunk_row.updated_at if chunk_row else None)),
                score=float(getattr(chunk, "score", 0.0)),
            )
        )
        if doc:
            if doc.data_updated_at and (data_last_updated_at is None or doc.data_updated_at > data_last_updated_at):
                data_last_updated_at = doc.data_updated_at
            if doc.indexed_at and (indexed_at is None or doc.indexed_at > indexed_at):
                indexed_at = doc.indexed_at
    return citations, data_last_updated_at, indexed_at


INTENTS = [
    "GREETING",
    "MEDICINE_SEARCH",
    "PRODUCT_SEARCH",
    "SERVICES_INFO",
    "HOURS_CONTACT",
    "APPOINTMENT_BOOKING",
    "RX_UPLOAD",
    "ORDER_CART",
    "GENERAL_RAG",
    "RISKY_MEDICAL",
    "UNKNOWN",
]

_HOURS = {"hours", "open", "opening", "closing", "schedule", "time", "working", "contact", "phone", "email", "address"}
_DELIVERY = {"delivery", "deliver", "shipping", "cod", "cash", "payment", "pay"}
_APPOINTMENT = {"appointment", "book", "booking", "schedule", "visit", "consultation", "vaccination"}
_RX = {"rx", "prescription"}
_OTC = {"otc", "product", "toothpaste", "toothbrush", "vitamin", "supplement", "skincare", "lotion", "soap", "shampoo"}
_AVAILABILITY = {"have", "available", "availability", "stock", "price", "cost", "medicine", "medication", "drug"}
_GENERAL = {"info", "information", "details", "about", "policy", "services", "faq"}
_RISK = {
    "chest pain",
    "shortness of breath",
    "seizure",
    "unconscious",
    "bleeding",
    "pregnant",
    "overdose",
    "anaphylaxis",
    "suicidal",
}


def _normalize_tokens(message: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", message or "") if t]


def _has_phrase(message: str, phrases: set[str]) -> bool:
    msg = (message or "").lower()
    return any(phrase in msg for phrase in phrases)


def _matches(message: str, keywords: set[str]) -> bool:
    tokens = _normalize_tokens(message)
    return any(t in keywords for t in tokens)


async def _respond_smalltalk_llm(pharmacy_name: str, message: str, label: str) -> str:
    if (os.getenv("AI_PROVIDER") or "").strip().lower() == "stub":
        if label == "GREETING":
            return "Hello! How can I assist you today?"
        return (
            "I'm not sure what you mean. Could you rephrase?\n"
            "For example, I can help with medication availability, booking appointments, or pharmacy hours."
        )

    provider = get_ai_provider()
    system = (
        "You are a pharmacy assistant for a single pharmacy tenant.\n"
        "Do not provide medical advice.\n"
        "Keep responses to 1-2 short sentences.\n"
    )
    if label == "GREETING":
        user = f"User said: {message}\nRespond with a friendly greeting for {pharmacy_name} and ask how you can help."
    else:
        user = (
            f"User said: {message}\n"
            "Respond that you're not sure what they mean and ask them to rephrase.\n"
            "Offer 2-3 example things you can help with (availability/appointments/hours)."
    )
    return (await provider.chat([ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)])).strip()


async def _classify(message: str) -> ClassifierResult:
    res = await classify_message(message)
    if res is not None:
        return res
    return fallback_classify(message)


def _summarize_medicine(med: models.Medicine) -> str:
    rx = "Prescription required" if med.prescription_required else "OTC"
    price = f"{med.price:.2f}" if med.price is not None else "-"
    availability = "available" if int(med.stock_level or 0) > 0 else "out of stock"
    return f"{med.name} - {rx}, price {price}, {availability}"


def _summarize_product(product: models.Product) -> str:
    price = f"{product.price:.2f}" if product.price is not None else "-"
    availability = "available" if int(product.stock_level or 0) > 0 else "out of stock"
    return f"{product.name} - price {price}, {availability}"


def _token_subjects(message: str, blocklist: set[str]) -> list[str]:
    return [t for t in _normalize_tokens(message) if t not in blocklist and len(t) >= 3]


def _wants_add_to_cart(message: str) -> bool:
    tokens = _normalize_tokens(message)
    return ("cart" in tokens and ("add" in tokens or "put" in tokens)) or ("addtocart" in tokens) or ("add" in tokens and "cart" in tokens)


def _wants_reserve(message: str) -> bool:
    tokens = _normalize_tokens(message)
    return "reserve" in tokens or "reservation" in tokens


def _find_product_match(db: Session, pharmacy_id: int, message: str) -> models.Product | None:
    tokens = _token_subjects(message, _AVAILABILITY | _RX | _OTC)
    if not tokens:
        return None
    filters = [models.Product.name.ilike(f"%{token}%") for token in tokens]
    return (
        db.query(models.Product)
        .filter(models.Product.pharmacy_id == pharmacy_id, or_(*filters))
        .order_by(models.Product.name.asc())
        .first()
    )


def _find_medicines(db: Session, pharmacy_id: int, message: str, *, rx_only: bool = False, limit: int = 3) -> list[models.Medicine]:
    tokens = _token_subjects(message, _AVAILABILITY | _RX | _OTC)
    if not tokens:
        return []
    filters = [models.Medicine.name.ilike(f"%{token}%") for token in tokens]
    query = db.query(models.Medicine).filter(models.Medicine.pharmacy_id == pharmacy_id)
    if rx_only:
        query = query.filter(models.Medicine.prescription_required.is_(True))
    return query.filter(or_(*filters)).order_by(models.Medicine.name.asc()).limit(limit).all()


def _find_fuzzy_medicines(db: Session, pharmacy_id: int, message: str, *, rx_only: bool = False, limit: int = 3) -> list[models.Medicine]:
    tokens = _token_subjects(message, _AVAILABILITY | _RX | _OTC)
    if not tokens:
        return []
    needle = " ".join(tokens).lower()
    query = db.query(models.Medicine).filter(models.Medicine.pharmacy_id == pharmacy_id)
    if rx_only:
        query = query.filter(models.Medicine.prescription_required.is_(True))
    meds = query.all()
    name_map = {str(med.name or "").lower(): med for med in meds if med.name}
    names = list(name_map.keys())
    close = difflib.get_close_matches(needle, names, n=limit, cutoff=0.72)
    return [name_map[name] for name in close]


def _build_medicine_response(
    *,
    pharmacy_id: int,
    medicine: models.Medicine,
    indexed_at: datetime | None = None,
) -> tuple[str, list[schemas.MedicineCard], list[schemas.AIAction], list[str]]:
    rx = bool(medicine.prescription_required)
    stock = int(medicine.stock_level or 0)
    price = float(medicine.price) if medicine.price is not None else None
    card = schemas.MedicineCard(
        medicine_id=int(medicine.id),
        name=str(medicine.name),
        dosage=(medicine.dosage or None),
        category=getattr(medicine, "category", None),
        rx=rx,
        price=price,
        stock=stock,
        updated_at=medicine.updated_at,
        indexed_at=indexed_at,
    )

    actions: list[schemas.AIAction] = []
    if rx:
        actions.append(
            schemas.AIAction(
                type="add_to_cart",
                label="Add to cart",
                medicine_id=int(medicine.id),
                payload={"medicine_id": int(medicine.id), "quantity": 1, "requires_prescription": True},
            )
        )
        answer = (
            f"Yes, we have {medicine.name} available. See the details card below. "
            "This medicine requires a prescription, which you'll upload at checkout."
        )
    else:
        if stock > 0:
            actions.append(
                schemas.AIAction(
                    type="add_to_cart",
                    label="Add to cart",
                    medicine_id=int(medicine.id),
                    payload={"medicine_id": int(medicine.id), "quantity": 1},
                )
            )
            answer = (
                f"Yes, we have {medicine.name} available. See the details card below."
                + (f" Price: {price:.2f}." if price is not None else "")
                + " Would you like me to add it to your cart?"
            )
        else:
            actions.append(
                schemas.AIAction(
                    type="request_notify",
                    label="Request notification",
                    medicine_id=int(medicine.id),
                    payload={"medicine_id": int(medicine.id)},
                )
            )
            answer = f"Sorry, {medicine.name} is currently out of stock. See the details card below."

    quick_replies = ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"]
    answer = f"{answer}\n\nDo you want another medicine or any other service?"
    return answer, [card], actions, quick_replies


def _find_products(db: Session, pharmacy_id: int, message: str, *, limit: int = 3) -> list[models.Product]:
    tokens = _token_subjects(message, _OTC | _AVAILABILITY)
    if not tokens:
        return []
    filters = [models.Product.name.ilike(f"%{token}%") for token in tokens]
    return (
        db.query(models.Product)
        .filter(models.Product.pharmacy_id == pharmacy_id, or_(*filters))
        .order_by(models.Product.name.asc())
        .limit(limit)
        .all()
    )


def _find_fuzzy_products(db: Session, pharmacy_id: int, message: str, *, limit: int = 3) -> list[models.Product]:
    tokens = _token_subjects(message, _OTC | _AVAILABILITY)
    if not tokens:
        return []
    needle = " ".join(tokens).lower()
    products = db.query(models.Product).filter(models.Product.pharmacy_id == pharmacy_id).all()
    name_map = {str(product.name or "").lower(): product for product in products if product.name}
    names = list(name_map.keys())
    close = difflib.get_close_matches(needle, names, n=limit, cutoff=0.72)
    return [name_map[name] for name in close]


def _appointment_summary(db: Session, pharmacy_id: int) -> tuple[list[str], list[str]]:
    now = datetime.utcnow()
    services = (
        db.query(models.Appointment.type)
        .filter(models.Appointment.pharmacy_id == pharmacy_id, models.Appointment.type.isnot(None))
        .distinct()
        .all()
    )
    service_list = sorted({str(row[0]).strip() for row in services if row and str(row[0]).strip()})
    slots = (
        db.query(models.Appointment.scheduled_time)
        .filter(
            models.Appointment.pharmacy_id == pharmacy_id,
            models.Appointment.scheduled_time >= now,
            models.Appointment.status.in_(["PENDING", "CONFIRMED"]),
        )
        .order_by(models.Appointment.scheduled_time.asc())
        .limit(5)
        .all()
    )
    slot_list = [row[0].isoformat() for row in slots if row and row[0]]
    return service_list, slot_list


def _parse_iso_datetime(text: str) -> datetime | None:
    msg = (text or "").strip()
    if not msg:
        return None
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(:\d{2})?\b", msg)
    if not m:
        return None
    dt_text = f"{m.group(1)}T{m.group(2)}{m.group(3) or ''}"
    try:
        return datetime.fromisoformat(dt_text)
    except Exception:
        return None


def _extract_name(text: str) -> str | None:
    msg = (text or "").strip()
    if not msg:
        return None
    m = re.search(r"\b(my name is|i am|i'm)\s+([a-zA-Z][a-zA-Z\s'-]{1,60})\b", msg, flags=re.IGNORECASE)
    if not m:
        return None
    name = m.group(2).strip()
    return name if name else None


def _extract_phone(text: str) -> str | None:
    msg = (text or "").strip()
    if not msg:
        return None
    m = re.search(r"(\+\d{7,15})", msg)
    if not m:
        return None
    try:
        return validate_e164_phone(m.group(1), "customer")
    except Exception:
        return None


def get_customer_chat_id(chat_id: str | None) -> str:
    if chat_id and chat_id.strip():
        return chat_id.strip()
    return secrets.token_urlsafe(12)


@dataclass(frozen=True)
class IntentResult:
    intent: str
    answer: str
    escalated: bool
    confidence: float
    citations: list[schemas.AICitation]
    cards: list[schemas.MedicineCard] = field(default_factory=list)
    actions: list[schemas.AIAction] = field(default_factory=list)
    quick_replies: list[str] = field(default_factory=list)
    data_last_updated_at: datetime | None = None
    indexed_at: datetime | None = None


async def route_intent(
    db: Session,
    pharmacy_id: int,
    customer_id: str,
    message: str,
    *,
    memory_context: list[str] | None = None,
    turns: list[dict] | None = None,
    session_id: str | None = None,
) -> IntentResult:
    classification = await _classify(message)
    intent = classification.intent
    query = (classification.query or "").strip() or message

    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    pharmacy_name = (pharmacy.name if pharmacy else "").strip() or "our pharmacy"
    hours = (pharmacy.operating_hours if pharmacy else None) or ""
    cod = bool(getattr(pharmacy, "support_cod", True)) if pharmacy else True
    contact_phone = (getattr(pharmacy, "contact_phone", None) if pharmacy else None) or ""
    contact_email = (getattr(pharmacy, "contact_email", None) if pharmacy else None) or ""
    playbook_doc = (
        db.query(models.Document)
        .filter(
            models.Document.pharmacy_id == pharmacy_id,
            models.Document.source_type == "pharmacy",
            models.Document.source_key == "pharmacy:playbook",
        )
            .first()
    )

    quick_replies = ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"]

    if intent in {"GREETING", "UNKNOWN"}:
        answer = await _respond_smalltalk_llm(pharmacy_name, message, intent)
        return IntentResult(
            intent=intent,
            answer=answer,
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("intent_router", intent.lower())],
            quick_replies=quick_replies,
        )

    if intent == "RISKY_MEDICAL":
        contact_bits = []
        if contact_phone:
            contact_bits.append(f"Phone: {contact_phone}")
        if contact_email:
            contact_bits.append(f"Email: {contact_email}")
        contact_text = (" " + " ".join(contact_bits)) if contact_bits else ""
        return IntentResult(
            intent=intent,
            answer=(
                "This looks like a medical-risk question. I will escalate this to the pharmacist. "
                "If this is an emergency, seek urgent medical care."
                + contact_text
            ),
            escalated=True,
            confidence=0.2,
            citations=[_system_citation("medical_risk", "Escalation required for medical risk.")],
            quick_replies=quick_replies,
        )

    if intent == "HOURS_CONTACT":
        parts = []
        if hours:
            parts.append(f"Store hours: {hours}.")
        if contact_phone:
            parts.append(f"Phone: {contact_phone}.")
        if contact_email:
            parts.append(f"Email: {contact_email}.")
        if parts:
            return IntentResult(
                intent=intent,
                answer=" ".join(parts) + "\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_playbook_citation(pharmacy, "hours_contact", " ".join(parts))],
                quick_replies=quick_replies,
                data_last_updated_at=pharmacy.updated_at if pharmacy else None,
                indexed_at=playbook_doc.indexed_at if playbook_doc else None,
            )

    if intent == "SERVICES_INFO" and _matches(message, _DELIVERY):
        delivery = "Cash on delivery is available." if cod else "Cash on delivery is not available."
        return IntentResult(
            intent=intent,
            answer=delivery + "\n\nDo you want another medicine or any other service?",
            escalated=False,
            confidence=0.0,
            citations=[_playbook_citation(pharmacy, "delivery_cod", delivery)],
            quick_replies=quick_replies,
            data_last_updated_at=pharmacy.updated_at if pharmacy else None,
            indexed_at=playbook_doc.indexed_at if playbook_doc else None,
        )

    if intent == "APPOINTMENT_BOOKING":
        services, slots = _appointment_summary(db, pharmacy_id)
        appointment_doc = (
            db.query(models.Document)
            .filter(
                models.Document.pharmacy_id == pharmacy_id,
                models.Document.source_type == "appointment",
                models.Document.source_key == "appointment:summary",
            )
            .first()
        )

        state = session_memory.get_state(turns or [], "appointment_booking") if turns is not None else None
        desired_time = _parse_iso_datetime(message)
        if desired_time is None and state and state.get("scheduled_time"):
            try:
                desired_time = datetime.fromisoformat(str(state.get("scheduled_time")))
            except Exception:
                desired_time = None

        desired_type = (str(state.get("type")) if state and state.get("type") else "").strip()
        if not desired_type:
            msg_lower = (message or "").lower()
            for svc in services:
                if svc and svc.lower() in msg_lower:
                    desired_type = svc
                    break
        if not desired_type:
            desired_type = "Consultation"

        customer_name = _extract_name(message) or (str(state.get("customer_name")).strip() if state and state.get("customer_name") else None)
        customer_phone = _extract_phone(message) or (str(state.get("customer_phone")).strip() if state and state.get("customer_phone") else None)

        missing_bits: list[str] = []
        if not desired_time:
            missing_bits.append("a preferred date/time (YYYY-MM-DD HH:MM)")
        if not customer_name:
            missing_bits.append("your name")
        if not customer_phone:
            missing_bits.append("your phone number in E.164 format (e.g., +15551234567)")

        services_text = ", ".join(services) if services else "Not listed yet"
        slots_text = ", ".join(slots) if slots else "Not listed yet"

        if missing_bits:
            if turns is not None:
                session_memory.set_state(
                    turns,
                    "appointment_booking",
                    {
                        "type": desired_type,
                        "scheduled_time": desired_time.isoformat() if desired_time else None,
                        "customer_name": customer_name,
                        "customer_phone": customer_phone,
                    },
                )
                if session_id:
                    session_memory.save_turns(db, pharmacy_id, session_id, turns)
            answer = (
                "I can book the appointment here in chat. Please share "
                + ", ".join(missing_bits)
                + ".\n"
                + f"Available services: {services_text}\n"
                + f"Next available slots: {slots_text}\n\n"
                + "Do you want another medicine or any other service?"
            )
            return IntentResult(
                intent=intent,
                answer=answer,
                escalated=False,
                confidence=0.0,
                citations=[_appointment_citation(appointment_doc, f"services={services_text}, slots={slots_text}")],
                quick_replies=quick_replies,
                data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
                indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
            )

        if desired_time and desired_time < datetime.utcnow():
            return IntentResult(
                intent=intent,
                answer="That time looks in the past. Please share a future date/time (YYYY-MM-DD HH:MM).",
                escalated=False,
                confidence=0.0,
                citations=[_appointment_citation(appointment_doc, "Requested a future time")],
                quick_replies=quick_replies,
                data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
                indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
            )

        appt = models.Appointment(
            customer_id=customer_id,
            customer_name=(customer_name.strip() if customer_name else None),
            customer_phone=validate_e164_phone(customer_phone, "customer") if customer_phone else None,
            type=str(desired_type).strip() or "Consultation",
            scheduled_time=desired_time,
            status="PENDING",
            pharmacy_id=pharmacy_id,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)
        if turns is not None:
            session_memory.clear_state(turns, "appointment_booking")
            if session_id:
                session_memory.save_turns(db, pharmacy_id, session_id, turns)

        return IntentResult(
            intent=intent,
            answer=f"Booked your {appt.type} appointment for {appt.scheduled_time.isoformat()}. Reference: #{appt.id}.\n\nDo you want another medicine or any other service?",
            escalated=False,
            confidence=0.0,
            citations=[_appointment_citation(appointment_doc, f"appointment_id={appt.id}")],
            quick_replies=quick_replies,
            data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
            indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
        )

    if intent == "ORDER_CART":
        if turns is None:
            return IntentResult(
                intent=intent,
                answer="Which medicine should I add to your cart?\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_system_citation("cart_missing_context", "No session turns available.")],
                quick_replies=quick_replies,
            )
        last_item = session_memory.get_state(turns, "last_item") or {}
        medicine_id = int(last_item.get("medicine_id") or 0)
        if not _wants_add_to_cart(message) or medicine_id <= 0:
            return IntentResult(
                intent=intent,
                answer="Which medicine should I add to your cart?\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_system_citation("cart_prompt", "Missing medicine context for cart action.")],
                quick_replies=quick_replies,
            )
        action = schemas.AIAction(
            type="add_to_cart",
            label="Add to cart",
            medicine_id=medicine_id,
            payload={"medicine_id": medicine_id, "quantity": 1},
        )
        if session_id:
            session_memory.save_turns(db, pharmacy_id, session_id, turns)
        return IntentResult(
            intent=intent,
            answer="Ready to add it to your cart.",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("cart_action", f"add_to_cart:medicine:{medicine_id}")],
            actions=[action],
            quick_replies=quick_replies,
        )

    if intent == "RX_UPLOAD":
        action = schemas.AIAction(type="upload_prescription", label="Upload prescription", medicine_id=None, payload=None)
        return IntentResult(
            intent=intent,
            answer="Please upload your prescription below.\n\nDo you want another medicine or any other service?",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("rx_upload", "Requested prescription upload.")],
            actions=[action],
            quick_replies=quick_replies,
        )

    if intent == "MEDICINE_SEARCH":
        matches = _find_medicines(db, pharmacy_id, query, rx_only=False)
        if matches:
            first = matches[0]
            answer_text, cards, actions, qrs = _build_medicine_response(pharmacy_id=pharmacy_id, medicine=first, indexed_at=None)
            if turns is not None:
                session_memory.set_state(turns, "last_item", {"medicine_id": int(first.id), "name": str(first.name)})
                if session_id:
                    session_memory.save_turns(db, pharmacy_id, session_id, turns)
            return IntentResult(
                intent=intent,
                answer=answer_text,
                escalated=False,
                confidence=0.0,
                citations=[_medicine_citation(med) for med in matches],
                cards=cards,
                actions=actions,
                quick_replies=qrs,
                data_last_updated_at=max((med.updated_at for med in matches), default=None),
            )
        fuzzy = _find_fuzzy_medicines(db, pharmacy_id, query, rx_only=False)
        if fuzzy:
            suggestions = "\n".join(f"- {med.name}" for med in fuzzy if med.name)
            return IntentResult(
                intent=intent,
                answer=f"I could not find an exact match. Did you mean:\n{suggestions}\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_medicine_citation(med) for med in fuzzy],
                quick_replies=[med.name for med in fuzzy if med.name][:3] + quick_replies,
                data_last_updated_at=max((med.updated_at for med in fuzzy), default=None),
            )
        return IntentResult(
            intent=intent,
            answer="I couldn't find that medicine in this pharmacy. Please confirm the exact name and dosage.\n\nDo you want another medicine or any other service?",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("medicine_not_found", "Medicine lookup returned no matches.")],
            quick_replies=quick_replies,
        )

    if intent == "PRODUCT_SEARCH":
        matches = _find_products(db, pharmacy_id, query)
        if matches:
            lines = "\n".join(f"- {_summarize_product(product)}" for product in matches)
            return IntentResult(
                intent=intent,
                answer=f"Here are matching products:\n{lines}\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_product_citation(product) for product in matches],
                quick_replies=quick_replies,
            )
        fuzzy = _find_fuzzy_products(db, pharmacy_id, query)
        if fuzzy:
            suggestions = "\n".join(f"- {product.name}" for product in fuzzy if product.name)
            return IntentResult(
                intent=intent,
                answer=f"I could not find an exact match. Did you mean:\n{suggestions}\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_product_citation(product) for product in fuzzy],
                quick_replies=[product.name for product in fuzzy if product.name][:3] + quick_replies,
            )
        return IntentResult(
            intent=intent,
            answer="Which product are you looking for? Please share the name.\n\nDo you want another medicine or any other service?",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("product_prompt", "Requesting product name for lookup.")],
            quick_replies=quick_replies,
        )

    if intent in {"SERVICES_INFO", "GENERAL_RAG"}:
        answer, citations, confidence, escalated, freshness, _ = await hybrid_answer(
            db, pharmacy_id, query, customer_id=customer_id, memory_context=memory_context
        )
        return IntentResult(
            intent=intent,
            answer=answer,
            escalated=bool(escalated),
            confidence=float(confidence),
            citations=citations,
            quick_replies=quick_replies,
            data_last_updated_at=freshness.get("data_last_updated_at"),
            indexed_at=freshness.get("indexed_at"),
        )

    # Fallback
    return IntentResult(
        intent="UNKNOWN",
        answer="I'm not sure what you mean. Could you rephrase?\n\nDo you want another medicine or any other service?",
        escalated=False,
        confidence=0.0,
        citations=[_system_citation("fallback", "No handler matched.")],
        quick_replies=quick_replies,
    )

    # Greetings and unknown inputs are handled by the chat model (no hardcoded responses).
    if intent in {"GREETING", "UNKNOWN"}:
        answer = await _respond_smalltalk_llm(pharmacy_name, message, intent)
        return IntentResult(
            intent=intent,
            answer=answer,
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("ai_intent", f"{intent.lower()}_handled_by_ai")],
            quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
            data_last_updated_at=None,
            indexed_at=None,
        )

    if intent == "MEDICAL_ADVICE_RISK":
        return IntentResult(
            intent=intent,
            answer=(
                "This looks like a medical-risk question. I will escalate this to the pharmacist. "
                "If this is an emergency, seek urgent medical care."
            ),
            escalated=True,
            confidence=0.2,
            citations=[_system_citation("medical_risk", "Escalation required for medical risk.")],
            data_last_updated_at=None,
            indexed_at=None,
        )

    if intent == "HOURS_CONTACT":
        parts = []
        if hours:
            parts.append(f"Store hours: {hours}.")
        if contact_phone:
            parts.append(f"Phone: {contact_phone}.")
        if contact_email:
            parts.append(f"Email: {contact_email}.")
        answer = " ".join(parts) if parts else "Store hours and contact details are not available yet."
        preview = " ".join(parts) if parts else "Not available"
        return IntentResult(
            intent=intent,
            answer=answer,
            escalated=False,
            confidence=0.0,
            citations=[_playbook_citation(pharmacy, "hours", preview)],
            data_last_updated_at=pharmacy.updated_at if pharmacy else None,
            indexed_at=playbook_doc.indexed_at if playbook_doc else None,
        )

    if intent == "DELIVERY_COD":
        delivery = "Cash on delivery is available." if cod else "Cash on delivery is not available."
        return IntentResult(
            intent=intent,
            answer=delivery,
            escalated=False,
            confidence=0.0,
            citations=[_playbook_citation(pharmacy, "cod", delivery)],
            data_last_updated_at=pharmacy.updated_at if pharmacy else None,
            indexed_at=playbook_doc.indexed_at if playbook_doc else None,
        )

    if intent == "APPOINTMENT_BOOKING":
        services, slots = _appointment_summary(db, pharmacy_id)
        appointment_doc = (
            db.query(models.Document)
            .filter(
                models.Document.pharmacy_id == pharmacy_id,
                models.Document.source_type == "appointment",
                models.Document.source_key == "appointment:summary",
            )
            .first()
        )
        state = session_memory.get_state(turns or [], "appointment_booking") if turns is not None else None
        desired_time = _parse_iso_datetime(message)
        if desired_time is None and state and state.get("scheduled_time"):
            try:
                desired_time = datetime.fromisoformat(str(state.get("scheduled_time")))
            except Exception:
                desired_time = None

        desired_type = (str(state.get("type")) if state and state.get("type") else "").strip()
        if not desired_type:
            msg_lower = (message or "").lower()
            for svc in services:
                if svc and svc.lower() in msg_lower:
                    desired_type = svc
                    break
        if not desired_type and _matches(message, _APPOINTMENT):
            desired_type = "Consultation"

        customer_name = _extract_name(message) or (str(state.get("customer_name")).strip() if state and state.get("customer_name") else None)
        customer_phone = _extract_phone(message) or (str(state.get("customer_phone")).strip() if state and state.get("customer_phone") else None)

        missing_bits: list[str] = []
        if not desired_type:
            missing_bits.append("the visit type")
        if not desired_time:
            missing_bits.append("a preferred date/time (YYYY-MM-DD HH:MM)")
        if not customer_name:
            missing_bits.append("your name")
        if not customer_phone:
            missing_bits.append("your phone number in E.164 format (e.g., +15551234567)")

        services_text = ", ".join(services) if services else "Not listed yet"
        slots_text = ", ".join(slots) if slots else "Not listed yet"

        if missing_bits:
            if turns is not None:
                session_memory.set_state(
                    turns,
                    "appointment_booking",
                    {
                        "type": desired_type or None,
                        "scheduled_time": desired_time.isoformat() if desired_time else None,
                        "customer_name": customer_name,
                        "customer_phone": customer_phone,
                    },
                )
                if session_id:
                    session_memory.save_turns(db, pharmacy_id, session_id, turns)
            answer = (
                "I can book the appointment here in chat. Please share "
                + ", ".join(missing_bits)
                + ".\n"
                + f"Available services: {services_text}\n"
                + f"Next available slots: {slots_text}"
            )
            return IntentResult(
                intent=intent,
                answer=answer,
                escalated=False,
                confidence=0.0,
                citations=[_appointment_citation(appointment_doc, f"services={services_text}, slots={slots_text}")],
                data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
                indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
            )

        if desired_time and desired_time < datetime.utcnow():
            if turns is not None:
                session_memory.set_state(
                    turns,
                    "appointment_booking",
                    {
                        "type": desired_type,
                        "scheduled_time": None,
                        "customer_name": customer_name,
                        "customer_phone": customer_phone,
                    },
                )
                if session_id:
                    session_memory.save_turns(db, pharmacy_id, session_id, turns)
            return IntentResult(
                intent=intent,
                answer="That time looks in the past. Please share a future date/time (YYYY-MM-DD HH:MM).",
                escalated=False,
                confidence=0.0,
                citations=[_appointment_citation(appointment_doc, "Requested a future time")],
                data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
                indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
            )

        appt = models.Appointment(
            customer_id=customer_id,
            customer_name=(customer_name.strip() if customer_name else None),
            customer_phone=validate_e164_phone(customer_phone, "customer") if customer_phone else None,
            type=str(desired_type).strip() or "Consultation",
            scheduled_time=desired_time,
            status="PENDING",
            pharmacy_id=pharmacy_id,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)
        if turns is not None:
            session_memory.clear_state(turns, "appointment_booking")
            if session_id:
                session_memory.save_turns(db, pharmacy_id, session_id, turns)

        return IntentResult(
            intent=intent,
            answer=f"Booked your {appt.type} appointment for {appt.scheduled_time.isoformat()}. Reference: #{appt.id}.",
            escalated=False,
            confidence=0.0,
            citations=[_appointment_citation(appointment_doc, f"appointment_id={appt.id}")],
            data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
            indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
        )
        answer, confidence, escalated, chunks = await rag_service.answer_for_sources(
            db,
            pharmacy_id,
            customer_id,
            message,
            {"appointment"},
            memory_context=memory_context,
        )
        citations, data_last_updated_at, indexed_at = _citations_from_chunks(db, chunks)
        if answer.lower() not in {"i don't know", "i don't know."}:
            return IntentResult(
                intent=intent,
                answer=answer,
                escalated=bool(escalated),
                confidence=float(confidence),
                citations=citations,
                data_last_updated_at=data_last_updated_at,
                indexed_at=indexed_at,
            )
        return IntentResult(
            intent=intent,
            answer=(
                "You can book an appointment on the appointments page. "
                "Please share the visit type and a preferred date/time (e.g., 2025-02-12 15:30)."
            ),
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("appointment_booking", "Direct customers to the appointments page.")],
            data_last_updated_at=None,
            indexed_at=None,
        )

    if intent in {"AVAILABILITY_CHECK", "RX_MEDICINE_QUERY"}:
        rx_only = intent == "RX_MEDICINE_QUERY"
        if intent == "AVAILABILITY_CHECK":
            subjects = _token_subjects(message, _AVAILABILITY | _RX | _OTC)
            if not subjects:
                if any(t in {"painkiller", "antibiotic", "cold", "flu", "allergy"} for t in _normalize_tokens(message)):
                    return IntentResult(
                        intent=intent,
                        answer=(
                            "Which medicine exactly do you mean (brand name), and is this for an adult or child? "
                            "Also mention any allergies."
                        ),
                        escalated=False,
                        confidence=0.0,
                        citations=[_system_citation("clarify_medicine", "Vague medicine query; request clarification.")],
                        quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                        data_last_updated_at=None,
                        indexed_at=None,
                    )
                return IntentResult(
                    intent=intent,
                    answer="Which medicine are you asking about? Please share the exact name (and dosage, if possible).",
                    escalated=False,
                    confidence=0.0,
                    citations=[_system_citation("availability_prompt", "Requesting medicine name for availability check.")],
                    quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                    data_last_updated_at=None,
                    indexed_at=None,
                )
            matches = _find_medicines(db, pharmacy_id, message, rx_only=False)
            if matches:
                first = matches[0]
                answer_text, cards, actions, quick_replies = _build_medicine_response(
                    pharmacy_id=pharmacy_id,
                    medicine=first,
                    indexed_at=None,
                )
                if turns is not None:
                    session_memory.set_state(
                        turns,
                        "last_item",
                        {
                            "medicine_id": int(first.id),
                            "name": str(first.name),
                        },
                    )
                    if session_id:
                        session_memory.save_turns(db, pharmacy_id, session_id, turns)
                return IntentResult(
                    intent=intent,
                    answer=answer_text,
                    escalated=False,
                    confidence=0.0,
                    citations=[_medicine_citation(med) for med in matches],
                    cards=cards,
                    actions=actions,
                    quick_replies=quick_replies,
                    data_last_updated_at=max((med.updated_at for med in matches), default=None),
                    indexed_at=None,
                )

            fuzzy = _find_fuzzy_medicines(db, pharmacy_id, message, rx_only=False)
            if fuzzy:
                suggestions = "\n".join(f"- {med.name}" for med in fuzzy if med.name)
                return IntentResult(
                    intent=intent,
                    answer=f"I could not find an exact match. Did you mean:\n{suggestions}\n\nDo you want another medicine or any other service?",
                    escalated=False,
                    confidence=0.0,
                    citations=[_medicine_citation(med) for med in fuzzy],
                    quick_replies=[med.name for med in fuzzy if med.name][:3]
                    + ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                    data_last_updated_at=max((med.updated_at for med in fuzzy), default=None),
                    indexed_at=None,
                )

            # Fall back to hybrid only if we couldn't match by name.
            if memory_context:
                answer, citations, confidence, escalated, freshness, _ = await hybrid_answer(
                    db, pharmacy_id, message, customer_id=customer_id, memory_context=memory_context
                )
                return IntentResult(
                    intent=intent,
                    answer=answer,
                    escalated=bool(escalated),
                    confidence=float(confidence),
                    citations=citations,
                    quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                    data_last_updated_at=freshness.get("data_last_updated_at"),
                    indexed_at=freshness.get("indexed_at"),
                )
            return IntentResult(
                intent=intent,
                answer="I couldn't find that medicine in this pharmacy. Please confirm the exact name and dosage.",
                escalated=False,
                confidence=0.0,
                citations=[_system_citation("medicine_not_found", "Medicine name lookup returned no matches.")],
                quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                data_last_updated_at=None,
                indexed_at=None,
            )
        matches = _find_medicines(db, pharmacy_id, message, rx_only=rx_only)
        if matches:
            first = matches[0]
            answer_text, cards, actions, quick_replies = _build_medicine_response(
                pharmacy_id=pharmacy_id,
                medicine=first,
                indexed_at=None,
            )
            if turns is not None:
                session_memory.set_state(
                    turns,
                    "last_item",
                    {
                        "medicine_id": int(first.id),
                        "name": str(first.name),
                    },
                )
                if session_id:
                    session_memory.save_turns(db, pharmacy_id, session_id, turns)
            return IntentResult(
                intent=intent,
                answer=answer_text,
                escalated=False,
                confidence=0.0,
                citations=[_medicine_citation(med) for med in matches],
                cards=cards,
                actions=actions,
                quick_replies=quick_replies,
                data_last_updated_at=max((med.updated_at for med in matches), default=None),
                indexed_at=None,
            )
        fuzzy = _find_fuzzy_medicines(db, pharmacy_id, message, rx_only=rx_only)
        if fuzzy:
            suggestions = "\n".join(f"- {med.name}" for med in fuzzy if med.name)
            return IntentResult(
                intent=intent,
                answer=f"I could not find an exact match. Did you mean:\n{suggestions}",
                escalated=False,
                confidence=0.0,
                citations=[_medicine_citation(med) for med in fuzzy],
                quick_replies=[med.name for med in fuzzy if med.name][:3]
                + ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                data_last_updated_at=max((med.updated_at for med in fuzzy), default=None),
                indexed_at=None,
            )
        return IntentResult(
            intent=intent,
            answer="Which medicine are you asking about? Please share the exact name (and dosage, if possible).",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("availability_prompt", "Requesting medicine name for availability check.")],
            quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
            data_last_updated_at=None,
            indexed_at=None,
        )

    if intent == "OTC_PRODUCT_QUERY":
        matches = _find_products(db, pharmacy_id, message)
        if matches:
            lines = "\n".join(f"- {_summarize_product(product)}" for product in matches)
            return IntentResult(
                intent=intent,
                answer=f"Here are matching products:\n{lines}",
                escalated=False,
                confidence=0.0,
                citations=[_product_citation(product) for product in matches],
                data_last_updated_at=None,
                indexed_at=None,
            )
        fuzzy = _find_fuzzy_products(db, pharmacy_id, message)
        if fuzzy:
            suggestions = "\n".join(f"- {product.name}" for product in fuzzy if product.name)
            return IntentResult(
                intent=intent,
                answer=f"I could not find an exact match. Did you mean:\n{suggestions}",
                escalated=False,
                confidence=0.0,
                citations=[_product_citation(product) for product in fuzzy],
                data_last_updated_at=None,
                indexed_at=None,
            )
        answer, confidence, escalated, chunks = await rag_service.answer_for_sources(
            db,
            pharmacy_id,
            customer_id,
            message,
            {"product"},
            memory_context=memory_context,
        )
        citations, data_last_updated_at, indexed_at = _citations_from_chunks(db, chunks)
        if answer.lower() not in {"i don't know", "i don't know."}:
            return IntentResult(
                intent=intent,
                answer=answer,
                escalated=bool(escalated),
                confidence=float(confidence),
                citations=citations,
                data_last_updated_at=data_last_updated_at,
                indexed_at=indexed_at,
            )
        return IntentResult(
            intent=intent,
            answer="Which product are you looking for? Please share the name.",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("product_prompt", "Requesting product name for lookup.")],
            data_last_updated_at=None,
            indexed_at=None,
        )

    if intent in {"GENERAL_INFO_RAG", "UNKNOWN"}:
        answer, citations, confidence, escalated, freshness, _ = await hybrid_answer(
            db, pharmacy_id, message, customer_id=customer_id, memory_context=memory_context
        )
        return IntentResult(
            intent=intent,
            answer=answer,
            escalated=bool(escalated),
            confidence=float(confidence),
            citations=citations,
            data_last_updated_at=freshness.get("data_last_updated_at"),
            indexed_at=freshness.get("indexed_at"),
        )

    return IntentResult(
        intent=intent,
        answer="I don't know.",
        escalated=False,
        confidence=0.0,
        citations=[_system_citation("fallback", "No source matched the question.")],
        data_last_updated_at=None,
        indexed_at=None,
    )
def _find_products(db: Session, pharmacy_id: int, message: str, *, limit: int = 3) -> list[models.Product]:
    tokens = _token_subjects(message, _OTC | _AVAILABILITY)
    if not tokens:
        return []
    filters = [models.Product.name.ilike(f"%{token}%") for token in tokens]
    return (
        db.query(models.Product)
        .filter(models.Product.pharmacy_id == pharmacy_id, or_(*filters))
        .order_by(models.Product.name.asc())
        .limit(limit)
        .all()
    )


def _find_fuzzy_products(db: Session, pharmacy_id: int, message: str, *, limit: int = 3) -> list[models.Product]:
    tokens = _token_subjects(message, _OTC | _AVAILABILITY)
    if not tokens:
        return []
    needle = " ".join(tokens).lower()
    products = db.query(models.Product).filter(models.Product.pharmacy_id == pharmacy_id).all()
    name_map = {str(product.name or "").lower(): product for product in products if product.name}
    names = list(name_map.keys())
    close = difflib.get_close_matches(needle, names, n=limit, cutoff=0.72)
    return [name_map[name] for name in close]


def _appointment_summary(db: Session, pharmacy_id: int) -> tuple[list[str], list[str]]:
    now = datetime.utcnow()
    services = (
        db.query(models.Appointment.type)
        .filter(models.Appointment.pharmacy_id == pharmacy_id, models.Appointment.type.isnot(None))
        .distinct()
        .all()
    )
    service_list = sorted({str(row[0]).strip() for row in services if row and str(row[0]).strip()})
    slots = (
        db.query(models.Appointment.scheduled_time)
        .filter(
            models.Appointment.pharmacy_id == pharmacy_id,
            models.Appointment.scheduled_time >= now,
            models.Appointment.status.in_(["PENDING", "CONFIRMED"]),
        )
        .order_by(models.Appointment.scheduled_time.asc())
        .limit(5)
        .all()
    )
    slot_list = [row[0].isoformat() for row in slots if row and row[0]]
    return service_list, slot_list


def _parse_iso_datetime(text: str) -> datetime | None:
    msg = (text or "").strip()
    if not msg:
        return None
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(:\d{2})?\b", msg)
    if not m:
        return None
    dt_text = f"{m.group(1)}T{m.group(2)}{m.group(3) or ''}"
    try:
        return datetime.fromisoformat(dt_text)
    except Exception:
        return None


def _extract_name(text: str) -> str | None:
    msg = (text or "").strip()
    if not msg:
        return None
    m = re.search(r"\b(my name is|i am|i'm)\s+([a-zA-Z][a-zA-Z\s'-]{1,60})\b", msg, flags=re.IGNORECASE)
    if not m:
        return None
    name = m.group(2).strip()
    return name if name else None


def _extract_phone(text: str) -> str | None:
    msg = (text or "").strip()
    if not msg:
        return None
    m = re.search(r"(\+\d{7,15})", msg)
    if not m:
        return None
    try:
        return validate_e164_phone(m.group(1), "customer")
    except Exception:
        return None


def get_customer_chat_id(chat_id: str | None) -> str:
    if chat_id and chat_id.strip():
        return chat_id.strip()
    return secrets.token_urlsafe(12)


@dataclass(frozen=True)
class IntentResult:
    intent: str
    answer: str
    escalated: bool
    confidence: float
    citations: list[schemas.AICitation]
    cards: list[schemas.MedicineCard] = field(default_factory=list)
    actions: list[schemas.AIAction] = field(default_factory=list)
    quick_replies: list[str] = field(default_factory=list)
    data_last_updated_at: datetime | None = None
    indexed_at: datetime | None = None


async def route_intent(
    db: Session,
    pharmacy_id: int,
    customer_id: str,
    message: str,
    *,
    memory_context: list[str] | None = None,
    turns: list[dict] | None = None,
    session_id: str | None = None,
) -> IntentResult:
    classification = await _classify(message)
    intent = classification.intent
    query = (classification.query or "").strip() or message

    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    pharmacy_name = (pharmacy.name if pharmacy else "").strip() or "our pharmacy"
    hours = (pharmacy.operating_hours if pharmacy else None) or ""
    cod = bool(getattr(pharmacy, "support_cod", True)) if pharmacy else True
    contact_phone = (getattr(pharmacy, "contact_phone", None) if pharmacy else None) or ""
    contact_email = (getattr(pharmacy, "contact_email", None) if pharmacy else None) or ""
    playbook_doc = (
        db.query(models.Document)
        .filter(
            models.Document.pharmacy_id == pharmacy_id,
            models.Document.source_type == "pharmacy",
            models.Document.source_key == "pharmacy:playbook",
        )
            .first()
    )

    quick_replies = ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"]

    if intent in {"GREETING", "UNKNOWN"}:
        answer = await _respond_smalltalk_llm(pharmacy_name, message, intent)
        return IntentResult(
            intent=intent,
            answer=answer,
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("intent_router", intent.lower())],
            quick_replies=quick_replies,
        )

    if intent == "RISKY_MEDICAL":
        contact_bits = []
        if contact_phone:
            contact_bits.append(f"Phone: {contact_phone}")
        if contact_email:
            contact_bits.append(f"Email: {contact_email}")
        contact_text = (" " + " ".join(contact_bits)) if contact_bits else ""
        return IntentResult(
            intent=intent,
            answer=(
                "This looks like a medical-risk question. I will escalate this to the pharmacist. "
                "If this is an emergency, seek urgent medical care."
                + contact_text
            ),
            escalated=True,
            confidence=0.2,
            citations=[_system_citation("medical_risk", "Escalation required for medical risk.")],
            quick_replies=quick_replies,
        )

    if intent == "HOURS_CONTACT":
        parts = []
        if hours:
            parts.append(f"Store hours: {hours}.")
        if contact_phone:
            parts.append(f"Phone: {contact_phone}.")
        if contact_email:
            parts.append(f"Email: {contact_email}.")
        if parts:
            return IntentResult(
                intent=intent,
                answer=" ".join(parts) + "\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_playbook_citation(pharmacy, "hours_contact", " ".join(parts))],
                quick_replies=quick_replies,
                data_last_updated_at=pharmacy.updated_at if pharmacy else None,
                indexed_at=playbook_doc.indexed_at if playbook_doc else None,
            )

    if intent == "SERVICES_INFO" and _matches(message, _DELIVERY):
        delivery = "Cash on delivery is available." if cod else "Cash on delivery is not available."
        return IntentResult(
            intent=intent,
            answer=delivery + "\n\nDo you want another medicine or any other service?",
            escalated=False,
            confidence=0.0,
            citations=[_playbook_citation(pharmacy, "delivery_cod", delivery)],
            quick_replies=quick_replies,
            data_last_updated_at=pharmacy.updated_at if pharmacy else None,
            indexed_at=playbook_doc.indexed_at if playbook_doc else None,
        )

    if intent == "APPOINTMENT_BOOKING":
        services, slots = _appointment_summary(db, pharmacy_id)
        appointment_doc = (
            db.query(models.Document)
            .filter(
                models.Document.pharmacy_id == pharmacy_id,
                models.Document.source_type == "appointment",
                models.Document.source_key == "appointment:summary",
            )
            .first()
        )

        state = session_memory.get_state(turns or [], "appointment_booking") if turns is not None else None
        desired_time = _parse_iso_datetime(message)
        if desired_time is None and state and state.get("scheduled_time"):
            try:
                desired_time = datetime.fromisoformat(str(state.get("scheduled_time")))
            except Exception:
                desired_time = None

        desired_type = (str(state.get("type")) if state and state.get("type") else "").strip()
        if not desired_type:
            msg_lower = (message or "").lower()
            for svc in services:
                if svc and svc.lower() in msg_lower:
                    desired_type = svc
                    break
        if not desired_type:
            desired_type = "Consultation"

        customer_name = _extract_name(message) or (str(state.get("customer_name")).strip() if state and state.get("customer_name") else None)
        customer_phone = _extract_phone(message) or (str(state.get("customer_phone")).strip() if state and state.get("customer_phone") else None)

        missing_bits: list[str] = []
        if not desired_time:
            missing_bits.append("a preferred date/time (YYYY-MM-DD HH:MM)")
        if not customer_name:
            missing_bits.append("your name")
        if not customer_phone:
            missing_bits.append("your phone number in E.164 format (e.g., +15551234567)")

        services_text = ", ".join(services) if services else "Not listed yet"
        slots_text = ", ".join(slots) if slots else "Not listed yet"

        if missing_bits:
            if turns is not None:
                session_memory.set_state(
                    turns,
                    "appointment_booking",
                    {
                        "type": desired_type,
                        "scheduled_time": desired_time.isoformat() if desired_time else None,
                        "customer_name": customer_name,
                        "customer_phone": customer_phone,
                    },
                )
                if session_id:
                    session_memory.save_turns(db, pharmacy_id, session_id, turns)
            answer = (
                "I can book the appointment here in chat. Please share "
                + ", ".join(missing_bits)
                + ".\n"
                + f"Available services: {services_text}\n"
                + f"Next available slots: {slots_text}\n\n"
                + "Do you want another medicine or any other service?"
            )
            return IntentResult(
                intent=intent,
                answer=answer,
                escalated=False,
                confidence=0.0,
                citations=[_appointment_citation(appointment_doc, f"services={services_text}, slots={slots_text}")],
                quick_replies=quick_replies,
                data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
                indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
            )

        if desired_time and desired_time < datetime.utcnow():
            return IntentResult(
                intent=intent,
                answer="That time looks in the past. Please share a future date/time (YYYY-MM-DD HH:MM).",
                escalated=False,
                confidence=0.0,
                citations=[_appointment_citation(appointment_doc, "Requested a future time")],
                quick_replies=quick_replies,
                data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
                indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
            )

        appt = models.Appointment(
            customer_id=customer_id,
            customer_name=(customer_name.strip() if customer_name else None),
            customer_phone=validate_e164_phone(customer_phone, "customer") if customer_phone else None,
            type=str(desired_type).strip() or "Consultation",
            scheduled_time=desired_time,
            status="PENDING",
            pharmacy_id=pharmacy_id,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)
        if turns is not None:
            session_memory.clear_state(turns, "appointment_booking")
            if session_id:
                session_memory.save_turns(db, pharmacy_id, session_id, turns)

        return IntentResult(
            intent=intent,
            answer=f"Booked your {appt.type} appointment for {appt.scheduled_time.isoformat()}. Reference: #{appt.id}.\n\nDo you want another medicine or any other service?",
            escalated=False,
            confidence=0.0,
            citations=[_appointment_citation(appointment_doc, f"appointment_id={appt.id}")],
            quick_replies=quick_replies,
            data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
            indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
        )

    if intent == "ORDER_CART":
        if turns is None:
            return IntentResult(
                intent=intent,
                answer="Which medicine should I add to your cart?\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_system_citation("cart_missing_context", "No session turns available.")],
                quick_replies=quick_replies,
            )
        last_item = session_memory.get_state(turns, "last_item") or {}
        medicine_id = int(last_item.get("medicine_id") or 0)
        if not _wants_add_to_cart(message) or medicine_id <= 0:
            return IntentResult(
                intent=intent,
                answer="Which medicine should I add to your cart?\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_system_citation("cart_prompt", "Missing medicine context for cart action.")],
                quick_replies=quick_replies,
            )
        action = schemas.AIAction(
            type="add_to_cart",
            label="Add to cart",
            medicine_id=medicine_id,
            payload={"medicine_id": medicine_id, "quantity": 1},
        )
        if session_id:
            session_memory.save_turns(db, pharmacy_id, session_id, turns)
        return IntentResult(
            intent=intent,
            answer="Ready to add it to your cart.",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("cart_action", f"add_to_cart:medicine:{medicine_id}")],
            actions=[action],
            quick_replies=quick_replies,
        )

    if intent == "RX_UPLOAD":
        action = schemas.AIAction(type="upload_prescription", label="Upload prescription", medicine_id=None, payload=None)
        return IntentResult(
            intent=intent,
            answer="Please upload your prescription below.\n\nDo you want another medicine or any other service?",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("rx_upload", "Requested prescription upload.")],
            actions=[action],
            quick_replies=quick_replies,
        )

    if intent == "MEDICINE_SEARCH":
        matches = _find_medicines(db, pharmacy_id, query, rx_only=False)
        if matches:
            first = matches[0]
            answer_text, cards, actions, qrs = _build_medicine_response(pharmacy_id=pharmacy_id, medicine=first, indexed_at=None)
            if turns is not None:
                session_memory.set_state(turns, "last_item", {"medicine_id": int(first.id), "name": str(first.name)})
                if session_id:
                    session_memory.save_turns(db, pharmacy_id, session_id, turns)
            return IntentResult(
                intent=intent,
                answer=answer_text,
                escalated=False,
                confidence=0.0,
                citations=[_medicine_citation(med) for med in matches],
                cards=cards,
                actions=actions,
                quick_replies=qrs,
                data_last_updated_at=max((med.updated_at for med in matches), default=None),
            )
        fuzzy = _find_fuzzy_medicines(db, pharmacy_id, query, rx_only=False)
        if fuzzy:
            suggestions = "\n".join(f"- {med.name}" for med in fuzzy if med.name)
            return IntentResult(
                intent=intent,
                answer=f"I could not find an exact match. Did you mean:\n{suggestions}\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_medicine_citation(med) for med in fuzzy],
                quick_replies=[med.name for med in fuzzy if med.name][:3] + quick_replies,
                data_last_updated_at=max((med.updated_at for med in fuzzy), default=None),
            )
        return IntentResult(
            intent=intent,
            answer="I couldn't find that medicine in this pharmacy. Please confirm the exact name and dosage.\n\nDo you want another medicine or any other service?",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("medicine_not_found", "Medicine lookup returned no matches.")],
            quick_replies=quick_replies,
        )

    if intent == "PRODUCT_SEARCH":
        matches = _find_products(db, pharmacy_id, query)
        if matches:
            lines = "\n".join(f"- {_summarize_product(product)}" for product in matches)
            return IntentResult(
                intent=intent,
                answer=f"Here are matching products:\n{lines}\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_product_citation(product) for product in matches],
                quick_replies=quick_replies,
            )
        fuzzy = _find_fuzzy_products(db, pharmacy_id, query)
        if fuzzy:
            suggestions = "\n".join(f"- {product.name}" for product in fuzzy if product.name)
            return IntentResult(
                intent=intent,
                answer=f"I could not find an exact match. Did you mean:\n{suggestions}\n\nDo you want another medicine or any other service?",
                escalated=False,
                confidence=0.0,
                citations=[_product_citation(product) for product in fuzzy],
                quick_replies=[product.name for product in fuzzy if product.name][:3] + quick_replies,
            )
        return IntentResult(
            intent=intent,
            answer="Which product are you looking for? Please share the name.\n\nDo you want another medicine or any other service?",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("product_prompt", "Requesting product name for lookup.")],
            quick_replies=quick_replies,
        )

    if intent in {"SERVICES_INFO", "GENERAL_RAG"}:
        answer, citations, confidence, escalated, freshness, _ = await hybrid_answer(
            db, pharmacy_id, query, customer_id=customer_id, memory_context=memory_context
        )
        return IntentResult(
            intent=intent,
            answer=answer,
            escalated=bool(escalated),
            confidence=float(confidence),
            citations=citations,
            quick_replies=quick_replies,
            data_last_updated_at=freshness.get("data_last_updated_at"),
            indexed_at=freshness.get("indexed_at"),
        )

    # Fallback
    return IntentResult(
        intent="UNKNOWN",
        answer="I'm not sure what you mean. Could you rephrase?\n\nDo you want another medicine or any other service?",
        escalated=False,
        confidence=0.0,
        citations=[_system_citation("fallback", "No handler matched.")],
        quick_replies=quick_replies,
    )

    # Greetings and unknown inputs are handled by the chat model (no hardcoded responses).
    if intent in {"GREETING", "UNKNOWN"}:
        answer = await _respond_smalltalk_llm(pharmacy_name, message, intent)
        return IntentResult(
            intent=intent,
            answer=answer,
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("ai_intent", f"{intent.lower()}_handled_by_ai")],
            quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
            data_last_updated_at=None,
            indexed_at=None,
        )

    if intent == "MEDICAL_ADVICE_RISK":
        return IntentResult(
            intent=intent,
            answer=(
                "This looks like a medical-risk question. I will escalate this to the pharmacist. "
                "If this is an emergency, seek urgent medical care."
            ),
            escalated=True,
            confidence=0.2,
            citations=[_system_citation("medical_risk", "Escalation required for medical risk.")],
            data_last_updated_at=None,
            indexed_at=None,
        )

    if intent == "HOURS_CONTACT":
        parts = []
        if hours:
            parts.append(f"Store hours: {hours}.")
        if contact_phone:
            parts.append(f"Phone: {contact_phone}.")
        if contact_email:
            parts.append(f"Email: {contact_email}.")
        answer = " ".join(parts) if parts else "Store hours and contact details are not available yet."
        preview = " ".join(parts) if parts else "Not available"
        return IntentResult(
            intent=intent,
            answer=answer,
            escalated=False,
            confidence=0.0,
            citations=[_playbook_citation(pharmacy, "hours", preview)],
            data_last_updated_at=pharmacy.updated_at if pharmacy else None,
            indexed_at=playbook_doc.indexed_at if playbook_doc else None,
        )

    if intent == "DELIVERY_COD":
        delivery = "Cash on delivery is available." if cod else "Cash on delivery is not available."
        return IntentResult(
            intent=intent,
            answer=delivery,
            escalated=False,
            confidence=0.0,
            citations=[_playbook_citation(pharmacy, "cod", delivery)],
            data_last_updated_at=pharmacy.updated_at if pharmacy else None,
            indexed_at=playbook_doc.indexed_at if playbook_doc else None,
        )

    if intent == "APPOINTMENT_BOOKING":
        services, slots = _appointment_summary(db, pharmacy_id)
        appointment_doc = (
            db.query(models.Document)
            .filter(
                models.Document.pharmacy_id == pharmacy_id,
                models.Document.source_type == "appointment",
                models.Document.source_key == "appointment:summary",
            )
            .first()
        )
        state = session_memory.get_state(turns or [], "appointment_booking") if turns is not None else None
        desired_time = _parse_iso_datetime(message)
        if desired_time is None and state and state.get("scheduled_time"):
            try:
                desired_time = datetime.fromisoformat(str(state.get("scheduled_time")))
            except Exception:
                desired_time = None

        desired_type = (str(state.get("type")) if state and state.get("type") else "").strip()
        if not desired_type:
            msg_lower = (message or "").lower()
            for svc in services:
                if svc and svc.lower() in msg_lower:
                    desired_type = svc
                    break
        if not desired_type and _matches(message, _APPOINTMENT):
            desired_type = "Consultation"

        customer_name = _extract_name(message) or (str(state.get("customer_name")).strip() if state and state.get("customer_name") else None)
        customer_phone = _extract_phone(message) or (str(state.get("customer_phone")).strip() if state and state.get("customer_phone") else None)

        missing_bits: list[str] = []
        if not desired_type:
            missing_bits.append("the visit type")
        if not desired_time:
            missing_bits.append("a preferred date/time (YYYY-MM-DD HH:MM)")
        if not customer_name:
            missing_bits.append("your name")
        if not customer_phone:
            missing_bits.append("your phone number in E.164 format (e.g., +15551234567)")

        services_text = ", ".join(services) if services else "Not listed yet"
        slots_text = ", ".join(slots) if slots else "Not listed yet"

        if missing_bits:
            if turns is not None:
                session_memory.set_state(
                    turns,
                    "appointment_booking",
                    {
                        "type": desired_type or None,
                        "scheduled_time": desired_time.isoformat() if desired_time else None,
                        "customer_name": customer_name,
                        "customer_phone": customer_phone,
                    },
                )
                if session_id:
                    session_memory.save_turns(db, pharmacy_id, session_id, turns)
            answer = (
                "I can book the appointment here in chat. Please share "
                + ", ".join(missing_bits)
                + ".\n"
                + f"Available services: {services_text}\n"
                + f"Next available slots: {slots_text}"
            )
            return IntentResult(
                intent=intent,
                answer=answer,
                escalated=False,
                confidence=0.0,
                citations=[_appointment_citation(appointment_doc, f"services={services_text}, slots={slots_text}")],
                data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
                indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
            )

        if desired_time and desired_time < datetime.utcnow():
            if turns is not None:
                session_memory.set_state(
                    turns,
                    "appointment_booking",
                    {
                        "type": desired_type,
                        "scheduled_time": None,
                        "customer_name": customer_name,
                        "customer_phone": customer_phone,
                    },
                )
                if session_id:
                    session_memory.save_turns(db, pharmacy_id, session_id, turns)
            return IntentResult(
                intent=intent,
                answer="That time looks in the past. Please share a future date/time (YYYY-MM-DD HH:MM).",
                escalated=False,
                confidence=0.0,
                citations=[_appointment_citation(appointment_doc, "Requested a future time")],
                data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
                indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
            )

        appt = models.Appointment(
            customer_id=customer_id,
            customer_name=(customer_name.strip() if customer_name else None),
            customer_phone=validate_e164_phone(customer_phone, "customer") if customer_phone else None,
            type=str(desired_type).strip() or "Consultation",
            scheduled_time=desired_time,
            status="PENDING",
            pharmacy_id=pharmacy_id,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)
        if turns is not None:
            session_memory.clear_state(turns, "appointment_booking")
            if session_id:
                session_memory.save_turns(db, pharmacy_id, session_id, turns)

        return IntentResult(
            intent=intent,
            answer=f"Booked your {appt.type} appointment for {appt.scheduled_time.isoformat()}. Reference: #{appt.id}.",
            escalated=False,
            confidence=0.0,
            citations=[_appointment_citation(appointment_doc, f"appointment_id={appt.id}")],
            data_last_updated_at=(appointment_doc.data_updated_at if appointment_doc else None),
            indexed_at=(appointment_doc.indexed_at if appointment_doc else None),
        )
        answer, confidence, escalated, chunks = await rag_service.answer_for_sources(
            db,
            pharmacy_id,
            customer_id,
            message,
            {"appointment"},
            memory_context=memory_context,
        )
        citations, data_last_updated_at, indexed_at = _citations_from_chunks(db, chunks)
        if answer.lower() not in {"i don't know", "i don't know."}:
            return IntentResult(
                intent=intent,
                answer=answer,
                escalated=bool(escalated),
                confidence=float(confidence),
                citations=citations,
                data_last_updated_at=data_last_updated_at,
                indexed_at=indexed_at,
            )
        return IntentResult(
            intent=intent,
            answer=(
                "You can book an appointment on the appointments page. "
                "Please share the visit type and a preferred date/time (e.g., 2025-02-12 15:30)."
            ),
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("appointment_booking", "Direct customers to the appointments page.")],
            data_last_updated_at=None,
            indexed_at=None,
        )

    if intent in {"AVAILABILITY_CHECK", "RX_MEDICINE_QUERY"}:
        rx_only = intent == "RX_MEDICINE_QUERY"
        if intent == "AVAILABILITY_CHECK":
            subjects = _token_subjects(message, _AVAILABILITY | _RX | _OTC)
            if not subjects:
                if any(t in {"painkiller", "antibiotic", "cold", "flu", "allergy"} for t in _normalize_tokens(message)):
                    return IntentResult(
                        intent=intent,
                        answer=(
                            "Which medicine exactly do you mean (brand name), and is this for an adult or child? "
                            "Also mention any allergies."
                        ),
                        escalated=False,
                        confidence=0.0,
                        citations=[_system_citation("clarify_medicine", "Vague medicine query; request clarification.")],
                        quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                        data_last_updated_at=None,
                        indexed_at=None,
                    )
                return IntentResult(
                    intent=intent,
                    answer="Which medicine are you asking about? Please share the exact name (and dosage, if possible).",
                    escalated=False,
                    confidence=0.0,
                    citations=[_system_citation("availability_prompt", "Requesting medicine name for availability check.")],
                    quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                    data_last_updated_at=None,
                    indexed_at=None,
                )
            matches = _find_medicines(db, pharmacy_id, message, rx_only=False)
            if matches:
                first = matches[0]
                answer_text, cards, actions, quick_replies = _build_medicine_response(
                    pharmacy_id=pharmacy_id,
                    medicine=first,
                    indexed_at=None,
                )
                if turns is not None:
                    session_memory.set_state(
                        turns,
                        "last_item",
                        {
                            "medicine_id": int(first.id),
                            "name": str(first.name),
                        },
                    )
                    if session_id:
                        session_memory.save_turns(db, pharmacy_id, session_id, turns)
                return IntentResult(
                    intent=intent,
                    answer=answer_text,
                    escalated=False,
                    confidence=0.0,
                    citations=[_medicine_citation(med) for med in matches],
                    cards=cards,
                    actions=actions,
                    quick_replies=quick_replies,
                    data_last_updated_at=max((med.updated_at for med in matches), default=None),
                    indexed_at=None,
                )

            fuzzy = _find_fuzzy_medicines(db, pharmacy_id, message, rx_only=False)
            if fuzzy:
                suggestions = "\n".join(f"- {med.name}" for med in fuzzy if med.name)
                return IntentResult(
                    intent=intent,
                    answer=f"I could not find an exact match. Did you mean:\n{suggestions}\n\nDo you want another medicine or any other service?",
                    escalated=False,
                    confidence=0.0,
                    citations=[_medicine_citation(med) for med in fuzzy],
                    quick_replies=[med.name for med in fuzzy if med.name][:3]
                    + ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                    data_last_updated_at=max((med.updated_at for med in fuzzy), default=None),
                    indexed_at=None,
                )

            # Fall back to hybrid only if we couldn't match by name.
            if memory_context:
                answer, citations, confidence, escalated, freshness, _ = await hybrid_answer(
                    db, pharmacy_id, message, customer_id=customer_id, memory_context=memory_context
                )
                return IntentResult(
                    intent=intent,
                    answer=answer,
                    escalated=bool(escalated),
                    confidence=float(confidence),
                    citations=citations,
                    quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                    data_last_updated_at=freshness.get("data_last_updated_at"),
                    indexed_at=freshness.get("indexed_at"),
                )
            return IntentResult(
                intent=intent,
                answer="I couldn't find that medicine in this pharmacy. Please confirm the exact name and dosage.",
                escalated=False,
                confidence=0.0,
                citations=[_system_citation("medicine_not_found", "Medicine name lookup returned no matches.")],
                quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                data_last_updated_at=None,
                indexed_at=None,
            )
        matches = _find_medicines(db, pharmacy_id, message, rx_only=rx_only)
        if matches:
            first = matches[0]
            answer_text, cards, actions, quick_replies = _build_medicine_response(
                pharmacy_id=pharmacy_id,
                medicine=first,
                indexed_at=None,
            )
            if turns is not None:
                session_memory.set_state(
                    turns,
                    "last_item",
                    {
                        "medicine_id": int(first.id),
                        "name": str(first.name),
                    },
                )
                if session_id:
                    session_memory.save_turns(db, pharmacy_id, session_id, turns)
            return IntentResult(
                intent=intent,
                answer=answer_text,
                escalated=False,
                confidence=0.0,
                citations=[_medicine_citation(med) for med in matches],
                cards=cards,
                actions=actions,
                quick_replies=quick_replies,
                data_last_updated_at=max((med.updated_at for med in matches), default=None),
                indexed_at=None,
            )
        fuzzy = _find_fuzzy_medicines(db, pharmacy_id, message, rx_only=rx_only)
        if fuzzy:
            suggestions = "\n".join(f"- {med.name}" for med in fuzzy if med.name)
            return IntentResult(
                intent=intent,
                answer=f"I could not find an exact match. Did you mean:\n{suggestions}",
                escalated=False,
                confidence=0.0,
                citations=[_medicine_citation(med) for med in fuzzy],
                quick_replies=[med.name for med in fuzzy if med.name][:3]
                + ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                data_last_updated_at=max((med.updated_at for med in fuzzy), default=None),
                indexed_at=None,
            )
        return IntentResult(
            intent=intent,
            answer="Which medicine are you asking about? Please share the exact name (and dosage, if possible).",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("availability_prompt", "Requesting medicine name for availability check.")],
            quick_replies=["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
            data_last_updated_at=None,
            indexed_at=None,
        )

    if intent == "OTC_PRODUCT_QUERY":
        matches = _find_products(db, pharmacy_id, message)
        if matches:
            lines = "\n".join(f"- {_summarize_product(product)}" for product in matches)
            return IntentResult(
                intent=intent,
                answer=f"Here are matching products:\n{lines}",
                escalated=False,
                confidence=0.0,
                citations=[_product_citation(product) for product in matches],
                data_last_updated_at=None,
                indexed_at=None,
            )
        fuzzy = _find_fuzzy_products(db, pharmacy_id, message)
        if fuzzy:
            suggestions = "\n".join(f"- {product.name}" for product in fuzzy if product.name)
            return IntentResult(
                intent=intent,
                answer=f"I could not find an exact match. Did you mean:\n{suggestions}",
                escalated=False,
                confidence=0.0,
                citations=[_product_citation(product) for product in fuzzy],
                data_last_updated_at=None,
                indexed_at=None,
            )
        answer, confidence, escalated, chunks = await rag_service.answer_for_sources(
            db,
            pharmacy_id,
            customer_id,
            message,
            {"product"},
            memory_context=memory_context,
        )
        citations, data_last_updated_at, indexed_at = _citations_from_chunks(db, chunks)
        if answer.lower() not in {"i don't know", "i don't know."}:
            return IntentResult(
                intent=intent,
                answer=answer,
                escalated=bool(escalated),
                confidence=float(confidence),
                citations=citations,
                data_last_updated_at=data_last_updated_at,
                indexed_at=indexed_at,
            )
        return IntentResult(
            intent=intent,
            answer="Which product are you looking for? Please share the name.",
            escalated=False,
            confidence=0.0,
            citations=[_system_citation("product_prompt", "Requesting product name for lookup.")],
            data_last_updated_at=None,
            indexed_at=None,
        )

    if intent in {"GENERAL_INFO_RAG", "UNKNOWN"}:
        answer, citations, confidence, escalated, freshness, _ = await hybrid_answer(
            db, pharmacy_id, message, customer_id=customer_id, memory_context=memory_context
        )
        return IntentResult(
            intent=intent,
            answer=answer,
            escalated=bool(escalated),
            confidence=float(confidence),
            citations=citations,
            data_last_updated_at=freshness.get("data_last_updated_at"),
            indexed_at=freshness.get("indexed_at"),
        )

    return IntentResult(
        intent=intent,
        answer="I don't know.",
        escalated=False,
        confidence=0.0,
        citations=[_system_citation("fallback", "No source matched the question.")],
        data_last_updated_at=None,
        indexed_at=None,
    )
