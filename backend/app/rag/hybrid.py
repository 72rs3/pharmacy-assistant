from __future__ import annotations

import difflib
import os
import re
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app import models, schemas
from app.ai import rag_service


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

_HOURS_CONTACT = {"hours", "open", "opening", "closing", "schedule", "time", "contact", "phone", "email", "address"}
_DELIVERY_COD = {"delivery", "deliver", "shipping", "cod", "cash", "payment", "pay"}
_AVAILABILITY = {"availability", "available", "stock", "price", "cost", "medicine", "medication", "drug", "have"}
_PLAYBOOK = {"policy", "return", "refund", "services", "about", "info", "information", "details"}


def _normalize_tokens(message: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", message or "") if t]


def _matches(message: str, keywords: set[str]) -> bool:
    tokens = _normalize_tokens(message)
    return any(t in keywords for t in tokens)


def _subject_tokens(message: str) -> list[str]:
    tokens = _normalize_tokens(message)
    return [t for t in tokens if t not in _STOPWORDS and t not in _AVAILABILITY and len(t) >= 3]


def _summarize_medicine(med: models.Medicine) -> str:
    rx = "Prescription required" if med.prescription_required else "OTC"
    price = f"{med.price:.2f}" if med.price is not None else "-"
    return f"{med.name} - {rx}, price {price}, stock {med.stock_level}"


def _medicine_citation(med: models.Medicine) -> schemas.AICitation:
    preview_parts = [
        f"dosage={med.dosage or '-'}",
        f"stock={med.stock_level}",
    ]
    return schemas.AICitation(
        source_type="medicine",
        title=med.name,
        doc_id=int(med.id),
        chunk_id=0,
        preview=", ".join(preview_parts),
        last_updated_at=med.updated_at,
        score=None,
    )


def _exact_medicine_match(db: Session, pharmacy_id: int, tokens: list[str]) -> models.Medicine | None:
    if not tokens:
        return None
    normalized = " ".join(tokens).strip().lower()
    candidates = [token.lower() for token in tokens]
    if normalized:
        candidates.append(normalized)
    return (
        db.query(models.Medicine)
        .filter(
            models.Medicine.pharmacy_id == pharmacy_id,
            or_(
                *[func.lower(models.Medicine.name) == token for token in candidates],
            ),
        )
        .first()
    )


def _ilike_medicine_matches(db: Session, pharmacy_id: int, tokens: list[str], limit: int) -> list[models.Medicine]:
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


def _trigram_medicine_matches(db: Session, pharmacy_id: int, tokens: list[str], limit: int) -> list[models.Medicine]:
    if db.bind.dialect.name != "postgresql":
        return []
    if not tokens:
        return []
    normalized = " ".join(tokens)
    try:
        has_trgm = db.execute(
            text("SELECT 1 FROM pg_extension WHERE extname='pg_trgm'")
        ).fetchone()
        if not has_trgm:
            return []
        rows = db.execute(
            text(
                """
                SELECT id
                FROM medicines
                WHERE pharmacy_id = :pid
                ORDER BY similarity(name, :q) DESC
                LIMIT :limit
                """
            ),
            {"pid": pharmacy_id, "q": normalized, "limit": limit},
        ).fetchall()
        ids = [int(row[0]) for row in rows]
        if not ids:
            return []
        meds = db.query(models.Medicine).filter(models.Medicine.id.in_(ids)).all()
        return meds
    except Exception:
        return []


def _python_fuzzy_matches(db: Session, pharmacy_id: int, tokens: list[str], limit: int) -> list[models.Medicine]:
    if not tokens:
        return []
    needle = " ".join(tokens).lower()
    meds = db.query(models.Medicine).filter(models.Medicine.pharmacy_id == pharmacy_id).all()
    name_map = {str(med.name or "").lower(): med for med in meds if med.name}
    names = list(name_map.keys())
    try:
        from rapidfuzz import process

        results = process.extract(needle, names, limit=limit, score_cutoff=72)
        return [name_map[name] for name, _, _ in results]
    except Exception:
        close = difflib.get_close_matches(needle, names, n=limit, cutoff=0.72)
        return [name_map[name] for name in close]


def _availability_lookup(db: Session, pharmacy_id: int, message: str) -> tuple[str | None, list[schemas.AICitation], float, dict[str, Any]]:
    tokens = _subject_tokens(message)
    exact = _exact_medicine_match(db, pharmacy_id, tokens)
    if exact:
        answer = _summarize_medicine(exact)
        return answer, [_medicine_citation(exact)], 0.35, {"stage": "sql_exact", "matches": [exact.name]}

    ilike_matches = _ilike_medicine_matches(db, pharmacy_id, tokens, limit=3)
    if ilike_matches:
        suggestions = "\n".join(f"- {med.name}" for med in ilike_matches if med.name)
        return (
            f"I could not find an exact match. Did you mean:\n{suggestions}",
            [_medicine_citation(med) for med in ilike_matches],
            0.3,
            {"stage": "sql_fuzzy", "matches": [m.name for m in ilike_matches]},
        )

    trgm_matches = _trigram_medicine_matches(db, pharmacy_id, tokens, limit=3)
    if trgm_matches:
        suggestions = "\n".join(f"- {med.name}" for med in trgm_matches if med.name)
        return (
            f"I could not find an exact match. Did you mean:\n{suggestions}",
            [_medicine_citation(med) for med in trgm_matches],
            0.2,
            {"stage": "sql_trgm", "matches": [m.name for m in trgm_matches]},
        )

    fuzzy = _python_fuzzy_matches(db, pharmacy_id, tokens, limit=3)
    if fuzzy:
        suggestions = "\n".join(f"- {med.name}" for med in fuzzy if med.name)
        return (
            f"I could not find an exact match. Did you mean:\n{suggestions}",
            [_medicine_citation(med) for med in fuzzy],
            0.2,
            {"stage": "sql_fuzzy_python", "matches": [m.name for m in fuzzy]},
        )

    return None, [], 0.0, {"stage": "sql_none"}


def _playbook_lookup(pharmacy: models.Pharmacy, message: str) -> tuple[str | None, str | None, dict[str, Any]]:
    if not _matches(message, _PLAYBOOK):
        return None, None, {"stage": "playbook_skipped"}
    if pharmacy.branding_details:
        return pharmacy.branding_details.strip(), "policies", {"stage": "playbook_branding"}
    return None, None, {"stage": "playbook_empty"}


def _playbook_citation(pharmacy: models.Pharmacy, section_key: str, preview: str) -> schemas.AICitation:
    return schemas.AICitation(
        source_type="playbook",
        title=section_key,
        doc_id=int(pharmacy.id),
        chunk_id=0,
        preview=preview,
        last_updated_at=pharmacy.updated_at,
        score=None,
    )


def _chunk_citations(
    db: Session, chunks: list[rag_service.RetrievedChunk]
) -> tuple[list[schemas.AICitation], datetime | None, datetime | None]:
    if not chunks:
        return [], None, None
    inventory_ids = {abs(int(c.id)) for c in chunks if c.document_id == 0 and int(c.id) < 0}
    doc_ids = {int(c.document_id) for c in chunks if c.document_id}
    chunk_ids = {int(c.id) for c in chunks if c.document_id and int(c.id) > 0}
    docs = (
        db.query(models.Document)
        .filter(models.Document.id.in_(doc_ids))
        .all()
    )
    doc_map = {int(doc.id): doc for doc in docs}
    chunk_rows = (
        db.query(models.DocumentChunk)
        .filter(models.DocumentChunk.id.in_(chunk_ids))
        .all()
    )
    chunk_map = {int(row.id): row for row in chunk_rows}
    medicines = []
    if inventory_ids:
        medicines = db.query(models.Medicine).filter(models.Medicine.id.in_(inventory_ids)).all()
    medicine_map = {int(med.id): med for med in medicines}
    citations: list[schemas.AICitation] = []
    data_last_updated_at: datetime | None = None
    indexed_at: datetime | None = None
    for chunk in chunks:
        if chunk.document_id == 0 and int(chunk.id) < 0:
            med = medicine_map.get(abs(int(chunk.id)))
            if med:
                citations.append(_medicine_citation(med))
                if med.updated_at and (data_last_updated_at is None or med.updated_at > data_last_updated_at):
                    data_last_updated_at = med.updated_at
            continue
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


async def hybrid_answer(
    db: Session,
    pharmacy_id: int,
    query: str,
    *,
    customer_id: str | None = None,
    memory_context: list[str] | None = None,
) -> tuple[str, list[schemas.AICitation], float, bool, dict[str, datetime | None], dict[str, Any]]:
    message = (query or "").strip()
    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not pharmacy:
        return "Pharmacy not found.", [], 0.0, False, {"data_last_updated_at": None, "indexed_at": None}, {"stage": "pharmacy_missing"}

    playbook_doc = (
        db.query(models.Document)
        .filter(
            models.Document.pharmacy_id == pharmacy_id,
            models.Document.source_type == "pharmacy",
            models.Document.source_key == "pharmacy:playbook",
        )
        .first()
    )

    if _matches(message, _HOURS_CONTACT):
        parts = []
        preview_parts = []
        if pharmacy.operating_hours:
            parts.append(f"Store hours: {pharmacy.operating_hours}.")
            preview_parts.append(pharmacy.operating_hours)
        if pharmacy.contact_phone:
            parts.append(f"Phone: {pharmacy.contact_phone}.")
            preview_parts.append(pharmacy.contact_phone)
        if pharmacy.contact_email:
            parts.append(f"Email: {pharmacy.contact_email}.")
            preview_parts.append(pharmacy.contact_email)
        if pharmacy.contact_address:
            parts.append(f"Address: {pharmacy.contact_address}.")
            preview_parts.append(pharmacy.contact_address)
        if parts:
            citation = _playbook_citation(pharmacy, "hours", ", ".join(preview_parts))
            freshness = {
                "data_last_updated_at": pharmacy.updated_at,
                "indexed_at": playbook_doc.indexed_at if playbook_doc else None,
            }
            return " ".join(parts), [citation], 0.0, False, freshness, {"stage": "shortcut_hours_contact"}

    if _matches(message, _DELIVERY_COD):
        delivery = "Cash on delivery is available." if pharmacy.support_cod else "Cash on delivery is not available."
        citation = _playbook_citation(pharmacy, "cod", delivery)
        freshness = {
            "data_last_updated_at": pharmacy.updated_at,
            "indexed_at": playbook_doc.indexed_at if playbook_doc else None,
        }
        return delivery, [citation], 0.0, False, freshness, {"stage": "shortcut_cod"}

    if _matches(message, _AVAILABILITY):
        answer, citations, confidence, debug = _availability_lookup(db, pharmacy_id, message)
        if answer:
            latest_updated = max(
                (c.last_updated_at for c in citations if c.last_updated_at), default=None
            )
            return (
                answer,
                citations,
                confidence,
                False,
                {"data_last_updated_at": latest_updated, "indexed_at": None},
                debug,
            )

    playbook_answer, section_key, playbook_debug = _playbook_lookup(pharmacy, message)
    if playbook_answer:
        citation = _playbook_citation(pharmacy, section_key or "policies", playbook_answer[:160])
        freshness = {
            "data_last_updated_at": pharmacy.updated_at,
            "indexed_at": playbook_doc.indexed_at if playbook_doc else None,
        }
        return playbook_answer, [citation], 0.2, False, freshness, playbook_debug

    answer, confidence, escalated, chunks = await rag_service.answer(
        db, pharmacy_id, customer_id or "", message, memory_context=memory_context
    )
    citations, data_last_updated_at, indexed_at = _chunk_citations(db, chunks)
    if answer.lower() in {"i don't know", "i don't know."}:
        return (
            "I don't know.",
            citations,
            float(confidence),
            True,
            {"data_last_updated_at": data_last_updated_at, "indexed_at": indexed_at},
            {"stage": "fallback"},
        )
    return (
        answer,
        citations,
        float(confidence),
        bool(escalated),
        {"data_last_updated_at": data_last_updated_at, "indexed_at": indexed_at},
        {"stage": "rag"},
    )
