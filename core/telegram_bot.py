"""Telegram bot using python-telegram-bot with pairing, allowlist, and resilient chat mode."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections import deque
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core.llm import complete as llm_complete
from core.llm import read_secret
from core.memory.embedding_service import DEFAULT_EMBED_MODEL, EmbeddingService, chunk_text
from core.memory.episodic_memory import EpisodicMemoryStore
from core.memory.project_memory import ProjectMemoryStore
from core.memory.profile_memory import ProfileMemoryStore
from core.memory.transcript_memory import TranscriptMemoryStore
from core.memory.vector_memory import VectorMemoryStore
from core.profile import Profile

CONVERSATION_MAX_TURNS = 10
MAX_TELEGRAM_MESSAGE_LEN = 3900
DEFAULT_CHAT_MODE = "chat"
DEFAULT_LLM_TIMEOUT_SECONDS = 20


def _truncate(text: str) -> str:
    if len(text) <= MAX_TELEGRAM_MESSAGE_LEN:
        return text
    return text[: MAX_TELEGRAM_MESSAGE_LEN - 3] + "..."


class TelegramBot:
    def __init__(
        self,
        profile: Profile,
        episodic_memory: EpisodicMemoryStore,
        profile_memory: ProfileMemoryStore,
        api_usage_store: Any = None,
    ) -> None:
        self._profile = profile
        self._episodic = episodic_memory
        self._profile_memory = profile_memory
        self._api_usage_store = api_usage_store
        self._token: str | None = None
        self._started_at = 0.0
        self._llm_api_key: str | None = None
        self._llm_key_source: str = "none"
        self._llm_base_url: str | None = None
        self._llm_model: str = profile.llm_default_model
        self._embedding_model: str = DEFAULT_EMBED_MODEL
        self._llm_timeout_seconds: int = DEFAULT_LLM_TIMEOUT_SECONDS
        self._embedding_service: EmbeddingService | None = None
        self._conversations: dict[int, deque[dict[str, str]]] = {}
        self._allowlist_path = profile.paths.secrets_dir / "telegram_allowlist_chat_ids.txt"
        self._pairing_code_path = profile.paths.secrets_dir / "telegram_pairing_code.txt"
        self._allowed_chat_ids: set[int] = set()
        self._pairing_code: str | None = None
        self._app: Application | None = None

    @property
    def enabled(self) -> bool:
        return self._token is not None

    def _record_in_db(self, event_type: str, payload: dict[str, Any], decision: str = "allow") -> None:
        """Record an episodic event using a fresh connection (handler may run in library thread)."""
        conn = sqlite3.connect(str(self._profile.paths.db_path))
        conn.row_factory = sqlite3.Row
        try:
            store = EpisodicMemoryStore(conn)
            store.record(event_type, payload, decision=decision)
            conn.commit()
        finally:
            conn.close()

    def _record_transcript(
        self,
        *,
        chat_id: int,
        direction: str,
        text: str,
        message_type: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        if not text:
            return 0
        conn = sqlite3.connect(str(self._profile.paths.db_path))
        conn.row_factory = sqlite3.Row
        try:
            store = TranscriptMemoryStore(conn)
            message_id = store.record(
                chat_id=chat_id,
                direction=direction,
                text=text,
                message_type=message_type,
                source="telegram",
                metadata=metadata,
            )
            if self._embedding_service is not None:
                self._embed_text(
                    conn=conn,
                    source_kind="telegram_message",
                    source_id=message_id,
                    source_ref=f"chat:{chat_id}:{direction}",
                    text=text,
                )
            conn.commit()
            return message_id
        finally:
            conn.close()

    def _capture_inbound(self, update: Update, *, message_type: str = "text") -> None:
        chat_id = update.effective_chat.id if update.effective_chat else 0
        message = update.effective_message
        if message is None:
            return
        text = (message.text or message.caption or "").strip()
        if not text:
            text = f"[{message_type}]"
        self._record_transcript(
            chat_id=chat_id,
            direction="inbound",
            text=text,
            message_type=message_type,
            metadata={"profile": self._profile.name},
        )

    async def _reply_text(self, update: Update, text: str, *, message_type: str = "text") -> None:
        if update.effective_message is None:
            return
        await update.effective_message.reply_text(text)
        chat_id = update.effective_chat.id if update.effective_chat else 0
        self._record_transcript(
            chat_id=chat_id,
            direction="outbound",
            text=text,
            message_type=message_type,
            metadata={"profile": self._profile.name},
        )

    def _embed_text(
        self,
        *,
        conn: sqlite3.Connection,
        source_kind: str,
        source_id: int,
        source_ref: str | None,
        text: str,
    ) -> None:
        if self._embedding_service is None:
            return
        chunks = chunk_text(text)
        if not chunks:
            return
        out: list[tuple[int, str, list[float]]] = []
        for idx, chunk in enumerate(chunks):
            try:
                embedding = self._embedding_service.embed(chunk)
            except Exception as exc:
                self._record_in_db(
                    "telegram_embedding_error",
                    {"source_kind": source_kind, "source_id": source_id, "error": str(exc)},
                    decision="deny",
                )
                return
            if embedding:
                out.append((idx, chunk, embedding))
        if not out:
            return
        vectors = VectorMemoryStore(conn)
        vectors.replace_chunks(
            source_kind=source_kind,
            source_id=source_id,
            source_ref=source_ref,
            chunks=out,
            embedding_model=self._embedding_model,
        )

    def _load_token(self) -> str | None:
        path = self._profile.paths.secrets_dir / "telegram_bot_token.txt"
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8").strip()
        return raw if raw else None

    def _load_llm_config(self) -> None:
        secrets = self._profile.paths.secrets_dir
        llm_key = read_secret(secrets, "llm_api_key.txt")
        openai_key = read_secret(secrets, "openai_api_key.txt")
        self._llm_api_key = llm_key or openai_key
        self._llm_key_source = "llm_api_key.txt" if llm_key else ("openai_api_key.txt" if openai_key else "none")
        self._llm_base_url = read_secret(secrets, "llm_base_url.txt") if self._llm_api_key else None
        model = read_secret(secrets, "llm_model.txt")
        if model:
            self._llm_model = model
        embed_model = read_secret(secrets, "embedding_model.txt")
        if embed_model:
            self._embedding_model = embed_model
        timeout_raw = read_secret(secrets, "llm_timeout_seconds.txt")
        if timeout_raw and timeout_raw.isdigit():
            self._llm_timeout_seconds = max(5, min(120, int(timeout_raw)))
        self._embedding_service = None
        if self._llm_api_key:
            self._embedding_service = EmbeddingService(
                self._llm_api_key,
                base_url=self._llm_base_url,
                model=self._embedding_model,
            )

    def _load_security_config(self) -> None:
        self._allowed_chat_ids = self._read_allowlist()
        self._pairing_code = read_secret(self._profile.paths.secrets_dir, "telegram_pairing_code.txt")

    def _read_allowlist(self) -> set[int]:
        if not self._allowlist_path.exists():
            return set()
        out: set[int] = set()
        for line in self._allowlist_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.add(int(line))
            except ValueError:
                continue
        return out

    def _write_allowlist(self, chat_ids: set[int]) -> None:
        self._allowlist_path.parent.mkdir(parents=True, exist_ok=True)
        self._allowlist_path.write_text(
            "\n".join(str(c) for c in sorted(chat_ids)) + "\n",
            encoding="utf-8",
        )
        self._allowlist_path.chmod(0o600)

    def _is_chat_allowed(self, chat_id: int) -> bool:
        if len(self._allowed_chat_ids) == 0:
            return False
        return chat_id in self._allowed_chat_ids

    def start(self) -> bool:
        token = self._load_token()
        if token is None:
            return False
        self._token = token
        self._started_at = time.time()
        self._load_llm_config()
        self._load_security_config()

        self._app = (
            Application.builder()
            .token(token)
            .post_init(self._post_init)
            .build()
        )
        self._setup_handlers()

        self._episodic.record(
            "telegram_bot_started",
            {
                "profile": self._profile.name,
                "llm_enabled": self._llm_api_key is not None,
                "allowlist_size": len(self._allowed_chat_ids),
                "pairing_required": len(self._allowed_chat_ids) == 0,
            },
            decision="allow",
        )
        if len(self._allowed_chat_ids) == 0:
            self._episodic.record(
                "telegram_pair_required",
                {"profile": self._profile.name, "pairing_code_present": self._pairing_code is not None},
                decision="require_approval",
            )

        # Run polling in main thread (like Pepper); signal handlers only work there.
        asyncio.run(
            self._app.run_polling(drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)
        )
        return True

    async def _post_init(self, app: Application) -> None:
        await app.bot.set_my_commands([])

    def stop(self) -> None:
        if self._app is not None:
            self._app.stop()
        self._app = None
        if self._token:
            self._episodic.record(
                "telegram_bot_stopped",
                {"profile": self._profile.name},
                decision="allow",
            )
        self._token = None

    def _setup_handlers(self) -> None:
        assert self._app is not None
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("ping", self._cmd_ping))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("whoami", self._cmd_whoami))
        self._app.add_handler(CommandHandler("health", self._cmd_health))
        self._app.add_handler(CommandHandler("logs", self._cmd_logs))
        self._app.add_handler(CommandHandler("mode", self._cmd_mode))
        self._app.add_handler(CommandHandler("pair", self._cmd_pair))
        self._app.add_handler(CommandHandler("idea", self._cmd_idea))
        self._app.add_handler(CommandHandler("ideas", self._cmd_ideas))
        self._app.add_handler(CommandHandler("idea_search", self._cmd_idea_search))
        self._app.add_handler(CommandHandler("whatsnew", self._cmd_whatsnew))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text)
        )
        self._app.add_handler(
            MessageHandler(~filters.TEXT & ~filters.COMMAND, self._handle_unsupported)
        )

    async def _guard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Return True if chat is allowed or was just paired; otherwise send lock message and return False."""
        self._capture_inbound(update)
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return False
        text = (update.effective_message.text or "").strip() if update.effective_message else ""
        if self._is_chat_allowed(chat_id):
            return True
        if text.lower().startswith("/pair "):
            return True
        msg = "This bot is locked. Pair first with: /pair <code>" if self._pairing_code else "This bot is locked and pairing code is not configured."
        await self._reply_text(update, msg)
        self._record_in_db(
            "telegram_message_denied",
            {"chat_id": chat_id, "reason": "chat_not_allowlisted"},
            decision="deny",
        )
        return False

    async def _cmd_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._capture_inbound(update)
        chat_id = update.effective_chat.id
        text = (update.effective_message.text or "").strip()
        parts = text.split(maxsplit=1)
        code = parts[1].strip() if len(parts) > 1 else ""
        if not self._pairing_code or code != self._pairing_code:
            await self._reply_text(update, "Invalid or missing pairing code.")
            return
        self._allowed_chat_ids.add(chat_id)
        self._write_allowlist(self._allowed_chat_ids)
        await self._reply_text(update, "Pairing successful. This chat is now allowed.")
        self._record_in_db(
            "telegram_paired",
            {"chat_id": chat_id, "profile": self._profile.name},
            decision="allow",
        )

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        msg = (
            f"{self._profile.display_name} online.\n"
            "Commands: /help, /ping, /status, /whoami, /health, /logs, /mode, /idea, /ideas, /idea_search"
        )
        await self._reply_text(update, msg)
        self._record_in_db("telegram_command_handled", {"chat_id": update.effective_chat.id, "command": "start"}, decision="allow")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        msg = (
            "/ping - connectivity\n"
            "/status - runtime profile status\n"
            "/whoami - profile identity\n"
            "/health - health summary\n"
            "/logs [N] - recent events\n"
            "/mode [chat|command] - set or view input mode\n"
            "/idea <text> - capture idea\n"
            "/ideas [N] - list latest ideas\n"
            "/idea_search <query> - semantic idea search\n"
            "/whatsnew - latest features and capabilities"
        )
        await self._reply_text(update, msg)
        self._record_in_db("telegram_command_handled", {"chat_id": update.effective_chat.id, "command": "help"}, decision="allow")

    async def _cmd_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        chat_id = update.effective_chat.id
        text = (update.effective_message.text or "").strip()
        parts = text.split(maxsplit=1)
        if len(parts) == 1:
            mode = self._get_chat_mode(chat_id)
            await self._reply_text(update, f"mode={mode}")
            return
        requested = parts[1].strip().lower()
        if requested not in {"chat", "command"}:
            await self._reply_text(update, "Usage: /mode chat or /mode command")
            return
        self._set_chat_mode(chat_id, requested)
        await self._reply_text(update, f"mode set to {requested}")
        self._record_in_db(
            "telegram_chat_mode_changed",
            {"chat_id": chat_id, "mode": requested},
            decision="allow",
        )

    async def _cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        await self._reply_text(update, f"pong ({self._profile.name})")
        self._record_in_db("telegram_command_handled", {"chat_id": update.effective_chat.id, "command": "ping"}, decision="allow")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        msg = (
            f"profile={self._profile.name}\n"
            f"policy_tier={self._profile.policy_tier}\n"
            f"runtime=online\nllm={'on' if self._llm_api_key else 'off'}\n"
            f"llm_model={self._llm_model}\n"
            f"llm_key_source={self._llm_key_source}\n"
            f"allowlist_size={len(self._allowed_chat_ids)}"
        )
        await self._reply_text(update, msg)
        self._record_in_db("telegram_command_handled", {"chat_id": update.effective_chat.id, "command": "status"}, decision="allow")

    async def _cmd_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        msg = f"profile={self._profile.name}\ndisplay_name={self._profile.display_name}"
        await self._reply_text(update, msg)
        self._record_in_db("telegram_command_handled", {"chat_id": update.effective_chat.id, "command": "whoami"}, decision="allow")

    async def _cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        msg = (
            "status=ok\n"
            f"profile={self._profile.name}\n"
            f"uptime={int(time.time() - self._started_at)}"
        )
        await self._reply_text(update, msg)
        self._record_in_db("telegram_command_handled", {"chat_id": update.effective_chat.id, "command": "health"}, decision="allow")

    async def _cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        text = (update.effective_message.text or "").strip()
        parts = text.split()
        limit = 10
        if len(parts) > 1 and parts[1].isdigit():
            limit = max(1, min(20, int(parts[1])))
        conn = sqlite3.connect(str(self._profile.paths.db_path))
        conn.row_factory = sqlite3.Row
        try:
            store = EpisodicMemoryStore(conn)
            events = store.latest(limit=limit)
        finally:
            conn.close()
        if not events:
            await self._reply_text(update, "No events yet.")
        else:
            lines = [f"{e['id']} {e['created_at']} {e['event_type']}" for e in events]
            await self._reply_text(update, _truncate("\n".join(lines)))
        self._record_in_db("telegram_command_handled", {"chat_id": update.effective_chat.id, "command": "logs"}, decision="allow")

    def _create_idea_record(self, *, chat_id: int, text: str, source: str) -> int:
        title = text.strip().splitlines()[0][:80] if text.strip() else "Idea"
        conn = sqlite3.connect(str(self._profile.paths.db_path))
        conn.row_factory = sqlite3.Row
        try:
            projects = ProjectMemoryStore(conn)
            project_id = projects.create(
                title=title or "Idea",
                body=text.strip() or "(empty idea)",
                status="idea",
            )
            if self._embedding_service is not None:
                self._embed_text(
                    conn=conn,
                    source_kind="project_idea",
                    source_id=project_id,
                    source_ref=f"chat:{chat_id}:{source}",
                    text=text,
                )
            conn.commit()
            return project_id
        finally:
            conn.close()

    async def _cmd_idea(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        text = (update.effective_message.text or "").strip()
        parts = text.split(maxsplit=1)
        idea_text = parts[1].strip() if len(parts) > 1 else ""
        if not idea_text:
            await self._reply_text(update, "Usage: /idea <text>")
            return
        chat_id = update.effective_chat.id
        idea_id = self._create_idea_record(chat_id=chat_id, text=idea_text, source="command")
        await self._reply_text(update, f"Idea saved: id={idea_id}")
        self._record_in_db(
            "idea_captured",
            {"chat_id": chat_id, "idea_id": idea_id, "source": "command"},
            decision="allow",
        )

    async def _cmd_ideas(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        text = (update.effective_message.text or "").strip()
        parts = text.split()
        limit = 10
        if len(parts) > 1 and parts[1].isdigit():
            limit = max(1, min(30, int(parts[1])))
        conn = sqlite3.connect(str(self._profile.paths.db_path))
        conn.row_factory = sqlite3.Row
        try:
            projects = ProjectMemoryStore(conn)
            ideas = projects.latest(limit=limit, status="idea")
        finally:
            conn.close()
        if not ideas:
            await self._reply_text(update, "No ideas saved yet.")
            return
        lines = [f"{item['id']} {item['updated_at']} {item['title']}" for item in ideas]
        await self._reply_text(update, _truncate("\n".join(lines)))

    async def _cmd_idea_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        text = (update.effective_message.text or "").strip()
        parts = text.split(maxsplit=1)
        query = parts[1].strip() if len(parts) > 1 else ""
        if not query:
            await self._reply_text(update, "Usage: /idea_search <query>")
            return
        conn = sqlite3.connect(str(self._profile.paths.db_path))
        conn.row_factory = sqlite3.Row
        try:
            if self._embedding_service is None:
                ideas = ProjectMemoryStore(conn).search_like(query, limit=10)
                if not ideas:
                    await self._reply_text(update, "No matching ideas.")
                    return
                lines = [f"{item['id']} {item['title']}" for item in ideas]
                await self._reply_text(update, _truncate("\n".join(lines)))
                return
            query_embedding = self._embedding_service.embed(query)
            matches = VectorMemoryStore(conn).search(
                query_embedding=query_embedding,
                source_kinds=["project_idea"],
                limit=8,
            )
        finally:
            conn.close()
        if not matches:
            await self._reply_text(update, "No semantic matches yet.")
            return
        lines = [
            f"{m['source_kind']}#{m['source_id']} score={m['score']:.3f} {m['text_chunk'][:90]}"
            for m in matches
        ]
        await self._reply_text(update, _truncate("\n".join(lines)))

    async def _cmd_whatsnew(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        path = self._profile.paths.base_data_dir / "release_notes_latest.txt"
        if not path.exists():
            await self._reply_text(update, "No release notes yet. Ask me what I can do!")
            return
        try:
            text = path.read_text(encoding="utf-8").strip()
            await self._reply_text(update, _truncate(text))
        except Exception:
            await self._reply_text(update, "Could not read release notes.")
        self._record_in_db("telegram_command_handled", {"chat_id": update.effective_chat.id, "command": "whatsnew"}, decision="allow")

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update, context):
            return
        chat_id = update.effective_chat.id
        text = (update.effective_message.text or "").strip()
        if "#ideaengine" in text.lower():
            idea_id = self._create_idea_record(chat_id=chat_id, text=text, source="tag")
            ack = f"[ideaengine] captured idea id={idea_id}"
            await self._reply_text(update, ack)
            self._record_in_db(
                "idea_captured",
                {"chat_id": chat_id, "idea_id": idea_id, "source": "tag"},
                decision="allow",
            )
        chat_mode = self._get_chat_mode(chat_id)
        if chat_mode == "command":
            reply = "Command mode active. Use slash commands, or run /mode chat to resume conversation."
            await self._reply_text(update, _truncate(reply))
            self._record_in_db(
                "telegram_text_blocked_command_mode",
                {"chat_id": chat_id, "text": text[:200]},
                decision="allow",
            )
            return
        reply = await self._reply_for_text(chat_id, text)
        await self._reply_text(update, _truncate(reply))
        self._record_in_db(
            "telegram_message_processed",
            {"chat_id": chat_id, "text": text[:200]},
            decision="allow",
        )

    async def _reply_for_text(self, chat_id: int, text: str) -> str:
        if self._llm_api_key:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._llm_reply, chat_id, text),
                    timeout=self._llm_timeout_seconds,
                )
            except asyncio.TimeoutError:
                self._record_in_db(
                    "telegram_update_error",
                    {"chat_id": chat_id, "error": "LLM timeout"},
                    decision="deny",
                )
                return "[status=degraded] I am running but the model timed out. Try again in a moment."
        return (
            f"[status=local_only] {self._profile.display_name} here. I received your message; "
            "I don't have an LLM configured on this node so I can't reply with a full answer. "
            "Use /help for commands, or add an LLM API key to get conversational replies."
        )

    def _chat_mode_key(self, chat_id: int) -> str:
        return f"telegram_chat_mode_{chat_id}"

    def _open_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._profile.paths.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _get_chat_mode(self, chat_id: int) -> str:
        conn = self._open_db()
        try:
            profile = ProfileMemoryStore(conn)
            raw = profile.get_fact(self._chat_mode_key(chat_id))
            if raw in {"chat", "command"}:
                return raw
            return DEFAULT_CHAT_MODE
        finally:
            conn.close()

    def _set_chat_mode(self, chat_id: int, mode: str) -> None:
        conn = self._open_db()
        try:
            profile = ProfileMemoryStore(conn)
            profile.set_fact(self._chat_mode_key(chat_id), mode)
        finally:
            conn.close()

    def _build_memory_context(self, chat_id: int) -> str:
        conn = self._open_db()
        try:
            profile_store = ProfileMemoryStore(conn)
            project_store = ProjectMemoryStore(conn)
            episodic_store = EpisodicMemoryStore(conn)

            facts = [
                f"{f['key']}={f['value']}"
                for f in profile_store.list_facts()
                if not str(f["key"]).startswith("telegram_chat_mode_")
            ][:8]

            projects = project_store.list_all()[:3]
            project_lines = [
                f"{p['id']}:{p['title']}[{p['status']}] {str(p['body'])[:120]}"
                for p in projects
            ]

            events = episodic_store.latest(limit=5)
            event_lines = [f"{e['event_type']}@{e['created_at']}" for e in events]
        finally:
            conn.close()

        sections: list[str] = []
        if facts:
            sections.append("ProfileFacts: " + "; ".join(facts))
        if project_lines:
            sections.append("ProjectMemory: " + " | ".join(project_lines))
        if event_lines:
            sections.append("RecentEvents: " + " | ".join(event_lines))
        sections.append(f"ChatMode: {self._get_chat_mode(chat_id)}")
        release_notes_path = self._profile.paths.base_data_dir / "release_notes_latest.txt"
        if release_notes_path.exists():
            try:
                notes = release_notes_path.read_text(encoding="utf-8").strip()
                if notes:
                    sections.append("LatestReleaseNotes: " + notes[:2000])
            except Exception:
                pass
        return "\n".join(sections)

    def _conversation(self, chat_id: int) -> deque[dict[str, str]]:
        if chat_id not in self._conversations:
            self._conversations[chat_id] = deque(maxlen=CONVERSATION_MAX_TURNS * 2)
        return self._conversations[chat_id]

    def _llm_reply(self, chat_id: int, user_text: str) -> str:
        memory_context = self._build_memory_context(chat_id)
        system = (
            f"You are {self._profile.display_name}, the voice of this family agent. "
            f"You are a helpful, warm assistant for this household (profile={self._profile.name}). "
            "Reply in first person, concisely and in a friendly tone. No markdown. "
            "Identify yourself when it fits the conversation. "
            "If API/backends are degraded, explain clearly in one line with a status marker. "
            "Use LatestReleaseNotes in MemoryContext to answer questions about what's new, what you can do, or how to use features.\n"
            f"MemoryContext:\n{memory_context}"
        )
        conv = self._conversation(chat_id)
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for msg in conv:
            messages.append(msg)
        messages.append({"role": "user", "content": user_text})
        try:
            reply, usage = llm_complete(
                messages,
                self._llm_api_key,
                base_url=self._llm_base_url or None,
                model=self._llm_model,
                max_tokens=512,
            )
            if self._api_usage_store:
                self._api_usage_store.record(
                    self._profile.name,
                    "telegram_llm",
                    self._llm_model,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                )
        except Exception as exc:
            self._record_in_db(
                "telegram_update_error",
                {"error": f"LLM: {exc}", "user_text": user_text[:200]},
                decision="deny",
            )
            return "[status=degraded] I could not generate a response right now. Try again."
        conv.append({"role": "user", "content": user_text})
        conv.append({"role": "assistant", "content": reply})
        return reply

    async def _handle_unsupported(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._capture_inbound(update, message_type="unsupported")
        if update.effective_message:
            await self._reply_text(update, "Unsupported message type. Send text or /help.", message_type="unsupported")
        self._record_in_db(
            "telegram_command_handled",
            {"chat_id": update.effective_chat.id if update.effective_chat else 0, "command": "unsupported_message"},
            decision="allow",
        )
