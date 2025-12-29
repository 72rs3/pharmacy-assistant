from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import crud, schemas
from ..db import get_db
from ..deps import get_current_pharmacy_id

router = APIRouter(prefix="/medicines", tags=["Medicines"])

@router.post("/", response_model=schemas.Medicine)
def create_medicine(
    medicine: schemas.MedicineCreate,
    pharmacy_id: int = Depends(get_current_pharmacy_id),
    db: Session = Depends(get_db),
):
    if medicine.pharmacy_id != pharmacy_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pharmacy_id mismatch with X-Pharmacy-ID header",
        )
    return crud.create_medicine(db=db, medicine=medicine)

@router.get("/", response_model=list[schemas.Medicine])
def list_medicines(
    pharmacy_id: int | None = None,
    db: Session = Depends(get_db),
):
    if pharmacy_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pharmacy_id query parameter is required",
        )
    return crud.get_medicines(db, pharmacy_id=pharmacy_id)
