from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from . import models, schemas


def _ensure_pharmacy_exists(db: Session, pharmacy_id: int) -> None:
    exists = db.query(models.Pharmacy.id).filter(models.Pharmacy.id == pharmacy_id).first()
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pharmacy_id",
        )


# Pharmacy CRUD
def create_pharmacy(db: Session, pharmacy: schemas.PharmacyCreate):
    data = pharmacy.dict()
    data["status"] = "PENDING"
    data["is_active"] = False
    db_pharmacy = models.Pharmacy(**data)
    db.add(db_pharmacy)
    db.commit()
    db.refresh(db_pharmacy)
    return db_pharmacy


def get_pharmacies(db: Session, active_only: bool = False, status: str | None = None):
    query = db.query(models.Pharmacy)
    if active_only:
        query = query.filter(
            models.Pharmacy.is_active.is_(True),
            models.Pharmacy.status == "APPROVED",
        )
    if status:
        query = query.filter(models.Pharmacy.status == status)
    return query.all()


def approve_pharmacy(db: Session, pharmacy_id: int):
    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not pharmacy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pharmacy not found",
        )
    pharmacy.status = "APPROVED"
    pharmacy.is_active = True
    db.commit()
    db.refresh(pharmacy)
    return pharmacy


# Medicine CRUD
def create_medicine(db: Session, medicine: schemas.MedicineCreate):
    _ensure_pharmacy_exists(db, medicine.pharmacy_id)
    db_medicine = models.Medicine(**medicine.dict())
    db.add(db_medicine)
    db.commit()
    db.refresh(db_medicine)
    return db_medicine


def get_medicines(db: Session, pharmacy_id: int | None = None):
    query = db.query(models.Medicine)
    if pharmacy_id is not None:
        query = query.filter(models.Medicine.pharmacy_id == pharmacy_id)
    return query.all()
