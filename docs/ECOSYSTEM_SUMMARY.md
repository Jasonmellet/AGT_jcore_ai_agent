# Family Agent Ecosystem – Summary

This document summarizes the ecosystem, infrastructure, and capabilities of the Family Agent (jcore) and sub-agents (jencore, score, kcore, Pepper).

---

## 1. Nodes and Roles

| Node   | Profile  | Role        | Host / User                         | Notes |
|--------|----------|-------------|-------------------------------------|--------|
| **jcore**   | jason    | **Master (Family Agent)** | 192.168.7.10 / jcore   | Central hub; runs dashboard, ngrok, daily check-ins to sub-agents. |
| **jencore** | jennifer | Sub-agent   | (in nodes.yaml) / jennifer          | Jennifer’s personal agent. |
| **score**   | scarlet  | Sub-agent   | 192.168.7.191 / scarletcore         | Scarlet’s agent. |
| **kcore**   | kiera    | Sub-agent   | 192.168.4.140 / kieracore           | Kiera’s agent. |
| **Pepper**  | (placeholder) | Placeholder | peppers-mac-mini.local / pepperpotts | No service on 8600 yet; shown on dashboard as placeholder. |

- **Single source of truth for nodes:** `config/nodes.yaml` (host, profile, user per node).
- **Master vs sub-agents:** jcore is the Family Agent (Master); others are sub-agents. See `docs/FAMILY_NETWORK.md` for roles and secure tunnel.

---

## 2. Infrastructure

- **Deploy:** One repo, multiple profiles. `scripts/deploy.sh` deploys a profile to a node (SSH + rsync). Uses `secrets/deploy_key` when present (`IdentitiesOnly=yes`) so automation can deploy without interactive auth.
- **Backup:** GitHub backup repos (e.g. AGT_score_ai_agent, AGT_kcore_ai_agent). `scripts/backup_code.sh` and `scripts/backup_data.sh`; `scripts/install_backup_cron.sh` installs cron on each Mini. Deploy can wire a profile’s backup repo when the URL is passed.
- **Secrets (repo):** Per-profile: `secrets/<profile>.telegram.token`, `secrets/<profile>.telegram.pairing_code`, `secrets/<profile>.openai_api_key` (or `.llm_api_key`). Shared: `secrets/interop_shared_key.txt`, `secrets/deploy_key` (+ `.pub`). Optional: `secrets/<profile>.telegram_chat_id` for notify.
- **Profiles:** `config/profiles/<name>.yaml`; each node runs one profile (same codebase, different config and secrets).

---

## 3. Tunnel and Interop

- **Secure tunnel:** All nodes share one key: `secrets/interop_shared_key.txt`. Deploy copies it into each profile’s `secrets/` on the Mini.
- **Mechanism:** `core/interop/bridge.py` – `send_task(target_node_id, task_type, payload)` signs requests; receiver validates and processes. Health server exposes `POST /interop/inbox` for incoming envelopes.
- **Task types:** `delegate_node_task`, `skills_checkin`, `route_envelope`, `skill_request`, `skill_approve`, `skill_deliver`, `skill_install_result`.
- **Hub-routed reliability:** `route_envelope` lets sub-agents relay through jcore. Sender -> jcore -> target gives reliable connectivity even when sub↔sub LAN routes are broken.
- **Daily skills check-in (LLM-to-LLM):**  
  - At most once per 24h per target. Sender asks “do you have any cool new skills?”  
  - Receiver (`core/health/server.py`) handles `task_type == "skills_checkin"` by calling an LLM with the receiving profile’s API key (system + user prompt: source, question, current tools, recent interop).  
  - Reply is LLM-generated text (and tools/usage); stored in outbox payload and shown in dashboard “Recent Communication” feed.
- **Scheduler:** In `core/agent.py`, after health server start, a daemon thread runs the daily check-in loop (e.g. every 3600s, bridge sends check-ins per interval).  
- **Note:** Only jcore↔sub-agent links are consistently reliable; sub-agent↔sub-agent can fail (e.g. routing between 192.168.7.x and 192.168.4.x). Hub mode (only jcore initiates check-ins) is an option.
- **Security migration:** Shared-key HMAC remains active; optional per-node Ed25519 identity signatures support provenance and strict modes.

### Skill transfer layer (new)

- **Manifest:** each node keeps `~/agent_skills/manifest.yaml` with `skill_id`, name, version, description, entrypoints, dependencies, `permissions_requested`, checksum, and optional signer.
- **Discovery:** `skills_checkin` includes friendly reply plus `skills_manifest_delta` for machine-readable comparison.
- **Transfer unit:** `tar.gz` bundle + SHA256 checksum.
- **Governed install flow:** request -> approval -> deliver -> install -> test -> register -> install result.
- **Guardrails:** risky permissions require override/approval; installs are rate-limited to 1 successful new skill/day per node unless override is explicitly approved.

---

## 4. Dashboard and Ngrok

- **Endpoints:** `GET /dashboard` (single-file HTML UI), `GET /dashboard/data` (JSON). Implemented in `core/health/server.py`. Both are allowed in `public_readonly_mode` (no sensitive fields).
- **Data:** Nodes from control plane; per-node health/status/API/backup via HTTP; interop messages and edges; growth stages (infant → child → teen → adult); tunnel links (dashed vs active with counts). Recent Communication shows skills_checkin question/reply snippets.
- **Hosting:** Dashboard runs on jcore (port 8600). User runs ngrok: `ngrok http --url=agt-mellet-ai-agents-dashboard.ngrok.io 8600`. Public URL: `https://agt-mellet-ai-agents-dashboard.ngrok.io/dashboard`.

---

## 5. Telegram, Release Notes, Notify

- **Telegram:** Each profile has its own bot (token in `secrets/<profile>.telegram.token`). Pairing and chat_id via `secrets/<profile>.telegram.pairing_code` and optional `secrets/<profile>.telegram_chat_id`.
- **Release notes:** `release_notes/<profile>.txt` (e.g. jennifer, scarlet, kiera). Deploy copies the relevant file to the Mini as `release_notes_latest.txt`.
- **Post-deploy notify:** `scripts/notify_agent_user.sh` reads Telegram token, resolves chat_id (file or SSH allowlist), sends a message built from `release_notes/<profile>.txt` and invites the user to ask “what’s new” or use `/whatsnew`.
- **Bot “what’s new”:** In `core/telegram_bot.py`, `_build_memory_context` appends `release_notes_latest.txt` as `LatestReleaseNotes`; system prompt tells the bot to use it for “what’s new”/capabilities; `/whatsnew` command and `/help` updated.

---

## 6. Tools and Capabilities (Current)

- **Conversational replies:** Plain-language chat with full answers (OpenAI on that node).
- **Memory:** Inbound/outbound text stored for memory and search; semantic embeddings for search by meaning.
- **Idea engine:** `/idea <text>`, `/ideas`, `/idea_search <query>`; `#ideaengine` in any message to capture as idea.
- **API usage:** Token usage recorded; `/api-usage` (dashboard-ready).
- **Interop:** Send/receive tasks (e.g. delegate_node_task, skills_checkin); LLM-generated replies for skills check-in.
- **Health and dashboard:** Health server (8600), dashboard UI and JSON, growth stages and tunnel visualization.
- **Family network:** Shared interop key, tunnel semantics, and optional hub mode described in `docs/FAMILY_NETWORK.md`.

Capabilities are aligned across agents (same codebase); per-profile differences are config, secrets, and release notes. Pepper is a placeholder until a profile is deployed and a health endpoint exists.

---

## 7. Key Paths

| Purpose        | Path |
|----------------|------|
| Node list      | `config/nodes.yaml` |
| Profiles       | `config/profiles/<name>.yaml` |
| Deploy         | `scripts/deploy.sh` |
| Notify user    | `scripts/notify_agent_user.sh` |
| Install SSH key| `scripts/install_deploy_key.sh` |
| Backup         | `scripts/backup_code.sh`, `scripts/backup_data.sh`, `scripts/install_backup_cron.sh` |
| Interop        | `core/interop/bridge.py` |
| Health/dashboard | `core/health/server.py` |
| Telegram + /whatsnew | `core/telegram_bot.py` |
| Daily check-in loop | `core/agent.py` |
| Family network doc | `docs/FAMILY_NETWORK.md` |
