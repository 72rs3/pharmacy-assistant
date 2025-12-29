from __future__ import annotations

import difflib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app import models
from app.ai.provider_factory import get_ai_provider
from app.ai.providers.base import ChatMessage
from app.config.rag import get_rag_config
from app.ai.openrouter_client import openrouter_embed


@dataclass(frozen=True)
class RetrievedChunk:
    id: int
    document_id: int
    chunk_index: int
    content: str
    source: str
    score: float


def _chunk_text(text_value: str, *, max_chars: int = 1200) -> list[str]:
    cleaned = (text_value or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        chunks.append(cleaned[start:end].strip())
        start = end
    return [c for c in chunks if c]


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
    "context",
    "customer",
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
    "question",
    "related",
    "the",
    "their",
    "there",
    "this",
    "to",
    "u",
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

_FOLLOW_UP_INTENT = {
    "price",
    "prices",
    "cost",
    "how",
    "much",
    "stock",
    "available",
    "availability",
    "otc",
    "rx",
    "prescription",
    "effect",
    "effects",
    "side",
    "sideeffects",
}

_HOURS_INTENT = {
    "hours",
    "open",
    "opening",
    "closing",
    "schedule",
    "time",
    "working",
}

_DELIVERY_INTENT = {
    "delivery",
    "deliver",
    "shipping",
    "cod",
    "cash",
    "payment",
}

_APPOINTMENT_INTENT = {
    "appointment",
    "book",
    "booking",
    "schedule",
    "visit",
    "consultation",
    "vaccination",
}

_AVAILABILITY_INTENT = {
    "availability",
    "available",
    "stock",
    "price",
    "cost",
    "rx",
    "prescription",
    "otc",
    "medicine",
    "medication",
    "drug",
}


def _normalize_tokens(message: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", message or "") if t]


def _is_greeting(message: str) -> bool:
    msg = (message or "").strip().lower()
    if not msg:
        return False
    if msg in {"hi", "hello", "hey", "hi there", "hello there", "hey there"}:
        return True
    return msg.startswith(("hi ", "hello ", "hey "))


def _is_follow_up_without_subject(message: str) -> bool:
    tokens = _normalize_tokens(message)
    if not tokens:
        return False
    msg = " ".join(tokens)
    if "that medicine" in msg:
        return True
    if not any(t in _FOLLOW_UP_INTENT for t in tokens):
        return False
    subject_tokens = [t for t in tokens if t not in _STOPWORDS and t not in _FOLLOW_UP_INTENT and len(t) >= 4]
    return len(subject_tokens) == 0


def _matches_intent(message: str, intent: set[str]) -> bool:
    tokens = _normalize_tokens(message)
    return any(t in intent for t in tokens)


def _has_subject_token(message: str, intent: set[str]) -> bool:
    tokens = _normalize_tokens(message)
    return any(t not in _STOPWORDS and t not in intent and len(t) >= 3 for t in tokens)


def _medicine_text(medicine: models.Medicine) -> str:
    rx = "Prescription required" if medicine.prescription_required else "OTC"
    return "\n".join(
        [
            f"Medicine: {medicine.name}",
            f"Category: {medicine.category or '-'}",
            f"Price: {medicine.price}",
            f"Stock: {medicine.stock_level}",
            f"Rx: {rx}",
            f"Dosage: {medicine.dosage or '-'}",
            f"Side effects: {medicine.side_effects or '-'}",
        ]
    )


def _product_text(product: models.Product) -> str:
    return "\n".join(
        [
            f"Product: {product.name}",
            f"Category: {product.category or '-'}",
            f"Price: {product.price}",
            f"Stock: {product.stock_level}",
            f"Description: {product.description or '-'}",
        ]
    )


def _summarize_medicine(medicine: models.Medicine) -> str:
    rx = "Prescription required" if medicine.prescription_required else "OTC"
    price = f"{medicine.price:.2f}" if medicine.price is not None else "-"
    return f"{medicine.name} - {rx}, price {price}, stock {medicine.stock_level}"


def _appointment_summary_text(services: list[str], slots: list[str]) -> str:
    services_line = ", ".join(services) if services else "-"
    slots_line = ", ".join(slots) if slots else "-"
    return "\n".join(
        [
            "Appointments summary",
            f"Available services: {services_line}",
            f"Next available slots: {slots_line}",
        ]
    )


def _find_medicine_matches(db: Session, pharmacy_id: int, message: str, *, limit: int = 3) -> list[models.Medicine]:
    tokens = [t for t in _normalize_tokens(message) if t not in _STOPWORDS and t not in _AVAILABILITY_INTENT and len(t) >= 3]
    if not tokens:
        return []
    filters = [models.Medicine.name.ilike(f"%{token}%") for token in tokens]
    return (
        db.query(models.Medicine)
        .filter(models.Medicine.pharmacy_id == pharmacy_id, or_(*filters))
        .order_by(models.Medicine.name.asc())
        .limit(limit)
        .all()
    )


def _find_fuzzy_medicine_matches(db: Session, pharmacy_id: int, message: str, *, limit: int = 3) -> list[models.Medicine]:
    tokens = [t for t in _normalize_tokens(message) if t not in _STOPWORDS and t not in _AVAILABILITY_INTENT and len(t) >= 3]
    if not tokens:
        return []
    needle = " ".join(tokens).lower()
    meds = db.query(models.Medicine).filter(models.Medicine.pharmacy_id == pharmacy_id).all()
    if not meds:
        return []
    name_map = {str(med.name or "").lower(): med for med in meds if med.name}
    names = list(name_map.keys())
    close = difflib.get_close_matches(needle, names, n=limit, cutoff=0.72)
    return [name_map[name] for name in close]


def _score_medicine(medicine: models.Medicine, tokens: list[str], normalized_query: str) -> float:
    if not tokens:
        return 0.0
    name = (medicine.name or "").lower()
    category = (medicine.category or "").lower()
    if normalized_query and normalized_query == name:
        return 0.95
    if normalized_query and normalized_query in name:
        return 0.9
    if any(token in name for token in tokens):
        return 0.85
    if category and any(token in category for token in tokens):
        return 0.6
    return 0.0


def _retrieve_inventory(
    db: Session, pharmacy_id: int, query: str, *, top_k: int
) -> list[RetrievedChunk]:
    tokens = [t for t in _normalize_tokens(query) if len(t) >= 3 and t not in _STOPWORDS]
    if not tokens:
        return []
    normalized_query = " ".join(tokens)

    query_builder = db.query(models.Medicine).filter(models.Medicine.pharmacy_id == pharmacy_id)
    if tokens:
        filters = [models.Medicine.name.ilike(f"%{token}%") for token in tokens]
        filters += [models.Medicine.category.ilike(f"%{token}%") for token in tokens]
        query_builder = query_builder.filter(or_(*filters))
    medicines = query_builder.limit(max(top_k * 4, 8)).all()

    scored: list[RetrievedChunk] = []
    for med in medicines:
        score = _score_medicine(med, tokens, normalized_query)
        if score <= 0:
            continue
        scored.append(
            RetrievedChunk(
                id=-int(med.id),
                document_id=0,
                chunk_index=0,
                content=_medicine_text(med),
                source=f"Medicine: {med.name}",
                score=score,
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


async def upsert_medicine_index(db: Session, pharmacy_id: int) -> int:
    """
    Rebuild the medicine index for a pharmacy: documents + chunks + embeddings.
    Returns number of chunks created.
    """

    provider = get_ai_provider()

    now = datetime.utcnow()
    version_map = {
        doc.source_key: (doc.version or 0)
        for doc in db.query(models.Document)
        .filter(models.Document.pharmacy_id == pharmacy_id)
        .all()
        if doc.source_key
    }

    # Remove existing medicine/product/appointment documents and the per-pharmacy playbook (keep other source types for future).
    docs = (
        db.query(models.Document)
        .filter(
            models.Document.pharmacy_id == pharmacy_id,
            models.Document.source_type.in_(["medicine", "product", "appointment"]),
        )
        .all()
    )
    for doc in docs:
        db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == doc.id).delete()
        db.delete(doc)
    playbooks = (
        db.query(models.Document)
        .filter(
            models.Document.pharmacy_id == pharmacy_id,
            models.Document.source_type == "pharmacy",
            models.Document.source_key == "pharmacy:playbook",
        )
        .all()
    )
    for doc in playbooks:
        db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == doc.id).delete()
        db.delete(doc)
    db.flush()

    medicines = db.query(models.Medicine).filter(models.Medicine.pharmacy_id == pharmacy_id).all()
    products = db.query(models.Product).filter(models.Product.pharmacy_id == pharmacy_id).all()
    appointments = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.pharmacy_id == pharmacy_id,
            models.Appointment.status.in_(["PENDING", "CONFIRMED"]),
        )
        .all()
    )
    chunks_to_embed: list[tuple[models.DocumentChunk, str]] = []

    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    pharmacy_name = (pharmacy.name if pharmacy else "").strip() or f"Pharmacy #{pharmacy_id}"
    hours = (pharmacy.operating_hours if pharmacy else None) or "-"
    cod = bool(getattr(pharmacy, "support_cod", True)) if pharmacy else True

    playbook_doc = models.Document(
        title=f"Pharmacy assistant playbook: {pharmacy_name}",
        source_type="pharmacy",
        source_key="pharmacy:playbook",
        created_at=now,
        updated_at=now,
        data_updated_at=pharmacy.updated_at if pharmacy else None,
        indexed_at=now,
        version=version_map.get("pharmacy:playbook", 0) + 1,
        pharmacy_id=pharmacy_id,
    )
    db.add(playbook_doc)
    db.flush()

    contact_phone = (getattr(pharmacy, "contact_phone", None) if pharmacy else None) or "-"
    contact_email = (getattr(pharmacy, "contact_email", None) if pharmacy else None) or "-"
    contact_address = (getattr(pharmacy, "contact_address", None) if pharmacy else None) or "-"

    playbook_content = "\n".join(
        [
            f"Pharmacy: {pharmacy_name}",
            f"Operating hours: {hours}",
            f"Cash on delivery (COD): {'Yes' if cod else 'No'}",
            f"Contact phone: {contact_phone}",
            f"Contact email: {contact_email}",
            f"Contact address: {contact_address}",
            "",
            "Assistant role:",
            "- Help customers with questions about medicines available in THIS pharmacy.",
            "- Use ONLY the pharmacy data provided in retrieved sources (medicines + pharmacy details).",
            "",
            "How to respond:",
            "- If the user greets (hello/hi/hey), greet back and ask what medicine they are looking for.",
            "- If asked about store hours, share the Operating hours line.",
            "- If asked about delivery/payment, explain COD availability.",
            "- If asked to book an appointment, tell them to use the appointments page and ask for a preferred time.",
            "- If asked about availability/price/stock/Rx requirement, answer from the medicine source.",
            "- If the sources do not contain the answer, say: I don't know.",
            "- If the question is medical-risk (e.g., chest pain, overdose), escalate to the pharmacist.",
        ]
    )
    for idx, chunk in enumerate(_chunk_text(playbook_content)):
        row = models.DocumentChunk(
            document_id=playbook_doc.id,
            chunk_index=idx,
            content=chunk,
            embedding=None,
            created_at=now,
            updated_at=now,
            indexed_at=now,
            version=playbook_doc.version,
            pharmacy_id=pharmacy_id,
        )
        db.add(row)
        db.flush()
        chunks_to_embed.append((row, chunk))

    for medicine in medicines:
        title = f"Medicine: {medicine.name}"
        doc = models.Document(
            title=title,
            source_type="medicine",
            source_key=f"medicine:{medicine.id}",
            created_at=now,
            updated_at=now,
            data_updated_at=medicine.updated_at,
            indexed_at=now,
            version=version_map.get(f"medicine:{medicine.id}", 0) + 1,
            pharmacy_id=pharmacy_id,
        )
        db.add(doc)
        db.flush()

        content = _medicine_text(medicine)
        chunks = _chunk_text(content)
        for idx, chunk in enumerate(chunks):
            row = models.DocumentChunk(
                document_id=doc.id,
                chunk_index=idx,
                content=chunk,
                embedding=None,
                created_at=now,
                updated_at=now,
                indexed_at=now,
                version=doc.version,
                pharmacy_id=pharmacy_id,
            )
            db.add(row)
            db.flush()
            chunks_to_embed.append((row, chunk))

    for product in products:
        title = f"Product: {product.name}"
        doc = models.Document(
            title=title,
            source_type="product",
            source_key=f"product:{product.id}",
            created_at=now,
            updated_at=now,
            data_updated_at=product.updated_at,
            indexed_at=now,
            version=version_map.get(f"product:{product.id}", 0) + 1,
            pharmacy_id=pharmacy_id,
        )
        db.add(doc)
        db.flush()

        content = _product_text(product)
        chunks = _chunk_text(content)
        for idx, chunk in enumerate(chunks):
            row = models.DocumentChunk(
                document_id=doc.id,
                chunk_index=idx,
                content=chunk,
                embedding=None,
                created_at=now,
                updated_at=now,
                indexed_at=now,
                version=doc.version,
                pharmacy_id=pharmacy_id,
            )
            db.add(row)
            db.flush()
            chunks_to_embed.append((row, chunk))

    service_types = sorted({appt.type for appt in appointments if appt.type})
    upcoming_slots = sorted(
        {appt.scheduled_time.isoformat() for appt in appointments if appt.scheduled_time and appt.scheduled_time >= now},
    )
    appointment_summary = _appointment_summary_text(service_types, upcoming_slots[:5])
    appointment_doc = models.Document(
        title=f"Appointments summary: {pharmacy_name}",
        source_type="appointment",
        source_key="appointment:summary",
        created_at=now,
        updated_at=now,
        data_updated_at=now,
        indexed_at=now,
        version=version_map.get("appointment:summary", 0) + 1,
        pharmacy_id=pharmacy_id,
    )
    db.add(appointment_doc)
    db.flush()
    for idx, chunk in enumerate(_chunk_text(appointment_summary)):
        row = models.DocumentChunk(
            document_id=appointment_doc.id,
            chunk_index=idx,
            content=chunk,
            embedding=None,
            created_at=now,
            updated_at=now,
            indexed_at=now,
            version=appointment_doc.version,
            pharmacy_id=pharmacy_id,
        )
        db.add(row)
        db.flush()
        chunks_to_embed.append((row, chunk))

    if not chunks_to_embed:
        db.commit()
        return 0

    embeddings_enabled = bool(get_rag_config().embeddings_enabled)
    if embeddings_enabled:
        embeddings = await provider.embed([chunk for _, chunk in chunks_to_embed])
        for (row, _), emb in zip(chunks_to_embed, embeddings):
            row.embedding = emb

    db.commit()
    return len(chunks_to_embed)


def ensure_pharmacy_playbook(db: Session, pharmacy_id: int) -> None:
    """
    Ensure a minimal, tenant-scoped "playbook" document exists so new pharmacies
    are not blank (greetings/help can be answered from tenant data).

    This function does NOT require embeddings.
    """

    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    pharmacy_name = (pharmacy.name if pharmacy else "").strip() or f"Pharmacy #{pharmacy_id}"
    hours = (pharmacy.operating_hours if pharmacy else None) or "-"
    cod = bool(getattr(pharmacy, "support_cod", True)) if pharmacy else True
    contact_phone = (getattr(pharmacy, "contact_phone", None) if pharmacy else None) or "-"
    contact_email = (getattr(pharmacy, "contact_email", None) if pharmacy else None) or "-"
    contact_address = (getattr(pharmacy, "contact_address", None) if pharmacy else None) or "-"

    doc = (
        db.query(models.Document)
        .filter(
            models.Document.pharmacy_id == pharmacy_id,
            models.Document.source_type == "pharmacy",
            models.Document.source_key == "pharmacy:playbook",
        )
        .first()
    )
    now = datetime.utcnow()
    if doc is None:
        doc = models.Document(
            title=f"Pharmacy assistant playbook: {pharmacy_name}",
            source_type="pharmacy",
            source_key="pharmacy:playbook",
            created_at=now,
            updated_at=now,
            data_updated_at=pharmacy.updated_at if pharmacy else None,
            indexed_at=now,
            version=1,
            pharmacy_id=pharmacy_id,
        )
        db.add(doc)
        db.flush()
    else:
        doc.title = f"Pharmacy assistant playbook: {pharmacy_name}"
        doc.updated_at = now
        doc.data_updated_at = pharmacy.updated_at if pharmacy else None
        doc.indexed_at = now
        doc.version = (doc.version or 0) + 1
        db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == doc.id).delete()
        db.flush()

    playbook_content = "\n".join(
        [
            f"Pharmacy: {pharmacy_name}",
            f"Operating hours: {hours}",
            f"Cash on delivery (COD): {'Yes' if cod else 'No'}",
            f"Contact phone: {contact_phone}",
            f"Contact email: {contact_email}",
            f"Contact address: {contact_address}",
            "",
            "Assistant role:",
            "- Help customers with questions about medicines available in THIS pharmacy.",
            "- If this pharmacy has no medicines listed yet, explain that the inventory is not available and ask them to check back later.",
            "",
            "How to respond:",
            "- If the user greets (hello/hi/hey), greet back and ask what medicine they are looking for.",
            "- If asked about store hours, share the Operating hours line.",
            "- If asked about delivery/payment, explain COD availability.",
            "- If asked to book an appointment, tell them to use the appointments page and ask for a preferred time.",
            "- If asked about availability/price/stock/Rx requirement, answer ONLY from medicine sources.",
            "- If the sources do not contain the answer, say: I don't know.",
            "- If the question is medical-risk (e.g., chest pain, overdose), escalate to the pharmacist.",
        ]
    )
    for idx, chunk in enumerate(_chunk_text(playbook_content)):
        row = models.DocumentChunk(
            document_id=doc.id,
            chunk_index=idx,
            content=chunk,
            embedding=None,
            created_at=now,
            updated_at=now,
            indexed_at=now,
            version=doc.version,
            pharmacy_id=pharmacy_id,
        )
        db.add(row)


async def answer_for_sources(
    db: Session,
    pharmacy_id: int,
    customer_id: str,
    message: str,
    source_types: set[str],
    *,
    memory_context: list[str] | None = None,
) -> tuple[str, float, bool, list[RetrievedChunk]]:
    cfg = get_rag_config()
    top_k = int(cfg.top_k)
    retrieval_query = message
    if memory_context and _is_follow_up_without_subject(message):
        recent_questions = [q for q in memory_context if q]
        last_question = next((q for q in reversed(recent_questions) if q.lower() != (message or "").strip().lower()), "")
        if last_question:
            retrieval_query = f"{message}\nRelated context: {last_question}"
    chunks = await retrieve(db, pharmacy_id, retrieval_query, top_k=top_k)
    if chunks and source_types:
        doc_ids = {int(c.document_id) for c in chunks if c.document_id}
        docs = (
            db.query(models.Document)
            .filter(models.Document.id.in_(doc_ids))
            .all()
        )
        allowed = {int(doc.id) for doc in docs if doc.source_type in source_types}
        chunks = [chunk for chunk in chunks if int(chunk.document_id) in allowed]

    top_score = max((c.score for c in chunks), default=0.0)
    min_score = _min_score_for_message(message)
    weak_retrieval = (not chunks) or top_score < min_score
    escalated = weak_retrieval

    provider = get_ai_provider()
    sources_max_chars = int(cfg.sources_max_chars)
    sources_parts: list[str] = []
    total = 0
    for c in chunks:
        if not c.content:
            continue
        block = f"[doc_id={c.document_id} chunk_id={c.id} title={c.source}]\n{c.content}"
        if sources_max_chars > 0 and total + len(block) > sources_max_chars:
            break
        sources_parts.append(block)
        total += len(block)
    sources = "\n\n".join(sources_parts)
    system = (
        "You are a pharmacy assistant for a single pharmacy tenant.\n"
        "You MUST answer ONLY from the provided SOURCES.\n"
        "If the SOURCES do not contain enough information to answer, respond with exactly: I don't know.\n"
        "Return valid JSON with keys: answer (string), citations (array).\n"
        "Each citation must reference a SOURCE chunk_id and include: source_type, title, doc_id, chunk_id, preview, last_updated_at, score.\n"
    )
    user = f"Customer question:\n{message}\n\nSOURCES:\n{sources}\n\nReturn only JSON."

    if weak_retrieval:
        return "I don't know.", float(top_score), True, chunks

    response = await provider.chat([ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)])
    raw = (response or "").strip()
    extracted = _extract_json_object(raw)
    if not extracted:
        retry_system = system + "Output ONLY minified JSON. No markdown. No code fences.\n"
        retry_user = (
            f"Your previous response was not valid JSON.\n\n"
            f"Customer question:\n{message}\n\nSOURCES:\n{sources}\n\n"
            f"Return ONLY a JSON object with keys answer and citations."
        )
        retry = await provider.chat(
            [ChatMessage(role="system", content=retry_system), ChatMessage(role="user", content=retry_user)]
        )
        extracted = _extract_json_object((retry or "").strip())
        if not extracted:
            cleaned = (raw or "").strip()
            if cleaned and cleaned.lower() not in {"i don't know", "i don't know."}:
                return cleaned, float(top_score), False, chunks
            return "I don't know.", float(top_score), True, chunks
    try:
        data = json.loads(extracted)
        answer_text = (data.get("answer") or "").strip()
    except Exception:
        cleaned = (raw or "").strip()
        if cleaned and cleaned.lower() not in {"i don't know", "i don't know."}:
            return cleaned, float(top_score), False, chunks
        return "I don't know.", float(top_score), True, chunks

    if answer_text.lower() in {"i don't know", "i don't know."}:
        return "I don't know.", float(top_score), True, chunks

    return answer_text, float(top_score), False, chunks


async def retrieve(db: Session, pharmacy_id: int, query: str, *, top_k: int) -> list[RetrievedChunk]:
    retrieval_mode = get_rag_config().retrieval_mode
    use_vector = retrieval_mode in {"vector", "hybrid"}
    query_emb: list[float] | None = None
    if use_vector:
        embed_model = (os.getenv("OPENROUTER_EMBED_MODEL") or "").strip()
        if (os.getenv("AI_PROVIDER") or "").strip().lower() == "openrouter" and embed_model:
            query_emb = (await openrouter_embed(model=embed_model, texts=[query]))[0]
        else:
            provider = get_ai_provider()
            query_emb = (await provider.embed([query]))[0]

    # Use pgvector distance if available (postgres). Otherwise fall back to naive substring ranking.
    if db.bind.dialect.name == "postgresql":
        def keyword_rows() -> list[RetrievedChunk]:
            keywords = [t for t in _normalize_tokens(query) if len(t) >= 3]
            significant = [t for t in keywords if t not in _STOPWORDS]
            likeq = max(significant, key=len) if significant else ""
            rows = db.execute(
                text(
                    """
                    SELECT
                      c.id,
                      c.document_id,
                      c.chunk_index,
                      c.content,
                      d.title,
                      GREATEST(
                        CASE WHEN :likeq = '' THEN 0
                          ELSE CASE WHEN lower(c.content) LIKE ('%' || :likeq || '%') THEN 0.9 ELSE 0 END
                        END,
                        CASE WHEN :tsquery = '' THEN 0
                          ELSE (ts_rank_cd(to_tsvector('english', c.content), websearch_to_tsquery('english', :tsquery)) * 2.0)
                        END
                      ) AS score
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.pharmacy_id = :pid
                    ORDER BY score DESC
                    LIMIT :k
                    """
                ),
                {"pid": pharmacy_id, "k": top_k, "tsquery": query, "likeq": likeq},
            ).fetchall()
            return [
                RetrievedChunk(
                    id=int(row[0]),
                    document_id=int(row[1]),
                    chunk_index=int(row[2]),
                    content=row[3],
                    source=row[4],
                    score=float(row[5] or 0.0),
                )
                for row in rows
            ]

        query_vec = ""
        if query_emb is not None:
            query_vec = "[" + ",".join(f"{float(x):.8f}" for x in query_emb) + "]"
        if retrieval_mode == "vector":
            rows = db.execute(
                text(
                    """
                    SELECT
                      c.id,
                      c.document_id,
                      c.chunk_index,
                      c.content,
                      d.title,
                      (1 - (c.embedding <=> :q)) AS score
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.pharmacy_id = :pid AND c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> :q
                    LIMIT :k
                    """
                ),
                {"pid": pharmacy_id, "k": top_k, "q": query_vec},
            ).fetchall()
            out = [
                RetrievedChunk(
                    id=int(row[0]),
                    document_id=int(row[1]),
                    chunk_index=int(row[2]),
                    content=row[3],
                    source=row[4],
                    score=float(row[5] or 0.0),
                )
                for row in rows
            ]
            # If embeddings aren't ready for this tenant (or query returns nothing), fall back to keyword retrieval.
            return out if out else keyword_rows()
        if not use_vector:
            return keyword_rows()
        keywords = [t for t in _normalize_tokens(query) if len(t) >= 3]
        significant = [t for t in keywords if t not in _STOPWORDS]
        likeq = max(significant, key=len) if significant else ""
        rows = db.execute(
            text(
                """
                SELECT
                  c.id,
                  c.document_id,
                  c.chunk_index,
                  c.content,
                  d.title,
                  GREATEST(
                    COALESCE(1 - (c.embedding <=> :q), 0),
                    CASE WHEN :likeq = '' THEN 0
                      ELSE CASE WHEN lower(c.content) LIKE ('%' || :likeq || '%') THEN 0.9 ELSE 0 END
                    END,
                    CASE WHEN :tsquery = '' THEN 0
                      ELSE (ts_rank_cd(to_tsvector('english', c.content), websearch_to_tsquery('english', :tsquery)) * 2.0)
                    END
                  ) AS score
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.pharmacy_id = :pid AND c.embedding IS NOT NULL
                ORDER BY score DESC, COALESCE(c.embedding <=> :q, 1e9) ASC
                LIMIT :k
                """
            ),
            {"q": query_vec, "pid": pharmacy_id, "k": top_k, "tsquery": query, "likeq": likeq},
        ).fetchall()
        out = [
            RetrievedChunk(
                id=int(row[0]),
                document_id=int(row[1]),
                chunk_index=int(row[2]),
                content=row[3],
                source=row[4],
                score=float(row[5] or 0.0),
            )
            for row in rows
        ]
        return out if out else keyword_rows()

    # SQLite/test fallback: basic keyword match scoring.
    lowered = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in query.lower()).strip()
    tokens = [t for t in lowered.split() if len(t) >= 4]
    candidates = (
        db.query(models.DocumentChunk, models.Document)
        .join(models.Document, models.Document.id == models.DocumentChunk.document_id)
        .filter(models.DocumentChunk.pharmacy_id == pharmacy_id)
        .all()
    )
    scored: list[RetrievedChunk] = []
    for chunk, doc in candidates:
        content = (chunk.content or "").lower()
        score = 0.0
        if lowered and lowered in content:
            score = 0.8
        elif any(token in content for token in tokens):
            score = 0.5
        scored.append(
            RetrievedChunk(
                id=int(chunk.id),
                document_id=int(chunk.document_id),
                chunk_index=int(chunk.chunk_index),
                content=chunk.content,
                source=doc.title,
                score=score,
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def _risk_escalate(message: str) -> bool:
    msg = message.lower()
    return any(
        token in msg
        for token in [
            "chest pain",
            "shortness of breath",
            "seizure",
            "unconscious",
            "bleeding",
            "pregnant",
            "overdose",
            "anaphylaxis",
            "suicidal",
        ]
    )


def _extract_json_object(raw: str) -> str | None:
    cleaned = (raw or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith("```"):
        # Strip fenced code blocks like ```json ... ```
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return cleaned[start : end + 1]


def _token_count(message: str) -> int:
    tokens = [t for t in re.findall(r"[a-zA-Z0-9]+", message or "") if t]
    return len(tokens)


def _min_score_for_message(message: str) -> float:
    cfg = get_rag_config()
    base = float(cfg.min_score)
    short = float(cfg.min_score_short)
    return short if _token_count(message) <= 2 else base


async def answer(
    db: Session,
    pharmacy_id: int,
    customer_id: str,
    message: str,
    *,
    memory_context: list[str] | None = None,
) -> tuple[str, float, bool, list[RetrievedChunk]]:
    cfg = get_rag_config()
    top_k = int(cfg.top_k)
    inventory_top_k = int(cfg.inventory_top_k)
    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    pharmacy_name = (pharmacy.name if pharmacy else "").strip() or "our pharmacy"
    hours = (pharmacy.operating_hours if pharmacy else None) or ""
    cod = bool(getattr(pharmacy, "support_cod", True)) if pharmacy else True
    contact_phone = (getattr(pharmacy, "contact_phone", None) if pharmacy else None) or ""
    contact_email = (getattr(pharmacy, "contact_email", None) if pharmacy else None) or ""
    # Expand retrieval for follow-up queries like "what is the price?" by including the last customer question.
    retrieval_query = message
    recent_questions: list[str] = []
    is_follow_up = _is_follow_up_without_subject(message)
    if memory_context and is_follow_up:
        recent_questions = [q for q in memory_context if q]
        last_question = next((q for q in reversed(recent_questions) if q.lower() != (message or "").strip().lower()), "")
        if last_question:
            retrieval_query = f"{message}\nRelated context: {last_question}"
    elif customer_id and is_follow_up:
        recent = (
            db.query(models.AIInteraction.customer_query)
            .filter(models.AIInteraction.pharmacy_id == pharmacy_id, models.AIInteraction.customer_id == customer_id)
            .order_by(models.AIInteraction.created_at.desc())
            .limit(5)
            .all()
        )
        recent_questions = [str(row[0]).strip() for row in recent if row and str(row[0]).strip()]
        last_question = next((q for q in recent_questions if q.lower() != (message or "").strip().lower()), "")
        if last_question and is_follow_up:
            retrieval_query = f"{message}\nRelated context: {last_question}"

    if _matches_intent(message, _HOURS_INTENT):
        if hours:
            return f"Store hours: {hours}.", 0.0, False, []
        return "Store hours have not been shared yet. Please contact the pharmacy for the latest schedule.", 0.0, False, []
    if _matches_intent(message, _DELIVERY_INTENT):
        delivery = "Cash on delivery is available." if cod else "Cash on delivery is not available."
        contact = []
        if contact_phone:
            contact.append(f"Phone: {contact_phone}")
        if contact_email:
            contact.append(f"Email: {contact_email}")
        contact_text = f" Contact us if you have questions. {' '.join(contact)}" if contact else ""
        return f"{delivery}{contact_text}", 0.0, False, []
    if _matches_intent(message, _APPOINTMENT_INTENT):
        return (
            "You can book an appointment on the appointments page. "
            "Please share the visit type and a preferred date/time (e.g., 2025-02-12 15:30).",
            0.0,
            False,
            [],
        )
    if _matches_intent(message, _AVAILABILITY_INTENT) and not _has_subject_token(message, _AVAILABILITY_INTENT):
        return "Which medicine are you asking about? Please share the name (and dosage, if possible).", 0.0, False, []
    if _matches_intent(message, _AVAILABILITY_INTENT):
        matches = _find_medicine_matches(db, pharmacy_id, message, limit=3)
        if matches:
            lines = "\n".join(f"- {_summarize_medicine(med)}" for med in matches)
            return f"Here is what I found:\n{lines}", 0.0, False, []
        fuzzy = _find_fuzzy_medicine_matches(db, pharmacy_id, message, limit=3)
        if fuzzy:
            suggestions = "\n".join(f"- {med.name}" for med in fuzzy if med.name)
            return f"I could not find an exact match. Did you mean:\n{suggestions}", 0.0, False, []
        return "I could not find that medicine in this pharmacy. Please confirm the exact name and dosage.", 0.0, False, []

    inventory_chunks = _retrieve_inventory(db, pharmacy_id, retrieval_query, top_k=inventory_top_k)
    chunks = inventory_chunks + await retrieve(db, pharmacy_id, retrieval_query, top_k=top_k)
    if chunks:
        seen = set()
        deduped: list[RetrievedChunk] = []
        for chunk in chunks:
            key = (chunk.document_id, chunk.id, chunk.content)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(chunk)
        chunks = deduped

    top_score = max((c.score for c in chunks), default=0.0)
    min_score = _min_score_for_message(message)
    weak_retrieval = (not chunks) or top_score < min_score
    escalated = _risk_escalate(message) or weak_retrieval

    provider = get_ai_provider()
    sources_max_chars = int(cfg.sources_max_chars)
    sources_parts: list[str] = []
    total = 0
    for c in chunks:
        if not c.content:
            continue
        block = f"[doc_id={c.document_id} chunk_id={c.id} title={c.source}]\n{c.content}"
        if sources_max_chars > 0 and total + len(block) > sources_max_chars:
            break
        sources_parts.append(block)
        total += len(block)
    sources = "\n\n".join(sources_parts)
    system = (
        "You are a pharmacy assistant for a single pharmacy tenant.\n"
        "You MUST answer ONLY from the provided SOURCES.\n"
        "Conversation context may be provided to help resolve references, but it is NOT a source of facts.\n"
        "If the SOURCES do not contain enough information to answer, respond with exactly: I don't know.\n"
        "Return valid JSON with keys: answer (string), citations (array).\n"
        "Each citation must reference a SOURCE chunk_id and include: source_type, title, doc_id, chunk_id, preview, last_updated_at, score.\n"
    )
    convo = ""
    if recent_questions and is_follow_up:
        recent_lines = "\n".join(f"- {q}" for q in list(reversed(recent_questions[:3])) if q)
        convo = f"\n\nConversation context (NOT a source):\n{recent_lines}"
    user = f"Customer question:\n{message}{convo}\n\nSOURCES:\n{sources}\n\nReturn only JSON."

    if weak_retrieval:
        return "I don't know.", float(top_score), True, chunks

    if _risk_escalate(message):
        answer_text = (
            "This looks like a medical-risk question. I will escalate this to the pharmacist. "
            "If this is an emergency, seek urgent medical care."
        )
        return answer_text, min(float(top_score), 0.2), True, chunks

    response = await provider.chat([ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)])
    raw = (response or "").strip()
    extracted = _extract_json_object(raw)
    if not extracted:
        retry_system = system + "Output ONLY minified JSON. No markdown. No code fences.\n"
        retry_user = (
            f"Your previous response was not valid JSON.\n\n"
            f"Customer question:\n{message}\n\nSOURCES:\n{sources}\n\n"
            f"Return ONLY a JSON object with keys answer and citations."
        )
        retry = await provider.chat(
            [ChatMessage(role="system", content=retry_system), ChatMessage(role="user", content=retry_user)]
        )
        extracted = _extract_json_object((retry or "").strip())
        if not extracted:
            cleaned = (raw or "").strip()
            if cleaned and cleaned.lower() not in {"i don't know", "i don't know."}:
                return cleaned, float(top_score), False, chunks
            return "I don't know.", float(top_score), True, chunks
    try:
        data = json.loads(extracted)
        answer_text = (data.get("answer") or "").strip()
    except Exception:
        cleaned = (raw or "").strip()
        if cleaned and cleaned.lower() not in {"i don't know", "i don't know."}:
            return cleaned, float(top_score), False, chunks
        return "I don't know.", float(top_score), True, chunks

    if answer_text.lower() in {"i don't know", "i don't know."}:
        return "I don't know.", float(top_score), True, chunks

    return answer_text, float(top_score), False, chunks
