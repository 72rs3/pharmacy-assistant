import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from app.utils.rate_limit import reset_rate_limits


@pytest.fixture(autouse=True)
def clear_rate_limits():
    reset_rate_limits()
    yield
    reset_rate_limits()
