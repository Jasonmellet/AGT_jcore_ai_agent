# Family Agent OS — Roadmap

Aligned with [FOUNDATION.md](FOUNDATION.md). Check off items as they land.

---

## Phase 1 — Jason Core (reference node)

### Core runtime
- [x] Profile-aware runtime (`--profile <name>`)
- [x] Profile config and paths (`config/profiles/*.yaml`)
- [x] Policy tier enforcement (Tier 0/1/2)
- [x] SQLite memory (profile, project, episodic)
- [x] Approval queue for gated actions
- [x] Sandbox boundary checks
- [x] Health server (daemon thread) + `/health`, `/status`, `/logs`, `/api-usage`
- [x] Deploy: single-node script, stop-then-start, bootstrap, LaunchAgent

### Telegram (Jason Core)
- [x] Telegram bot (python-telegram-bot, main-thread polling)
- [x] Pairing + allowlist (no env-based user IDs)
- [x] Commands: `/start`, `/help`, `/ping`, `/status`, `/whoami`, `/health`, `/logs`, `/pair`
- [x] Optional LLM-backed replies (OpenAI-compatible API)
- [x] Episodic logging for pairing/denials/commands/errors

### Jason Core — next
- [ ] Document memory (chunked + embedded) — FOUNDATION §3.7
- [x] Tool tier wiring: register real Tier 0/1/2 tools and approval flow
- [x] API usage tracking (LLM token counts, `/api-usage`) — FOUNDATION §7
- [ ] Starter skill packs under `/skills/` (communication, system, memory, builders)
- [ ] Stabilize and lock Jason node as golden reference

---

## Phase 2 — Family nodes

- [ ] Jennifer node (creative automation, communication, light builder tools)
- [ ] Kiera node (idea incubation, micro-business, approval gating)
- [ ] Scarlet node (math tools, builder pack, structured projects)
- [ ] Multi-node deploy from `config/nodes.yaml` (deploy_all.sh) verified

---

## Later (vision)

- [ ] Cross-node communication (Jason-approved)
- [ ] Shared knowledge exchange (opt-in only)
- [ ] Home automation / inter-agent collaboration

---

## Non-goals (FOUNDATION §9)

We are *not* building: AI toy, uncontrolled bot, public SaaS, cloud dependency, plugin marketplace, self-modifying system without oversight. No OpenClaw.
