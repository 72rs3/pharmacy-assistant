from __future__ import annotations

import re

from app import models


_RISK_PATTERNS = [
    (r"\bdiagnos(e|is|ing)\b", "diagnosis request"),
    (r"\b(dosage|dose|mg|ml|increase|decrease|change dose)\b", "dosage change"),
    (r"\b(pregnant|pregnancy|breastfeed|lactat)\b", "pregnancy or breastfeeding"),
    (r"\b(child|infant|baby|toddler|kid)\b", "child guidance"),
    (r"\b(interaction|combine|mix with|together with)\b", "medicine interactions"),
    (r"\b(chest pain|shortness of breath|seizure|unconscious|bleeding|overdose)\b", "severe condition"),
]


def detect_risk(text: str) -> tuple[bool, str]:
    msg = (text or "").lower()
    for pattern, reason in _RISK_PATTERNS:
        if re.search(pattern, msg):
            return True, reason
    return False, ""


def safe_response(pharmacy: models.Pharmacy | None, reason: str) -> str:
    contact_bits = []
    if pharmacy:
        if pharmacy.contact_phone:
            contact_bits.append(f"Phone: {pharmacy.contact_phone}")
        if pharmacy.contact_email:
            contact_bits.append(f"Email: {pharmacy.contact_email}")
        if pharmacy.contact_address:
            contact_bits.append(f"Address: {pharmacy.contact_address}")
    contact_text = " ".join(contact_bits) if contact_bits else "Please contact the pharmacy directly."
    reason_text = f"Reason: {reason}." if reason else "Reason: medical safety."
    return (
        "I’m not able to provide medical advice or guidance on this topic. "
        "Please consider speaking with a pharmacist for proper evaluation. "
        f"{reason_text} "
        f"{contact_text} "
        "This is not medical advice. If this is urgent, seek emergency care."
    )
