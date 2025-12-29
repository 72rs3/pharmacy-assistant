from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app import models


_TTL_MINUTES = 30
_STATE_KEY_PREFIX = "state:"


def new_session_id() -> str:
    return str(uuid4())


def _redis_client():
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis  # type: ignore

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _redis_key(pharmacy_id: int, session_id: str) -> str:
    return f"pharmacy:{pharmacy_id}:session:{session_id}"


def load_turns(db: Session, pharmacy_id: int, session_id: str) -> list[dict[str, Any]]:
    if not session_id:
        return []
    client = _redis_client()
    if client:
        try:
            raw = client.get(_redis_key(pharmacy_id, session_id))
            if not raw:
                return []
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    row = (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.pharmacy_id == pharmacy_id,
            models.ChatSession.session_id == session_id,
        )
        .first()
    )
    if not row:
        return []
    if row.expires_at and row.expires_at < datetime.utcnow():
        db.delete(row)
        db.commit()
        return []
    try:
        data = json.loads(row.turns_json or "[]")
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_turns(db: Session, pharmacy_id: int, session_id: str, turns: list[dict[str, Any]]) -> None:
    if not session_id:
        return
    trimmed = turns[-10:]
    payload = json.dumps(trimmed, ensure_ascii=False)
    client = _redis_client()
    if client:
        try:
            key = _redis_key(pharmacy_id, session_id)
            client.setex(key, timedelta(minutes=_TTL_MINUTES), payload)
            return
        except Exception:
            pass

    expires_at = datetime.utcnow() + timedelta(minutes=_TTL_MINUTES)
    row = (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.pharmacy_id == pharmacy_id,
            models.ChatSession.session_id == session_id,
        )
        .first()
    )
    if row:
        row.turns_json = payload
        row.expires_at = expires_at
    else:
        row = models.ChatSession(
            pharmacy_id=pharmacy_id,
            session_id=session_id,
            turns_json=payload,
            expires_at=expires_at,
        )
        db.add(row)
    db.commit()


def append_turns(
    db: Session,
    pharmacy_id: int,
    session_id: str,
    user_text: str,
    assistant_text: str,
) -> None:
    turns = load_turns(db, pharmacy_id, session_id)
    turns.append({"role": "user", "text": user_text, "ts": datetime.utcnow().isoformat()})
    turns.append({"role": "assistant", "text": assistant_text, "ts": datetime.utcnow().isoformat()})
    save_turns(db, pharmacy_id, session_id, turns)


def user_context(turns: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("text")).strip() for item in turns if item.get("role") == "user" and str(item.get("text")).strip()]


def get_state(turns: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    if not turns or not key:
        return None
    target = f"{_STATE_KEY_PREFIX}{key}"
    for item in reversed(turns):
        if item.get("role") != "state":
            continue
        if item.get("key") == target and isinstance(item.get("value"), dict):
            return item["value"]
    return None


def set_state(turns: list[dict[str, Any]], key: str, value: dict[str, Any]) -> None:
    if not key:
        return
    turns.append(
        {
            "role": "state",
            "key": f"{_STATE_KEY_PREFIX}{key}",
            "value": value,
            "ts": datetime.utcnow().isoformat(),
        }
    )


def clear_state(turns: list[dict[str, Any]], key: str) -> None:
    if not key:
        return
    set_state(turns, key, {})
