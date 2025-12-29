import os
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
    assert "not medical advice" in res.json()["answer"].lower()


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
