import re

from fastapi import HTTPException, status
from pydantic import EmailStr, TypeAdapter, ValidationError

_E164_REGEX = re.compile(r"^\+[1-9]\d{1,14}$")
_EMAIL_ADAPTER = TypeAdapter(EmailStr)


def validate_email(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        _EMAIL_ADAPTER.validate_python(cleaned)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name} email format",
        ) from exc
    return cleaned


def validate_e164_phone(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not _E164_REGEX.match(cleaned):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name} phone number. Use E.164 (e.g. +15551234567).",
        )
    return cleaned
