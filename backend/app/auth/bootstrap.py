import os

from sqlalchemy.orm import Session

from app import models
from app.auth.utils import hash_password
from app.db import SessionLocal


def ensure_admin_user(db: Session | None = None) -> bool:
    """
    One-time bootstrap for an initial admin user.

    Set either:
      - PHARMACY_ADMIN_EMAIL / PHARMACY_ADMIN_PASSWORD (preferred), or
      - ADMIN_EMAIL / ADMIN_PASSWORD
    """

    email = os.getenv("PHARMACY_ADMIN_EMAIL") or os.getenv("ADMIN_EMAIL")
    password = os.getenv("PHARMACY_ADMIN_PASSWORD") or os.getenv("ADMIN_PASSWORD")
    full_name = os.getenv("PHARMACY_ADMIN_FULL_NAME") or "Admin"

    if not email or not password:
        return False

    owns_session = db is None
    session = db or SessionLocal()
    try:
        existing_admin = (
            session.query(models.User).filter(models.User.is_admin.is_(True)).first()
        )
        if existing_admin:
            return False

        existing_user = session.query(models.User).filter(models.User.email == email).first()
        if existing_user:
            existing_user.is_admin = True
            existing_user.pharmacy_id = None
            existing_user.role = "ADMIN"
            existing_user.full_name = existing_user.full_name or full_name
            existing_user.hashed_password = hash_password(password)
            session.commit()
            return True

        user = models.User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_admin=True,
            pharmacy_id=None,
            role="ADMIN",
        )
        session.add(user)
        session.commit()
        return True
    finally:
        if owns_session:
            session.close()
