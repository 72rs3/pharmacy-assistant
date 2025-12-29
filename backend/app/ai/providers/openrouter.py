from __future__ import annotations

import os

import httpx

from .base import AIProvider, ChatMessage


class OpenRouterProvider(AIProvider):
    name = "openrouter"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        self.chat_model = os.getenv("OPENROUTER_CHAT_MODEL", "deepseek/deepseek-r1-0528:free")
        self.embed_model = os.getenv("OPENROUTER_EMBED_MODEL", "text-embedding-3-small")
        self.dimensions = int(os.getenv("OPENROUTER_EMBED_DIM", "1536"))
        self.http_referer = (os.getenv("OPENROUTER_HTTP_REFERER") or "").strip() or None
        self.x_title = (os.getenv("OPENROUTER_X_TITLE") or "").strip() or None
        self.timeout_s = float(os.getenv("OPENROUTER_TIMEOUT_S", "60"))
        self.max_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "400"))

        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_s,
            headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer
        if self.x_title:
            headers["X-Title"] = self.x_title
        return headers

    @staticmethod
    def _raise_openrouter_error(res: httpx.Response) -> None:
        try:
            payload = res.json()
            message = payload.get("error", {}).get("message") or payload.get("message") or res.text
        except Exception:
            message = res.text
        raise RuntimeError(f"OpenRouter API error ({res.status_code}): {message}")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        res = await self._client.post(
            "/embeddings",
            json={"model": self.embed_model, "input": texts},
        )
        if res.status_code >= 400:
            self._raise_openrouter_error(res)
        data = res.json()
        return [item["embedding"] for item in data["data"]]

    async def chat(self, messages: list[ChatMessage]) -> str:
        payload_messages = [{"role": m.role, "content": m.content} for m in messages]
        res = await self._client.post(
            "/chat/completions",
            json={
                "model": self.chat_model,
                "messages": payload_messages,
                "temperature": float(os.getenv("OPENROUTER_TEMPERATURE", "0.2")),
                "max_tokens": self.max_tokens,
            },
        )
        if res.status_code >= 400:
            self._raise_openrouter_error(res)
        data = res.json()
        return data["choices"][0]["message"]["content"]
