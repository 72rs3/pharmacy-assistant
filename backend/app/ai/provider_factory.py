from __future__ import annotations

import os
from functools import lru_cache

from app.ai.providers.base import AIProvider
from app.ai.providers.openrouter import OpenRouterProvider
from app.ai.providers.stub import StubProvider


@lru_cache(maxsize=1)
def get_ai_provider() -> AIProvider:
    provider_name = (os.getenv("AI_PROVIDER") or "openrouter").strip().lower()
    if provider_name == "stub":
        return StubProvider()
    if provider_name == "openrouter":
        return OpenRouterProvider()
    raise RuntimeError(f"Unsupported AI_PROVIDER: {provider_name}")
