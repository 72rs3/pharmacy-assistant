from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.auth.deps import require_admin, require_owner
from app.deps import get_active_public_pharmacy
from .. import crud, schemas
from ..db import get_db

router = APIRouter(prefix="/pharmacies", tags=["Pharmacies"])

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
    return crud.approve_pharmacy(db, pharmacy_id=pharmacy_id)
