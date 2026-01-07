from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import asyncio
import logging
import httpx

from app.ai.providers.base import ChatMessage


_RETRYABLE = {429, 500, 502, 503, 504}
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenRouterError(RuntimeError):
    status_code: int | None
    message: str

    def __str__(self) -> str:  # pragma: no cover
        prefix = f"OpenRouter error ({self.status_code})" if self.status_code is not None else "OpenRouter error"
        return f"{prefix}: {self.message}"


def _headers() -> dict[str, str]:
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise OpenRouterError(None, "OPENROUTER_API_KEY is not set")
    headers = {"Authorization": f"Bearer {api_key}"}
    http_referer = (os.getenv("OPENROUTER_HTTP_REFERER") or "").strip()
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    x_title = (os.getenv("OPENROUTER_X_TITLE") or "").strip()
    if x_title:
        headers["X-Title"] = x_title
    return headers


def _base_url() -> str:
    return (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")


def _timeout_s() -> float:
    return float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", os.getenv("OPENROUTER_TIMEOUT_S", "30")))


def _max_retries() -> int:
    return int(os.getenv("OPENROUTER_MAX_RETRIES", "1"))


def _raise_openrouter_error(res: httpx.Response) -> None:
    try:
        payload = res.json()
        msg = payload.get("error", {}).get("message") or payload.get("message") or res.text
    except Exception:
        msg = res.text
    raise OpenRouterError(res.status_code, str(msg))


def _is_stub_mode() -> bool:
    return (os.getenv("AI_PROVIDER") or "").strip().lower() == "stub"


def _should_stub_fail_main(model: str) -> bool:
    if (os.getenv("OPENROUTER_STUB_FAIL_MAIN") or "").strip() != "1":
        return False
    main = (os.getenv("OPENROUTER_MAIN_MODEL") or "").strip()
    return bool(main) and model == main


def _stub_router(message: str) -> str:
    low = (message or "").strip().lower()
    if not low:
        return json.dumps({"language": "en", "intent": "UNKNOWN", "query": None, "greeting": False, "confidence": 0.0, "risk": "low", "clarifying_questions": []})
    if any(ch in low for ch in ["مرحبا", "اهلا"]):
        return json.dumps({"language": "ar", "intent": "GREETING", "query": None, "greeting": True, "confidence": 0.9, "risk": "low", "clarifying_questions": []})
    if low.startswith(("hi", "hello", "hey")):
        rest = low
        for prefix in ["hi", "hello", "hey"]:
            if rest.startswith(prefix):
                rest = rest[len(prefix):].strip()
                break
        if rest:
            return json.dumps({"language": "en", "intent": "MEDICINE_SEARCH", "query": rest, "greeting": True, "confidence": 0.7, "risk": "low", "clarifying_questions": []})
        return json.dumps({"language": "en", "intent": "GREETING", "query": None, "greeting": True, "confidence": 0.9, "risk": "low", "clarifying_questions": []})
    if "pregnant" in low or "pregnancy" in low:
        return json.dumps({"language": "en", "intent": "RISKY_MEDICAL", "query": None, "greeting": False, "confidence": 0.9, "risk": "high", "clarifying_questions": []})
    if "appointment" in low or "book" in low:
        return json.dumps({"language": "en", "intent": "APPOINTMENT", "query": None, "greeting": False, "confidence": 0.8, "risk": "low", "clarifying_questions": []})
    if "hours" in low or "open" in low or "contact" in low:
        return json.dumps({"language": "en", "intent": "HOURS_CONTACT", "query": None, "greeting": False, "confidence": 0.8, "risk": "low", "clarifying_questions": []})
    if "delivery" in low or "shipping" in low or "cod" in low or "cash on delivery" in low:
        return json.dumps({"language": "en", "intent": "SERVICES", "query": None, "greeting": False, "confidence": 0.75, "risk": "low", "clarifying_questions": []})
    if any(w in low for w in ["toothpaste", "toothbrush", "shampoo", "soap", "vitamin"]):
        return json.dumps({"language": "en", "intent": "PRODUCT_SEARCH", "query": low, "greeting": False, "confidence": 0.7, "risk": "low", "clarifying_questions": []})
    if any(w in low for w in ["panadol", "amoxicillin", "brufen"]) or any(w in low for w in ["have", "available", "stock", "price", "looking for", "need", "want", "give me"]):
        q = low
        for prefix in ["im looking for", "i'm looking for", "looking for", "i want", "i need", "do you have"]:
            if q.startswith(prefix):
                q = q[len(prefix):].strip()
                break
        return json.dumps({"language": "en", "intent": "MEDICINE_SEARCH", "query": q or low, "greeting": False, "confidence": 0.7, "risk": "low", "clarifying_questions": []})
    if "cart" in low or "add to cart" in low:
        return json.dumps({"language": "en", "intent": "CART", "query": None, "greeting": False, "confidence": 0.7, "risk": "low", "clarifying_questions": []})
    if len(low) >= 6 and len(set(low)) <= 3:
        return json.dumps({"language": "en", "intent": "UNKNOWN", "query": None, "greeting": False, "confidence": 0.2, "risk": "low", "clarifying_questions": []})
    if len(low.split()) <= 2:
        return json.dumps({"language": "en", "intent": "MEDICINE_SEARCH", "query": low, "greeting": False, "confidence": 0.6, "risk": "low", "clarifying_questions": []})
    return json.dumps({"language": "en", "intent": "GENERAL_RAG", "query": low, "greeting": False, "confidence": 0.6, "risk": "low", "clarifying_questions": []})


def _stub_generate(tool_context: dict) -> str:
    intent = (tool_context.get("intent") or "").upper()
    language = tool_context.get("language") or "en"
    answer = "I don't know based on available pharmacy data."
    actions = []
    citations = tool_context.get("citations") or []
    quick_replies = tool_context.get("quick_replies") or []
    escalated = bool(tool_context.get("escalated") or False)

    if intent == "MEDICINE_SEARCH":
        found = bool(tool_context.get("found"))
        items = tool_context.get("items") or []
        suggestions = tool_context.get("suggestions") or []
        if found and items:
            item = items[0]
            name = item.get("name") or "medicine"
            rx = bool(item.get("rx"))
            stock = int(item.get("stock") or 0)
            price = item.get("price")
            if rx:
                answer = f"Yes, we have {name} available. This medicine requires a prescription."
                actions = [
                    {
                        "type": "add_to_cart",
                        "label": "Add to cart",
                        "payload": {"medicine_id": int(item.get("id")), "quantity": 1, "requires_prescription": True},
                    }
                ]
            elif stock > 0:
                answer = f"Yes, we have {name} available." + (f" Price: {float(price):.2f}." if price is not None else "")
                actions = [{"type": "add_to_cart", "label": "Add to cart", "payload": {"medicine_id": int(item.get("id")), "quantity": 1}}]
            else:
                answer = f"Sorry, {name} is out of stock."
        elif suggestions:
            answer = "I could not find an exact match. Did you mean: " + ", ".join(suggestions)

    return json.dumps(
        {
            "answer": answer,
            "language": language,
            "confidence": 0.75 if not escalated else 0.2,
            "citations": citations,
            "actions": actions,
            "quick_replies": quick_replies,
            "escalated": escalated,
        },
        ensure_ascii=False,
    )


async def openrouter_chat(
    *,
    model: str,
    messages: list[ChatMessage],
    temperature: float = 0.2,
    max_tokens: int = 400,
) -> str:
    if _is_stub_mode():
        if _should_stub_fail_main(model):
            raise OpenRouterError(503, "stub: simulated main model outage")
        system = next((m.content for m in messages if m.role == "system"), "")
        user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        if "STRICT JSON" in system and "intent" in system and "confidence" in system:
            return _stub_router(user.replace("Message:", "").strip())
        if "tool_context" in system or "TOOL_CONTEXT" in system:
            try:
                ctx = json.loads(user.split("TOOL_CONTEXT:", 1)[-1].strip())
            except Exception:
                ctx = {}
            return _stub_generate(ctx if isinstance(ctx, dict) else {})
        # fallback to existing stub provider behavior
        from app.ai.provider_factory import get_ai_provider

        provider = get_ai_provider()
        return await provider.chat(messages)

    if not model:
        raise OpenRouterError(None, "Model is required")

    retries = _max_retries()
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        start = time.time()
        try:
            async with httpx.AsyncClient(base_url=_base_url(), timeout=_timeout_s(), headers=_headers()) as client:
                res = await client.post(
                    "/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": m.role, "content": m.content} for m in messages],
                        "temperature": float(temperature),
                        "max_tokens": int(max_tokens),
                    },
                )
            elapsed_ms = int((time.time() - start) * 1000)
            if res.status_code >= 400:
                _logger.info("openrouter chat status=%s model=%s ms=%s", res.status_code, model, elapsed_ms)
                if res.status_code == 503:
                    _raise_openrouter_error(res)
                if res.status_code in _RETRYABLE and attempt < retries:
                    if res.status_code == 429:
                        retry_after = (res.headers.get("Retry-After") or "").strip()
                        try:
                            delay_s = float(retry_after) if retry_after else 1.0
                        except Exception:
                            delay_s = 1.0
                    else:
                        delay_s = 1.0 * (2**attempt)
                    await asyncio.sleep(min(delay_s, 5.0))
                    continue
                _raise_openrouter_error(res)
            data = res.json()
            _logger.info("openrouter chat status=200 model=%s ms=%s", model, elapsed_ms)
            return data["choices"][0]["message"]["content"]
        except OpenRouterError as exc:
            last_error = exc
            break
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            continue
    raise OpenRouterError(None, str(last_error or "unknown error"))


async def openrouter_embed(*, model: str, texts: list[str]) -> list[list[float]]:
    if _is_stub_mode():
        from app.ai.provider_factory import get_ai_provider

        provider = get_ai_provider()
        return await provider.embed(texts)

    if not model:
        raise OpenRouterError(None, "Embedding model is required")
    retries = _max_retries()
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        start = time.time()
        try:
            async with httpx.AsyncClient(base_url=_base_url(), timeout=_timeout_s(), headers=_headers()) as client:
                res = await client.post("/embeddings", json={"model": model, "input": texts})
            elapsed_ms = int((time.time() - start) * 1000)
            if res.status_code >= 400:
                _logger.info("openrouter embed status=%s model=%s ms=%s", res.status_code, model, elapsed_ms)
                if res.status_code == 503:
                    _raise_openrouter_error(res)
                if res.status_code in _RETRYABLE and attempt < retries:
                    if res.status_code == 429:
                        retry_after = (res.headers.get("Retry-After") or "").strip()
                        try:
                            delay_s = float(retry_after) if retry_after else 1.0
                        except Exception:
                            delay_s = 1.0
                    else:
                        delay_s = 1.0 * (2**attempt)
                    await asyncio.sleep(min(delay_s, 5.0))
                    continue
                _raise_openrouter_error(res)
            data = res.json()
            _logger.info("openrouter embed status=200 model=%s ms=%s", model, elapsed_ms)
            return [item["embedding"] for item in data["data"]]
        except OpenRouterError as exc:
            last_error = exc
            break
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            continue
    raise OpenRouterError(None, str(last_error or "unknown error"))
