import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from app import schemas
from app.ai.tool_executor import ToolContext
from app.routes.ai_routes import _enforce_action_policy


def test_rx_medicine_never_returns_add_to_cart_action():
    tool_ctx = ToolContext(
        intent="MEDICINE_SEARCH",
        language="en",
        found=True,
        items=[{"id": 10, "name": "Amoxicillin", "rx": True, "stock": 110}],
        suggestions=[],
        citations=[],
        snippets=[],
        cards=[schemas.MedicineCard(medicine_id=10, name="Amoxicillin", dosage="250mg", category=None, rx=True, price=45.0, stock=110)],
        quick_replies=[],
    )
    actions = [
        schemas.AIAction(type="add_to_cart", label="Add Amoxicillin to cart", medicine_id=10, payload={"medicine_id": 10, "quantity": 1}),
    ]
    fixed = _enforce_action_policy(tool_ctx, actions)
    assert all(a.type != "add_to_cart" for a in fixed)
    assert any(a.type == "upload_prescription" for a in fixed)


def test_otc_out_of_stock_removes_add_to_cart_action():
    tool_ctx = ToolContext(
        intent="MEDICINE_SEARCH",
        language="en",
        found=True,
        items=[{"id": 5, "name": "Panadol", "rx": False, "stock": 0}],
        suggestions=[],
        citations=[],
        snippets=[],
        cards=[schemas.MedicineCard(medicine_id=5, name="Panadol", dosage="500mg", category=None, rx=False, price=5.0, stock=0)],
        quick_replies=[],
    )
    actions = [
        schemas.AIAction(type="add_to_cart", label="Add to cart", medicine_id=5, payload={"medicine_id": 5, "quantity": 1}),
    ]
    fixed = _enforce_action_policy(tool_ctx, actions)
    assert all(a.type != "add_to_cart" for a in fixed)

