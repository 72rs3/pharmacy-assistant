from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.ai.provider_factory import get_ai_provider
from app.ai.providers.base import ChatMessage


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
    if not any(t in _FOLLOW_UP_INTENT for t in tokens):
        return False
    subject_tokens = [t for t in tokens if t not in _STOPWORDS and t not in _FOLLOW_UP_INTENT and len(t) >= 4]
    return len(subject_tokens) == 0


async def upsert_medicine_index(db: Session, pharmacy_id: int) -> int:
    """
    Rebuild the medicine index for a pharmacy: documents + chunks + embeddings.
    Returns number of chunks created.
    """

    provider = get_ai_provider()

    # Remove existing medicine documents and the per-pharmacy playbook (keep other source types for future).
    docs = (
        db.query(models.Document)
        .filter(models.Document.pharmacy_id == pharmacy_id, models.Document.source_type == "medicine")
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
    chunks_to_embed: list[tuple[models.DocumentChunk, str]] = []

    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    pharmacy_name = (pharmacy.name if pharmacy else "").strip() or f"Pharmacy #{pharmacy_id}"
    hours = (pharmacy.operating_hours if pharmacy else None) or "-"
    cod = bool(getattr(pharmacy, "support_cod", True)) if pharmacy else True

    playbook_doc = models.Document(
        title=f"Pharmacy assistant playbook: {pharmacy_name}",
        source_type="pharmacy",
        source_key="pharmacy:playbook",
        created_at=datetime.utcnow(),
        pharmacy_id=pharmacy_id,
    )
    db.add(playbook_doc)
    db.flush()

    playbook_content = "\n".join(
        [
            f"Pharmacy: {pharmacy_name}",
            f"Operating hours: {hours}",
            f"Cash on delivery (COD): {'Yes' if cod else 'No'}",
            "",
            "Assistant role:",
            "- Help customers with questions about medicines available in THIS pharmacy.",
            "- Use ONLY the pharmacy data provided in retrieved sources (medicines + pharmacy details).",
            "",
            "How to respond:",
            "- If the user greets (hello/hi/hey), greet back and ask what medicine they are looking for.",
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
            created_at=datetime.utcnow(),
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
            created_at=datetime.utcnow(),
            pharmacy_id=pharmacy_id,
        )
        db.add(doc)
        db.flush()

        rx = "Prescription required" if medicine.prescription_required else "OTC"
        content = "\n".join(
            [
                title,
                f"Category: {medicine.category or '-'}",
                f"Price: {medicine.price}",
                f"Stock: {medicine.stock_level}",
                f"Rx: {rx}",
                f"Dosage: {medicine.dosage or '-'}",
                f"Side effects: {medicine.side_effects or '-'}",
            ]
        )
        chunks = _chunk_text(content)
        for idx, chunk in enumerate(chunks):
            row = models.DocumentChunk(
                document_id=doc.id,
                chunk_index=idx,
                content=chunk,
                embedding=None,
                created_at=datetime.utcnow(),
                pharmacy_id=pharmacy_id,
            )
            db.add(row)
            db.flush()
            chunks_to_embed.append((row, chunk))

    if not chunks_to_embed:
        db.commit()
        return 0

    embeddings_enabled = (os.getenv("RAG_EMBEDDINGS_ENABLED") or "1").strip().lower() in {"1", "true", "yes", "on"}
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

    doc = (
        db.query(models.Document)
        .filter(
            models.Document.pharmacy_id == pharmacy_id,
            models.Document.source_type == "pharmacy",
            models.Document.source_key == "pharmacy:playbook",
        )
        .first()
    )
    if doc is None:
        doc = models.Document(
            title=f"Pharmacy assistant playbook: {pharmacy_name}",
            source_type="pharmacy",
            source_key="pharmacy:playbook",
            created_at=datetime.utcnow(),
            pharmacy_id=pharmacy_id,
        )
        db.add(doc)
        db.flush()
    else:
        doc.title = f"Pharmacy assistant playbook: {pharmacy_name}"
        db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == doc.id).delete()
        db.flush()

    playbook_content = "\n".join(
        [
            f"Pharmacy: {pharmacy_name}",
            f"Operating hours: {hours}",
            f"Cash on delivery (COD): {'Yes' if cod else 'No'}",
            "",
            "Assistant role:",
            "- Help customers with questions about medicines available in THIS pharmacy.",
            "- If this pharmacy has no medicines listed yet, explain that the inventory is not available and ask them to check back later.",
            "",
            "How to respond:",
            "- If the user greets (hello/hi/hey), greet back and ask what medicine they are looking for.",
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
            created_at=datetime.utcnow(),
            pharmacy_id=pharmacy_id,
        )
        db.add(row)


async def retrieve(db: Session, pharmacy_id: int, query: str, *, top_k: int) -> list[RetrievedChunk]:
    retrieval_mode = (os.getenv("RAG_RETRIEVAL_MODE") or "vector").strip().lower()
    if retrieval_mode not in {"vector", "hybrid", "keyword"}:
        retrieval_mode = "vector"
    use_vector = retrieval_mode in {"vector", "hybrid"}
    query_emb: list[float] | None = None
    if use_vector:
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
    base = float(os.getenv("RAG_MIN_SCORE", "0.35"))
    short = float(os.getenv("RAG_MIN_SCORE_SHORT", "0.15"))
    return short if _token_count(message) <= 2 else base


async def answer(db: Session, pharmacy_id: int, customer_id: str, message: str) -> tuple[str, float, bool, list[RetrievedChunk]]:
    top_k = int(os.getenv("RAG_TOP_K", "6"))
    # Expand retrieval for follow-up queries like "what is the price?" by including the last customer question.
    retrieval_query = message
    recent_questions: list[str] = []
    is_greeting = _is_greeting(message)
    is_follow_up = _is_follow_up_without_subject(message)
    if customer_id and (is_follow_up or is_greeting):
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

    if is_greeting:
        retrieval_query = f"{message}\nRelated context: greeting pharmacy assistant"

    chunks = await retrieve(db, pharmacy_id, retrieval_query, top_k=top_k)

    top_score = max((c.score for c in chunks), default=0.0)
    min_score = _min_score_for_message(message)
    weak_retrieval = (not chunks) or top_score < min_score
    escalated = _risk_escalate(message) or weak_retrieval

    provider = get_ai_provider()
    sources_max_chars = int(os.getenv("RAG_SOURCES_MAX_CHARS", "6000"))
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
        "Each citation must reference a SOURCE chunk_id and include: doc_id, chunk_id, snippet.\n"
    )
    convo = ""
    if recent_questions and (is_follow_up or is_greeting):
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
