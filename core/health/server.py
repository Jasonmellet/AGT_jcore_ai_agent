"""HTTP health and status server."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from core.approval.engine import ApprovalEngine
from core.control_plane import ControlPlane
from core.interop.bridge import InteropBridge
from core.memory.episodic_memory import EpisodicMemoryStore
from core.tools.registry import ToolRegistry


class HealthServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        profile_name: str,
        tool_registry: ToolRegistry,
        approval_engine: ApprovalEngine,
        episodic_memory: EpisodicMemoryStore,
        api_usage_provider: Callable[[], dict[str, Any]] | None = None,
        control_plane: ControlPlane | None = None,
        interop_bridge: InteropBridge | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._profile_name = profile_name
        self._tool_registry = tool_registry
        self._approval_engine = approval_engine
        self._episodic_memory = episodic_memory
        self._api_usage_provider = api_usage_provider or (lambda: {"enabled": False})
        self._control_plane = control_plane
        self._interop_bridge = interop_bridge
        self._started_at = time.time()
        self._thread: threading.Thread | None = None
        self._httpd: ThreadingHTTPServer | None = None

    def start(self) -> None:
        handler_cls = self._build_handler()
        self._httpd = ThreadingHTTPServer((self._host, self._port), handler_cls)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._httpd = None
        self._thread = None

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        profile_name = self._profile_name
        tool_registry = self._tool_registry
        approval_engine = self._approval_engine
        episodic_memory = self._episodic_memory
        api_usage_provider = self._api_usage_provider
        control_plane = self._control_plane
        interop_bridge = self._interop_bridge
        started_at = self._started_at

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._write_json(
                        200,
                        {
                            "status": "ok",
                            "profile": profile_name,
                            "uptime": int(time.time() - started_at),
                        },
                    )
                    return

                if self.path == "/status":
                    self._write_json(
                        200,
                        {
                            "profile": profile_name,
                            "tools_registered": tool_registry.count(),
                            "tools": tool_registry.list_tools(),
                            "pending_approvals": len(approval_engine.list_pending(limit=1000)),
                            "recent_events": len(episodic_memory.latest(limit=10)),
                        },
                    )
                    return

                if self.path == "/approvals":
                    pending = approval_engine.list_pending(limit=100)
                    recent = approval_engine.list_recent(limit=100)
                    self._write_json(200, {"pending": pending, "recent": recent})
                    return

                if self.path == "/logs":
                    self._write_json(200, {"events": episodic_memory.latest(limit=200)})
                    return

                if self.path == "/api-usage":
                    self._write_json(200, api_usage_provider())
                    return
                if self.path == "/fleet/status":
                    if control_plane is None:
                        self._write_json(404, {"error": "Fleet control plane disabled"})
                        return
                    self._write_json(200, control_plane.health_report())
                    return
                if self.path == "/interop/messages":
                    if interop_bridge is None:
                        self._write_json(404, {"error": "Interop bridge disabled"})
                        return
                    self._write_json(200, {"messages": interop_bridge.recent_messages(limit=200)})
                    return

                self._write_json(404, {"error": "Not found"})

            def do_POST(self) -> None:  # noqa: N802
                path = self.path.split("?")[0]
                if path == "/tools/execute":
                    try:
                        content_len = int(self.headers.get("Content-Length", 0))
                        body = self.rfile.read(content_len).decode("utf-8")
                        data = json.loads(body) if body else {}
                    except (ValueError, json.JSONDecodeError):
                        self._write_json(400, {"error": "Invalid JSON body"})
                        return
                    tool_name = (data.get("tool_name") or "").strip()
                    payload = data.get("payload")
                    if not tool_name:
                        self._write_json(400, {"error": "Missing tool_name"})
                        return
                    if payload is None:
                        payload = {}
                    result = tool_registry.execute(tool_name, payload)
                    status = 200 if result.ok else 400
                    self._write_json(status, {"ok": result.ok, "output": result.output})
                    return
                if path.startswith("/approvals/") and path.endswith("/resolve"):
                    try:
                        approval_id = int(path.split("/")[2])
                    except (IndexError, ValueError):
                        self._write_json(400, {"error": "Invalid approval id"})
                        return
                    try:
                        content_len = int(self.headers.get("Content-Length", 0))
                        body = self.rfile.read(content_len).decode("utf-8")
                        data = json.loads(body) if body else {}
                    except (ValueError, json.JSONDecodeError):
                        self._write_json(400, {"error": "Invalid JSON body"})
                        return
                    approve = data.get("approve", False)
                    if approval_engine.resolve(approval_id, approve=approve):
                        episodic_memory.record(
                            "approval_resolved",
                            {"approval_id": approval_id, "approve": bool(approve)},
                            decision="allow",
                        )
                        self._write_json(200, {"resolved": True, "approve": approve})
                    else:
                        self._write_json(404, {"error": "Approval not found or already resolved"})
                    return
                if path.startswith("/approvals/") and path.endswith("/execute"):
                    try:
                        approval_id = int(path.split("/")[2])
                    except (IndexError, ValueError):
                        self._write_json(400, {"error": "Invalid approval id"})
                        return
                    result = tool_registry.execute_approved(approval_id)
                    status = 200 if result.ok else 400
                    episodic_memory.record(
                        "approval_execution_attempted",
                        {"approval_id": approval_id, "ok": result.ok, "output": result.output},
                        decision="allow" if result.ok else "deny",
                    )
                    self._write_json(status, {"ok": result.ok, "output": result.output})
                    return
                if path == "/fleet/deploy":
                    if control_plane is None:
                        self._write_json(404, {"error": "Fleet control plane disabled"})
                        return
                    deploy_result = control_plane.deploy_all()
                    episodic_memory.record(
                        "fleet_deploy_triggered",
                        {"ok": deploy_result.get("ok", False), "returncode": deploy_result.get("returncode")},
                        decision="allow" if deploy_result.get("ok", False) else "deny",
                    )
                    self._write_json(200 if deploy_result.get("ok", False) else 500, deploy_result)
                    return
                if path == "/interop/inbox":
                    if interop_bridge is None:
                        self._write_json(404, {"error": "Interop bridge disabled"})
                        return
                    try:
                        content_len = int(self.headers.get("Content-Length", 0))
                        body = self.rfile.read(content_len).decode("utf-8")
                        data = json.loads(body) if body else {}
                    except (ValueError, json.JSONDecodeError):
                        self._write_json(400, {"error": "Invalid JSON body"})
                        return
                    envelope = data.get("envelope")
                    if not isinstance(envelope, dict):
                        self._write_json(400, {"error": "Missing envelope object"})
                        return
                    try:
                        accepted = interop_bridge.receive_envelope(envelope)
                        episodic_memory.record(
                            "interop_message_received",
                            {"source": accepted["source"], "task_type": accepted["task_type"], "nonce": accepted["nonce"]},
                            decision="allow",
                        )
                        self._write_json(200, accepted)
                    except RuntimeError as exc:
                        episodic_memory.record(
                            "interop_message_rejected",
                            {"error": str(exc)},
                            decision="deny",
                        )
                        self._write_json(400, {"error": str(exc)})
                    return
                self._write_json(404, {"error": "Not found"})

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                # Keep console output quiet; events are tracked in episodic memory.
                _ = (format, args)
                return

            def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
                encoded = json.dumps(payload, ensure_ascii=True).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        return Handler
