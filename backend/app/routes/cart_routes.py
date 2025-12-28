from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.deps import get_active_public_pharmacy_id


router = APIRouter(prefix="/pharmacies/{pharmacy_id}/cart", tags=["Cart"])


class CartItemAddIn(BaseModel):
    medicine_id: int
    quantity: int = 1


class CartItemAddOut(BaseModel):
    medicine_id: int
    name: str
    price: float | None = None
    stock: int


@router.post("/items", response_model=CartItemAddOut)
def add_cart_item(
    pharmacy_id: int,
    payload: CartItemAddIn,
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
):
    if pharmacy_id != tenant_pharmacy_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pharmacy_id mismatch with resolved tenant")
    if payload.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be positive")

    medicine = (
        db.query(models.Medicine)
        .filter(models.Medicine.pharmacy_id == tenant_pharmacy_id, models.Medicine.id == int(payload.medicine_id))
        .first()
    )
    if not medicine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicine not found")

    if int(medicine.stock_level or 0) < int(payload.quantity):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient stock")

    if bool(medicine.prescription_required):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prescription required; cannot add to cart")

    return CartItemAddOut(
        medicine_id=int(medicine.id),
        name=str(medicine.name),
        price=float(medicine.price) if medicine.price is not None else None,
        stock=int(medicine.stock_level or 0),
    )

