from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.db import get_db


def _normalize_domain(value: str) -> str:
    domain = value.strip().lower()
    domain = domain.split(",")[0].strip()
    domain = domain.split(":")[0].strip()
    return domain


def get_current_pharmacy(
    request: Request,
    db: Session = Depends(get_db),
    pharmacy_id: int | None = Header(None, alias="X-Pharmacy-ID"),
    pharmacy_domain: str | None = Header(None, alias="X-Pharmacy-Domain"),
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

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Provide X-Pharmacy-ID, or set pharmacy.domain and send X-Pharmacy-Domain",
    )


def get_current_pharmacy_id(pharmacy: models.Pharmacy = Depends(get_current_pharmacy)) -> int:
    return pharmacy.id


def get_active_pharmacy(pharmacy: models.Pharmacy = Depends(get_current_pharmacy)) -> models.Pharmacy:
    if not pharmacy.is_active or pharmacy.status != "APPROVED":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pharmacy not found")
    return pharmacy


def get_active_pharmacy_id(pharmacy: models.Pharmacy = Depends(get_active_pharmacy)) -> int:
    return pharmacy.id
