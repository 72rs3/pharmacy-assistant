from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models
from app.appointments.email_templates import render_reminder
from app.utils.email import send_email


def process_due_reminders(db: Session, pharmacy_id: int | None = None) -> dict:
    now = datetime.utcnow()
    query = (
        db.query(models.AppointmentReminder)
        .join(models.Appointment, models.AppointmentReminder.appointment_id == models.Appointment.id)
        .filter(
            models.AppointmentReminder.status == "PENDING",
            models.AppointmentReminder.send_at <= now,
        )
    )
    if pharmacy_id is not None:
        query = query.filter(models.Appointment.pharmacy_id == pharmacy_id)

    reminders = query.all()
    sent = 0
    failed = 0
    skipped = 0

    for reminder in reminders:
        appointment = reminder.appointment
        if not appointment or appointment.customer_email is None:
            reminder.status = "SKIPPED"
            reminder.error_message = "Missing customer email"
            skipped += 1
            continue
        settings = (
            db.query(models.AppointmentSettings)
            .filter(models.AppointmentSettings.pharmacy_id == appointment.pharmacy_id)
            .first()
        )
        template = render_reminder(
            appointment=appointment,
            pharmacy=appointment.pharmacy,
            settings=settings,
            template_key=reminder.template,
        )
        ok, error = send_email(appointment.customer_email, template.subject, template.body)
        if ok:
            reminder.status = "SENT"
            reminder.sent_at = datetime.utcnow()
            reminder.error_message = None
            sent += 1
        else:
            reminder.status = "FAILED"
            reminder.error_message = error
            failed += 1
    db.commit()
    return {"sent": sent, "failed": failed, "skipped": skipped}


def process_no_shows(db: Session, pharmacy_id: int | None = None) -> dict:
    now = datetime.utcnow()
    query = db.query(models.Appointment).filter(
        models.Appointment.no_show.is_(False),
        models.Appointment.status.in_(["PENDING", "CONFIRMED"]),
    )
    if pharmacy_id is not None:
        query = query.filter(models.Appointment.pharmacy_id == pharmacy_id)

    appointments = query.all()
    updated = 0
    for appointment in appointments:
        settings = (
            db.query(models.AppointmentSettings)
            .filter(models.AppointmentSettings.pharmacy_id == appointment.pharmacy_id)
            .first()
        )
        no_show_minutes = max(5, getattr(settings, "no_show_minutes", 30))
        if appointment.scheduled_time + timedelta(minutes=no_show_minutes) <= now:
            appointment.no_show = True
            appointment.no_show_marked_at = now
            db.add(
                models.AppointmentAudit(
                    appointment_id=appointment.id,
                    action="no_show_auto",
                    old_values_json="{}",
                    new_values_json='{"no_show": true}',
                    changed_by_user_id=None,
                    created_at=now,
                )
            )
            updated += 1
    db.commit()
    return {"updated": updated}
