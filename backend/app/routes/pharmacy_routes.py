import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.auth.deps import require_admin, require_owner
from app.deps import get_active_public_pharmacy
from app.ai import rag_service
from .. import crud, schemas
from ..db import get_db

router = APIRouter(prefix="/pharmacies", tags=["Pharmacies"])


_HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")
_THEME_PRESETS = {"classic", "fresh", "minimal"}
_LAYOUT_PRESETS = {"classic", "breeze", "studio", "market"}


def _normalize_hex(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if not _HEX_COLOR_RE.match(raw):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid color (expected hex like #7CB342)",
        )
    return raw if raw.startswith("#") else f"#{raw}"

@router.post("/", response_model=schemas.Pharmacy)
def create_pharmacy(
    pharmacy: schemas.PharmacyCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return crud.create_pharmacy(db=db, pharmacy=pharmacy)

@router.get("/", response_model=list[schemas.Pharmacy])
def list_pharmacies(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return crud.get_pharmacies(db, active_only=True)

@router.get("/me", response_model=schemas.Pharmacy)
def my_pharmacy(
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    pharmacy = (
        db.query(models.Pharmacy)
        .filter(models.Pharmacy.id == current_user.pharmacy_id)
        .first()
    )
    if not pharmacy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pharmacy not found")
    return pharmacy


@router.patch("/me", response_model=schemas.Pharmacy)
def update_my_pharmacy(
    payload: schemas.PharmacyUpdate,
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    pharmacy = (
        db.query(models.Pharmacy)
        .filter(models.Pharmacy.id == current_user.pharmacy_id)
        .first()
    )
    if not pharmacy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pharmacy not found")

    data = payload.model_dump(exclude_unset=True)

    for key in ("primary_color", "primary_color_600", "accent_color"):
        if key in data:
            data[key] = _normalize_hex(data[key])

    for key, value in list(data.items()):
        if isinstance(value, str) and not value.strip():
            data[key] = None

    if "theme_preset" in data and data["theme_preset"] is not None:
        preset = str(data["theme_preset"]).strip().lower()
        if preset not in _THEME_PRESETS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid theme preset",
            )
        data["theme_preset"] = preset

    if "storefront_layout" in data and data["storefront_layout"] is not None:
        layout = str(data["storefront_layout"]).strip().lower()
        if layout not in _LAYOUT_PRESETS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid storefront layout",
            )
        data["storefront_layout"] = layout

    for key, value in data.items():
        setattr(pharmacy, key, value)

    db.commit()
    db.refresh(pharmacy)
    return pharmacy


@router.get("/current", response_model=schemas.Pharmacy)
def get_current_public_pharmacy(
    pharmacy: models.Pharmacy = Depends(get_active_public_pharmacy),
):
    return pharmacy


@router.get("/admin", response_model=list[schemas.Pharmacy])
def list_all_pharmacies(
    status: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return crud.get_pharmacies(db, active_only=False, status=status)


@router.post("/{pharmacy_id}/approve", response_model=schemas.Pharmacy)
def approve_pharmacy(
    pharmacy_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    pharmacy = crud.approve_pharmacy(db, pharmacy_id=pharmacy_id)
    rag_service.ensure_pharmacy_playbook(db, pharmacy.id)
    db.commit()
    db.refresh(pharmacy)
    return pharmacy
