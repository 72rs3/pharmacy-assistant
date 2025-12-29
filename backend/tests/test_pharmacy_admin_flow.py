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

from app.auth import deps as auth_deps
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
    app.dependency_overrides[auth_deps.require_admin] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_admin_can_approve_pending_pharmacy(client: TestClient):
    register_payload = {
        "email": "owner@example.com",
        "password": "example-password",
        "full_name": "Owner One",
        "pharmacy_name": "Sunrise Pharmacy",
        "pharmacy_domain": "sunrise.local",
    }
    register_response = client.post("/auth/register-owner", json=register_payload)
    assert register_response.status_code == 200

    login_response = client.post(
        "/auth/login",
        json={"email": register_payload["email"], "password": register_payload["password"]},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {token}"}

    # Owner can read their pharmacy settings, but cannot use the owner dashboard until approved.
    my_pharmacy_before = client.get("/pharmacies/me", headers=owner_headers)
    assert my_pharmacy_before.status_code == 200
    assert my_pharmacy_before.json()["status"] == "PENDING"
    assert my_pharmacy_before.json()["is_active"] is False

    owner_products_before = client.get("/products/owner", headers=owner_headers)
    assert owner_products_before.status_code == 403

    # Public tenant resolution should reject pending/inactive pharmacies
    public_before = client.get("/pharmacies/current", headers={"X-Pharmacy-Domain": "sunrise.local"})
    assert public_before.status_code == 404

    # Admin view sees the pending pharmacy
    admin_list = client.get("/pharmacies/admin")
    assert admin_list.status_code == 200
    pharmacies = admin_list.json()
    assert len(pharmacies) == 1
    assert pharmacies[0]["status"] == "PENDING"
    assert pharmacies[0]["is_active"] is False
    pharmacy_id = pharmacies[0]["id"]

    # Admin approves the pharmacy
    approve_response = client.post(f"/pharmacies/{pharmacy_id}/approve")
    assert approve_response.status_code == 200
    approved = approve_response.json()
    assert approved["status"] == "APPROVED"
    assert approved["is_active"] is True

    # Owner dashboard APIs unlock after approval.
    owner_products_after = client.get("/products/owner", headers=owner_headers)
    assert owner_products_after.status_code == 200

    # After approval the public tenant endpoint resolves successfully
    public_after = client.get("/pharmacies/current", headers={"X-Pharmacy-Domain": "sunrise.local"})
    assert public_after.status_code == 200
    assert public_after.json()["id"] == pharmacy_id
