from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.deps import get_active_public_pharmacy_id


router = APIRouter(prefix="/pharmacies/{pharmacy_id}/cart", tags=["Cart"])


class CartItemAddIn(BaseModel):
    session_id: str = Field(..., min_length=1)
    medicine_id: int | None = None
    product_id: int | None = None
    quantity: int = 1


class CartItemOut(BaseModel):
    id: int
    session_id: str
    item_type: str
    item_id: int
    medicine_id: int | None = None
    product_id: int | None = None
    name: str
    price: float | None = None
    quantity: int


@router.post("/items", response_model=CartItemOut)
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
    if bool(payload.medicine_id) == bool(payload.product_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide either medicine_id or product_id")

    item_type = "medicine" if payload.medicine_id else "product"
    if payload.medicine_id:
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
        name = str(medicine.name)
        price = float(medicine.price) if medicine.price is not None else None
    else:
        product = (
            db.query(models.Product)
            .filter(models.Product.pharmacy_id == tenant_pharmacy_id, models.Product.id == int(payload.product_id))
            .first()
        )
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        if int(product.stock_level or 0) < int(payload.quantity):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient stock")
        name = str(product.name)
        price = float(product.price) if product.price is not None else None

    existing = (
        db.query(models.CartItem)
        .filter(
            models.CartItem.pharmacy_id == tenant_pharmacy_id,
            models.CartItem.session_id == payload.session_id,
            models.CartItem.medicine_id == (int(payload.medicine_id) if payload.medicine_id else None),
            models.CartItem.product_id == (int(payload.product_id) if payload.product_id else None),
        )
        .first()
    )
    if existing:
        existing.quantity = int(existing.quantity or 0) + int(payload.quantity)
        cart_item = existing
    else:
        cart_item = models.CartItem(
            session_id=payload.session_id,
            pharmacy_id=tenant_pharmacy_id,
            medicine_id=int(payload.medicine_id) if payload.medicine_id else None,
            product_id=int(payload.product_id) if payload.product_id else None,
            quantity=int(payload.quantity),
        )
        db.add(cart_item)

    db.add(
        models.AILog(
            log_type="action_executed",
            details=f"action=add_to_cart {item_type}_id={payload.medicine_id or payload.product_id} qty={int(payload.quantity)}",
            pharmacy_id=tenant_pharmacy_id,
            timestamp=datetime.utcnow(),
        )
    )
    db.commit()
    db.refresh(cart_item)

    return CartItemOut(
        id=int(cart_item.id),
        session_id=cart_item.session_id,
        item_type=item_type,
        item_id=int(payload.medicine_id or payload.product_id),
        medicine_id=cart_item.medicine_id,
        product_id=cart_item.product_id,
        name=name,
        price=price,
        quantity=int(cart_item.quantity),
    )


@router.get("/items", response_model=list[CartItemOut])
def list_cart_items(
    pharmacy_id: int,
    session_id: str,
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
):
    if pharmacy_id != tenant_pharmacy_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pharmacy_id mismatch with resolved tenant")
    if not session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_id is required")

    items = (
        db.query(models.CartItem)
        .filter(models.CartItem.pharmacy_id == tenant_pharmacy_id, models.CartItem.session_id == session_id)
        .all()
    )
    results: list[CartItemOut] = []
    for item in items:
        if item.medicine_id:
            name = str(item.medicine.name) if item.medicine else "Unknown medicine"
            price = float(item.medicine.price) if item.medicine and item.medicine.price is not None else None
            item_type = "medicine"
        elif item.product_id:
            name = str(item.product.name) if item.product else "Unknown product"
            price = float(item.product.price) if item.product and item.product.price is not None else None
            item_type = "product"
        else:
            name = "Unknown item"
            price = None
            item_type = "unknown"
        results.append(
            CartItemOut(
                id=int(item.id),
                session_id=item.session_id,
                item_type=item_type,
                item_id=int(item.medicine_id or item.product_id or item.id),
                medicine_id=item.medicine_id,
                product_id=item.product_id,
                name=name,
                price=price,
                quantity=int(item.quantity or 0),
            )
        )
    return results
