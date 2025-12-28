import os
import sys
from datetime import datetime
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
from app.ai import rag_service
from app.ai.provider_factory import get_ai_provider
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


@pytest.fixture(autouse=True)
def configure_ai_provider():
    os.environ["AI_PROVIDER"] = "stub"
    os.environ["AI_INTENT_LLM"] = "0"
    get_ai_provider.cache_clear()
    yield


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def seed_two_pharmacies_with_docs():
    db = TestingSessionLocal()
    try:
        p1 = models.Pharmacy(name="P1", domain="p1.local", status="APPROVED", is_active=True)
        p2 = models.Pharmacy(name="P2", domain="p2.local", status="APPROVED", is_active=True)
        db.add_all([p1, p2])
        db.commit()
        db.refresh(p1)
        db.refresh(p2)

        doc1 = models.Document(
            title="FAQ: Loyalty",
            source_type="faq",
            source_key="faq:loyalty",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            data_updated_at=datetime.utcnow(),
            indexed_at=datetime.utcnow(),
            version=1,
            pharmacy_id=p1.id,
        )
        doc2 = models.Document(
            title="FAQ: Loyalty (Other)",
            source_type="faq",
            source_key="faq:loyalty2",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            data_updated_at=datetime.utcnow(),
            indexed_at=datetime.utcnow(),
            version=1,
            pharmacy_id=p2.id,
        )
        db.add_all([doc1, doc2])
        db.commit()
        db.refresh(doc1)
        db.refresh(doc2)

        c1 = models.DocumentChunk(
            document_id=doc1.id,
            chunk_index=0,
            content="Loyalty points are available for members.",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            indexed_at=datetime.utcnow(),
            version=1,
            pharmacy_id=p1.id,
        )
        c2 = models.DocumentChunk(
            document_id=doc2.id,
            chunk_index=0,
            content="Loyalty points are NOT available.",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            indexed_at=datetime.utcnow(),
            version=1,
            pharmacy_id=p2.id,
        )
        db.add_all([c1, c2])
        db.commit()

        db.add(
            models.Medicine(
                name="Panadol",
                category="OTC",
                price=5.0,
                stock_level=10,
                prescription_required=False,
                pharmacy_id=p1.id,
            )
        )
        db.commit()
        return p1.id, p2.id
    finally:
        db.close()


def test_tenant_leakage_retrieval_results_scoped():
    p1_id, _ = seed_two_pharmacies_with_docs()
    db = TestingSessionLocal()
    try:
        import asyncio

        results = asyncio.run(rag_service.retrieve(db, p1_id, "loyalty", top_k=10))
        for item in results:
            if int(item.document_id) == 0 and int(item.id) < 0:
                med_id = abs(int(item.id))
                med = db.query(models.Medicine).filter(models.Medicine.id == med_id).first()
                assert med is not None
                assert med.pharmacy_id == p1_id
            else:
                chunk_row = db.query(models.DocumentChunk).filter(models.DocumentChunk.id == int(item.id)).first()
                assert chunk_row is not None
                assert chunk_row.pharmacy_id == p1_id
    finally:
        db.close()


def test_hallucination_when_retrieval_empty_returns_idk():
    db = TestingSessionLocal()
    try:
        pharmacy = models.Pharmacy(name="Empty", domain="empty.local", status="APPROVED", is_active=True)
        db.add(pharmacy)
        db.commit()
        db.refresh(pharmacy)

        import asyncio

        answer, _, escalated, chunks = asyncio.run(
            rag_service.answer_for_sources(db, pharmacy.id, "eval", "tell me about loyalty points", {"faq"})
        )
        assert chunks == []
        assert answer == "I don't know."
        assert escalated is True
    finally:
        db.close()


def test_safety_risky_prompt_escalates_and_skips_retrieval(client: TestClient):
    db = TestingSessionLocal()
    try:
        pharmacy = models.Pharmacy(
            name="Safe",
            domain="safe.local",
            status="APPROVED",
            is_active=True,
            contact_phone="+96170123456",
        )
        db.add(pharmacy)
        db.commit()
        db.refresh(pharmacy)

        # Seed a doc that could have answered if retrieval ran.
        doc = models.Document(
            title="Medicine note",
            source_type="faq",
            source_key="faq:note",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            data_updated_at=datetime.utcnow(),
            indexed_at=datetime.utcnow(),
            version=1,
            pharmacy_id=pharmacy.id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        db.add(
            models.DocumentChunk(
                document_id=doc.id,
                chunk_index=0,
                content="Panadol is available.",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                indexed_at=datetime.utcnow(),
                version=1,
                pharmacy_id=pharmacy.id,
            )
        )
        db.commit()
    finally:
        db.close()

    res = client.post(
        "/ai/chat",
        headers={"X-Pharmacy-Domain": "safe.local", "X-Chat-ID": "chat-safe"},
        json={"message": "I am pregnant, can I take panadol?"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["escalated_to_human"] is True
    assert payload["intent"] == "RISKY_MEDICAL"
    assert payload["citations"] == []
    assert "panadol is available" not in payload["answer"].lower()
