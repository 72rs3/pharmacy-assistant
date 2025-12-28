from __future__ import annotations

import hashlib
import json
import math
import re

from .base import AIProvider, ChatMessage


class StubProvider(AIProvider):
    """
    Deterministic provider for tests/dev when an external LLM is not configured.
    """

    name = "stub"
    dimensions = 16

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [b / 255.0 for b in digest[: self.dimensions]]
            out.append(vec)
        return out

    async def chat(self, messages: list[ChatMessage]) -> str:
        user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        match = re.search(r"\[doc_id=(\d+)\s+chunk_id=(\d+)[^\]]*\]\s*\n", user)
        doc_id = int(match.group(1)) if match else 0
        chunk_id = int(match.group(2)) if match else 0
        snippet = ""
        if match:
            start = match.end()
            end = user.find("\n\n[doc_id=", start)
            if end == -1:
                end = len(user)
            snippet = user[start:end].strip().replace("\n", " ")[:160]

        if snippet:
            answer = f"{snippet}"
        else:
            answer = "I don't know."

        payload = {
            "answer": answer,
            "citations": (
                [
                    {
                        "source_type": "document",
                        "title": "source",
                        "doc_id": doc_id,
                        "chunk_id": chunk_id,
                        "preview": snippet,
                        "last_updated_at": None,
                        "score": None,
                    }
                ]
                if (doc_id and chunk_id and snippet)
                else []
            ),
        }
        return json.dumps(payload, ensure_ascii=False)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)
