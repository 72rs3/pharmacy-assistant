from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from fastapi import HTTPException, status

from . import models, schemas


def _ensure_pharmacy_exists(db: Session, pharmacy_id: int) -> None:
    exists = db.query(models.Pharmacy.id).filter(models.Pharmacy.id == pharmacy_id).first()
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pharmacy_id",
        )



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


def get_medicine(db: Session, medicine_id: int, *, pharmacy_id: int | None = None):
    query = db.query(models.Medicine).filter(models.Medicine.id == medicine_id)
    if pharmacy_id is not None:
        query = query.filter(models.Medicine.pharmacy_id == pharmacy_id)
    return query.first()


def update_medicine(db: Session, medicine_id: int, updates: schemas.MedicineUpdate, *, pharmacy_id: int):
    medicine = get_medicine(db, medicine_id, pharmacy_id=pharmacy_id)
    if not medicine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicine not found")

    data = updates.dict(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    if "category" in data and data["category"] is not None:
        data["category"] = data["category"].strip() or None
    if "dosage" in data and data["dosage"] is not None:
        data["dosage"] = data["dosage"].strip() or None
    if "side_effects" in data and data["side_effects"] is not None:
        data["side_effects"] = data["side_effects"].strip() or None

    for key, value in data.items():
        setattr(medicine, key, value)

    db.commit()
    db.refresh(medicine)
    return medicine


def delete_medicine(db: Session, medicine_id: int, *, pharmacy_id: int) -> None:
    medicine = get_medicine(db, medicine_id, pharmacy_id=pharmacy_id)
    if not medicine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicine not found")
    db.delete(medicine)
    db.commit()


def stock_in_medicine(db: Session, medicine_id: int, payload: schemas.MedicineStockIn, *, pharmacy_id: int):
    medicine = get_medicine(db, medicine_id, pharmacy_id=pharmacy_id)
    if not medicine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicine not found")

    delta = int(payload.quantity_delta)
    if delta <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="quantity_delta must be a positive integer",
        )

    medicine.stock_level = int(medicine.stock_level or 0) + delta
    if payload.expiry_date is not None:
        medicine.expiry_date = payload.expiry_date

    db.commit()
    db.refresh(medicine)
    return medicine


def bulk_import_medicines(db: Session, payload: schemas.MedicineBulkImportIn, *, pharmacy_id: int) -> schemas.MedicineBulkImportOut:
    _ensure_pharmacy_exists(db, pharmacy_id)

    errors: list[schemas.MedicineBulkImportError] = []
    created = 0
    updated = 0
    stock_in = 0

    items = payload.items or []
    if not items:
        return schemas.MedicineBulkImportOut(created=0, updated=0, stock_in=0, errors=[])

    def norm_text(value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed if trimmed else None

    def key_for(name: str, dosage: str | None) -> tuple[str, str]:
        return (name.strip().lower(), (dosage or "").strip().lower())

    wanted_names = {norm_text(item.name) for item in items}
    wanted_names = {n.lower() for n in wanted_names if n}
    existing: list[models.Medicine] = []
    if wanted_names:
        existing = (
            db.query(models.Medicine)
            .filter(models.Medicine.pharmacy_id == pharmacy_id, func.lower(models.Medicine.name).in_(wanted_names))
            .all()
        )

    by_key: dict[tuple[str, str], models.Medicine] = {}
    by_name: dict[str, list[models.Medicine]] = {}
    for med in existing:
        k = key_for(med.name or "", med.dosage)
        by_key[k] = med
        by_name.setdefault(k[0], []).append(med)

    for idx, item in enumerate(items):
        name = norm_text(item.name)
        if not name:
            errors.append(schemas.MedicineBulkImportError(row=idx + 1, message="name is required"))
            continue

        dosage = norm_text(item.dosage)
        category = norm_text(item.category)
        side_effects = norm_text(item.side_effects)
        stock_delta = int(item.stock_delta or 0)
        if stock_delta < 0:
            errors.append(schemas.MedicineBulkImportError(row=idx + 1, message="stock_delta must be >= 0"))
            continue

        k = key_for(name, dosage)
        medicine = by_key.get(k)
        if medicine is None and (not dosage):
            same_name = by_name.get(k[0], [])
            if len(same_name) == 1:
                medicine = same_name[0]
            elif len(same_name) > 1:
                errors.append(
                    schemas.MedicineBulkImportError(
                        row=idx + 1,
                        message=f"multiple existing medicines match name '{name}'; provide dosage to disambiguate",
                    )
                )
                continue

        if medicine is None:
            if item.price is None:
                errors.append(
                    schemas.MedicineBulkImportError(
                        row=idx + 1,
                        message=f"price is required for new medicine '{name}'",
                    )
                )
                continue
            db_medicine = models.Medicine(
                name=name,
                dosage=dosage,
                category=category,
                price=float(item.price),
                stock_level=stock_delta,
                expiry_date=item.expiry_date,
                prescription_required=bool(item.prescription_required) if item.prescription_required is not None else False,
                side_effects=side_effects,
                pharmacy_id=pharmacy_id,
            )
            db.add(db_medicine)
            db.flush()
            created += 1
            # Make subsequent rows in this request able to match the newly created medicine.
            by_key[key_for(db_medicine.name, db_medicine.dosage)] = db_medicine
            by_name.setdefault(db_medicine.name.strip().lower(), []).append(db_medicine)
            continue

        changed = False
        if stock_delta > 0:
            medicine.stock_level = int(medicine.stock_level or 0) + stock_delta
            stock_in += 1
            changed = True
        if item.expiry_date is not None:
            medicine.expiry_date = item.expiry_date
            changed = True

        if payload.update_fields:
            if category is not None:
                medicine.category = category
                changed = True
            if dosage is not None:
                medicine.dosage = dosage
                changed = True
            if side_effects is not None:
                medicine.side_effects = side_effects
                changed = True
            if item.price is not None:
                medicine.price = float(item.price)
                changed = True
            if item.prescription_required is not None:
                medicine.prescription_required = bool(item.prescription_required)
                changed = True

        if changed:
            updated += 1

    db.commit()
    return schemas.MedicineBulkImportOut(created=created, updated=updated, stock_in=stock_in, errors=errors)


def bulk_import_products(db: Session, payload: schemas.ProductBulkImportIn, *, pharmacy_id: int) -> schemas.ProductBulkImportOut:
    _ensure_pharmacy_exists(db, pharmacy_id)

    errors: list[schemas.ProductBulkImportError] = []
    created = 0
    updated = 0

    items = payload.items or []
    if not items:
        return schemas.ProductBulkImportOut(created=0, updated=0, errors=[])

    def norm_text(value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed if trimmed else None

    # Load existing products for this pharmacy and match by case-insensitive name.
    wanted_names = {norm_text(item.name) for item in items}
    wanted_names = {n.lower() for n in wanted_names if n}
    existing: list[models.Product] = []
    if wanted_names:
        existing = (
            db.query(models.Product)
            .filter(models.Product.pharmacy_id == pharmacy_id, func.lower(models.Product.name).in_(wanted_names))
            .all()
        )
    by_name = {str(p.name or "").strip().lower(): p for p in existing}

    for idx, item in enumerate(items):
        row = idx + 1
        name = norm_text(item.name)
        if not name:
            errors.append(schemas.ProductBulkImportError(row=row, message="name is required"))
            continue

        category = norm_text(item.category)
        description = norm_text(item.description)
        image_url = norm_text(item.image_url)

        stock_level = item.stock_level
        if stock_level is None:
            stock_level = 0
        try:
            stock_level = int(stock_level)
        except Exception:
            errors.append(schemas.ProductBulkImportError(row=row, message="stock_level must be an integer"))
            continue
        if stock_level < 0:
            errors.append(schemas.ProductBulkImportError(row=row, message="stock_level must be >= 0"))
            continue

        product = by_name.get(name.lower())
        if product is None:
            if item.price is None:
                errors.append(schemas.ProductBulkImportError(row=row, message=f"price is required for new product '{name}'"))
                continue
            price = float(item.price)
            if price < 0:
                errors.append(schemas.ProductBulkImportError(row=row, message="price must be >= 0"))
                continue
            db_product = models.Product(
                name=name,
                category=category,
                price=price,
                stock_level=stock_level,
                description=description,
                image_url=image_url,
                pharmacy_id=pharmacy_id,
            )
            db.add(db_product)
            db.flush()
            created += 1
            by_name[name.lower()] = db_product
            continue

        changed = False
        # Always allow stock_level set when provided (or defaulted to 0 for missing).
        if item.stock_level is not None:
            product.stock_level = stock_level
            changed = True

        if payload.update_fields:
            if category is not None:
                product.category = category
                changed = True
            if description is not None:
                product.description = description
                changed = True
            if image_url is not None:
                product.image_url = image_url
                changed = True
            if item.price is not None:
                price = float(item.price)
                if price < 0:
                    errors.append(schemas.ProductBulkImportError(row=row, message="price must be >= 0"))
                    continue
                product.price = price
                changed = True

        if changed:
            updated += 1

    db.commit()
    return schemas.ProductBulkImportOut(created=created, updated=updated, errors=errors)
