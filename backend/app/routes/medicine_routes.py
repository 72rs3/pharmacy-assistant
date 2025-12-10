from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import crud, schemas
from ..db import get_db

router = APIRouter(prefix="/medicines", tags=["Medicines"])

@router.post("/", response_model=schemas.Medicine)
def create_medicine(medicine: schemas.MedicineCreate, db: Session = Depends(get_db)):
    return crud.create_medicine(db=db, medicine=medicine)

@router.get("/", response_model=list[schemas.Medicine])
def list_medicines(db: Session = Depends(get_db)):
    return crud.get_medicines(db)
