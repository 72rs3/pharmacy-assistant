from __future__ import annotations

import json
import secrets
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.deps import require_approved_owner, require_pharmacy_owner
from app.db import get_db
from app.deps import get_active_public_pharmacy_id, get_current_pharmacy_id
from app.appointments.reminders import process_due_reminders, process_no_shows
from app.utils.validation import validate_e164_phone

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def _require_customer_tracking_code(
    tracking_code: str | None = Header(None, alias="X-Customer-ID"),
) -> str:
    if not tracking_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Customer-ID tracking code",
        )
    return tracking_code


def _default_weekly_hours() -> dict:
    return {
        "mon": [{"start": "09:00", "end": "18:00"}],
        "tue": [{"start": "09:00", "end": "18:00"}],
        "wed": [{"start": "09:00", "end": "18:00"}],
        "thu": [{"start": "09:00", "end": "18:00"}],
        "fri": [{"start": "09:00", "end": "18:00"}],
        "sat": [{"start": "09:00", "end": "14:00"}],
        "sun": [],
    }


def _get_or_create_settings(db: Session, pharmacy_id: int) -> models.AppointmentSettings:
    settings = db.query(models.AppointmentSettings).filter(models.AppointmentSettings.pharmacy_id == pharmacy_id).first()
    if settings:
        return settings
    settings = models.AppointmentSettings(
        pharmacy_id=pharmacy_id,
        slot_minutes=15,
        buffer_minutes=0,
        timezone="UTC",
        weekly_hours_json=json.dumps(_default_weekly_hours()),
        no_show_minutes=30,
        locale="en",
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def _load_weekly_hours(settings: models.AppointmentSettings) -> dict:
    try:
        data = json.loads(settings.weekly_hours_json or "{}")
    except json.JSONDecodeError:
        data = {}
    if not data:
        data = _default_weekly_hours()
    return data


def _is_within_business_hours(scheduled_time: datetime, settings: models.AppointmentSettings) -> bool:
    weekly_hours = _load_weekly_hours(settings)
    weekday_key = scheduled_time.strftime("%a").lower()[:3]
    ranges = weekly_hours.get(weekday_key, [])
    if not ranges:
        return False
    for block in ranges:
        try:
            start_parts = [int(part) for part in block.get("start", "09:00").split(":")]
            end_parts = [int(part) for part in block.get("end", "18:00").split(":")]
            start_time = time(start_parts[0], start_parts[1])
            end_time = time(end_parts[0], end_parts[1])
        except Exception:
            continue
        start_dt = datetime.combine(scheduled_time.date(), start_time)
        end_dt = datetime.combine(scheduled_time.date(), end_time)
        if start_dt <= scheduled_time < end_dt:
            return True
    return False


def _has_conflict(db: Session, pharmacy_id: int, scheduled_time: datetime, exclude_id: int | None = None) -> bool:
    query = db.query(models.Appointment).filter(
        models.Appointment.pharmacy_id == pharmacy_id,
        models.Appointment.scheduled_time == scheduled_time,
        models.Appointment.status.in_(["PENDING", "CONFIRMED"]),
    )
    if exclude_id is not None:
        query = query.filter(models.Appointment.id != exclude_id)
    return db.query(query.exists()).scalar()


def _validate_slot(db: Session, pharmacy_id: int, scheduled_time: datetime, exclude_id: int | None = None) -> None:
    settings = _get_or_create_settings(db, pharmacy_id)
    if not _is_within_business_hours(scheduled_time, settings):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected time is outside business hours. Please choose another time.",
        )
    if _has_conflict(db, pharmacy_id, scheduled_time, exclude_id=exclude_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That slot is already booked. Please choose another time.",
        )


def _log_audit(
    db: Session,
    appointment_id: int,
    action: str,
    old_values: dict | None,
    new_values: dict | None,
    changed_by_user_id: int | None,
):
    audit = models.AppointmentAudit(
        appointment_id=appointment_id,
        action=action,
        old_values_json=json.dumps(old_values or {}),
        new_values_json=json.dumps(new_values or {}),
        changed_by_user_id=changed_by_user_id,
        created_at=datetime.utcnow(),
    )
    db.add(audit)


def _clear_pending_reminders(db: Session, appointment_id: int) -> None:
    db.query(models.AppointmentReminder).filter(
        models.AppointmentReminder.appointment_id == appointment_id,
        models.AppointmentReminder.status == "PENDING",
    ).delete()


def _schedule_reminders(db: Session, appointment: models.Appointment) -> None:
    if appointment.status != "PENDING":
        return
    if appointment.no_show:
        return
    if appointment.customer_email is None:
        return
    now = datetime.utcnow()
    reminder_offsets = [
        ("24h", timedelta(hours=24)),
        ("2h", timedelta(hours=2)),
    ]
    for template, delta in reminder_offsets:
        send_at = appointment.scheduled_time - delta
        if send_at <= now:
            continue
        db.add(
            models.AppointmentReminder(
                appointment_id=appointment.id,
                channel="EMAIL",
                template=template,
                send_at=send_at,
                status="PENDING",
            )
        )


@router.post("", response_model=schemas.CustomerAppointmentCreated)
def create_customer_appointment(
    payload: schemas.CustomerAppointmentCreate,
    customer_tracking_code: str | None = Header(None, alias="X-Customer-ID"),
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
):
    tracking_code = (customer_tracking_code or "").strip() or secrets.token_urlsafe(12)
    _validate_slot(db, tenant_pharmacy_id, payload.scheduled_time)
    appt = models.Appointment(
        customer_id=tracking_code,
        customer_name=payload.customer_name.strip(),
        customer_phone=validate_e164_phone(payload.customer_phone, "customer"),
        customer_email=(payload.customer_email.strip() if payload.customer_email else None),
        type=payload.type.strip(),
        scheduled_time=payload.scheduled_time,
        status="PENDING",
        vaccine_name=(payload.vaccine_name.strip() if payload.vaccine_name else None),
        pharmacy_id=tenant_pharmacy_id,
    )
    db.add(appt)
    db.add(
        models.AILog(
            log_type="action_executed",
            details=f"action=book_appointment appt_id=pending scheduled={payload.scheduled_time.isoformat()}",
            pharmacy_id=tenant_pharmacy_id,
            timestamp=datetime.utcnow(),
        )
    )
    db.commit()
    db.refresh(appt)
    _schedule_reminders(db, appt)
    db.commit()
    return schemas.CustomerAppointmentCreated(
        id=appt.id,
        type=appt.type,
        scheduled_time=appt.scheduled_time,
        status=appt.status,
        vaccine_name=appt.vaccine_name,
        tracking_code=tracking_code,
    )


@router.get("/my", response_model=list[schemas.CustomerAppointmentOut])
def list_customer_appointments(
    db: Session = Depends(get_db),
    tenant_pharmacy_id: int = Depends(get_active_public_pharmacy_id),
    tracking_code: str = Depends(_require_customer_tracking_code),
):
    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.pharmacy_id == tenant_pharmacy_id,
            models.Appointment.customer_id == tracking_code,
        )
        .order_by(models.Appointment.scheduled_time.desc())
        .all()
    )


@router.get("/owner", response_model=list[schemas.Appointment])
def list_owner_appointments(
    response: Response,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
    statuses: list[str] | None = Query(None, alias="status"),
    appointment_type: str | None = Query(None, alias="type"),
    q: str | None = Query(None),
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    sort: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = db.query(models.Appointment).filter(models.Appointment.pharmacy_id == current_user.pharmacy_id)

    if statuses:
        normalized = [str(value).upper() for value in statuses if value]
        if normalized:
            query = query.filter(models.Appointment.status.in_(normalized))

    if appointment_type:
        query = query.filter(models.Appointment.type.ilike(f"%{appointment_type.strip()}%"))

    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.Appointment.customer_name.ilike(needle),
                models.Appointment.customer_phone.ilike(needle),
                models.Appointment.type.ilike(needle),
                models.Appointment.vaccine_name.ilike(needle),
            )
        )

    if from_dt is not None:
        query = query.filter(models.Appointment.scheduled_time >= from_dt)
    if to_dt is not None:
        query = query.filter(models.Appointment.scheduled_time <= to_dt)

    status_priority = case(
        (models.Appointment.status == "PENDING", 0),
        (models.Appointment.status == "CONFIRMED", 1),
        (models.Appointment.status == "COMPLETED", 2),
        (models.Appointment.status == "CANCELLED", 3),
        else_=4,
    )

    total_count = query.order_by(None).count()
    response.headers["X-Total-Count"] = str(total_count)

    sort_mode = (sort or "queue").strip().lower()
    if sort_mode == "schedule":
        query = query.order_by(
            models.Appointment.scheduled_time.asc(),
            status_priority.asc(),
            models.Appointment.id.desc(),
        )
    elif sort_mode == "recent":
        query = query.order_by(
            models.Appointment.created_at.desc(),
            models.Appointment.id.desc(),
        )
    else:
        sentinel_early = datetime(1970, 1, 1)
        sentinel_late = datetime(9999, 1, 1)
        pending_created_sort = case(
            (models.Appointment.status == "PENDING", models.Appointment.created_at),
            else_=sentinel_early,
        )
        nonpending_scheduled_sort = case(
            (models.Appointment.status != "PENDING", models.Appointment.scheduled_time),
            else_=sentinel_late,
        )
        query = query.order_by(
            status_priority.asc(),
            pending_created_sort.desc(),
            nonpending_scheduled_sort.asc(),
            models.Appointment.scheduled_time.asc(),
            models.Appointment.id.desc(),
        )

    return query.offset(offset).limit(limit).all()


@router.get("/settings", response_model=schemas.AppointmentSettings)
def get_appointment_settings(
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    settings = _get_or_create_settings(db, current_user.pharmacy_id)
    return settings


@router.put("/settings", response_model=schemas.AppointmentSettings)
def update_appointment_settings(
    payload: schemas.AppointmentSettingsUpdate,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    settings = _get_or_create_settings(db, current_user.pharmacy_id)
    settings.slot_minutes = max(5, payload.slot_minutes)
    settings.buffer_minutes = max(0, payload.buffer_minutes)
    settings.timezone = payload.timezone.strip() if payload.timezone else "UTC"
    settings.weekly_hours_json = payload.weekly_hours_json or "{}"
    settings.no_show_minutes = max(5, payload.no_show_minutes)
    settings.locale = payload.locale.strip() if payload.locale else "en"
    settings.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(settings)
    return settings


@router.get("/availability")
def get_appointment_availability(
    date_str: str = Query(..., alias="date"),
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    settings = _get_or_create_settings(db, current_user.pharmacy_id)
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format") from exc

    weekly_hours = _load_weekly_hours(settings)

    weekday_key = target_date.strftime("%a").lower()[:3]
    ranges = weekly_hours.get(weekday_key, [])
    slot_minutes = max(5, settings.slot_minutes)
    buffer_minutes = max(0, settings.buffer_minutes)

    slots = []
    if ranges:
        for block in ranges:
            try:
                start_parts = [int(part) for part in block.get("start", "09:00").split(":")]
                end_parts = [int(part) for part in block.get("end", "18:00").split(":")]
                start_time = time(start_parts[0], start_parts[1])
                end_time = time(end_parts[0], end_parts[1])
            except Exception:
                continue
            start_dt = datetime.combine(target_date, start_time)
            end_dt = datetime.combine(target_date, end_time)
            step = timedelta(minutes=slot_minutes + buffer_minutes)
            current = start_dt
            while current + timedelta(minutes=slot_minutes) <= end_dt:
                slots.append(
                    {
                        "start": current.isoformat(),
                        "end": (current + timedelta(minutes=slot_minutes)).isoformat(),
                        "booked": False,
                        "appointment_id": None,
                    }
                )
                current += step

    if slots:
        day_start = datetime.combine(target_date, time(0, 0))
        day_end = datetime.combine(target_date, time(23, 59, 59))
        appts = (
            db.query(models.Appointment)
            .filter(
                models.Appointment.pharmacy_id == current_user.pharmacy_id,
                models.Appointment.scheduled_time >= day_start,
                models.Appointment.scheduled_time <= day_end,
            )
            .all()
        )
        appt_by_iso = {appt.scheduled_time.isoformat(): appt for appt in appts}
        for slot in slots:
            appt = appt_by_iso.get(slot["start"])
            if appt:
                slot["booked"] = True
                slot["appointment_id"] = appt.id
                slot["status"] = appt.status
                slot["customer_name"] = appt.customer_name
    return {"date": target_date.isoformat(), "slots": slots, "timezone": settings.timezone}


@router.post("/{appointment_id}/status", response_model=schemas.Appointment)
def update_appointment_status(
    appointment_id: int,
    status_in: schemas.AppointmentStatusIn,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_current_pharmacy_id),
    current_user: models.User = Depends(require_pharmacy_owner),
):
    appointment = (
        db.query(models.Appointment)
        .filter(models.Appointment.id == appointment_id, models.Appointment.pharmacy_id == pharmacy_id)
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    if status_in.status not in {"PENDING", "CONFIRMED", "CANCELLED", "COMPLETED"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    old_values = {"status": appointment.status}
    appointment.status = status_in.status
    _log_audit(
        db,
        appointment_id=appointment.id,
        action="status_update",
        old_values=old_values,
        new_values={"status": appointment.status},
        changed_by_user_id=current_user.id if current_user else None,
    )
    _clear_pending_reminders(db, appointment.id)
    _schedule_reminders(db, appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.patch("/{appointment_id}", response_model=schemas.Appointment)
def update_appointment(
    appointment_id: int,
    payload: schemas.AppointmentUpdateIn,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_current_pharmacy_id),
    current_user: models.User = Depends(require_pharmacy_owner),
):
    appointment = (
        db.query(models.Appointment)
        .filter(models.Appointment.id == appointment_id, models.Appointment.pharmacy_id == pharmacy_id)
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    data = payload.model_dump(exclude_unset=True)
    old_values: dict[str, object] = {}
    new_values: dict[str, object] = {}
    status_value = data.get("status")
    if status_value is not None:
        if status_value not in {"PENDING", "CONFIRMED", "CANCELLED", "COMPLETED"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
        old_values["status"] = appointment.status
        appointment.status = status_value
        new_values["status"] = status_value

    if "scheduled_time" in data and data["scheduled_time"] is not None:
        _validate_slot(db, pharmacy_id, data["scheduled_time"], exclude_id=appointment.id)
        old_values["scheduled_time"] = appointment.scheduled_time.isoformat()
        appointment.scheduled_time = data["scheduled_time"]
        new_values["scheduled_time"] = appointment.scheduled_time.isoformat()

    if old_values or new_values:
        _log_audit(
            db,
            appointment_id=appointment.id,
            action="update",
            old_values=old_values,
            new_values=new_values,
            changed_by_user_id=current_user.id if current_user else None,
        )
        _clear_pending_reminders(db, appointment.id)
        _schedule_reminders(db, appointment)

    db.commit()
    db.refresh(appointment)
    return appointment


@router.post("/{appointment_id}/no-show", response_model=schemas.Appointment)
def mark_no_show(
    appointment_id: int,
    db: Session = Depends(get_db),
    pharmacy_id: int = Depends(get_current_pharmacy_id),
    current_user: models.User = Depends(require_pharmacy_owner),
):
    appointment = (
        db.query(models.Appointment)
        .filter(models.Appointment.id == appointment_id, models.Appointment.pharmacy_id == pharmacy_id)
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    old_values = {"no_show": appointment.no_show}
    appointment.no_show = True
    appointment.no_show_marked_at = datetime.utcnow()
    _log_audit(
        db,
        appointment_id=appointment.id,
        action="no_show",
        old_values=old_values,
        new_values={"no_show": True},
        changed_by_user_id=current_user.id if current_user else None,
    )
    _clear_pending_reminders(db, appointment.id)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.get("/{appointment_id}/audits", response_model=list[schemas.AppointmentAudit])
def list_appointment_audits(
    appointment_id: int,
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.AppointmentAudit)
        .join(models.Appointment, models.AppointmentAudit.appointment_id == models.Appointment.id)
        .filter(
            models.Appointment.id == appointment_id,
            models.Appointment.pharmacy_id == current_user.pharmacy_id,
        )
        .order_by(models.AppointmentAudit.created_at.desc())
        .all()
    )


@router.post("/reminders/run")
def run_due_reminders(
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    return process_due_reminders(db, pharmacy_id=current_user.pharmacy_id)


@router.post("/no-shows/run")
def run_no_show_marking(
    current_user: models.User = Depends(require_approved_owner),
    db: Session = Depends(get_db),
):
    return process_no_shows(db, pharmacy_id=current_user.pharmacy_id)
