from __future__ import annotations

import json
import os
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.ai.openrouter_client import OpenRouterError, openrouter_chat
from app.ai.providers.base import ChatMessage
from app.ai.tool_executor import ToolContext


class GeneratedCitation(BaseModel):
    source: str | None = None
    doc_id: int | None = None
    chunk_id: int | None = None


class GeneratedAction(BaseModel):
    type: Literal["add_to_cart", "upload_prescription", "book_appointment", "search_medicine"]
    label: str
    payload: dict[str, Any] = Field(default_factory=dict)


class GeneratedResponse(BaseModel):
    answer: str
    language: Literal["en", "ar", "fr"] = "en"
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    citations: list[GeneratedCitation] = Field(default_factory=list)
    actions: list[GeneratedAction] = Field(default_factory=list)
    quick_replies: list[str] = Field(default_factory=list)
    escalated: bool = False


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


async def _call_model(model: str, *, tool_context: dict, user_message: str, max_tokens: int) -> GeneratedResponse:
    system = (
        "You are a careful pharmacist assistant (not a doctor).\n"
        "You MUST answer using ONLY the TOOL_CONTEXT.\n"
        "Return STRICT JSON only. No prose. No markdown.\n"
        "If TOOL_CONTEXT has no relevant info, answer: \"I don’t know based on available pharmacy data.\".\n"
        "Output schema:\n"
        "{\n"
        '  "answer": string,\n'
        '  "language": "en|ar|fr",\n'
        '  "confidence": number,\n'
        '  "citations": [{"source": string, "doc_id": number, "chunk_id": number}],\n'
        '  "actions": [{"type":"add_to_cart|upload_prescription|book_appointment|search_medicine","label":string,"payload":{}}],\n'
        '  "quick_replies": [string],\n'
        '  "escalated": boolean\n'
        "}\n"
    )
    user = f"USER_MESSAGE:\n{user_message}\n\nTOOL_CONTEXT:\n{json.dumps(tool_context, ensure_ascii=False)}"
    raw = await openrouter_chat(
        model=model,
        messages=[ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)],
        temperature=0.2,
        max_tokens=int(max_tokens),
    )
    extracted = _extract_json_object(raw)
    if not extracted:
        raise ValueError("model did not return JSON")
    data = json.loads(extracted)
    return GeneratedResponse.model_validate(data)


async def generate_answer(
    *,
    tool_context: ToolContext,
    user_message: str,
    router_confidence: float,
) -> GeneratedResponse:
    main_model = (os.getenv("OPENROUTER_MAIN_MODEL") or "").strip() or (os.getenv("OPENROUTER_CHAT_MODEL") or "").strip()
    fallback_model = (os.getenv("OPENROUTER_FALLBACK_MODEL") or "").strip() or (os.getenv("OPENROUTER_CHAT_MODEL") or "").strip()

    ctx_dict = {
        "intent": tool_context.intent,
        "language": tool_context.language,
        "found": tool_context.found,
        "items": tool_context.items or [],
        "suggestions": tool_context.suggestions or [],
        "citations": tool_context.citations or [],
        "snippets": getattr(tool_context, "snippets", None) or [],
        "quick_replies": tool_context.quick_replies or [],
        "escalated": bool(tool_context.escalated),
    }

    if tool_context.intent in {"GREETING", "HOURS_CONTACT", "SERVICES", "APPOINTMENT", "CART", "RISKY_MEDICAL"}:
        return GeneratedResponse(
            answer="",
            language=tool_context.language,  # unused
            confidence=1.0,
            citations=[],
            actions=[],
            quick_replies=tool_context.quick_replies or [],
            escalated=bool(tool_context.escalated),
        )

    use_fallback = router_confidence < 0.55
    default_max = int(os.getenv("OPENROUTER_MAX_TOKENS", "400"))
    main_max = int(os.getenv("OPENROUTER_MAIN_MAX_TOKENS", str(default_max)))
    fallback_max = int(os.getenv("OPENROUTER_FALLBACK_MAX_TOKENS", str(default_max)))

    if not use_fallback and main_model:
        try:
            main = await _call_model(
                main_model,
                tool_context=ctx_dict,
                user_message=user_message,
                max_tokens=main_max,
            )
            if main.confidence >= 0.55:
                return main
            use_fallback = True
        except (OpenRouterError, ValidationError, ValueError, json.JSONDecodeError):
            use_fallback = True

    if fallback_model:
        try:
            fb = await _call_model(
                fallback_model,
                tool_context=ctx_dict,
                user_message=user_message,
                max_tokens=fallback_max,
            )
            return fb
        except Exception:
            pass

    return GeneratedResponse(
        answer="Assistant temporarily unavailable. Please try again.",
        language=tool_context.language if tool_context.language in {"en", "ar", "fr"} else "en",
        confidence=0.0,
        citations=[],
        actions=[],
        quick_replies=tool_context.quick_replies or [],
        escalated=bool(tool_context.escalated),
    )
