"""Family Agent runtime entry point."""

from __future__ import annotations

import argparse
import signal
import threading
import time
from pathlib import Path

from core.api_usage import ApiUsageStore
from core.approval.engine import ApprovalEngine
from core.backup_status import BackupStatusProvider
from core.control_plane import ControlPlane
from core.health.server import HealthServer
from core.interop.bridge import InteropBridge
from core.interop.identity import ensure_identity_keys
from core.memory.engine import MemoryEngine
from core.memory.episodic_memory import EpisodicMemoryStore
from core.memory.profile_memory import ProfileMemoryStore
from core.memory.project_memory import ProjectMemoryStore
from core.policy import PolicyEngine
from core.profile import ensure_profile_directories, load_profile
from core.sandbox import Sandbox
from core.telegram_bot import TelegramBot
from core.tools.get_time_tool import GetTimeTool
from core.tools.math_tool import MathTool
from core.tools.delegate_node_task_tool import DelegateNodeTaskTool
from core.tools.runtime_diagnostics_tool import RuntimeDiagnosticsTool
from core.tools.sandbox_list_tool import SandboxListTool
from core.tools.sandbox_read_text_tool import SandboxReadTextTool
from core.tools.registry import ToolRegistry
from core.tools.request_email_tool import RequestEmailTool
from core.tools.idea_search_tool import IdeaSearchTool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Family Agent runtime")
    parser.add_argument("--profile", required=True, help="Profile name, e.g. jason")
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Optional repo root override for config loading",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else None
    runtime_repo_root = repo_root or Path(__file__).resolve().parent.parent
    profile = load_profile(args.profile, repo_root=repo_root)
    ensure_profile_directories(profile)
    (profile.paths.secrets_dir / "interop_identity_mode.txt").write_text(
        f"{profile.interop_identity_mode}\n",
        encoding="utf-8",
    )
    ensure_identity_keys(profile.paths.secrets_dir)

    memory_engine = MemoryEngine(profile.paths.db_path)
    memory_engine.initialize()
    conn = memory_engine.connect()

    profile_memory = ProfileMemoryStore(conn)
    project_memory = ProjectMemoryStore(conn)
    episodic_memory = EpisodicMemoryStore(conn)
    approval_engine = ApprovalEngine(conn)
    policy_engine = PolicyEngine(profile)
    tool_registry = ToolRegistry(
        policy_engine=policy_engine,
        approval_engine=approval_engine,
        episodic_memory=episodic_memory,
        profile_name=profile.name,
    )
    api_usage_store = ApiUsageStore(conn)
    backup_status = BackupStatusProvider(profile.paths.base_data_dir)
    control_plane = ControlPlane(runtime_repo_root)
    interop_bridge = InteropBridge(
        conn=conn,
        profile_name=profile.name,
        secrets_dir=profile.paths.secrets_dir,
        nodes_file=runtime_repo_root / "config" / "nodes.yaml",
        health_port=profile.health_port,
    )

    sandbox = Sandbox(profile)
    sandbox.ensure()
    for tool in (
        MathTool(),
        GetTimeTool(),
        RuntimeDiagnosticsTool(profile),
        SandboxListTool(sandbox),
        SandboxReadTextTool(sandbox),
        RequestEmailTool(),
        DelegateNodeTaskTool(interop_bridge),
        IdeaSearchTool(db_path=profile.paths.db_path, secrets_dir=profile.paths.secrets_dir),
    ):
        tool_registry.register(tool)

    profile_memory.set_fact("runtime_profile", profile.name)
    profile_memory.set_fact("policy_tier", profile.policy_tier)
    project_memory.create(
        "Node initialization",
        "Initial runtime bootstrap marker.",
        status="completed",
    )
    episodic_memory.record(
        "agent_boot",
        {"profile": profile.name, "health_port": profile.health_port},
        decision="allow",
    )

    health_server = HealthServer(
        host="0.0.0.0",
        port=profile.health_port,
        profile_name=profile.name,
        tool_registry=tool_registry,
        approval_engine=approval_engine,
        episodic_memory=episodic_memory,
        api_usage_provider=lambda window_days=None: {**api_usage_store.summary(window_days=window_days), "profile": profile.name},
        backup_status_provider=backup_status.summary,
        control_plane=control_plane,
        interop_bridge=interop_bridge,
        public_readonly_mode=profile.public_readonly_mode,
        public_readonly_get_endpoints=profile.public_readonly_get_endpoints,
        skills_dir=profile.paths.skills_dir,
        skill_packages_dir=profile.paths.skill_packages_dir,
    )
    health_server.start()
    running = True
    checkin_thread: threading.Thread | None = None

    def _daily_skills_checkin_loop() -> None:
        # At-most-daily interop check-ins; wakes hourly.
        while running:
            try:
                results = interop_bridge.send_daily_skills_checkins(interval_seconds=86400)
                for item in results:
                    episodic_memory.record(
                        "interop_skills_checkin_sent",
                        item,
                        decision="allow" if item.get("ok") else "deny",
                    )
            except RuntimeError as exc:
                episodic_memory.record(
                    "interop_skills_checkin_error",
                    {"error": str(exc)},
                    decision="deny",
                )
            for _ in range(3600):
                if not running:
                    break
                time.sleep(1)

    def handle_shutdown(*_: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    checkin_thread = threading.Thread(target=_daily_skills_checkin_loop, daemon=True)
    checkin_thread.start()

    telegram_bot = TelegramBot(
        profile=profile,
        episodic_memory=episodic_memory,
        profile_memory=profile_memory,
        api_usage_store=api_usage_store,
    )
    telegram_enabled = telegram_bot.start()
    profile_memory.set_fact("telegram_enabled", "true" if telegram_enabled else "false")

    try:
        while running and not telegram_enabled:
            time.sleep(1)
    finally:
        episodic_memory.record("agent_shutdown", {"profile": profile.name}, decision="allow")
        telegram_bot.stop()
        if checkin_thread is not None:
            checkin_thread.join(timeout=2)
        health_server.stop()
        memory_engine.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
