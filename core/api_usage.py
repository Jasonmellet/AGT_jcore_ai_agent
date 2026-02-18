"""Persistent API usage tracking (e.g. LLM tokens per profile)."""

from __future__ import annotations

import sqlite3
from typing import Any


class ApiUsageStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(
        self,
        profile_name: str,
        caller: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO api_usage (profile_name, caller, model, prompt_tokens, completion_tokens, total_tokens)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                profile_name,
                caller,
                model,
                int(prompt_tokens),
                int(completion_tokens),
                int(prompt_tokens) + int(completion_tokens),
            ),
        )
        self._conn.commit()

    def summary(self, *, window_days: int | None = None) -> dict[str, Any]:
        where = ""
        params: tuple[Any, ...] = ()
        if window_days is not None:
            safe_days = max(1, min(365, int(window_days)))
            where = "WHERE created_at >= datetime('now', ?)"
            params = (f"-{safe_days} days",)

        totals = self._conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_calls,
                COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM api_usage
            {where}
            """,
            params,
        ).fetchone()
        by_model_rows = self._conn.execute(
            f"""
            SELECT model, COUNT(*) AS calls, COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM api_usage
            {where}
            GROUP BY model
            ORDER BY total_tokens DESC
            """,
            params,
        ).fetchall()
        by_caller_rows = self._conn.execute(
            f"""
            SELECT caller, COUNT(*) AS calls, COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM api_usage
            {where}
            GROUP BY caller
            ORDER BY total_tokens DESC
            """,
            params,
        ).fetchall()
        recent_rows = self._conn.execute(
            """
            SELECT profile_name, caller, model, prompt_tokens, completion_tokens, total_tokens, created_at
            FROM api_usage
            ORDER BY id DESC
            LIMIT 25
            """
        ).fetchall()

        total_calls = int(totals["total_calls"]) if totals else 0
        total_prompt = int(totals["total_prompt_tokens"]) if totals else 0
        total_completion = int(totals["total_completion_tokens"]) if totals else 0
        return {
            "enabled": True,
            "total_calls": total_calls,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "window_days": window_days,
            "by_model": [dict(r) for r in by_model_rows],
            "by_caller": [dict(r) for r in by_caller_rows],
            "recent_calls": [dict(r) for r in recent_rows],
        }
