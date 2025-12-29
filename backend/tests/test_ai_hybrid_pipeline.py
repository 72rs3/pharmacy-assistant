import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from app import models
from app.db import Base
from app.rag.hybrid import hybrid_answer

SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def configure_ai_provider():
    os.environ["AI_PROVIDER"] = "stub"
    from app.ai.provider_factory import get_ai_provider

    get_ai_provider.cache_clear()
    yield


def seed_pharmacy(db, *, branding_details: str | None = None) -> models.Pharmacy:
    pharmacy = models.Pharmacy(
        name="Sunr",
        domain="sunrise.local",
        status="APPROVED",
        is_active=True,
        operating_hours="Mon-Fri 9am-7pm",
        support_cod=True,
        branding_details=branding_details,
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
    db.commit()
    return pharmacy


def seed_rag_doc(db, pharmacy_id: int) -> None:
    doc = models.Document(
        title="FAQ: Loyalty",
        source_type="faq",
        source_key="faq:loyalty",
        created_at=datetime.utcnow(),
        pharmacy_id=pharmacy_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    chunk = models.DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="Loyalty points are available for members.",
        created_at=datetime.utcnow(),
        pharmacy_id=pharmacy_id,
    )
    db.add(chunk)
    db.commit()


def test_hybrid_shortcut_hours():
    db = TestingSessionLocal()
    try:
        pharmacy = seed_pharmacy(db)
        answer, _, _, _, _, debug = asyncio.run(hybrid_answer(db, pharmacy.id, "store hours"))
        assert debug["stage"] == "shortcut_hours_contact"
        assert "Store hours" in answer
    finally:
        db.close()


def test_hybrid_sql_exact_match():
    db = TestingSessionLocal()
    try:
        pharmacy = seed_pharmacy(db)
        answer, _, _, _, _, debug = asyncio.run(hybrid_answer(db, pharmacy.id, "do you have panadol"))
        assert debug["stage"] == "sql_exact"
        assert "Panadol" in answer
    finally:
        db.close()


def test_hybrid_sql_fuzzy_match():
    db = TestingSessionLocal()
    try:
        pharmacy = seed_pharmacy(db)
        answer, _, _, _, _, debug = asyncio.run(hybrid_answer(db, pharmacy.id, "do you have panadoll"))
        assert debug["stage"].startswith("sql_fuzzy")
        assert "Did you mean" in answer
    finally:
        db.close()


def test_hybrid_playbook_lookup():
    db = TestingSessionLocal()
    try:
        pharmacy = seed_pharmacy(db, branding_details="Return policy: 30 days.")
        answer, _, _, _, _, debug = asyncio.run(hybrid_answer(db, pharmacy.id, "return policy"))
        assert debug["stage"] == "playbook_branding"
        assert "Return policy" in answer
    finally:
        db.close()


def test_hybrid_rag_path():
    db = TestingSessionLocal()
    try:
        pharmacy = seed_pharmacy(db)
        seed_rag_doc(db, pharmacy.id)
        answer, _, _, _, _, debug = asyncio.run(hybrid_answer(db, pharmacy.id, "loyalty points"))
        assert debug["stage"] == "rag"
        assert "Loyalty points" in answer
    finally:
        db.close()


def test_hybrid_fallback_path():
    db = TestingSessionLocal()
    try:
        pharmacy = seed_pharmacy(db)
        answer, _, _, escalated, _, debug = asyncio.run(hybrid_answer(db, pharmacy.id, "asdkjasdkl"))
        assert debug["stage"] == "fallback"
        assert answer == "I don't know."
        assert escalated is True
    finally:
        db.close()
