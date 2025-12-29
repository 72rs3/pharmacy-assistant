from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.deps import require_owner, require_pharmacy_owner
from app.db import get_db
from app.deps import get_active_public_pharmacy_id, get_current_pharmacy_id

router = APIRouter(prefix="/orders", tags=["Orders"])


def _require_customer_tracking_code(
    tracking_code: str | None = Header(None, alias="X-Customer-ID"),
) -> str:
    if not tracking_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Customer-ID tracking code",
        )
    return tracking_code


@router.post("", response_model=schemas.CustomerOrderCreated)
def create_customer_order(
    payload: schemas.CustomerOrderCreate,
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
):
    if not payload.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order must include items")

    medicine_ids = [item.medicine_id for item in payload.items]
    medicines = (
        db.query(models.Medicine)
        .filter(
            models.Medicine.pharmacy_id == tenant_pharmacy_id,
            models.Medicine.id.in_(medicine_ids),
        )
        .all()
    )
    medicine_by_id = {medicine.id: medicine for medicine in medicines}
    missing = sorted(set(medicine_ids) - set(medicine_by_id.keys()))
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid medicine_id(s) for this pharmacy: {', '.join(map(str, missing))}",
        )

    items: list[models.OrderItem] = []
    requires_prescription = False
    for item in payload.items:
        if item.quantity <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be positive")
        medicine = medicine_by_id[item.medicine_id]
        if medicine.prescription_required:
            requires_prescription = True
        items.append(
            models.OrderItem(
                medicine_id=medicine.id,
                quantity=item.quantity,
                unit_price=float(medicine.price),
            )
        )

    tracking_code = secrets.token_urlsafe(16)
    order = models.Order(
        customer_id=tracking_code,
        customer_name=payload.customer_name.strip(),
        customer_phone=payload.customer_phone.strip(),
        customer_address=payload.customer_address.strip(),
        customer_notes=(payload.customer_notes.strip() if payload.customer_notes else None),
        status="PENDING",
        payment_method="COD",
        payment_status="UNPAID",
        order_date=datetime.utcnow(),
        pharmacy_id=tenant_pharmacy_id,
    )
    db.add(order)
    db.flush()

    for item in items:
        item.order_id = order.id
        db.add(item)

    db.commit()
    return schemas.CustomerOrderCreated(
        order_id=order.id,
        tracking_code=tracking_code,
        status=order.status,
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        order_date=order.order_date,
        requires_prescription=requires_prescription,
    )


@router.get("/my", response_model=list[schemas.CustomerOrderSummary])
def list_customer_orders(
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    tracking_code: str = Depends(_require_customer_tracking_code),
):
    return (
        db.query(models.Order)
        .filter(
            models.Order.pharmacy_id == tenant_pharmacy_id,
            models.Order.customer_id == tracking_code,
        )
        .order_by(models.Order.order_date.desc())
        .all()
    )


@router.get("/owner", response_model=list[schemas.Order])
def list_owner_orders(
    current_user: models.User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Order)
        .filter(models.Order.pharmacy_id == current_user.pharmacy_id)
        .order_by(models.Order.order_date.desc())
        .all()
    )


@router.get("/{order_id}", response_model=schemas.Order)
def get_customer_order(
    order_id: int,
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    tracking_code: str = Depends(_require_customer_tracking_code),
):
    order = (
        db.query(models.Order)
        .filter(
            models.Order.id == order_id,
            models.Order.pharmacy_id == tenant_pharmacy_id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.customer_id != tracking_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid tracking code")
    return order


@router.post("/{order_id}/approve", response_model=schemas.Order)
def approve_order(
    order_id: int,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_current_pharmacy_id),
    _=Depends(require_pharmacy_owner),
):
    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_id, models.Order.pharmacy_id == pharmacy_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order is not pending")

    order_items = db.query(models.OrderItem).filter(models.OrderItem.order_id == order.id).all()
    if not order_items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order has no items")

    med_ids = [item.medicine_id for item in order_items]
    medicines = (
        db.query(models.Medicine)
        .filter(models.Medicine.pharmacy_id == pharmacy_id, models.Medicine.id.in_(med_ids))
        .all()
    )
    medicine_by_id = {m.id: m for m in medicines}
    for item in order_items:
        medicine = medicine_by_id.get(item.medicine_id)
        if not medicine:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order contains invalid medicine")
        if medicine.stock_level < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for {medicine.name}",
            )

    prescription_needed = any(medicine_by_id[item.medicine_id].prescription_required for item in order_items)
    if prescription_needed:
        approved_prescription = (
            db.query(models.Prescription)
            .filter(models.Prescription.order_id == order.id, models.Prescription.status == "APPROVED")
            .first()
        )
        if not approved_prescription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prescription required and not approved",
            )

    for item in order_items:
        medicine = medicine_by_id[item.medicine_id]
        medicine.stock_level -= item.quantity

    order.status = "APPROVED"
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/cancel", response_model=schemas.Order)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_current_pharmacy_id),
    _=Depends(require_pharmacy_owner),
):
    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_id, models.Order.pharmacy_id == pharmacy_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status == "CANCELLED":
        return order
    if order.status == "DELIVERED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Delivered orders cannot be cancelled")

    order.status = "CANCELLED"
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/deliver", response_model=schemas.Order)
def deliver_order(
    order_id: int,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_current_pharmacy_id),
    _=Depends(require_pharmacy_owner),
):
    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_id, models.Order.pharmacy_id == pharmacy_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status != "APPROVED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only approved orders can be delivered")

    order.status = "DELIVERED"
    order.payment_status = "PAID" if order.payment_method == "COD" else order.payment_status
    db.commit()
    db.refresh(order)
    return order
