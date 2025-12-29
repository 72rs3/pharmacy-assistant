from __future__ import annotations

import json
from typing import Any

from sqlalchemy.types import TypeDecorator, TEXT, UserDefinedType


class _Vector(UserDefinedType):
    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dimensions})"


class Embedding(TypeDecorator):
    """
    Cross-dialect embedding type.

    - Postgres: pgvector `vector(dim)`
    - SQLite/others: TEXT storing JSON
    """

    cache_ok = True
    impl = TEXT

    def __init__(self, dimensions: int):
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_Vector(self.dimensions))
        return dialect.type_descriptor(TEXT())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            # pgvector literal format: "[1,2,3]"
            return "[" + ",".join(f"{float(x):.8f}" for x in value) + "]"
        return json.dumps([float(x) for x in value])

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return [float(x) for x in value]
        try:
            if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                if not inner:
                    return []
                return [float(x) for x in inner.split(",")]
            return json.loads(value)
        except Exception:
            return None

