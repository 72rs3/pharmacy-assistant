from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.auth.deps import require_owner, require_pharmacy_owner
from .. import crud, schemas
from ..db import get_db
from ..deps import get_active_public_pharmacy_id, get_current_pharmacy_id

router = APIRouter(prefix="/medicines", tags=["Medicines"])


@router.get("/owner", response_model=list[schemas.Medicine])
def list_owner_medicines(
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return crud.get_medicines(db, pharmacy_id=current_user.pharmacy_id)


@router.post("/owner", response_model=schemas.Medicine)
def create_owner_medicine(
    medicine: schemas.MedicineCreate,
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    owner_pharmacy_id = current_user.pharmacy_id
    if medicine.pharmacy_id is not None and medicine.pharmacy_id != owner_pharmacy_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pharmacy_id mismatch with logged-in owner",
        )

    data = medicine.dict()
    data["pharmacy_id"] = owner_pharmacy_id
    return crud.create_medicine(db=db, medicine=schemas.MedicineCreate(**data))


@router.post("/", response_model=schemas.Medicine)
def create_medicine(
    medicine: schemas.MedicineCreate,
    pharmacy_id: int = Depends(get_current_pharmacy_id),
    _=Depends(require_pharmacy_owner),
    db: Session = Depends(get_db),
):
    if medicine.pharmacy_id is not None and medicine.pharmacy_id != pharmacy_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pharmacy_id mismatch with X-Pharmacy-ID header",
        )

    data = medicine.dict()
    data["pharmacy_id"] = pharmacy_id
    return crud.create_medicine(db=db, medicine=schemas.MedicineCreate(**data))

@router.get("/", response_model=list[schemas.Medicine])
def list_medicines(
    pharmacy_id: int | None = None,
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    db: Session = Depends(get_db),
):
    if pharmacy_id is not None and pharmacy_id != tenant_pharmacy_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pharmacy_id mismatch with resolved tenant",
        )
    return crud.get_medicines(db, pharmacy_id=tenant_pharmacy_id)
