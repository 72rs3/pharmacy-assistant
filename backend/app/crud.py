from sqlalchemy.orm import Session
from . import models, schemas

# Pharmacy CRUD
def create_pharmacy(db: Session, pharmacy: schemas.PharmacyCreate):
    db_pharmacy = models.Pharmacy(**pharmacy.dict())
    db.add(db_pharmacy)
    db.commit()
    db.refresh(db_pharmacy)
    return db_pharmacy

def get_pharmacies(db: Session):
    return db.query(models.Pharmacy).all()


# Medicine CRUD
def create_medicine(db: Session, medicine: schemas.MedicineCreate):
    db_medicine = models.Medicine(**medicine.dict())
    db.add(db_medicine)
    db.commit()
    db.refresh(db_medicine)
    return db_medicine

def get_medicines(db: Session):
    return db.query(models.Medicine).all()
