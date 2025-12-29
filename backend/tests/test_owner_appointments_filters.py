import sys
from datetime import datetime, timedelta
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
    app.dependency_overrides[auth_deps.require_approved_owner] = lambda: SimpleNamespace(pharmacy_id=1, is_admin=False)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def seed_appointments():
    db = TestingSessionLocal()
    pharmacy = models.Pharmacy(name="Test Pharmacy", status="APPROVED", is_active=True)
    db.add(pharmacy)
    db.commit()
    db.refresh(pharmacy)

    now = datetime.utcnow()
    appt_pending_old = models.Appointment(
        customer_id="c1",
        customer_name="Fares",
        customer_phone="+96179111111",
        type="Consultation",
        scheduled_time=now + timedelta(days=7),
        status="PENDING",
        pharmacy_id=pharmacy.id,
        created_at=now - timedelta(hours=2),
    )
    appt_pending_new = models.Appointment(
        customer_id="c2",
        customer_name="Ali",
        customer_phone="+96179222222",
        type="Vaccination",
        scheduled_time=now + timedelta(days=10),
        status="PENDING",
        pharmacy_id=pharmacy.id,
        created_at=now - timedelta(minutes=15),
    )
    appt_confirmed = models.Appointment(
        customer_id="c3",
        customer_name="Sara",
        customer_phone="+96179333333",
        type="Consultation",
        scheduled_time=now + timedelta(days=1),
        status="CONFIRMED",
        pharmacy_id=pharmacy.id,
        created_at=now - timedelta(days=1),
    )
    db.add_all([appt_pending_old, appt_pending_new, appt_confirmed])
    db.commit()
    db.refresh(appt_pending_old)
    db.refresh(appt_pending_new)
    db.refresh(appt_confirmed)
    db.close()
    return appt_pending_old.id, appt_pending_new.id, appt_confirmed.id


def test_owner_queue_sort_orders_pending_newest_first(client: TestClient):
    pending_old_id, pending_new_id, confirmed_id = seed_appointments()
    res = client.get("/appointments/owner")
    assert res.status_code == 200
    assert res.headers.get("x-total-count") == "3"
    ids = [item["id"] for item in res.json()]
    assert ids[:3] == [pending_new_id, pending_old_id, confirmed_id]


def test_owner_filters_by_status_and_search(client: TestClient):
    pending_old_id, pending_new_id, _ = seed_appointments()

    res_pending = client.get("/appointments/owner", params={"status": "PENDING"})
    assert res_pending.status_code == 200
    ids_pending = [item["id"] for item in res_pending.json()]
    assert set(ids_pending) == {pending_old_id, pending_new_id}

    res_search = client.get("/appointments/owner", params={"q": "+961791"})
    assert res_search.status_code == 200
    ids_search = [item["id"] for item in res_search.json()]
    assert ids_search == [pending_old_id]
