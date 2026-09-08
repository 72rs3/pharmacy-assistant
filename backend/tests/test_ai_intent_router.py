import os
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from app import models
from app.auth import utils
from app.db import Base, get_db
from app.main import app

SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def seed_pharmacy():
    db = TestingSessionLocal()
    try:
        pharmacy = models.Pharmacy(
            name="Sunr",
            domain="sunrise.local",
            status="APPROVED",
            is_active=True,
            operating_hours="Mon-Fri 9am-7pm",
            support_cod=True,
            contact_phone="+96170123456",
            contact_email="info@sunr.test",
        )
        db.add(pharmacy)
        db.commit()
        db.refresh(pharmacy)

        db.add(
            models.Medicine(
                name="Panadol",
                category="OTC",
                price=5.0,
                stock_level=10,
                prescription_required=False,
                pharmacy_id=pharmacy.id,
            )
        )
        db.add(
            models.Medicine(
                name="Amoxicillin",
                category="Antibiotic",
                price=12.0,
                stock_level=8,
                prescription_required=True,
                pharmacy_id=pharmacy.id,
            )
        )
        db.add(
            models.Product(
                name="Toothpaste",
                category="Oral Care",
                price=3.5,
                stock_level=20,
                pharmacy_id=pharmacy.id,
            )
        )
        db.add(
            models.User(
                email="owner@example.com",
                full_name="Owner",
                hashed_password=utils.hash_password("owner-password-123"),
                is_admin=False,
                pharmacy_id=pharmacy.id,
                role="OWNER",
            )
        )
        db.commit()
    finally:
        db.close()


def seed_other_pharmacy_product():
    db = TestingSessionLocal()
    try:
        pharmacy = models.Pharmacy(
            name="Other",
            domain="other.local",
            status="APPROVED",
            is_active=True,
        )
        db.add(pharmacy)
        db.commit()
        db.refresh(pharmacy)

        db.add(
            models.Product(
                name="Sunscreen",
                category="Skincare",
                price=11.0,
                stock_level=15,
                pharmacy_id=pharmacy.id,
            )
        )
        db.commit()
    finally:
        db.close()


def seed_other_pharmacy_medicine():
    db = TestingSessionLocal()
    try:
        pharmacy = models.Pharmacy(
            name="OtherMed",
            domain="othermed.local",
            status="APPROVED",
            is_active=True,
        )
        db.add(pharmacy)
        db.commit()
        db.refresh(pharmacy)

        db.add(
            models.Medicine(
                name="Brufen",
                category="OTC",
                price=6.0,
                stock_level=12,
                prescription_required=False,
                pharmacy_id=pharmacy.id,
            )
        )
        db.commit()
    finally:
        db.close()


def test_intent_router_labels(client: TestClient):
    os.environ["AI_PROVIDER"] = "stub"
    os.environ["OPENROUTER_ROUTER_MODEL"] = "stub/router"
    os.environ["OPENROUTER_MAIN_MODEL"] = "stub/main"
    os.environ["OPENROUTER_FALLBACK_MODEL"] = "stub/fallback"
    from app.ai.provider_factory import get_ai_provider

    get_ai_provider.cache_clear()
    seed_pharmacy()

    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "chat-1"}

    res = client.post("/ai/chat", headers=headers, json={"message": "hello"})
    assert res.status_code == 200
    assert res.json()["intent"] == "GREETING"
    assert res.json()["citations"]

    res = client.post("/ai/chat", headers=headers, json={"message": "store hours"})
    assert res.status_code == 200
    assert res.json()["intent"] == "HOURS_CONTACT"
    assert res.json()["citations"]

    res = client.post("/ai/chat", headers=headers, json={"message": "delivery options"})
    assert res.status_code == 200
    assert res.json()["intent"] in {"SERVICES", "GENERAL_RAG"}
    assert res.json()["citations"]

    res = client.post("/ai/chat", headers=headers, json={"message": "book appointment"})
    assert res.status_code == 200
    assert res.json()["intent"] == "APPOINTMENT"
    assert res.json()["citations"]

    res = client.post("/ai/chat", headers=headers, json={"message": "do you have panadol"})
    assert res.status_code == 200
    assert res.json()["intent"] == "MEDICINE_SEARCH"
    assert res.json()["citations"]

    res = client.post("/ai/chat", headers=headers, json={"message": "do you have amoxicillin rx"})
    assert res.status_code == 200
    assert res.json()["intent"] == "MEDICINE_SEARCH"
    assert res.json()["citations"]

    res = client.post("/ai/chat", headers=headers, json={"message": "toothpaste"})
    assert res.status_code == 200
    assert res.json()["intent"] == "PRODUCT_SEARCH"
    assert res.json()["citations"]

    res = client.post("/ai/chat", headers=headers, json={"message": "I have chest pain"})
    assert res.status_code == 200
    assert res.json()["intent"] == "RISKY_MEDICAL"
    assert res.json()["escalated_to_human"] is True
    # Risky prompts are escalated; citations may be empty when retrieval is skipped.

    res = client.post("/ai/chat", headers=headers, json={"message": "tell me about your services"})
    assert res.status_code == 200
    assert res.json()["intent"] in {"SERVICES_INFO", "GENERAL_RAG"}
    assert res.json()["citations"]

    res = client.post("/ai/chat", headers=headers, json={"message": "asdasdasd"})
    assert res.status_code == 200
    assert res.json()["intent"] == "UNKNOWN"


def test_medicine_search_extracts_query_and_fuzzy_suggests(client: TestClient):
    os.environ["AI_PROVIDER"] = "stub"
    os.environ["OPENROUTER_ROUTER_MODEL"] = "stub/router"
    os.environ["OPENROUTER_MAIN_MODEL"] = "stub/main"
    os.environ["OPENROUTER_FALLBACK_MODEL"] = "stub/fallback"
    from app.ai.provider_factory import get_ai_provider

    get_ai_provider.cache_clear()
    seed_pharmacy()
    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "chat-9"}

    res = client.post("/ai/chat", headers=headers, json={"message": "im looking for panadol"})
    assert res.status_code == 200
    assert res.json()["intent"] == "MEDICINE_SEARCH"
    assert res.json()["cards"]
    assert any(a.get("type") == "add_to_cart" for a in (res.json().get("actions") or []))

    res = client.post("/ai/chat", headers=headers, json={"message": "paanadol"})
    assert res.status_code == 200
    assert res.json()["intent"] == "MEDICINE_SEARCH"
    assert ("panadol" in res.json()["answer"].lower()) or any(
        "panadol" in q.lower() for q in (res.json().get("quick_replies") or [])
    )


def test_product_queries_do_not_leak_other_tenant(client: TestClient):
    os.environ["AI_PROVIDER"] = "stub"
    os.environ["OPENROUTER_ROUTER_MODEL"] = "stub/router"
    os.environ["OPENROUTER_MAIN_MODEL"] = "stub/main"
    os.environ["OPENROUTER_FALLBACK_MODEL"] = "stub/fallback"
    from app.ai.provider_factory import get_ai_provider

    get_ai_provider.cache_clear()
    seed_pharmacy()
    seed_other_pharmacy_product()

    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "chat-2"}
    res = client.post("/ai/chat", headers=headers, json={"message": "sunscreen"})
    assert res.status_code == 200
    assert "sunscreen" not in res.json()["answer"].lower()


def test_session_memory_isolated_by_pharmacy(client: TestClient):
    os.environ["AI_PROVIDER"] = "stub"
    os.environ["OPENROUTER_ROUTER_MODEL"] = "stub/router"
    os.environ["OPENROUTER_MAIN_MODEL"] = "stub/main"
    os.environ["OPENROUTER_FALLBACK_MODEL"] = "stub/fallback"
    from app.ai.provider_factory import get_ai_provider

    get_ai_provider.cache_clear()
    seed_pharmacy()
    seed_other_pharmacy_medicine()

    session_id = "sess-1"
    headers_one = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "chat-1"}
    res_one = client.post("/ai/chat", headers=headers_one, json={"message": "do you have panadol", "session_id": session_id})
    assert res_one.status_code == 200

    headers_two = {"X-Pharmacy-Domain": "othermed.local", "X-Chat-ID": "chat-2"}
    res_two = client.post("/ai/chat", headers=headers_two, json={"message": "is it available", "session_id": session_id})
    assert res_two.status_code == 200
    assert "panadol" not in res_two.json()["answer"].lower()


def test_short_price_followup_uses_last_medicine_context(client: TestClient):
    os.environ["AI_PROVIDER"] = "stub"
    os.environ["OPENROUTER_ROUTER_MODEL"] = "stub/router"
    os.environ["OPENROUTER_MAIN_MODEL"] = "stub/main"
    os.environ["OPENROUTER_FALLBACK_MODEL"] = "stub/fallback"
    from app.ai.provider_factory import get_ai_provider

    get_ai_provider.cache_clear()
    seed_pharmacy()
    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "chat-price"}

    first = client.post("/ai/chat", headers=headers, json={"message": "hello i need panadol"})
    assert first.status_code == 200
    assert first.json()["cards"]
    assert first.json()["cards"][0]["name"].lower() == "panadol"

    followup = client.post("/ai/chat", headers=headers, json={"message": "price?"})
    assert followup.status_code == 200
    payload = followup.json()
    assert payload["intent"] == "MEDICINE_SEARCH"
    assert "panadol" in payload["answer"].lower()
    assert "5.00" in payload["answer"]
    assert payload["cards"]
    assert payload["cards"][0]["name"].lower() == "panadol"


def test_medical_guardrails_risky_prompt(client: TestClient):
    os.environ["AI_PROVIDER"] = "stub"
    os.environ["OPENROUTER_ROUTER_MODEL"] = "stub/router"
    os.environ["OPENROUTER_MAIN_MODEL"] = "stub/main"
    os.environ["OPENROUTER_FALLBACK_MODEL"] = "stub/fallback"
    from app.ai.provider_factory import get_ai_provider

    get_ai_provider.cache_clear()
    seed_pharmacy()

    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "chat-3"}
    res = client.post("/ai/chat", headers=headers, json={"message": "Can I change the dosage for this medicine?"})
    assert res.status_code == 200
    assert res.json()["escalated_to_human"] is True
    assert "pharmacist" in res.json()["answer"].lower()
    assert any(a["type"] == "escalate_to_pharmacist" for a in res.json()["actions"])


def test_arabic_greeting_language_detection(client: TestClient):
    os.environ["AI_PROVIDER"] = "stub"
    os.environ["OPENROUTER_ROUTER_MODEL"] = "stub/router"
    os.environ["OPENROUTER_MAIN_MODEL"] = "stub/main"
    os.environ["OPENROUTER_FALLBACK_MODEL"] = "stub/fallback"
    from app.ai.provider_factory import get_ai_provider

    get_ai_provider.cache_clear()
    seed_pharmacy()
    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "chat-ar"}

    res = client.post("/ai/chat", headers=headers, json={"message": "مرحبا"})
    assert res.status_code == 200
    assert res.json()["intent"] == "GREETING"
    assert "مرحب" in res.json()["answer"]


def test_main_outage_falls_back(client: TestClient):
    os.environ["AI_PROVIDER"] = "stub"
    os.environ["OPENROUTER_ROUTER_MODEL"] = "stub/router"
    os.environ["OPENROUTER_MAIN_MODEL"] = "stub/main"
    os.environ["OPENROUTER_FALLBACK_MODEL"] = "stub/fallback"
    os.environ["OPENROUTER_STUB_FAIL_MAIN"] = "1"
    from app.ai.provider_factory import get_ai_provider

    get_ai_provider.cache_clear()
    seed_pharmacy()
    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "chat-fb"}

    res = client.post("/ai/chat", headers=headers, json={"message": "tell me about your services"})
    assert res.status_code == 200
    assert "temporarily unavailable" not in res.json()["answer"].lower()


def test_openrouter_history_topic_change_and_untrusted_actions(client, monkeypatch):
    from app.ai import generator, tri_model_router
    from app.ai.provider_factory import get_ai_provider

    monkeypatch.setenv("AI_PROVIDER", "stub")
    monkeypatch.setenv("OPENROUTER_ROUTER_MODEL", "test/router")
    monkeypatch.setenv("OPENROUTER_MAIN_MODEL", "test/main")
    get_ai_provider.cache_clear()
    seed_pharmacy()
    router_calls, generation_calls = [], []

    async def classify(**kwargs):
        router_calls.append(kwargs["messages"])
        latest = kwargs["messages"][-1].content
        intent = "APPOINTMENT" if "appointment" in latest else "HEALTH_GUIDANCE"
        return json.dumps({"intent": intent, "query": latest, "confidence": 0.9})

    async def generate(**kwargs):
        generation_calls.append(kwargs["messages"])
        latest = kwargs["messages"][-1].content
        answer = "How long have you had trouble sleeping?"
        if "Three nights" in latest:
            answer = "For those three nights, has it affected your daytime activities?"
        if '"intent": "APPOINTMENT"' in latest:
            answer = "Use Book appointment to choose a time. No prescription required."
        return json.dumps({"answer": answer, "confidence": 0.9,
                           "actions": [{"type": "upload_prescription", "label": "Upload prescription"},
                                       {"type": "add_to_cart", "label": "Add", "payload": {"medicine_id": 99999}}],
                           "quick_replies": ["Upload prescription"]})

    monkeypatch.setattr(tri_model_router, "openrouter_chat", classify)
    monkeypatch.setattr(generator, "openrouter_chat", generate)
    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "conversation-test"}
    for message in ["I have insomnia", "Three nights", "I want to book an appointment"]:
        response = client.post("/ai/chat", headers=headers, json={"message": message})
        assert response.status_code == 200, response.text
        body = response.json()
        assert all(a["type"] not in {"upload_prescription", "add_to_cart"} for a in body["actions"])
        assert "Upload prescription" not in body["quick_replies"]
    assert body["intent"] == "APPOINTMENT"
    assert [a["type"] for a in body["actions"]] == ["book_appointment"]
    assert "No prescription required" in body["answer"]
    assert len(router_calls) == len(generation_calls) == 3
    for calls in [router_calls, generation_calls]:
        assert [(m.role, m.content) for m in calls[1][1:-1]] == [
            ("user", "I have insomnia"), ("assistant", "How long have you had trouble sleeping?")]
    other = client.post("/ai/chat", headers={**headers, "X-Chat-ID": "other-customer"},
                        json={"message": "I have insomnia", "session_id": body["session_id"]})
    assert other.status_code == 200
    assert len(router_calls[-1]) == len(generation_calls[-1]) == 2


def test_emergency_bypasses_model_outage(client, monkeypatch):
    from app.ai import tri_model_router
    from app.ai.provider_factory import get_ai_provider

    monkeypatch.setenv("AI_PROVIDER", "stub")
    get_ai_provider.cache_clear()
    seed_pharmacy()

    async def unavailable(*args, **kwargs):
        raise AssertionError("Emergency guidance must not wait for OpenRouter")

    monkeypatch.setattr(tri_model_router, "openrouter_chat", unavailable)
    response = client.post("/ai/chat", headers={"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "urgent-test"},
                           json={"message": "I have chest pain and can't breathe"})
    assert response.status_code == 200
    assert "emergency" in response.json()["answer"].lower()
    assert all(a["type"] != "add_to_cart" for a in response.json()["actions"])


def test_unrelated_request_redirects_without_tools(client, monkeypatch):
    from app.ai import tri_model_router, generator
    monkeypatch.setenv("AI_PROVIDER", "stub")
    monkeypatch.setenv("OPENROUTER_ROUTER_MODEL", "test/router")
    seed_pharmacy()

    async def classify(**kwargs):
        assert "translate water" in kwargs["messages"][0].content
        return json.dumps({"intent": "OUT_OF_SCOPE", "confidence": 0.99})

    async def forbidden(**kwargs):
        raise AssertionError("Unrelated answers must not be generated")

    monkeypatch.setattr(tri_model_router, "openrouter_chat", classify)
    monkeypatch.setattr(generator, "openrouter_chat", forbidden)
    response = client.post("/ai/chat", headers={"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "scope-test"},
                           json={"message": "Translate water to Arabic"})
    assert response.status_code == 200, response.text
    assert response.json()["intent"] == "OUT_OF_SCOPE"
    assert "pharmacy" in response.json()["answer"]
    assert response.json()["actions"] == []
    assert response.json()["cards"] == []


def test_cart_button_does_not_claim_completed_mutation(client, monkeypatch):
    from app.ai import tri_model_router, generator
    monkeypatch.setenv("AI_PROVIDER", "stub")
    monkeypatch.setenv("OPENROUTER_ROUTER_MODEL", "test/router")
    monkeypatch.setenv("OPENROUTER_MAIN_MODEL", "test/main")
    seed_pharmacy()

    async def classify(**kwargs):
        intent = "CART" if "yes add" in kwargs["messages"][-1].content else "MEDICINE_SEARCH"
        return json.dumps({"intent": intent, "query": "Panadol", "confidence": 0.99})

    async def generate(**kwargs):
        return json.dumps({"answer": "Adding Panadol to your cart now.", "confidence": 0.9})

    monkeypatch.setattr(tri_model_router, "openrouter_chat", classify)
    monkeypatch.setattr(generator, "openrouter_chat", generate)
    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "cart-wording-test"}
    first = client.post("/ai/chat", headers=headers, json={"message": "Panadol"})
    assert first.status_code == 200
    response = client.post("/ai/chat", headers=headers, json={"message": "yes add to", "session_id": first.json()["session_id"]})
    assert response.status_code == 200, response.text
    assert "Tap the Add" in response.json()["answer"]
    assert any(a["type"] == "add_to_cart" for a in response.json()["actions"])


def test_missing_medicine_is_not_reported_as_out_of_stock(client, monkeypatch):
    from app.ai import tri_model_router, generator
    monkeypatch.setenv("AI_PROVIDER", "stub")
    monkeypatch.setenv("OPENROUTER_ROUTER_MODEL", "test/router")
    monkeypatch.setenv("OPENROUTER_MAIN_MODEL", "test/main")
    seed_pharmacy()

    async def classify(**kwargs):
        return json.dumps({"intent": "MEDICINE_SEARCH", "query": "paracetamol", "confidence": 0.99})

    async def generate(**kwargs):
        return json.dumps({"answer": "Paracetamol is unavailable.", "confidence": 0.9})

    monkeypatch.setattr(tri_model_router, "openrouter_chat", classify)
    monkeypatch.setattr(generator, "openrouter_chat", generate)
    response = client.post("/ai/chat", headers={"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "no-match-test"},
                           json={"message": "you have paracetemol?"})
    assert response.status_code == 200, response.text
    assert "couldn't confirm" in response.json()["answer"]
    assert "unavailable" not in response.json()["answer"]
    assert response.json()["cards"] == []
