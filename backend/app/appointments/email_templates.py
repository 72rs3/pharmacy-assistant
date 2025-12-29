from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app import models


@dataclass
class EmailTemplate:
    subject: str
    body: str


_COPY = {
    "en": {
        "subject_24h": "Appointment reminder (24 hours)",
        "subject_2h": "Appointment reminder (in 2 hours)",
        "greeting": "Hello {name},",
        "intro": "This is a reminder for your appointment:",
        "type": "Type: {type}",
        "time": "Time: {time}",
        "footer": "If you need to reschedule, please contact the pharmacy.",
    },
    "ar": {
        "subject_24h": "تذكير بالموعد (بعد 24 ساعة)",
        "subject_2h": "تذكير بالموعد (بعد ساعتين)",
        "greeting": "مرحباً {name}",
        "intro": "هذا تذكير بموعدك:",
        "type": "النوع: {type}",
        "time": "الوقت: {time}",
        "footer": "إذا كنت بحاجة لتغيير الموعد، يرجى التواصل مع الصيدلية.",
    },
    "fr": {
        "subject_24h": "Rappel de rendez-vous (24h)",
        "subject_2h": "Rappel de rendez-vous (dans 2h)",
        "greeting": "Bonjour {name},",
        "intro": "Ceci est un rappel pour votre rendez-vous :",
        "type": "Type : {type}",
        "time": "Heure : {time}",
        "footer": "Pour reprogrammer, contactez la pharmacie.",
    },
}


def render_reminder(
    appointment: models.Appointment,
    pharmacy: models.Pharmacy | None,
    settings: models.AppointmentSettings | None,
    template_key: str,
) -> EmailTemplate:
    locale = (settings.locale if settings else "en") or "en"
    locale = locale if locale in _COPY else "en"
    copy = _COPY[locale]
    subject = copy["subject_24h"] if template_key == "24h" else copy["subject_2h"]
    customer_name = appointment.customer_name or "Customer"
    formatted_time = appointment.scheduled_time.strftime("%Y-%m-%d %H:%M")
    pharmacy_name = pharmacy.name if pharmacy else "Pharmacy"
    logo_url = getattr(pharmacy, "logo_url", None) if pharmacy else None
    primary_color = getattr(pharmacy, "primary_color", None) if pharmacy else None
    accent = primary_color or "#2563eb"

    body = f"""
    <div style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px">
      <div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:24px">
        <div style="display:flex;align-items:center;gap:12px">
          {f'<img src="{logo_url}" alt="{pharmacy_name}" style="height:36px"/>' if logo_url else ''}
          <div style="font-size:18px;font-weight:600;color:#0f172a">{pharmacy_name}</div>
        </div>
        <div style="margin-top:20px;font-size:14px;color:#0f172a">
          <div>{copy["greeting"].format(name=customer_name)}</div>
          <div style="margin-top:8px">{copy["intro"]}</div>
          <div style="margin-top:12px;padding:12px;border-radius:10px;background:#f1f5f9">
            <div>{copy["type"].format(type=appointment.type)}</div>
            <div>{copy["time"].format(time=formatted_time)}</div>
          </div>
          <div style="margin-top:16px">{copy["footer"]}</div>
        </div>
        <div style="margin-top:24px;font-size:12px;color:#64748b">
          {pharmacy_name}
        </div>
        <div style="margin-top:12px;height:4px;background:{accent};border-radius:999px"></div>
      </div>
    </div>
    """.strip()

    return EmailTemplate(subject=subject, body=body)
