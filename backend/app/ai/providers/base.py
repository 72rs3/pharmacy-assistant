from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system | user | assistant
    content: str


class EmbeddingsProvider(Protocol):
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChatProvider(Protocol):
    async def chat(self, messages: list[ChatMessage]) -> str: ...


class AIProvider(EmbeddingsProvider, ChatProvider, Protocol):
    name: str

