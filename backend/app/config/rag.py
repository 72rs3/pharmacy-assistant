from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RAGConfig:
    embeddings_enabled: bool = True
    retrieval_mode: str = "vector"  # vector | keyword | hybrid
    top_k: int = 6
    inventory_top_k: int = 4
    sources_max_chars: int = 6000
    min_score: float = 0.35
    min_score_short: float = 0.15


def _repo_backend_root() -> Path:
    # backend/app/config/rag.py -> backend/
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}

    # Minimal YAML reader for this repo's `backend/config/rag.yaml`.
    # Supports:
    # - top-level `rag:` mapping
    # - scalar `key: value` pairs under that mapping
    data: dict[str, Any] = {}
    rag: dict[str, Any] = {}
    in_rag = False
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not in_rag and stripped == "rag:":
            in_rag = True
            continue
        if in_rag:
            if not line.startswith("  "):
                in_rag = False
                continue
            kv = stripped.split(":", 1)
            if len(kv) != 2:
                continue
            key = kv[0].strip()
            val = kv[1].strip()
            if "#" in val:
                val = val.split("#", 1)[0].strip()
            if val.lower() in {"true", "false"}:
                rag[key] = val.lower() == "true"
            else:
                try:
                    rag[key] = int(val)
                except Exception:
                    try:
                        rag[key] = float(val)
                    except Exception:
                        rag[key] = val
    if rag:
        data["rag"] = rag
    return data


def _env_bool(key: str) -> bool | None:
    if key not in os.environ:
        return None
    val = (os.getenv(key) or "").strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    if val in {"0", "false", "no", "off"}:
        return False
    return None


def _env_int(key: str) -> int | None:
    if key not in os.environ:
        return None
    try:
        return int(os.getenv(key) or "")
    except Exception:
        return None


def _env_float(key: str) -> float | None:
    if key not in os.environ:
        return None
    try:
        return float(os.getenv(key) or "")
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_rag_config() -> RAGConfig:
    path = _repo_backend_root() / "config" / "rag.yaml"
    data = _load_yaml(path)
    rag = data.get("rag") if isinstance(data.get("rag"), dict) else {}

    cfg = RAGConfig(
        embeddings_enabled=bool(rag.get("embeddings_enabled", True)),
        retrieval_mode=str(rag.get("retrieval_mode", "vector") or "vector"),
        top_k=int(rag.get("top_k", 6) or 6),
        inventory_top_k=int(rag.get("inventory_top_k", 4) or 4),
        sources_max_chars=int(rag.get("sources_max_chars", 6000) or 6000),
        min_score=float(rag.get("min_score", 0.35) or 0.35),
        min_score_short=float(rag.get("min_score_short", 0.15) or 0.15),
    )

    env_embeddings_enabled = _env_bool("RAG_EMBEDDINGS_ENABLED")
    env_retrieval_mode = (os.getenv("RAG_RETRIEVAL_MODE") or "").strip().lower() if "RAG_RETRIEVAL_MODE" in os.environ else ""
    env_top_k = _env_int("RAG_TOP_K")
    env_inventory_top_k = _env_int("RAG_INVENTORY_TOP_K")
    env_sources_max_chars = _env_int("RAG_SOURCES_MAX_CHARS")
    env_min_score = _env_float("RAG_MIN_SCORE")
    env_min_score_short = _env_float("RAG_MIN_SCORE_SHORT")

    retrieval_mode = cfg.retrieval_mode.strip().lower()
    if env_retrieval_mode:
        retrieval_mode = env_retrieval_mode
    if retrieval_mode not in {"vector", "keyword", "hybrid"}:
        retrieval_mode = "vector"

    return RAGConfig(
        embeddings_enabled=(env_embeddings_enabled if env_embeddings_enabled is not None else cfg.embeddings_enabled),
        retrieval_mode=retrieval_mode,
        top_k=(env_top_k if env_top_k is not None else cfg.top_k),
        inventory_top_k=(env_inventory_top_k if env_inventory_top_k is not None else cfg.inventory_top_k),
        sources_max_chars=(env_sources_max_chars if env_sources_max_chars is not None else cfg.sources_max_chars),
        min_score=(env_min_score if env_min_score is not None else cfg.min_score),
        min_score_short=(env_min_score_short if env_min_score_short is not None else cfg.min_score_short),
    )
