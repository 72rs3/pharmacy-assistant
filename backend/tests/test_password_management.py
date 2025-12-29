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


def test_user_can_change_password(client: TestClient):
    register_payload = {
        "email": "owner@example.com",
        "password": "example-password",
        "full_name": "Owner One",
        "pharmacy_name": "Sunrise Pharmacy",
        "pharmacy_domain": "sunrise.local",
    }
    resp = client.post("/auth/register-owner", json=register_payload)
    assert resp.status_code == 200

    login = client.post("/auth/login", json={"email": "owner@example.com", "password": "example-password"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    change = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "example-password", "new_password": "new-password-123"},
    )
    assert change.status_code == 200
    assert change.json()["ok"] is True

    relogin = client.post("/auth/login", json={"email": "owner@example.com", "password": "new-password-123"})
    assert relogin.status_code == 200


def test_admin_can_reset_password(client: TestClient):
    db = TestingSessionLocal()
    try:
        db.add(models.Pharmacy(name="P1", domain="p1.local", status="APPROVED", is_active=True))
        db.commit()
        pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.name == "P1").first()

        owner = models.User(
            email="owner2@example.com",
            full_name="Owner Two",
            hashed_password=utils.hash_password("old-password-123"),
            is_admin=False,
            pharmacy_id=pharmacy.id,
        )
        admin = models.User(
            email="admin@example.com",
            full_name="Admin",
            hashed_password=utils.hash_password("admin-password-123"),
            is_admin=True,
            pharmacy_id=None,
            role="ADMIN",
        )
        db.add_all([owner, admin])
        db.commit()
    finally:
        db.close()

    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "admin-password-123"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    reset = client.post(
        "/auth/admin/reset-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "owner2@example.com", "new_password": "reset-password-123"},
    )
    assert reset.status_code == 200
    assert reset.json()["ok"] is True

    relogin = client.post("/auth/login", json={"email": "owner2@example.com", "password": "reset-password-123"})
    assert relogin.status_code == 200

