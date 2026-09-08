from __future__ import annotations

import json
import os
import re
import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.openrouter_client import openrouter_chat
from app.ai.providers.base import ChatMessage

_logger = logging.getLogger(__name__)


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
    "HEALTH_GUIDANCE",
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
    if any(w in tokens for w in {"appointment", "booking", "consultation", "vaccination"}) or "book a" in low:
        return RouterIntent(language=lang, intent="APPOINTMENT", confidence=0.8, query=message, greeting=greeting)
    if any(w in low for w in ["insomnia", "can't sleep", "cannot sleep", "trouble sleeping", "head hurts", "headache", "stomach", "hurting", "diarrhea", "dizzy"]):
        return RouterIntent(language=lang, intent="HEALTH_GUIDANCE", confidence=0.6, query=message, greeting=greeting)
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


async def route_intent(message: str, *, pharmacy_id: int | None = None, session_id: str | None = None,
                       history: list[ChatMessage] | None = None) -> RouterIntent:
    models = list(dict.fromkeys(value.strip() for value in [
        os.getenv("OPENROUTER_ROUTER_MODEL", ""), os.getenv("OPENROUTER_MAIN_MODEL", ""),
        os.getenv("OPENROUTER_CHAT_MODEL", "")
    ] if value.strip()))
    if not models:
        return _heuristic_fallback(message)

    system = (
        "You are a fast intent classifier + entity extractor for a multi-tenant pharmacy assistant.\n"
        "Return STRICT JSON only. No prose. No markdown. No code fences.\n"
        "Schema:\n"
        "{\n"
        '  "language": "en|ar|fr",\n'
        '  "intent": "GREETING|MEDICINE_SEARCH|PRODUCT_SEARCH|SERVICES|HOURS_CONTACT|APPOINTMENT|CART|GENERAL_RAG|HEALTH_GUIDANCE|RISKY_MEDICAL|UNKNOWN",\n'
        '  "query": string|null,\n'
        '  "greeting": boolean,\n'
        '  "confidence": number,\n'
        '  "risk": "low|medium|high",\n'
        '  "clarifying_questions": [string]\n'
        "}\n"
        "\n"
        "Rules:\n"
        "- Interpret the latest request using the preceding dialogue. A topic change overrides the previous workflow.\n"
        "- Use HEALTH_GUIDANCE for ordinary symptoms, insomnia, trouble sleeping, headaches, stomach pain, and general health questions, including follow-up answers.\n"
        "- 'I have insomnia' is a symptom, not a medicine search. 'I need an appointment' is APPOINTMENT.\n"
        "- Use MEDICINE_SEARCH for a named medicine's availability/price, not just because the user says have/need/want.\n"
        "- Resolve 'price?' or 'is it available?' to the medicine from the conversation; query must contain its name.\n"
        "- For APPOINTMENT use the booking workflow even after discussing prescription medicines; booking does not require a prescription.\n"
        "- Set query to the relevant search terms or full request for non-search intents.\n"
        "- Prefer PRODUCT_SEARCH for toothbrush/toothpaste/sunblock/vitamins/etc.\n"
        "- If pregnancy/child/severe symptoms/interactions/dosing/side effects -> intent=RISKY_MEDICAL, risk=high.\n"
        "- If asking only about availability/ordering (even antibiotics/controlled meds), use MEDICINE_SEARCH.\n"
        "- If the message includes a greeting AND another request, set greeting=true but keep intent for the request.\n"
        "- Always set confidence 0..1.\n"
    )
    user = f"Message: {message}"
    for model in models:
        try:
            raw = await openrouter_chat(
                model=model,
                messages=[ChatMessage(role="system", content=system), *(history or []), ChatMessage(role="user", content=user)],
                temperature=0.0,
                max_tokens=max(300, int(os.getenv("OPENROUTER_ROUTER_MAX_TOKENS", "300"))),
                json_mode=True,
            )
            extracted = _extract_json_object(raw)
            if not extracted:
                raise ValueError("router did not return JSON")
            return RouterIntent.model_validate(json.loads(extracted))
        except Exception as exc:
            _logger.warning("AI router failed model=%s error_type=%s status=%s",
                            model, type(exc).__name__, getattr(exc, "status_code", None))
    return _heuristic_fallback(message)
