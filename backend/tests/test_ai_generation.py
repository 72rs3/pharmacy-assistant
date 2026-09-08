import asyncio
import json

from app.ai import generator, tri_model_router
from app.ai.openrouter_client import OpenRouterError
from app.ai.providers.base import ChatMessage
from app.ai.tool_executor import ToolContext


def test_low_router_confidence_still_calls_main_model(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_MAIN_MODEL", "test/main")
    monkeypatch.delenv("OPENROUTER_FALLBACK_MODEL", raising=False)
    calls = []

    async def model(**kwargs):
        calls.append(kwargs)
        return json.dumps({"answer": "How long have you had trouble sleeping?", "confidence": 0.4})

    monkeypatch.setattr(generator, "openrouter_chat", model)
    response = asyncio.run(generator.generate_answer(
        tool_context=ToolContext(intent="HEALTH_GUIDANCE", language="en"),
        user_message="I have insomnia", router_confidence=0.1))
    assert response.model == "test/main"
    assert len(calls) == 1
    assert calls[0]["json_mode"] is True
    assert "general health knowledge" in calls[0]["messages"][0].content


def test_router_model_failure_preserves_history_on_fallback(monkeypatch):
    monkeypatch.setenv("OPENROUTER_ROUTER_MODEL", "test/missing")
    monkeypatch.setenv("OPENROUTER_MAIN_MODEL", "test/working")
    calls = []

    async def model(**kwargs):
        calls.append(kwargs)
        if kwargs["model"] == "test/missing":
            raise OpenRouterError(404, "No endpoints")
        return json.dumps({"intent": "HEALTH_GUIDANCE", "confidence": 0.9})

    monkeypatch.setattr(tri_model_router, "openrouter_chat", model)
    history = [ChatMessage(role="user", content="I have insomnia"),
               ChatMessage(role="assistant", content="How long?")]
    result = asyncio.run(tri_model_router.route_intent("Three nights", history=history))
    assert result.intent == "HEALTH_GUIDANCE"
    assert [c["model"] for c in calls] == ["test/missing", "test/working"]
    assert calls[1]["messages"][1:-1] == history


def test_generation_outage_uses_fallback(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MAIN_MODEL", "test/main")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODEL", "test/fallback")
    calls = []

    async def model(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "test/main":
            return "invalid JSON"
        return json.dumps({"answer": "Please speak with the pharmacist.", "escalated": True})

    monkeypatch.setattr(generator, "openrouter_chat", model)
    result = asyncio.run(generator.generate_answer(tool_context=ToolContext(intent="RISKY_MEDICAL", language="en"),
                                                  user_message="Can I change my dose?", router_confidence=0.9))
    assert result.escalated
    assert result.model == "test/fallback"
    assert calls == ["test/main", "test/fallback"]
