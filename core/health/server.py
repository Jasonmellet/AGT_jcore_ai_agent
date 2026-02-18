"""HTTP health and status server."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib import error, request
from urllib.parse import parse_qs, urlparse

from core.approval.engine import ApprovalEngine
from core.control_plane import ControlPlane
from core.interop.bridge import InteropBridge
from core.llm import complete as llm_complete
from core.llm import read_secret
from core.memory.episodic_memory import EpisodicMemoryStore
from core.tools.registry import ToolRegistry

_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Family Agent Dashboard</title>
  <style>
    :root {
      --bg: #0d1117;
      --panel: #161b22;
      --panel2: #1f2630;
      --text: #d6e3f0;
      --muted: #8b9bb0;
      --ok: #2ea043;
      --down: #f85149;
      --line: #3b4a5f;
      --accent: #7aa2ff;
    }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: radial-gradient(circle at 20% 0%, #1a2130 0%, var(--bg) 60%);
      color: var(--text);
    }
    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 18px;
    }
    h1 {
      margin: 0 0 6px 0;
      font-size: 28px;
    }
    .subtitle {
      color: var(--muted);
      margin-bottom: 16px;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .tile {
      background: linear-gradient(180deg, var(--panel2), var(--panel));
      border: 1px solid #2f3b4a;
      border-radius: 10px;
      padding: 10px 12px;
    }
    .tile .label { color: var(--muted); font-size: 12px; }
    .tile .value { font-size: 20px; font-weight: 600; margin-top: 2px; }
    .grid {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 12px;
    }
    @media (max-width: 980px) { .grid { grid-template-columns: 1fr; } }
    .panel {
      background: linear-gradient(180deg, var(--panel2), var(--panel));
      border: 1px solid #2f3b4a;
      border-radius: 12px;
      padding: 12px;
    }
    .panel h2 { margin: 0 0 8px 0; font-size: 16px; }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }
    .card {
      background: #141a22;
      border: 1px solid #2d3948;
      border-radius: 10px;
      padding: 10px;
    }
    .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
      margin-right: 8px;
    }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      color: var(--muted);
    }
    #graph {
      width: 100%;
      height: 360px;
      background: #0f141b;
      border: 1px solid #2d3948;
      border-radius: 10px;
    }
    .feed {
      max-height: 560px;
      overflow: auto;
      font-size: 13px;
      line-height: 1.4;
    }
    .feed-item {
      border-bottom: 1px solid #2b3644;
      padding: 8px 0;
    }
    .legend {
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted);
    }
    .growth-chip {
      border: 1px solid #2d3948;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 11px;
      color: #c7d6e8;
      background: #111722;
    }
    .muted { color: var(--muted); }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Family Agent Dashboard</h1>
    <div class="subtitle">Live view of node health, tunnel activity, and agent-to-agent communication.</div>
    <div class="summary" id="summary"></div>
    <div class="grid">
      <div class="panel">
        <h2>Tunnel Graph</h2>
        <svg id="graph" viewBox="0 0 1000 360" preserveAspectRatio="xMidYMid meet"></svg>
        <div class="legend">Gray dashed links show tunnel paths. Blue links glow when communication is active.</div>
        <div class="cards" id="cards"></div>
      </div>
      <div class="panel">
        <h2>Recent Communication</h2>
        <div class="feed" id="feed"></div>
      </div>
    </div>
  </div>
  <script>
    function esc(v) {
      return String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    }
    function fmtTime(ts) {
      if (!ts) return "n/a";
      const d = new Date(ts * 1000);
      return d.toLocaleString();
    }
    function renderSummary(data) {
      const up = data.nodes.filter(n => n.up).length;
      const total = data.nodes.length;
      const msgs = data.recent_messages.length;
      const activeLinks = (data.links || []).filter(l => Number(l.active_count || 0) > 0).length;
      const infant = data.nodes.filter(n => (n.growth_stage || "") === "infant").length;
      const html = [
        ["Nodes Up", up + " / " + total],
        ["Interop Messages", msgs],
        ["Tunnel Links Active", activeLinks],
        ["Infant Agents", infant],
        ["Last Refresh", fmtTime(data.generated_at)]
      ].map(([k, v]) => '<div class="tile"><div class="label">' + esc(k) + '</div><div class="value">' + esc(v) + '</div></div>').join("");
      document.getElementById("summary").innerHTML = html;
    }
    function renderCards(data) {
      const html = data.nodes.map(n => {
        const color = n.up ? "#2ea043" : "#f85149";
        return (
          '<div class="card">' +
            '<div class="row"><div><span class="dot" style="background:' + color + '"></span><strong>' + esc(n.node_id) + '</strong></div>' +
            '<div class="mono">' + esc(n.profile) + '</div></div>' +
            '<div class="mono">' + esc(n.host || "unconfigured") + '</div>' +
            '<div class="row"><span class="muted">Status</span><span>' + esc(n.status || "unknown") + '</span></div>' +
            '<div class="row"><span class="muted">Tools</span><span>' + esc(n.tools_registered ?? 0) + '</span></div>' +
            '<div class="row"><span class="muted">API</span><span>' + esc(n.api_enabled ? "enabled" : "off") + '</span></div>' +
            '<div class="row"><span class="muted">Growth</span><span class="growth-chip">' + esc(n.growth_stage || "infant") + '</span></div>' +
            '<div class="row"><span class="muted">Messages</span><span>' + esc((n.messages_sent || 0) + " out / " + (n.messages_received || 0) + " in") + '</span></div>' +
            '<div class="row"><span class="muted">Backup</span><span>' + esc((n.code_backup_status || "unknown") + " / " + (n.data_backup_status || "unknown")) + '</span></div>' +
          '</div>'
        );
      }).join("");
      document.getElementById("cards").innerHTML = html;
    }
    function renderGraph(data) {
      const svg = document.getElementById("graph");
      const nodes = data.nodes;
      const cx = 500, cy = 180, r = 130;
      const pos = {};
      const stageRadius = { infant: 14, child: 18, teen: 22, adult: 26 };
      nodes.forEach((n, i) => {
        const angle = (Math.PI * 2 * i / Math.max(nodes.length, 1)) - Math.PI / 2;
        pos[n.profile] = { x: cx + Math.cos(angle) * r * 2.1, y: cy + Math.sin(angle) * r };
      });
      const baseLines = (data.links || []).map(e => {
        const a = pos[e.source_profile], b = pos[e.target_profile];
        if (!a || !b) return "";
        return '<line x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '" stroke="#3f4f64" stroke-width="2" stroke-dasharray="8 6" opacity="0.65"></line>';
      }).join("");
      const lines = (data.links || []).map(e => {
        const a = pos[e.source_profile], b = pos[e.target_profile];
        if (!a || !b) return "";
        const active = Number(e.active_count || 0);
        if (active <= 0) return "";
        const width = Math.min(10, 2 + active);
        return '<line x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '" stroke="#7aa2ff" stroke-width="' + width + '" opacity="0.75"></line>' +
               '<text x="' + ((a.x + b.x) / 2) + '" y="' + ((a.y + b.y) / 2 - 8) + '" fill="#b8ccff" font-size="11">' + esc(active + " msgs") + '</text>';
      }).join("");
      const dots = nodes.map(n => {
        const p = pos[n.profile] || {x: 50, y: 50};
        const fill = n.up ? "#2ea043" : "#f85149";
        const growth = n.growth_stage || "infant";
        const radius = stageRadius[growth] || 14;
        const babyGlow = growth === "infant" ? '0.35' : '0.15';
        return '<circle cx="' + p.x + '" cy="' + p.y + '" r="' + (radius + 6) + '" fill="#89a6ff" opacity="' + babyGlow + '"></circle>' +
               '<circle cx="' + p.x + '" cy="' + p.y + '" r="' + radius + '" fill="' + fill + '"></circle>' +
               '<text x="' + p.x + '" y="' + (p.y + 4) + '" fill="#0b1220" text-anchor="middle" font-size="10">' + esc(growth) + '</text>' +
               '<text x="' + p.x + '" y="' + (p.y + radius + 18) + '" fill="#d6e3f0" text-anchor="middle" font-size="12">' + esc(n.node_id) + '</text>';
      }).join("");
      svg.innerHTML = baseLines + lines + dots;
    }
    function renderFeed(data) {
      const list = data.recent_messages.slice(0, 50).map(m => {
        const q = m.question ? ('<div class="muted">q: ' + esc(m.question) + '</div>') : '';
        const r = m.reply_message ? ('<div class="muted">reply: ' + esc(m.reply_message) + '</div>') : '';
        return (
          '<div class="feed-item">' +
            '<div><strong>' + esc(m.source_node || m.source_profile || "unknown") + '</strong> → <strong>' + esc(m.target_node || m.target_profile || "unknown") + '</strong></div>' +
            '<div class="muted">task=' + esc(m.task_type || "n/a") + ' | status=' + esc(m.status || "n/a") + '</div>' +
            q + r +
            '<div class="muted">' + esc(fmtTime(m.created_at_ts)) + '</div>' +
          '</div>'
        );
      }).join("");
      document.getElementById("feed").innerHTML = list || '<div class="muted">No recent messages yet.</div>';
    }
    async function refresh() {
      try {
        const r = await fetch("/dashboard/data", { cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        renderSummary(data);
        renderCards(data);
        renderGraph(data);
        renderFeed(data);
      } catch (err) {
        document.getElementById("summary").innerHTML = '<div class="tile"><div class="label">Dashboard</div><div class="value">Error loading data</div></div>';
      }
    }
    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>
"""


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
        api_usage_provider: Callable[..., dict[str, Any]] | None = None,
        backup_status_provider: Callable[[], dict[str, Any]] | None = None,
        control_plane: ControlPlane | None = None,
        interop_bridge: InteropBridge | None = None,
        public_readonly_mode: bool = False,
        public_readonly_get_endpoints: list[str] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._profile_name = profile_name
        self._tool_registry = tool_registry
        self._approval_engine = approval_engine
        self._episodic_memory = episodic_memory
        self._api_usage_provider = api_usage_provider or (lambda **_: {"enabled": False})
        self._backup_status_provider = backup_status_provider or (lambda: {"status": "unavailable"})
        self._control_plane = control_plane
        self._interop_bridge = interop_bridge
        self._public_readonly_mode = public_readonly_mode
        self._public_readonly_get_endpoints = set(
            public_readonly_get_endpoints
            or ["/health", "/status", "/api-usage", "/backup/status", "/dashboard", "/dashboard/data"]
        )
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
        backup_status_provider = self._backup_status_provider
        control_plane = self._control_plane
        interop_bridge = self._interop_bridge
        public_readonly_mode = self._public_readonly_mode
        public_readonly_get_endpoints = self._public_readonly_get_endpoints
        started_at = self._started_at
        default_health_port = self._port
        profile_secrets_dir = Path.home() / "agentdata" / profile_name / "secrets"

        def _fetch_json(host: str, path: str, timeout: float = 1.5) -> dict[str, Any] | None:
            if not host:
                return None
            url = f"http://{host}:{default_health_port}{path}"
            try:
                with request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
                    return json.loads(resp.read().decode("utf-8"))
            except (error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                return None

        def _parse_timestamp(raw: Any) -> int | None:
            if raw is None:
                return None
            if isinstance(raw, int):
                return raw
            if isinstance(raw, str):
                try:
                    return int(raw)
                except ValueError:
                    pass
                try:
                    # "YYYY-MM-DD HH:MM:SS"
                    parts = raw.strip().replace("T", " ").split(".")[0]
                    return int(time.mktime(time.strptime(parts, "%Y-%m-%d %H:%M:%S")))
                except (ValueError, OSError):
                    return None
            return None

        def _build_dashboard_data() -> dict[str, Any]:
            def _growth_stage(score: int) -> str:
                if score <= 2:
                    return "infant"
                if score <= 5:
                    return "child"
                if score <= 8:
                    return "teen"
                return "adult"

            if control_plane is None:
                return {
                    "generated_at": int(time.time()),
                    "master_profile": profile_name,
                    "nodes": [],
                    "edges": [],
                    "links": [],
                    "recent_messages": [],
                }

            nodes_payload: list[dict[str, Any]] = []
            for node in control_plane.list_nodes():
                host = node.get("host") or ""
                configured = bool(node.get("configured"))
                profile = str(node.get("profile") or node.get("node_id") or "")
                health = _fetch_json(host, "/health") if configured else None
                status_payload = _fetch_json(host, "/status") if configured else None
                api_usage = _fetch_json(host, "/api-usage?window_days=7") if configured else None
                backup = _fetch_json(host, "/backup/status") if configured else None

                # Fallback for local node if host fetch is unavailable.
                if profile == profile_name:
                    if health is None:
                        health = {"status": "ok", "profile": profile_name, "uptime": int(time.time() - started_at)}
                    if status_payload is None:
                        status_payload = {
                            "profile": profile_name,
                            "tools_registered": tool_registry.count(),
                            "tools": tool_registry.list_tools(),
                            "pending_approvals": len(approval_engine.list_pending(limit=1000)),
                            "recent_events": len(episodic_memory.latest(limit=10)),
                        }
                    if api_usage is None:
                        api_usage = api_usage_provider(window_days=7)
                    if backup is None:
                        backup = backup_status_provider()

                code_status = None
                data_status = None
                if isinstance(backup, dict):
                    code_status = (backup.get("code_backup") or {}).get("status")
                    data_status = (backup.get("data_backup") or {}).get("status")

                up = bool(isinstance(health, dict) and health.get("status") == "ok")
                nodes_payload.append(
                    {
                        "node_id": node.get("node_id"),
                        "profile": profile,
                        "host": host,
                        "configured": configured,
                        "user": node.get("user"),
                        "up": up,
                        "status": (health or {}).get("status", "down" if configured else "unconfigured"),
                        "uptime": (health or {}).get("uptime"),
                        "tools_registered": (status_payload or {}).get("tools_registered", 0),
                        "api_enabled": bool((api_usage or {}).get("enabled")),
                        "api_total_calls": int((api_usage or {}).get("total_calls", 0) or 0),
                        "code_backup_status": code_status or "unknown",
                        "data_backup_status": data_status or "unknown",
                        "messages_sent": 0,
                        "messages_received": 0,
                        "growth_score": 0,
                        "growth_stage": "infant",
                        "error": None if up else "unreachable",
                    }
                )

            recent_messages = interop_bridge.recent_messages(limit=200) if interop_bridge is not None else []
            edge_map: dict[tuple[str, str], dict[str, Any]] = {}
            message_counts: dict[str, dict[str, int]] = {}
            recent_slim: list[dict[str, Any]] = []
            for msg in recent_messages:
                src = str(msg.get("source_node") or "")
                dst = str(msg.get("target_node") or "")
                created_ts = _parse_timestamp(msg.get("created_at")) or 0
                if src and dst:
                    key = (src, dst)
                    if key not in edge_map:
                        edge_map[key] = {
                            "source_profile": src,
                            "target_profile": dst,
                            "count": 0,
                            "last_task_type": msg.get("task_type"),
                            "last_ts": created_ts,
                        }
                    edge_map[key]["count"] += 1
                    if created_ts >= int(edge_map[key].get("last_ts", 0)):
                        edge_map[key]["last_task_type"] = msg.get("task_type")
                        edge_map[key]["last_ts"] = created_ts
                    message_counts.setdefault(src, {"sent": 0, "received": 0})["sent"] += 1
                    message_counts.setdefault(dst, {"sent": 0, "received": 0})["received"] += 1
                recent_slim.append(
                    {
                        "id": msg.get("id"),
                        "direction": msg.get("direction"),
                        "source_profile": src,
                        "target_profile": dst,
                        "source_node": src,
                        "target_node": dst,
                        "task_type": msg.get("task_type"),
                        "status": msg.get("status"),
                        "question": (msg.get("payload") or {}).get("question")
                        if isinstance(msg.get("payload"), dict)
                        else None,
                        "reply_message": (
                            ((msg.get("payload") or {}).get("reply") or {}).get("message")
                            if isinstance((msg.get("payload") or {}).get("reply"), dict)
                            else None
                        )
                        if isinstance(msg.get("payload"), dict)
                        else None,
                        "created_at": msg.get("created_at"),
                        "created_at_ts": created_ts,
                    }
                )

            for node in nodes_payload:
                profile = str(node.get("profile") or "")
                sent = int(message_counts.get(profile, {}).get("sent", 0))
                received = int(message_counts.get(profile, {}).get("received", 0))
                node["messages_sent"] = sent
                node["messages_received"] = received

                score = 0
                if node.get("up"):
                    score += 2
                if node.get("api_enabled"):
                    score += 1
                if node.get("code_backup_status") == "ok":
                    score += 1
                if node.get("data_backup_status") == "ok":
                    score += 1
                score += min(2, int(node.get("tools_registered", 0)) // 4)

                traffic = sent + received
                if traffic > 20:
                    score += 3
                elif traffic > 5:
                    score += 2
                elif traffic > 0:
                    score += 1

                calls = int(node.get("api_total_calls", 0))
                if calls > 200:
                    score += 2
                elif calls > 20:
                    score += 1

                node["growth_score"] = score
                node["growth_stage"] = _growth_stage(score)

            master_profile = profile_name
            profiles = [str(n.get("profile") or "") for n in nodes_payload if str(n.get("profile") or "")]
            if master_profile not in profiles and profiles:
                master_profile = profiles[0]
            links: list[dict[str, Any]] = []
            for p in profiles:
                if p == master_profile:
                    continue
                forward = edge_map.get((master_profile, p), {})
                reverse = edge_map.get((p, master_profile), {})
                active_count = int(forward.get("count", 0)) + int(reverse.get("count", 0))
                links.append(
                    {
                        "source_profile": master_profile,
                        "target_profile": p,
                        "active_count": active_count,
                        "forward_count": int(forward.get("count", 0)),
                        "reverse_count": int(reverse.get("count", 0)),
                    }
                )

            return {
                "generated_at": int(time.time()),
                "master_profile": master_profile,
                "nodes": nodes_payload,
                "edges": list(edge_map.values()),
                "links": links,
                "recent_messages": recent_slim,
            }

        def _llm_skills_checkin_reply(*, source_profile: str, payload: dict[str, Any]) -> dict[str, Any]:
            api_key = read_secret(profile_secrets_dir, "llm_api_key.txt") or read_secret(
                profile_secrets_dir, "openai_api_key.txt"
            )
            if not api_key:
                return {
                    "kind": "skills_checkin_reply",
                    "ok": False,
                    "error": "LLM key missing on target node",
                    "new_skills": [],
                }
            base_url = read_secret(profile_secrets_dir, "llm_base_url.txt")
            model = read_secret(profile_secrets_dir, "llm_model.txt") or "gpt-4o-mini"
            tools = tool_registry.list_tools()
            question = str(payload.get("question") or "Do you have any cool new skills today?")
            recent = interop_bridge.recent_messages(limit=12) if interop_bridge is not None else []
            recent_lines: list[str] = []
            for item in recent:
                recent_lines.append(
                    f"{item.get('direction')} {item.get('source_node')}->{item.get('target_node')} "
                    f"task={item.get('task_type')} status={item.get('status')}"
                )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an AI family agent responding to another agent. "
                        "Answer briefly and concretely. "
                        "If there are no new skills, say so clearly. "
                        "If there are potentially useful capabilities, mention 1-3 with simple names."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Source agent: {source_profile}\n"
                        f"Target agent: {profile_name}\n"
                        f"Question: {question}\n"
                        f"Current tools: {', '.join(tools)}\n"
                        f"Recent interop activity:\n- " + ("\n- ".join(recent_lines) if recent_lines else "none")
                    ),
                },
            ]
            try:
                text, usage = llm_complete(
                    messages,
                    api_key,
                    base_url=base_url,
                    model=model,
                    max_tokens=220,
                )
                return {
                    "kind": "skills_checkin_reply",
                    "ok": True,
                    "model": model,
                    "message": text,
                    "tools_registered": tool_registry.count(),
                    "tools": tools,
                    "usage": usage,
                }
            except RuntimeError as exc:
                return {
                    "kind": "skills_checkin_reply",
                    "ok": False,
                    "error": str(exc),
                    "tools_registered": tool_registry.count(),
                    "tools": tools,
                }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)

                if public_readonly_mode and path not in public_readonly_get_endpoints:
                    self._write_json(403, {"error": "Endpoint blocked in public read-only mode"})
                    return

                if path == "/health":
                    self._write_json(
                        200,
                        {
                            "status": "ok",
                            "profile": profile_name,
                            "uptime": int(time.time() - started_at),
                        },
                    )
                    return

                if path == "/status":
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

                if path == "/approvals":
                    pending = approval_engine.list_pending(limit=100)
                    recent = approval_engine.list_recent(limit=100)
                    self._write_json(200, {"pending": pending, "recent": recent})
                    return

                if path == "/logs":
                    self._write_json(200, {"events": episodic_memory.latest(limit=200)})
                    return

                if path == "/api-usage":
                    raw_days = (query.get("window_days") or [None])[0]
                    window_days: int | None = None
                    if raw_days:
                        try:
                            window_days = int(raw_days)
                        except ValueError:
                            self._write_json(400, {"error": "window_days must be an integer"})
                            return
                    self._write_json(200, api_usage_provider(window_days=window_days))
                    return
                if path == "/backup/status":
                    self._write_json(200, backup_status_provider())
                    return
                if path == "/fleet/status":
                    if control_plane is None:
                        self._write_json(404, {"error": "Fleet control plane disabled"})
                        return
                    self._write_json(200, control_plane.health_report())
                    return
                if path == "/interop/messages":
                    if interop_bridge is None:
                        self._write_json(404, {"error": "Interop bridge disabled"})
                        return
                    self._write_json(200, {"messages": interop_bridge.recent_messages(limit=200)})
                    return
                if path == "/dashboard":
                    self._write_html(200, _DASHBOARD_HTML)
                    return
                if path == "/dashboard/data":
                    self._write_json(200, _build_dashboard_data())
                    return

                self._write_json(404, {"error": "Not found"})

            def do_POST(self) -> None:  # noqa: N802
                if public_readonly_mode:
                    self._write_json(403, {"error": "POST endpoints disabled in public read-only mode"})
                    return
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
                        response: dict[str, Any] = dict(accepted)
                        if accepted.get("task_type") == "skills_checkin":
                            response["reply"] = _llm_skills_checkin_reply(
                                source_profile=str(accepted.get("source") or "unknown"),
                                payload=dict(accepted.get("payload") or {}),
                            )
                        episodic_memory.record(
                            "interop_message_received",
                            {"source": accepted["source"], "task_type": accepted["task_type"], "nonce": accepted["nonce"]},
                            decision="allow",
                        )
                        self._write_json(200, response)
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

            def _write_html(self, status_code: int, html: str) -> None:
                encoded = html.encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        return Handler
