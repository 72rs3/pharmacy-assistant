from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require_admin
from .. import crud, schemas
from ..db import get_db

router = APIRouter(prefix="/pharmacies", tags=["Pharmacies"])

@router.post("/", response_model=schemas.Pharmacy)
def create_pharmacy(pharmacy: schemas.PharmacyCreate, db: Session = Depends(get_db)):
    return crud.create_pharmacy(db=db, pharmacy=pharmacy)

@router.get("/", response_model=list[schemas.Pharmacy])
def list_pharmacies(db: Session = Depends(get_db)):
    return crud.get_pharmacies(db, active_only=True)


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
