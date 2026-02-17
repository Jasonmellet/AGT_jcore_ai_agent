"""In-memory API usage tracking (e.g. LLM tokens per profile)."""

from __future__ import annotations

from typing import Any


class ApiUsageStore:
    def __init__(self) -> None:
        self._calls: list[dict[str, Any]] = []

    def record(
        self,
        profile_name: str,
        caller: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        self._calls.append({
            "profile": profile_name,
            "caller": caller,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        })

    def summary(self) -> dict[str, Any]:
        total_calls = len(self._calls)
        total_prompt = sum(c["prompt_tokens"] for c in self._calls)
        total_completion = sum(c["completion_tokens"] for c in self._calls)
        return {
            "enabled": True,
            "total_calls": total_calls,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
        }
