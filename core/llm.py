"""Minimal OpenAI-compatible LLM client for chat completions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_MODEL = "gpt-4o-mini"
OPENAI_BASE = "https://api.openai.com/v1"
MAX_CONTENT_LEN = 4096


def _parse_usage(data: dict[str, Any]) -> dict[str, Any]:
    usage = (data.get("usage") or {})
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


def read_secret(secrets_dir: Path, filename: str) -> str | None:
    """Read first line of a secret file; return None if missing or empty."""
    path = secrets_dir / filename
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    return raw if raw else None


def complete(
    messages: list[dict[str, str]],
    api_key: str,
    *,
    base_url: str | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 512,
) -> tuple[str, dict[str, Any]]:
    """
    Call OpenAI-compatible chat completions API.
    Returns (content, usage) where usage has prompt_tokens, completion_tokens, total_tokens.
    base_url: e.g. https://api.openai.com/v1 or http://localhost:11434/v1 (Ollama).
    """
    url = (base_url or OPENAI_BASE).rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    encoded = json.dumps(body).encode("utf-8")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = request.Request(url, data=encoded, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body_read = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API HTTP {exc.code}: {body_read}") from exc

    content: str | None = None
    for choice in data.get("choices") or []:
        msg = choice.get("message") or {}
        if "content" in msg:
            content = msg["content"]
            break
    if content is None:
        raise RuntimeError(f"LLM API unexpected response: {data}")
    if len(content) > MAX_CONTENT_LEN:
        content = content[: MAX_CONTENT_LEN - 3] + "..."
    usage = _parse_usage(data)
    return content.strip(), usage
