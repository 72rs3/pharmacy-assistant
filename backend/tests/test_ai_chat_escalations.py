import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure the backend package is importable when running tests from repo root
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


def test_ai_chat_escalation_owner_reply_roundtrip(client: TestClient):
    import os

    os.environ["AI_PROVIDER"] = "stub"
    from app.ai.provider_factory import get_ai_provider

    get_ai_provider.cache_clear()

    db = TestingSessionLocal()
    try:
        pharmacy = models.Pharmacy(
            name="Sunrise",
            domain="sunrise.local",
            status="APPROVED",
            is_active=True,
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

        owner = models.User(
            email="owner@example.com",
            full_name="Owner",
            hashed_password=utils.hash_password("owner-password-123"),
            is_admin=False,
            pharmacy_id=pharmacy.id,
            role="OWNER",
        )
        db.add(owner)
        db.commit()
    finally:
        db.close()

    # Owner indexes medicines for RAG.
    login = client.post("/auth/login", json={"email": "owner@example.com", "password": "owner-password-123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    reindex = client.post("/ai/rag/reindex", headers={"Authorization": f"Bearer {token}"})
    assert reindex.status_code == 200
    assert reindex.json()["chunks"] >= 1

    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "chat-1"}

    res = client.post("/ai/chat", headers=headers, json={"message": "Do you have panadol?"})
    assert res.status_code == 200
    assert res.json()["customer_id"] == "chat-1"
    assert "panadol" in res.json()["answer"].lower()

    risk = client.post("/ai/chat", headers=headers, json={"message": "I have chest pain"})
    assert risk.status_code == 200
    assert risk.json()["escalated_to_human"] is True

    escalations = client.get("/ai/escalations/owner", headers={"Authorization": f"Bearer {token}"})
    assert escalations.status_code == 200
    pending = escalations.json()
    assert len(pending) >= 1

    interaction_id = pending[0]["id"]
    reply = client.post(
        f"/ai/escalations/{interaction_id}/reply",
        headers={"Authorization": f"Bearer {token}"},
        json={"reply": "Please come to the pharmacy or call emergency services immediately."},
    )
    assert reply.status_code == 200
    assert reply.json()["owner_reply"]

    history = client.get("/ai/chat/my", headers=headers)
    assert history.status_code == 200
    assert any(item.get("owner_reply") for item in history.json())
