import os
import secrets

from sqlalchemy.orm import Session

from app import models
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
    if not domain_raw:
        return False

    normalized_domain = _normalize_domain(domain_raw)
    if not normalized_domain:
        return False

    name = (os.getenv("DEFAULT_PHARMACY_NAME") or "Pharmacy").strip() or "Pharmacy"
    auto_approve = _env_flag("DEFAULT_PHARMACY_AUTO_APPROVE", default=False)

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

