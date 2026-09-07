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


def _find_existing_pharmacy(
    session: Session,
    *,
    name: str,
    domain: str,
    fallback_domain: str | None = None,
) -> models.Pharmacy | None:
    normalized_domain = _normalize_domain(domain)
    normalized_fallback = _normalize_domain(fallback_domain) if fallback_domain else ""
    pharmacy = (
        session.query(models.Pharmacy)
        .filter(
            or_(
                models.Pharmacy.domain == normalized_domain,
                models.Pharmacy.name == name,
                models.Pharmacy.domain == normalized_fallback,
            )
        )
        .order_by(models.Pharmacy.id.asc())
        .first()
    )
    if pharmacy is not None:
        return pharmacy

    slug = normalized_domain.split(".", 1)[0]
    if slug:
        return (
            session.query(models.Pharmacy)
            .filter(
                or_(
                    models.Pharmacy.domain == slug,
                    models.Pharmacy.domain.like(f"{slug}.%"),
                    models.Pharmacy.name.ilike(f"%{slug}%"),
                )
            )
            .order_by(models.Pharmacy.id.asc())
            .first()
        )
    return None


def _ensure_pharmacy(
    session: Session,
    *,
    name: str,
    domain: str,
    fallback_domain: str | None = None,
) -> models.Pharmacy:
    normalized_domain = _normalize_domain(domain)
    pharmacy = _find_existing_pharmacy(session, name=name, domain=normalized_domain, fallback_domain=fallback_domain)
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

    name_owner = (
        session.query(models.Pharmacy)
        .filter(models.Pharmacy.name == name, models.Pharmacy.id != pharmacy.id)
        .first()
    )
    if name_owner is None:
        pharmacy.name = name
    if not pharmacy.domain:
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


DEMO_MEDICINES = [
    {
        "name": "Panadol",
        "category": "Pain Relief",
        "price": 5.50,
        "stock_level": 48,
        "prescription_required": False,
        "dosage": "500 mg tablet",
        "side_effects": "Follow the label. Ask a pharmacist if symptoms persist or you are unsure.",
    },
    {
        "name": "Ibuprofen",
        "category": "Pain Relief",
        "price": 4.75,
        "stock_level": 35,
        "prescription_required": False,
        "dosage": "200 mg tablet",
        "side_effects": "Avoid if you have a stomach ulcer, severe kidney disease, or NSAID allergy unless advised.",
    },
    {
        "name": "Cetirizine",
        "category": "Allergy",
        "price": 6.25,
        "stock_level": 28,
        "prescription_required": False,
        "dosage": "10 mg tablet",
        "side_effects": "May cause drowsiness in some people.",
    },
    {
        "name": "Oral Rehydration Salts",
        "category": "Digestive Health",
        "price": 3.00,
        "stock_level": 40,
        "prescription_required": False,
        "dosage": "1 sachet mixed with clean water",
        "side_effects": "Use as directed on the packet.",
    },
    {
        "name": "Promethazine",
        "category": "Prescription",
        "price": 8.75,
        "stock_level": 12,
        "prescription_required": True,
        "dosage": "25 mg hydrochloride tablet",
        "side_effects": "Prescription required. May cause drowsiness; avoid driving unless advised.",
    },
    {
        "name": "Amoxicillin",
        "category": "Antibiotic",
        "price": 11.00,
        "stock_level": 18,
        "prescription_required": True,
        "dosage": "500 mg capsule",
        "side_effects": "Prescription required. Complete the course exactly as prescribed.",
    },
]


DEMO_PRODUCTS = [
    {
        "name": "Digital Thermometer",
        "category": "Health Devices",
        "price": 12.00,
        "stock_level": 15,
        "description": "Fast digital thermometer for home fever checks.",
        "image_url": None,
    },
    {
        "name": "Vitamin C 1000mg",
        "category": "Vitamins",
        "price": 9.50,
        "stock_level": 30,
        "description": "Daily vitamin C supplement.",
        "image_url": None,
    },
    {
        "name": "Hand Sanitizer",
        "category": "Personal Care",
        "price": 2.25,
        "stock_level": 60,
        "description": "Pocket-size antibacterial hand sanitizer.",
        "image_url": None,
    },
    {
        "name": "Blood Pressure Monitor",
        "category": "Health Devices",
        "price": 45.00,
        "stock_level": 6,
        "description": "Automatic upper-arm blood pressure monitor.",
        "image_url": None,
    },
]


def _ensure_demo_catalog(session: Session, pharmacy: models.Pharmacy) -> bool:
    if not _env_flag("ENABLE_DEMO_CATALOG", default=_env_flag("ENABLE_DEMO_ACCOUNTS", default=False)):
        return False

    changed = False
    medicine_count = session.query(models.Medicine).filter(models.Medicine.pharmacy_id == pharmacy.id).count()
    if medicine_count == 0:
        session.add_all(
            models.Medicine(pharmacy_id=pharmacy.id, **item)
            for item in DEMO_MEDICINES
        )
        changed = True

    product_count = session.query(models.Product).filter(models.Product.pharmacy_id == pharmacy.id).count()
    if product_count == 0:
        session.add_all(
            models.Product(pharmacy_id=pharmacy.id, **item)
            for item in DEMO_PRODUCTS
        )
        changed = True

    return changed


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
    default_domain = os.getenv("DEFAULT_PHARMACY_DOMAIN")
    accounts = [
        {
            "pharmacy_name": "Sunrise Pharmacy",
            "pharmacy_domain": os.getenv("DEMO_SUNRISE_DOMAIN") or "sunrise.localhost",
            "fallback_domain": os.getenv("DEMO_SUNRISE_FALLBACK_DOMAIN") or default_domain,
            "owner_email": os.getenv("DEMO_SUNRISE_OWNER_EMAIL") or "owner.sunrise@gmail.com",
            "owner_name": "Sunrise Owner",
        },
        {
            "pharmacy_name": "Faysal Pharmacy",
            "pharmacy_domain": os.getenv("DEMO_FAYSAL_DOMAIN") or "faysal.localhost",
            "fallback_domain": os.getenv("DEMO_FAYSAL_FALLBACK_DOMAIN"),
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
                fallback_domain=account["fallback_domain"],
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
            _ensure_demo_catalog(session, pharmacy)
        session.commit()
        return True
    finally:
        if owns_session:
            session.close()
