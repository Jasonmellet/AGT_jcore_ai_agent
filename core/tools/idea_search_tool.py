"""Tier 1: semantic search across idea and transcript memory."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.llm import read_secret
from core.memory.embedding_service import DEFAULT_EMBED_MODEL, EmbeddingService
from core.memory.vector_memory import VectorMemoryStore
from core.policy import ToolTier
from core.tools.base import BaseTool, ToolExecutionResult


class IdeaSearchTool(BaseTool):
    name = "idea_search"
    tier = ToolTier.TIER1

    def __init__(self, *, db_path: Path, secrets_dir: Path) -> None:
        self._db_path = db_path
        self._secrets_dir = secrets_dir

    def execute(self, payload: dict[str, Any]) -> ToolExecutionResult:
        query = str(payload.get("query", "")).strip()
        if not query:
            return ToolExecutionResult(ok=False, output={"error": "Missing query"})
        limit_raw = int(payload.get("limit", 8) or 8)
        limit = max(1, min(25, limit_raw))
        scope = str(payload.get("scope", "all")).strip().lower()
        scope_map = {
            "all": None,
            "ideas": ["project_idea"],
            "transcripts": ["telegram_message"],
        }
        if scope not in scope_map:
            return ToolExecutionResult(ok=False, output={"error": "scope must be one of: all, ideas, transcripts"})

        api_key = read_secret(self._secrets_dir, "llm_api_key.txt") or read_secret(
            self._secrets_dir, "openai_api_key.txt"
        )
        if not api_key:
            return ToolExecutionResult(ok=False, output={"error": "LLM API key missing for embeddings"})
        base_url = read_secret(self._secrets_dir, "llm_base_url.txt")
        model = read_secret(self._secrets_dir, "embedding_model.txt") or DEFAULT_EMBED_MODEL
        embedder = EmbeddingService(api_key, base_url=base_url, model=model)

        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            vector_store = VectorMemoryStore(conn)
            query_embedding = embedder.embed(query)
            matches = vector_store.search(
                query_embedding=query_embedding,
                source_kinds=scope_map[scope],
                limit=limit,
            )
        finally:
            conn.close()

        return ToolExecutionResult(
            ok=True,
            output={
                "query": query,
                "scope": scope,
                "embedding_model": model,
                "matches": matches,
            },
        )
