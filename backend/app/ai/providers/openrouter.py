from __future__ import annotations

import os

from .base import AIProvider, ChatMessage
from app.ai.openrouter_client import openrouter_chat, openrouter_embed


class OpenRouterProvider(AIProvider):
    name = "openrouter"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        self.chat_model = (
            (os.getenv("OPENROUTER_MAIN_MODEL") or "").strip()
            or (os.getenv("OPENROUTER_CHAT_MODEL") or "").strip()
            or "meta-llama/llama-3.3-70b-instruct:free"
        )
        self.embed_model = os.getenv("OPENROUTER_EMBED_MODEL", "openai/text-embedding-3-small")
        self.dimensions = int(os.getenv("OPENROUTER_EMBED_DIM", "1536"))
        self.http_referer = (os.getenv("OPENROUTER_HTTP_REFERER") or "").strip() or None
        self.x_title = (os.getenv("OPENROUTER_X_TITLE") or "").strip() or None
        self.timeout_s = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", os.getenv("OPENROUTER_TIMEOUT_S", "60")))
        self.max_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "400"))

        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")

    async def aclose(self) -> None:
        return

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await openrouter_embed(model=self.embed_model, texts=texts)

    async def chat(self, messages: list[ChatMessage]) -> str:
        return await openrouter_chat(
            model=self.chat_model,
            messages=messages,
            temperature=float(os.getenv("OPENROUTER_TEMPERATURE", "0.2")),
            max_tokens=self.max_tokens,
        )
