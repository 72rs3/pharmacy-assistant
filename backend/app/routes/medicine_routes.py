import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.auth.deps import require_approved_owner, require_pharmacy_owner
from app.ai import rag_service
from .. import crud, schemas
from ..db import SessionLocal, get_db
from ..deps import get_active_public_pharmacy_id, get_current_pharmacy_id

router = APIRouter(prefix="/medicines", tags=["Medicines"])


def _reindex_medicines(pharmacy_id: int) -> None:
    db = SessionLocal()
    try:
        asyncio.run(rag_service.upsert_medicine_index(db, pharmacy_id))
    finally:
        db.close()


@router.get("/owner", response_model=list[schemas.Medicine])
def list_owner_medicines(
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    return crud.get_medicines(db, pharmacy_id=current_user.pharmacy_id)


@router.post("/owner", response_model=schemas.Medicine)
def create_owner_medicine(
    medicine: schemas.MedicineCreate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(require_approved_owner),
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
    created = crud.create_medicine(db=db, medicine=schemas.MedicineCreate(**data))
    background_tasks.add_task(_reindex_medicines, owner_pharmacy_id)
    return created


@router.post("/owner/bulk-import", response_model=schemas.MedicineBulkImportOut)
def bulk_import_owner_medicines(
    payload: schemas.MedicineBulkImportIn,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    result = crud.bulk_import_medicines(db, payload, pharmacy_id=current_user.pharmacy_id)
    background_tasks.add_task(_reindex_medicines, current_user.pharmacy_id)
    return result


@router.put("/owner/{medicine_id}", response_model=schemas.Medicine)
def update_owner_medicine(
    medicine_id: int,
    updates: schemas.MedicineUpdate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    updated = crud.update_medicine(db, medicine_id, updates, pharmacy_id=current_user.pharmacy_id)
    background_tasks.add_task(_reindex_medicines, current_user.pharmacy_id)
    return updated


@router.post("/owner/{medicine_id}/stock-in", response_model=schemas.Medicine)
def stock_in_owner_medicine(
    medicine_id: int,
    payload: schemas.MedicineStockIn,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    updated = crud.stock_in_medicine(db, medicine_id, payload, pharmacy_id=current_user.pharmacy_id)
    background_tasks.add_task(_reindex_medicines, current_user.pharmacy_id)
    return updated


@router.delete("/owner/{medicine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owner_medicine(
    medicine_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    crud.delete_medicine(db, medicine_id, pharmacy_id=current_user.pharmacy_id)
    background_tasks.add_task(_reindex_medicines, current_user.pharmacy_id)
    return None


@router.post("/", response_model=schemas.Medicine)
def create_medicine(
    medicine: schemas.MedicineCreate,
    background_tasks: BackgroundTasks,
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
    created = crud.create_medicine(db=db, medicine=schemas.MedicineCreate(**data))
    background_tasks.add_task(_reindex_medicines, pharmacy_id)
    return created

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
