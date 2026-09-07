import json
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from app import models
from app.auth import deps as auth_deps
from app.auth import utils
from app.auth.bootstrap import ensure_admin_user
from app.bootstrap import ensure_demo_accounts
from app.ai.provider_factory import get_ai_provider
from app.db import Base, get_db
from app.main import app
from app.utils.rate_limit import reset_rate_limits

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
def setup_database(monkeypatch):
    reset_rate_limits()
    get_ai_provider.cache_clear()
    monkeypatch.setenv("AI_PROVIDER", "stub")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    app.dependency_overrides.clear()
    reset_rate_limits()
    get_ai_provider.cache_clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _seed_public_pharmacy(domain: str = "sunrise.local") -> models.Pharmacy:
    db = TestingSessionLocal()
    try:
        pharmacy = models.Pharmacy(name="Sunrise", domain=domain, status="APPROVED", is_active=True)
        db.add(pharmacy)
        db.commit()
        db.refresh(pharmacy)
        db.expunge(pharmacy)
        return pharmacy
    finally:
        db.close()


def test_public_appointment_availability_hides_customer_details(client: TestClient):
    pharmacy = _seed_public_pharmacy()
    booked_time = datetime(2030, 1, 7, 9, 0)

    db = TestingSessionLocal()
    try:
        db.add(
            models.AppointmentSettings(
                pharmacy_id=pharmacy.id,
                slot_minutes=15,
                buffer_minutes=0,
                timezone="UTC",
                weekly_hours_json=json.dumps({"mon": [{"start": "09:00", "end": "09:30"}]}),
            )
        )
        db.add(
            models.Appointment(
                customer_id="customer-1",
                customer_name="Private Customer",
                customer_phone="+96179111111",
                type="Consultation",
                scheduled_time=booked_time,
                status="CONFIRMED",
                pharmacy_id=pharmacy.id,
            )
        )
        db.commit()
    finally:
        db.close()

    res = client.get(
        "/appointments/availability/public",
        params={"date": booked_time.date().isoformat()},
        headers={"X-Pharmacy-Domain": "sunrise.local"},
    )

    assert res.status_code == 200
    slots = res.json()["slots"]
    assert any(slot["booked"] is True for slot in slots)
    assert all("customer_name" not in slot for slot in slots)
    assert all("appointment_id" not in slot for slot in slots)
    assert all("status" not in slot for slot in slots)


def test_ai_chat_rejects_oversized_message_before_provider_call(client: TestClient):
    _seed_public_pharmacy()

    res = client.post(
        "/ai/chat",
        json={"message": "a" * 2001},
        headers={"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "chat-oversized"},
    )

    assert res.status_code == 422


def test_ai_chat_enforces_per_customer_rate_limit(client: TestClient, monkeypatch):
    _seed_public_pharmacy()
    monkeypatch.setenv("AI_CHAT_IP_RATE_LIMIT_PER_MIN", "100")
    monkeypatch.setenv("AI_CHAT_SESSION_RATE_LIMIT_PER_MIN", "1")

    headers = {"X-Pharmacy-Domain": "sunrise.local", "X-Chat-ID": "same-customer"}
    first = client.post("/ai/chat", json={"message": "hello"}, headers=headers)
    second = client.post("/ai/chat", json={"message": "hello again"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429


def test_prescription_draft_rejects_too_many_files_before_saving(client: TestClient):
    _seed_public_pharmacy()

    files = [
        ("files", (f"rx-{idx}.pdf", b"%PDF-1.4", "application/pdf"))
        for idx in range(4)
    ]
    res = client.post(
        "/prescriptions/draft",
        files=files,
        headers={"X-Pharmacy-Domain": "sunrise.local"},
    )

    assert res.status_code == 400
    assert "Upload up to" in res.json()["detail"]


def test_bootstrap_does_not_overwrite_existing_admin_password(monkeypatch):
    monkeypatch.setenv("PHARMACY_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("PHARMACY_ADMIN_PASSWORD", "render-env-password")
    monkeypatch.delenv("PHARMACY_ADMIN_FORCE_PASSWORD_RESET", raising=False)

    db = TestingSessionLocal()
    try:
        admin = models.User(
            email="admin@example.com",
            full_name="Admin",
            hashed_password=utils.hash_password("changed-password-123"),
            is_admin=True,
            role="ADMIN",
        )
        db.add(admin)
        db.commit()

        assert ensure_admin_user(db) is True
        db.refresh(admin)
        assert utils.verify_password("changed-password-123", admin.hashed_password)
        assert not utils.verify_password("render-env-password", admin.hashed_password)
    finally:
        db.close()


def test_demo_import_refuses_user_rows_by_default(client: TestClient, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_IMPORT", "1")
    monkeypatch.setenv("DEMO_IMPORT_ALLOW_USERS", "0")
    app.dependency_overrides[auth_deps.require_admin] = lambda: SimpleNamespace(id=1, is_admin=True)

    res = client.post(
        "/admin/demo-import",
        json={
            "clear_existing": True,
            "tables": {
                "users": [
                    {
                        "id": 1,
                        "email": "replacement@example.com",
                        "full_name": "Replacement",
                        "hashed_password": "not-a-real-hash",
                        "is_admin": True,
                    }
                ]
            },
        },
    )

    assert res.status_code == 400
    assert "Importing users is disabled" in res.json()["detail"]


def test_demo_import_preserves_existing_users_while_refreshing_pharmacy_data(client: TestClient, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_IMPORT", "1")
    monkeypatch.setenv("DEMO_IMPORT_ALLOW_USERS", "0")
    app.dependency_overrides[auth_deps.require_admin] = lambda: SimpleNamespace(id=1, is_admin=True)

    db = TestingSessionLocal()
    try:
        pharmacy = models.Pharmacy(id=1, name="Old Sunrise", domain="sunrise.local", status="APPROVED", is_active=True)
        owner = models.User(
            email="owner@example.com",
            full_name="Owner",
            hashed_password=utils.hash_password("owner-password-123"),
            is_admin=False,
            role="OWNER",
            pharmacy_id=1,
        )
        db.add_all([pharmacy, owner])
        db.commit()
    finally:
        db.close()

    res = client.post(
        "/admin/demo-import",
        json={
            "clear_existing": True,
            "tables": {
                "pharmacies": [
                    {
                        "id": 1,
                        "name": "Sunrise Pharmacy",
                        "domain": "sunrise.local",
                        "status": "APPROVED",
                        "is_active": True,
                    }
                ],
                "medicines": [
                    {
                        "id": 10,
                        "name": "Panadol",
                        "category": "OTC",
                        "price": 5.5,
                        "stock_level": 20,
                        "prescription_required": False,
                        "pharmacy_id": 1,
                    }
                ],
            },
        },
    )

    assert res.status_code == 200
    db = TestingSessionLocal()
    try:
        owner = db.query(models.User).filter(models.User.email == "owner@example.com").one()
        pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == 1).one()
        medicine = db.query(models.Medicine).filter(models.Medicine.name == "Panadol").one()
        assert utils.verify_password("owner-password-123", owner.hashed_password)
        assert owner.pharmacy_id == 1
        assert pharmacy.name == "Sunrise Pharmacy"
        assert medicine.pharmacy_id == 1
    finally:
        db.close()


def test_demo_accounts_create_stable_logins(monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_ACCOUNTS", "1")
    monkeypatch.setenv("DEMO_ACCOUNT_PASSWORD", "12345678")

    db = TestingSessionLocal()
    try:
        assert ensure_demo_accounts(db) is True

        admin = db.query(models.User).filter(models.User.email == "admin@example.com").one()
        sunrise = db.query(models.User).filter(models.User.email == "owner.sunrise@gmail.com").one()
        faysal = db.query(models.User).filter(models.User.email == "owner.faysal@gmail.com").one()

        assert admin.is_admin is True
        assert admin.role == "ADMIN"
        assert admin.pharmacy_id is None
        assert sunrise.pharmacy.name == "Sunrise Pharmacy"
        assert sunrise.pharmacy.domain == "sunrise.localhost"
        assert faysal.pharmacy.name == "Faysal Pharmacy"
        assert faysal.pharmacy.domain == "faysal.localhost"
        assert utils.verify_password("12345678", admin.hashed_password)
        assert utils.verify_password("12345678", sunrise.hashed_password)
        assert utils.verify_password("12345678", faysal.hashed_password)
    finally:
        db.close()


def test_demo_accounts_reset_drifted_demo_password(monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_ACCOUNTS", "1")
    monkeypatch.setenv("DEMO_ACCOUNT_PASSWORD", "12345678")

    db = TestingSessionLocal()
    try:
        pharmacy = models.Pharmacy(name="Sunrise Pharmacy", domain="sunrise.localhost", status="APPROVED", is_active=True)
        owner = models.User(
            email="owner.sunrise@gmail.com",
            full_name="Old Owner",
            hashed_password=utils.hash_password("changed-password-123"),
            is_admin=False,
            role="OWNER",
            pharmacy=pharmacy,
        )
        db.add(owner)
        db.commit()

        assert ensure_demo_accounts(db) is True
        db.refresh(owner)
        assert utils.verify_password("12345678", owner.hashed_password)
        assert owner.full_name == "Sunrise Owner"
        assert owner.pharmacy.name == "Sunrise Pharmacy"
    finally:
        db.close()
