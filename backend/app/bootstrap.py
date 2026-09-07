import os
import secrets
from urllib.parse import urlparse

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.auth.utils import hash_password
from app.db import SessionLocal


def _normalize_domain(value: str) -> str:
    domain = value.strip().lower()
    domain = domain.split(",")[0].strip()
    domain = domain.split(":")[0].strip()
    return domain


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def ensure_default_pharmacy(db: Session | None = None) -> bool:
    """
    Optional one-time bootstrap for a default public tenant pharmacy.

    Useful for single-host deployments (e.g. Render) where the storefront hostname
    should resolve to an approved pharmacy record.

    Env vars:
      - DEFAULT_PHARMACY_DOMAIN (required)
      - DEFAULT_PHARMACY_NAME (optional; default: "Pharmacy")
      - DEFAULT_PHARMACY_AUTO_APPROVE (optional; default: false)
    """

    domain_raw = os.getenv("DEFAULT_PHARMACY_DOMAIN")
    if not domain_raw and os.getenv("FRONTEND_DIST_DIR"):
        domain_raw = urlparse(os.getenv("APP_PUBLIC_BASE_URL", "")).netloc
    if not domain_raw:
        return False

    normalized_domain = _normalize_domain(domain_raw)
    if not normalized_domain:
        return False

    name = (os.getenv("DEFAULT_PHARMACY_NAME") or "Sunr Pharmacy").strip() or "Sunr Pharmacy"
    auto_approve = _env_flag("DEFAULT_PHARMACY_AUTO_APPROVE", default=bool(os.getenv("FRONTEND_DIST_DIR")))

    owns_session = db is None
    session = db or SessionLocal()
    try:
        existing = session.query(models.Pharmacy).filter(models.Pharmacy.domain == normalized_domain).first()
        if existing:
            changed = False
            if existing.name != name and not session.query(models.Pharmacy).filter(models.Pharmacy.name == name).first():
                existing.name = name
                changed = True
            if auto_approve and (existing.status != "APPROVED" or not existing.is_active):
                existing.status = "APPROVED"
                existing.is_active = True
                changed = True
            if changed:
                session.commit()
            return changed

        final_name = name
        if session.query(models.Pharmacy).filter(models.Pharmacy.name == final_name).first():
            final_name = f"{name}-{secrets.token_hex(3)}"

        pharmacy = models.Pharmacy(
            name=final_name,
            domain=normalized_domain,
            status="APPROVED" if auto_approve else "PENDING",
            is_active=bool(auto_approve),
            support_cod=True,
        )
        session.add(pharmacy)
        session.commit()
        return True
    finally:
        if owns_session:
            session.close()


def _demo_password() -> str:
    return os.getenv("DEMO_ACCOUNT_PASSWORD") or "12345678"


def _ensure_pharmacy(session: Session, *, name: str, domain: str) -> models.Pharmacy:
    normalized_domain = _normalize_domain(domain)
    pharmacy = (
        session.query(models.Pharmacy)
        .filter(or_(models.Pharmacy.domain == normalized_domain, models.Pharmacy.name == name))
        .order_by(models.Pharmacy.id.asc())
        .first()
    )
    if pharmacy is None:
        pharmacy = models.Pharmacy(
            name=name,
            domain=normalized_domain,
            status="APPROVED",
            is_active=True,
            support_cod=True,
        )
        session.add(pharmacy)
        session.flush()
        return pharmacy

    pharmacy.name = name
    pharmacy.domain = normalized_domain
    pharmacy.status = "APPROVED"
    pharmacy.is_active = True
    pharmacy.support_cod = True
    return pharmacy


def _ensure_demo_user(
    session: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    role: str,
    is_admin: bool,
    pharmacy_id: int | None,
) -> models.User:
    normalized_email = email.strip().lower()
    user = session.query(models.User).filter(models.User.email == normalized_email).first()
    if user is None:
        user = models.User(email=normalized_email)
        session.add(user)

    user.full_name = full_name
    user.hashed_password = hash_password(password)
    user.is_admin = is_admin
    user.role = role
    user.pharmacy_id = pharmacy_id
    return user


def ensure_demo_accounts(db: Session | None = None) -> bool:
    """
    Stable demo login bootstrap for public portfolio/test deployments.

    Enabled only with ENABLE_DEMO_ACCOUNTS=1. These accounts intentionally reset
    to DEMO_ACCOUNT_PASSWORD on startup so testers always use the same login.
    """

    if not _env_flag("ENABLE_DEMO_ACCOUNTS", default=False):
        return False

    password = _demo_password()
    admin_email = os.getenv("DEMO_ADMIN_EMAIL") or os.getenv("PHARMACY_ADMIN_EMAIL") or "admin@example.com"
    accounts = [
        {
            "pharmacy_name": "Sunrise Pharmacy",
            "pharmacy_domain": os.getenv("DEMO_SUNRISE_DOMAIN") or "sunrise.localhost",
            "owner_email": os.getenv("DEMO_SUNRISE_OWNER_EMAIL") or "owner.sunrise@gmail.com",
            "owner_name": "Sunrise Owner",
        },
        {
            "pharmacy_name": "Faysal Pharmacy",
            "pharmacy_domain": os.getenv("DEMO_FAYSAL_DOMAIN") or "faysal.localhost",
            "owner_email": os.getenv("DEMO_FAYSAL_OWNER_EMAIL") or "owner.faysal@gmail.com",
            "owner_name": "Faysal Owner",
        },
    ]

    owns_session = db is None
    session = db or SessionLocal()
    try:
        _ensure_demo_user(
            session,
            email=admin_email,
            full_name="Demo Admin",
            password=password,
            role="ADMIN",
            is_admin=True,
            pharmacy_id=None,
        )
        for account in accounts:
            pharmacy = _ensure_pharmacy(
                session,
                name=account["pharmacy_name"],
                domain=account["pharmacy_domain"],
            )
            _ensure_demo_user(
                session,
                email=account["owner_email"],
                full_name=account["owner_name"],
                password=password,
                role="OWNER",
                is_admin=False,
                pharmacy_id=pharmacy.id,
            )
        session.commit()
        return True
    finally:
        if owns_session:
            session.close()
