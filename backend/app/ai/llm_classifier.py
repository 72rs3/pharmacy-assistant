from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import httpx

from app.ai.providers.base import ChatMessage


INTENTS = {
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
}

LANGUAGES = {"en", "ar", "fr"}


@dataclass(frozen=True)
class ClassifierResult:
    intent: str
    language: str
    query: str | None = None
    needs_clarification: bool = False
    clarification_questions: list[str] | None = None
    risk: str | None = None  # low|medium|high


def _extract_json_object(raw: str) -> str | None:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if "```" in cleaned:
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return cleaned[start : end + 1]


def _normalize_result(data: dict) -> ClassifierResult | None:
    intent = str(data.get("intent") or "").strip().upper()
    language = str(data.get("language") or "").strip().lower()
    query = (data.get("query") or None)
    query = str(query).strip() if query is not None else None
    needs_clarification = bool(data.get("needs_clarification") or False)
    clarification_questions = data.get("clarification_questions")
    if isinstance(clarification_questions, list):
        clarification_questions = [str(x).strip() for x in clarification_questions if str(x).strip()]
    else:
        clarification_questions = None
    risk = str(data.get("risk") or "").strip().lower() or None

    if intent not in INTENTS:
        return None
    if language not in LANGUAGES:
        language = "en"
    if risk is not None and risk not in {"low", "medium", "high"}:
        risk = None
    return ClassifierResult(
        intent=intent,
        language=language,
        query=query or None,
        needs_clarification=needs_clarification,
        clarification_questions=clarification_questions,
        risk=risk,
    )


async def classify_message(message: str) -> ClassifierResult | None:
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    base_url = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
    model = (os.getenv("OPENROUTER_CLASSIFIER_MODEL") or "").strip() or (os.getenv("OPENROUTER_CHAT_MODEL") or "").strip()
    if not api_key or not model:
        return None

    system = (
        "You are a fast intent classifier + entity extractor for a multi-tenant pharmacy assistant.\n"
        "Return STRICT JSON only. No prose. No markdown. No code fences.\n"
        "Schema:\n"
        "{\n"
        '  "intent": "GREETING|MEDICINE_SEARCH|PRODUCT_SEARCH|SERVICES_INFO|HOURS_CONTACT|APPOINTMENT_BOOKING|RX_UPLOAD|ORDER_CART|GENERAL_RAG|RISKY_MEDICAL|UNKNOWN",\n'
        '  "language": "en|ar|fr",\n'
        '  "query": "string optional",\n'
        '  "needs_clarification": true|false,\n'
        '  "clarification_questions": ["..."] optional,\n'
        '  "risk": "low|medium|high"\n'
        "}\n"
        "\n"
        "Routing rules:\n"
        "- If the user is looking for/needs/wants/finding a medicine OR provides a medicine-like token (even misspelled), intent=MEDICINE_SEARCH and query=<best guess name>.\n"
        "- If the user asks for store products (toothpaste, shampoo, vitamins, skincare), intent=PRODUCT_SEARCH.\n"
        "- If the user asks to add to cart / reserve / order, intent=ORDER_CART.\n"
        "- If the user asks to upload a prescription, intent=RX_UPLOAD.\n"
        "- If the user asks about hours/contact, intent=HOURS_CONTACT.\n"
        "- If booking/appointment, intent=APPOINTMENT_BOOKING.\n"
        "- If medical advice risk/emergency/dose/symptoms/pregnancy/child, intent=RISKY_MEDICAL and risk=high.\n"
        "- If asking only about availability/ordering (even antibiotics/controlled meds), intent=MEDICINE_SEARCH.\n"
        "- Else if general policy/services, intent=SERVICES_INFO or GENERAL_RAG.\n"
        "- Greetings/thanks -> GREETING.\n"
        "- If unclear -> UNKNOWN.\n"
    )
    user = f"Message: {message}"

    payload_messages = [
        {"role": ChatMessage(role="system", content=system).role, "content": system},
        {"role": ChatMessage(role="user", content=user).role, "content": user},
    ]

    timeout_s = float(os.getenv("OPENROUTER_TIMEOUT_S", "30"))
    headers = {"Authorization": f"Bearer {api_key}"}
    http_referer = (os.getenv("OPENROUTER_HTTP_REFERER") or "").strip()
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    x_title = (os.getenv("OPENROUTER_X_TITLE") or "").strip()
    if x_title:
        headers["X-Title"] = x_title

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout_s, headers=headers) as client:
            res = await client.post(
                "/chat/completions",
                json={
                    "model": model,
                    "messages": payload_messages,
                    "temperature": 0.0,
                    "max_tokens": int(os.getenv("OPENROUTER_CLASSIFIER_MAX_TOKENS", "160")),
                },
            )
        if res.status_code >= 400:
            return None
        content = (res.json().get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
        extracted = _extract_json_object(str(content))
        if not extracted:
            return None
        data = json.loads(extracted)
        if not isinstance(data, dict):
            return None
        return _normalize_result(data)
    except Exception:
        return None


def fallback_classify(message: str) -> ClassifierResult:
    msg = (message or "").strip()
    low = msg.lower()
    tokens = re.findall(r"[a-zA-Z0-9]+", low)
    language = "en"
    if re.search(r"[\u0600-\u06FF]", msg):
        language = "ar"
    elif re.search(r"[àâçéèêëîïôûùüÿœæ]", low):
        language = "fr"
    if not tokens:
        return ClassifierResult(intent="UNKNOWN", language=language)
    if len(tokens) == 1:
        tok = tokens[0]
        if len(tok) >= 6 and len(set(tok)) <= 3:
            return ClassifierResult(intent="UNKNOWN", language=language)
    if low.startswith(("hi", "hello", "hey")) or low in {"hi", "hello", "hey", "thanks", "thank", "thx"}:
        return ClassifierResult(intent="GREETING", language=language)
    if any(w in tokens for w in {"hours", "open", "opening", "closing", "contact", "phone", "email", "address"}):
        return ClassifierResult(intent="HOURS_CONTACT", language=language)
    if any(w in tokens for w in {"appointment", "book", "booking", "schedule", "visit"}):
        return ClassifierResult(intent="APPOINTMENT_BOOKING", language=language)
    if any(w in low for w in ["chest pain", "shortness of breath", "overdose", "seizure"]) or any(
        w in tokens for w in {"diagnose", "dosage", "dose", "pregnant", "pregnancy", "breastfeed", "child", "infant"}
    ):
        return ClassifierResult(intent="RISKY_MEDICAL", language=language, risk="high")
    if "give me" in low:
        return ClassifierResult(intent="MEDICINE_SEARCH", language=language, query=msg)
    if any(w in tokens for w in {"cart", "add", "order", "reserve", "checkout"}):
        return ClassifierResult(intent="ORDER_CART", language=language)
    if any(w in tokens for w in {"upload", "prescription"}):
        return ClassifierResult(intent="RX_UPLOAD", language=language)
    if any(w in tokens for w in {"toothpaste", "toothbrush", "shampoo", "soap", "vitamin", "supplement", "skincare", "lotion"}):
        return ClassifierResult(intent="PRODUCT_SEARCH", language=language, query=msg)
    if any(w in tokens for w in {"services", "service", "policy", "policies", "faq"}):
        return ClassifierResult(intent="SERVICES_INFO", language=language, query=msg)
    if any(w in tokens for w in {"delivery", "deliver", "shipping", "cod", "payment", "pay"}):
        return ClassifierResult(intent="SERVICES_INFO", language=language, query=msg)

    if any(w in tokens for w in {"have", "available", "availability", "stock", "price", "cost", "medicine", "medication", "drug", "rx"}):
        return ClassifierResult(intent="MEDICINE_SEARCH", language=language, query=msg)

    m = re.search(r"\b(looking for|look for|need|want|find|search for|buy)\b\s+(.*)$", low)
    if m:
        q = m.group(2).strip()
        q = re.sub(r"^(a|an|the)\s+", "", q)
        q = q.strip()
        if q:
            return ClassifierResult(intent="MEDICINE_SEARCH", language=language, query=q)
    # Default: treat short messages as medicine search candidates.
    if len(tokens) <= 4:
        return ClassifierResult(intent="MEDICINE_SEARCH", language=language, query=msg)
    return ClassifierResult(intent="GENERAL_RAG", language=language, query=msg)
