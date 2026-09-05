from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.db import get_db


def _normalize_domain(value: str) -> str:
    domain = value.strip().lower()
    domain = domain.split(",")[0].strip()
    domain = domain.split(":")[0].strip()
    return domain


def _normalize_slug(value: str) -> str:
    return value.strip().lower().strip("/").split("/")[0].strip()


def _find_pharmacy_by_slug(db: Session, slug: str) -> models.Pharmacy | None:
    normalized = _normalize_slug(slug)
    if not normalized:
        return None
    matches = (
        db.query(models.Pharmacy)
        .filter(
            or_(
                models.Pharmacy.domain == normalized,
                models.Pharmacy.domain.like(f"{normalized}.%"),
            )
        )
        .order_by(models.Pharmacy.id.asc())
        .all()
    )
    if not matches:
        return None
    exact = next((pharmacy for pharmacy in matches if (pharmacy.domain or "").strip().lower() == normalized), None)
    if exact is not None:
        return exact
    unique_prefix_matches = [pharmacy for pharmacy in matches if (pharmacy.domain or "").split(".")[0].strip().lower() == normalized]
    if len(unique_prefix_matches) == 1:
        return unique_prefix_matches[0]
    if len(unique_prefix_matches) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Multiple pharmacies match this tenant slug",
        )
    return matches[0]


def get_current_pharmacy(
    request: Request,
    db: Session = Depends(get_db),
    pharmacy_id: int | None = Header(None, alias="X-Pharmacy-ID"),
    pharmacy_domain: str | None = Header(None, alias="X-Pharmacy-Domain"),
    pharmacy_slug: str | None = Header(None, alias="X-Pharmacy-Slug"),
    forwarded_host: str | None = Header(None, alias="X-Forwarded-Host"),
) -> models.Pharmacy:
    if pharmacy_id is not None:
        pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
        if pharmacy is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid pharmacy_id",
            )
        return pharmacy

    domain = pharmacy_domain or forwarded_host or request.headers.get("host")
    if domain:
        normalized = _normalize_domain(domain)
        pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.domain == normalized).first()
        if pharmacy is not None:
            return pharmacy

    if pharmacy_slug:
        pharmacy = _find_pharmacy_by_slug(db, pharmacy_slug)
        if pharmacy is not None:
            return pharmacy

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Provide X-Pharmacy-ID, or set pharmacy.domain and send X-Pharmacy-Domain/X-Pharmacy-Slug",
    )


def get_current_pharmacy_id(pharmacy: models.Pharmacy = Depends(get_current_pharmacy)) -> int:
    return pharmacy.id


def get_active_pharmacy(pharmacy: models.Pharmacy = Depends(get_current_pharmacy)) -> models.Pharmacy:
    if not pharmacy.is_active or pharmacy.status != "APPROVED":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pharmacy not found")
    return pharmacy


def get_active_pharmacy_id(pharmacy: models.Pharmacy = Depends(get_active_pharmacy)) -> int:
    return pharmacy.id


def get_public_pharmacy(
    request: Request,
    db: Session = Depends(get_db),
    pharmacy_domain: str | None = Header(None, alias="X-Pharmacy-Domain"),
    pharmacy_slug: str | None = Header(None, alias="X-Pharmacy-Slug"),
    forwarded_host: str | None = Header(None, alias="X-Forwarded-Host"),
) -> models.Pharmacy:
    """
    Public tenant resolver for customer-facing endpoints.

    Security rule: do NOT accept X-Pharmacy-ID here (prevents tenant discovery by ID guessing).
    """

    domain = pharmacy_domain or forwarded_host or request.headers.get("host")
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pharmacy not found")

    if pharmacy_slug:
        pharmacy = _find_pharmacy_by_slug(db, pharmacy_slug)
        if pharmacy is not None:
            return pharmacy

    normalized = _normalize_domain(domain)
    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.domain == normalized).first()
    if pharmacy is not None:
        return pharmacy
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pharmacy not found")


def get_active_public_pharmacy(
    pharmacy: models.Pharmacy = Depends(get_public_pharmacy),
) -> models.Pharmacy:
    if not pharmacy.is_active or pharmacy.status != "APPROVED":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pharmacy not found")
    return pharmacy


def get_active_public_pharmacy_id(
    pharmacy: models.Pharmacy = Depends(get_active_public_pharmacy),
) -> int:
    return pharmacy.id
