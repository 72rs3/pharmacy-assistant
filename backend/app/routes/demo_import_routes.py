import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.auth.deps import require_admin
from app.db import Base, get_db


router = APIRouter(prefix="/admin/demo-import", tags=["Demo Import"])


class DemoImportPayload(BaseModel):
    tables: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    clear_existing: bool = True


IMPORT_ORDER = [
    "pharmacies",
    "users",
    "medicines",
    "products",
    "orders",
    "order_items",
    "prescriptions",
    "prescription_medicines",
    "appointments",
    "appointment_settings",
    "appointment_audits",
    "appointment_reminders",
    "contact_messages",
    "ai_interactions",
    "ai_logs",
    "chat_sessions",
    "chat_messages",
    "documents",
    "document_chunks",
    "cart_items",
]


def _demo_import_enabled() -> bool:
    raw = os.getenv("ENABLE_DEMO_IMPORT", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _table_for_name(name: str):
    table = Base.metadata.tables.get(name)
    if table is None or name not in IMPORT_ORDER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported import table: {name}",
        )
    return table


@router.post("")
def import_demo_data(
    payload: DemoImportPayload,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    if not _demo_import_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    unknown = sorted(set(payload.tables) - set(IMPORT_ORDER))
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported import table(s): {', '.join(unknown)}",
        )

    try:
        if payload.clear_existing:
            for name in reversed(IMPORT_ORDER):
                table = _table_for_name(name)
                db.execute(table.delete())

        imported: dict[str, int] = {}
        for name in IMPORT_ORDER:
            rows = payload.tables.get(name) or []
            if not rows:
                continue

            table = _table_for_name(name)
            columns = set(table.c.keys())
            cleaned = [
                {key: value for key, value in row.items() if key in columns}
                for row in rows
            ]
            if cleaned:
                db.execute(table.insert(), cleaned)
                imported[name] = len(cleaned)

        if db.bind and db.bind.dialect.name == "postgresql":
            for name in IMPORT_ORDER:
                if payload.tables.get(name):
                    db.execute(
                        text(
                            "select setval(pg_get_serial_sequence(:table_name, 'id'), "
                            "greatest((select coalesce(max(id), 1) from "
                            f"{name}), 1), true)"
                        ),
                        {"table_name": f"public.{name}"},
                    )

        db.commit()
        return {"ok": True, "imported": imported}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Import failed: {exc}",
        ) from exc
