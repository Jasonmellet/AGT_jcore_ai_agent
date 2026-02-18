"""OpenAI-compatible embeddings client."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from core.llm import OPENAI_BASE

DEFAULT_EMBED_MODEL = "text-embedding-3-small"


class EmbeddingService:
    def __init__(self, api_key: str, *, base_url: str | None = None, model: str = DEFAULT_EMBED_MODEL) -> None:
        self._api_key = api_key
        self._base_url = (base_url or OPENAI_BASE).rstrip("/")
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            return []
        payload = {
            "model": self._model,
            "input": text,
        }
        encoded = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        req = request.Request(
            self._base_url + "/embeddings",
            data=encoded,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Embeddings API HTTP {exc.code}: {body}") from exc

        rows = data.get("data") or []
        if not rows:
            raise RuntimeError(f"Embeddings API returned no vectors: {data}")
        vector = rows[0].get("embedding")
        if not isinstance(vector, list):
            raise RuntimeError(f"Embeddings API returned invalid vector: {data}")
        return [float(v) for v in vector]


def chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    if len(raw) <= chunk_size:
        return [raw]
    out: list[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(raw):
        out.append(raw[start : start + chunk_size])
        start += step
    return out
