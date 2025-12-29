from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import asyncio

from sqlalchemy.orm import Session

from app import models
from app.ai.intent import route_intent
from app.ai.safety import detect_risk, safe_response
from app.ai import rag_service
from app.ai.provider_factory import get_ai_provider
from app.db import SessionLocal, ensure_sqlite_schema, engine


EVAL_FILE = Path(__file__).resolve().parents[3] / "tests" / "eval_questions.json"


@dataclass(frozen=True)
class EvalCase:
    pharmacy_id: int
    query: str
    expected_intent: str
    expected_source_type: str
    expected_escalation: bool
    expected_unknown: bool


def _load_cases(path: Path) -> list[EvalCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []
    for item in raw:
        cases.append(
            EvalCase(
                pharmacy_id=int(item["pharmacy_id"]),
                query=str(item["query"]),
                expected_intent=str(item["expected_intent"]),
                expected_source_type=str(item["expected_source_type"]),
                expected_escalation=bool(item["expected_escalation"]),
                expected_unknown=bool(item["expected_unknown"]),
            )
        )
    return cases


def _primary_source_type(citations: list[dict[str, Any]] | list[Any]) -> str:
    if not citations:
        return "none"
    first = citations[0]
    if isinstance(first, dict):
        return str(first.get("source_type") or "none")
    return str(getattr(first, "source_type", "none"))


def _run_case(db: Session, case: EvalCase) -> dict[str, Any]:
    os.environ.setdefault("AI_PROVIDER", "stub")
    get_ai_provider.cache_clear()
    rag_service.ensure_pharmacy_playbook(db, case.pharmacy_id)
    db.commit()

    risky, reason = detect_risk(case.query)
    if risky:
        pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == case.pharmacy_id).first()
        answer = safe_response(pharmacy, reason)
        return {
            "intent": "MEDICAL_ADVICE_RISK",
            "answer": answer,
            "citations": [],
            "escalated": True,
        }

    intent_result = asyncio.run(route_intent(db, case.pharmacy_id, "eval", case.query, memory_context=None))
    return {
        "intent": intent_result.intent,
        "answer": intent_result.answer,
        "citations": [c.model_dump() for c in intent_result.citations],
        "escalated": bool(intent_result.escalated),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pharmacy_id", type=int, required=True)
    parser.add_argument("--file", type=str, default=str(EVAL_FILE))
    args = parser.parse_args()

    ensure_sqlite_schema(engine)
    path = Path(args.file)
    cases = [c for c in _load_cases(path) if c.pharmacy_id == args.pharmacy_id]
    if not cases:
        raise SystemExit(f"No cases found for pharmacy_id={args.pharmacy_id} in {path}")

    db = SessionLocal()
    try:
        passed = 0
        failed = 0
        for case in cases:
            out = _run_case(db, case)
            intent = out["intent"]
            escalated = bool(out["escalated"])
            citations = out.get("citations") or []
            unknown = (str(out.get("answer") or "").strip().lower() in {"i don't know", "i don't know."})
            source_type = _primary_source_type(citations)
            ok = True
            ok &= intent == case.expected_intent
            ok &= escalated == case.expected_escalation
            ok &= unknown == case.expected_unknown
            ok &= (source_type == case.expected_source_type)

            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {case.query}")
            if not ok:
                print(
                    f"  got intent={intent} source_type={source_type} escalated={escalated} unknown={unknown}"
                )
                print(
                    f"  exp intent={case.expected_intent} source_type={case.expected_source_type} "
                    f"escalated={case.expected_escalation} unknown={case.expected_unknown}"
                )
                failed += 1
            else:
                passed += 1

        total = passed + failed
        print(f"\nTotal: {total}  Passed: {passed}  Failed: {failed}")
        if failed:
            raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
