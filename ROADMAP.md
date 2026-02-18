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

### Telegram + memory (Jason Core baseline)

- [x] Telegram bot (python-telegram-bot, main-thread polling)
- [x] Pairing + allowlist (no env-based user IDs)
- [x] Commands: `/start`, `/help`, `/ping`, `/status`, `/whoami`, `/health`, `/logs`, `/pair`
- [x] Optional LLM-backed replies (OpenAI-compatible API)
- [x] Episodic logging for pairing/denials/commands/errors
- [x] Full Telegram transcript persistence (`telegram_messages`)
- [x] Idea capture/search commands (`/idea`, `/ideas`, `/idea_search`, `#ideaengine`)
- [x] SQLite-local vector memory (`message_embeddings`) for semantic retrieval

### Jason Core — next

- [x] Document memory (chunked + embedded) — FOUNDATION §3.7
- [x] Tool tier wiring: register real Tier 0/1/2 tools and approval flow
- [x] API usage tracking (LLM token counts, `/api-usage`) — FOUNDATION §7
- [ ] Starter skill packs under `/skills/` (communication, system, memory, builders)
- [x] Stabilize and lock Jason node as golden reference

---

## Phase 2 — Family nodes

- [x] Jennifer node (jencore: creative automation, communication, light builder tools) — live on her desk, Telegram @jencore_ai_bot, GitHub backup
- [ ] Kiera node (idea incubation, micro-business, approval gating) **NEXT**
- [ ] Scarlet node (math tools, builder pack, structured projects)
- [ ] Multi-node deploy from `config/nodes.yaml` (deploy_all.sh) verified
- [x] Per-node read-only ngrok-safe mode (GET allowlist + POST blocked when enabled)
- [x] Persistent API usage telemetry (restart-safe, windowed breakdown)

---

## Later (vision)

- [x] Cross-node communication (Jason-approved) — minimal signed envelope + replay protection + inbox/outbox audit
- [ ] Shared knowledge exchange (opt-in only)
- [ ] Home automation / inter-agent collaboration

---

## Non-goals (FOUNDATION §9)

We are *not* building: AI toy, uncontrolled bot, public SaaS, cloud dependency, plugin marketplace, self-modifying system without oversight. No OpenClaw.
