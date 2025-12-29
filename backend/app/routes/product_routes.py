from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth.deps import require_approved_owner
from app.db import get_db
from app.deps import get_active_public_pharmacy_id

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=list[schemas.Product])
def list_products(
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Product)
        .filter(models.Product.pharmacy_id == tenant_pharmacy_id)
        .order_by(models.Product.name.asc())
        .all()
    )


@router.get("/owner", response_model=list[schemas.Product])
def list_owner_products(
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Product)
        .filter(models.Product.pharmacy_id == current_user.pharmacy_id)
        .order_by(models.Product.name.asc())
        .all()
    )


@router.post("/owner", response_model=schemas.Product)
def create_owner_product(
    payload: schemas.ProductCreate,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    data = payload.model_dump()
    data["pharmacy_id"] = current_user.pharmacy_id
    product = models.Product(**data)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.post("/owner/bulk-import", response_model=schemas.ProductBulkImportOut)
def bulk_import_owner_products(
    payload: schemas.ProductBulkImportIn,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    return crud.bulk_import_products(db, payload, pharmacy_id=current_user.pharmacy_id)


@router.put("/owner/{product_id}", response_model=schemas.Product)
def update_owner_product(
    product_id: int,
    updates: schemas.ProductUpdate,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    product = (
        db.query(models.Product)
        .filter(models.Product.id == product_id, models.Product.pharmacy_id == current_user.pharmacy_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    data = updates.model_dump(exclude_unset=True)
    for key in ("name", "category", "description", "image_url"):
        if key in data and data[key] is not None:
            data[key] = str(data[key]).strip() or None

    for key, value in data.items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)
    return product


@router.delete("/owner/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owner_product(
    product_id: int,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    product = (
        db.query(models.Product)
        .filter(models.Product.id == product_id, models.Product.pharmacy_id == current_user.pharmacy_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    db.delete(product)
    db.commit()
    return None
