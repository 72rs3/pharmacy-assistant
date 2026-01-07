from __future__ import annotations

import json
import os
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.ai.openrouter_client import openrouter_chat
from app.ai.providers.base import ChatMessage


Intent = Literal[
    "GREETING",
    "MEDICINE_SEARCH",
    "PRODUCT_SEARCH",
    "SERVICES",
    "HOURS_CONTACT",
    "APPOINTMENT",
    "CART",
    "GENERAL_RAG",
    "RISKY_MEDICAL",
    "UNKNOWN",
]


class RouterIntent(BaseModel):
    language: Literal["en", "ar", "fr"] = "en"
    intent: Intent
    query: str | None = None
    greeting: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    risk: Literal["low", "medium", "high"] = "low"
    clarifying_questions: list[str] = Field(default_factory=list)


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


def _detect_language(message: str) -> str:
    msg = message or ""
    if re.search(r"[\u0600-\u06FF]", msg):
        return "ar"
    if re.search(r"[àâçéèêëîïôûùüÿœæ]", msg.lower()):
        return "fr"
    return "en"


def _looks_like_availability_request(message: str) -> bool:
    low = (message or "").strip().lower()
    if not low:
        return False
    intent_phrases = [
        "do you have",
        "do u have",
        "available",
        "availability",
        "in stock",
        "stock",
        "price",
        "cost",
        "buy",
        "order",
        "add to cart",
        "looking for",
        "search",
        "find",
        "need",
        "want",
        "give me",
    ]
    if not any(phrase in low for phrase in intent_phrases):
        return False
    risk_phrases = [
        "dose",
        "dosage",
        "how to take",
        "how should i",
        "can i take",
        "should i take",
        "side effect",
        "interaction",
        "contraindication",
        "pregnant",
        "pregnancy",
        "breastfeed",
        "child",
        "infant",
        "symptom",
        "pain",
        "fever",
        "cough",
        "rash",
        "emergency",
    ]
    return not any(phrase in low for phrase in risk_phrases)


def _heuristic_fallback(message: str) -> RouterIntent:
    low = (message or "").strip().lower()
    tokens = re.findall(r"[a-zA-Z0-9]+", low)
    lang = _detect_language(message)
    if not tokens:
        return RouterIntent(language=lang, intent="UNKNOWN", confidence=0.0, risk="low")
    greeting = False
    if tokens and tokens[0] in {"hi", "hello", "hey"}:
        greeting = True
        tokens = tokens[1:]
        low = " ".join(tokens)
    if not tokens:
        if greeting:
            return RouterIntent(language=lang, intent="GREETING", confidence=0.8, risk="low", greeting=True)
        return RouterIntent(language=lang, intent="UNKNOWN", confidence=0.0, risk="low")
    if low in {"thanks", "thank", "thx"}:
        return RouterIntent(language=lang, intent="GREETING", confidence=0.8, risk="low", greeting=greeting)
    if any(w in low for w in ["pregnant", "pregnancy", "breastfeed"]) or any(
        w in low for w in ["chest pain", "shortness of breath", "seizure", "overdose"]
    ):
        return RouterIntent(language=lang, intent="RISKY_MEDICAL", confidence=0.9, risk="high", greeting=greeting)
    if _looks_like_availability_request(message):
        return RouterIntent(language=lang, intent="MEDICINE_SEARCH", confidence=0.7, risk="low", query=message.strip(), greeting=greeting)
    if any(w in tokens for w in {"hours", "open", "opening", "closing", "contact", "phone", "email", "address"}):
        return RouterIntent(language=lang, intent="HOURS_CONTACT", confidence=0.8, risk="low", greeting=greeting)
    if any(w in tokens for w in {"delivery", "deliver", "shipping", "cod", "cash", "payment", "refund", "return"}):
        return RouterIntent(language=lang, intent="SERVICES", confidence=0.7, risk="low", greeting=greeting)
    if any(w in tokens for w in {"appointment", "book", "booking", "schedule", "visit"}):
        return RouterIntent(language=lang, intent="APPOINTMENT", confidence=0.8, risk="low", greeting=greeting)
    if any(w in tokens for w in {"cart", "checkout", "reserve"}) or ("add" in tokens and "cart" in tokens):
        return RouterIntent(language=lang, intent="CART", confidence=0.7, risk="low", greeting=greeting)
    if any(w in tokens for w in {"toothpaste", "toothbrush", "shampoo", "soap", "vitamin", "supplement", "skincare", "lotion"}):
        return RouterIntent(language=lang, intent="PRODUCT_SEARCH", confidence=0.7, risk="low", query=message.strip(), greeting=greeting)
    if any(w in tokens for w in {"have", "available", "availability", "stock", "price", "cost", "medicine", "medication", "drug", "rx"}):
        return RouterIntent(language=lang, intent="MEDICINE_SEARCH", confidence=0.7, risk="low", query=message.strip(), greeting=greeting)
    if len(tokens) <= 2:
        return RouterIntent(language=lang, intent="MEDICINE_SEARCH", confidence=0.55, risk="low", query=message.strip(), greeting=greeting)
    return RouterIntent(language=lang, intent="GENERAL_RAG", confidence=0.5, risk="low", query=message.strip(), greeting=greeting)


async def route_intent(message: str, *, pharmacy_id: int | None = None, session_id: str | None = None) -> RouterIntent:
    model = (os.getenv("OPENROUTER_ROUTER_MODEL") or "").strip()
    if not model:
        return _heuristic_fallback(message)

    system = (
        "You are a fast intent classifier + entity extractor for a multi-tenant pharmacy assistant.\n"
        "Return STRICT JSON only. No prose. No markdown. No code fences.\n"
        "Schema:\n"
        "{\n"
        '  "language": "en|ar|fr",\n'
        '  "intent": "GREETING|MEDICINE_SEARCH|PRODUCT_SEARCH|SERVICES|HOURS_CONTACT|APPOINTMENT|CART|GENERAL_RAG|RISKY_MEDICAL|UNKNOWN",\n'
        '  "query": string|null,\n'
        '  "greeting": boolean,\n'
        '  "confidence": number,\n'
        '  "risk": "low|medium|high",\n'
        '  "clarifying_questions": [string]\n'
        "}\n"
        "\n"
        "Rules:\n"
        "- Prefer MEDICINE_SEARCH when the user mentions a drug/medicine name or says looking for/need/price/stock.\n"
        "- Prefer PRODUCT_SEARCH for toothbrush/toothpaste/sunblock/vitamins/etc.\n"
        "- If pregnancy/child/severe symptoms/interactions/dosing/side effects -> intent=RISKY_MEDICAL, risk=high.\n"
        "- If asking only about availability/ordering (even antibiotics/controlled meds), use MEDICINE_SEARCH.\n"
        "- If the message includes a greeting AND another request, set greeting=true but keep intent for the request.\n"
        "- Always set confidence 0..1.\n"
    )
    user = f"Message: {message}"
    try:
        raw = await openrouter_chat(
            model=model,
            messages=[ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)],
            temperature=0.0,
            max_tokens=int(os.getenv("OPENROUTER_ROUTER_MAX_TOKENS", os.getenv("OPENROUTER_CLASSIFIER_MAX_TOKENS", "150"))),
        )
        extracted = _extract_json_object(raw)
        if not extracted:
            return _heuristic_fallback(message)
        data = json.loads(extracted)
        result = RouterIntent.model_validate(data)
        if result.intent == "RISKY_MEDICAL" and _looks_like_availability_request(message):
            return RouterIntent(
                language=result.language,
                intent="MEDICINE_SEARCH",
                query=message.strip() or None,
                greeting=result.greeting,
                confidence=max(0.55, result.confidence),
                risk="low",
                clarifying_questions=[],
            )
        return result
    except (ValidationError, json.JSONDecodeError):
        return _heuristic_fallback(message)
    except Exception:
        return _heuristic_fallback(message)
