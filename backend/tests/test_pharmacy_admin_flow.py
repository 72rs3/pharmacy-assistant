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
    }
    register_response = client.post("/auth/register", json=register_payload)
    assert register_response.status_code == 200

    # Public listing should not expose pending/inactive pharmacies
    public_list = client.get("/pharmacies")
    assert public_list.status_code == 200
    assert public_list.json() == []

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

    # After approval the pharmacy appears in the public list
    post_approval_list = client.get("/pharmacies")
    assert post_approval_list.status_code == 200
    visible = post_approval_list.json()
    assert len(visible) == 1
    assert visible[0]["id"] == pharmacy_id
