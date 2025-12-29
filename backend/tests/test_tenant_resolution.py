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


def test_domain_header_resolves_active_tenant(client: TestClient):
    db = TestingSessionLocal()
    try:
        db.add(
            models.Pharmacy(
                name="Sunrise Pharmacy",
                status="APPROVED",
                is_active=True,
                domain="sunrise.local",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/medicines/", headers={"X-Pharmacy-Domain": "sunrise.local"})
    assert response.status_code == 200
    assert response.json() == []


def test_domain_header_rejects_inactive_or_pending_tenant(client: TestClient):
    db = TestingSessionLocal()
    try:
        db.add(
            models.Pharmacy(
                name="Pending Pharmacy",
                status="PENDING",
                is_active=False,
                domain="pending.local",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/medicines/", headers={"X-Pharmacy-Domain": "pending.local"})
    assert response.status_code == 404
