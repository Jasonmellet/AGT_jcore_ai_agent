# Family Agent OS

Local-first, profile-isolated runtime scaffold for the Family Agent Operating System.

## What Exists Now

- Profile-aware runtime: `python -m core.agent --profile <name>`
- Strict profile config: `config/profiles/*.yaml`
- Policy-tier enforcement (Tier 0/1/2): `core/policy.py`
- SQLite memory stores (profile, project, episodic): `core/memory/`
- Approval queue for gated actions: `core/approval/engine.py`
- Sandbox boundary checks: `core/sandbox.py`
- Telegram polling chat interface (enabled when token exists): `core/telegram_bot.py`
- Optional LLM-backed Telegram replies (API key): `core/llm.py` + secrets
- Observability endpoints:
  - `/health`
  - `/status`
  - `/api-usage` (LLM token usage when enabled)
  - `/backup/status` (latest code/data backup log status)
  - `/logs`
- Tool execution: `POST /tools/execute` with `{"tool_name": "...", "payload": {...}}`; Tier 0 (e.g. `math`, `get_time`, `runtime_diagnostics`, `sandbox_list`, `sandbox_read_text`) runs directly; Tier 1/Tier2 queue for approval. `GET /approvals` lists queue state; `POST /approvals/<id>/resolve` approves/rejects; `POST /approvals/<id>/execute` executes approved requests once (idempotent).
- Fleet + interop control: `GET /fleet/status`, `POST /fleet/deploy`, `GET /interop/messages`, `POST /interop/inbox`.
- Hub-routed interop: `route_envelope` enables reliable relay through jcore when direct node-to-node routing fails.
- Skill economy primitives: skill manifests (`~/agent_skills/manifest.yaml`), governed skill transfer tasks (`skill_request`, `skill_approve`, `skill_deliver`, `skill_install_result`), checksum-verified bundle installs.
- Deploy scripts for single-node and multi-node rollout: `scripts/`

## Prerequisites

- macOS host(s)
- Python 3.12+ on the Mini (bootstrap will install via Homebrew if needed)
- SSH access from your MacBook to each Mac Mini
- `rsync` on your MacBook (default on macOS)

## Initial setup: Jason Core Mac Mini (first time)

Do this once per new Mini before deploying.

### 1. On the Mac Mini

- Power on, complete macOS setup (create an admin user if needed).
- Connect to the same network as your MacBook (Wi‑Fi or Ethernet).
- Turn on Remote Login: **System Settings → General → Sharing → Remote Login** (enable it, allow your user if prompted).
- Note the Mini’s IP address (e.g. **System Settings → Network** or run `ipconfig getifaddr en0` in Terminal on the Mini).

### 2. On your MacBook

- Ensure you can SSH in without a password (password login is OK the first time; for scripted deploy you’ll type it once, or use SSH keys).

```bash
ssh <mini_username>@<mini_ip>
```

If the Mini username is the same as your MacBook user, you can omit it later; otherwise you’ll pass it as the third argument to `deploy.sh`.

From this repo on your MacBook, run deploy (see below). No need to install anything on the Mini by hand; the deploy script will copy the repo and run bootstrap on the Mini (Python 3.12, venv, dependencies, LaunchAgent).

### 3. Deploy Jason Core

From the `Family_Agent` repo on your MacBook:

```bash
cd /path/to/Family_Agent
chmod +x scripts/*.sh

# If your Mini username matches your MacBook $USER:
./scripts/deploy.sh jason <MINI_IP>

# If the Mini has a different username (e.g. "jason"):
./scripts/deploy.sh jason <MINI_IP> jason

# With Telegram bot token (optional):
./scripts/deploy.sh jason <MINI_IP> jason "<TELEGRAM_BOT_TOKEN>"

# With Telegram token + pairing code + LLM API key (optional):
./scripts/deploy.sh jason <MINI_IP> jason "<TELEGRAM_BOT_TOKEN>" "<PAIRING_CODE>" "<LLM_API_KEY>"
```

### 4. Verify

- Health: `curl http://<MINI_IP>:8600/health`
- If you added a Telegram token: open Telegram and send `/start` and `/ping` to your bot.

After this, the agent runs under LaunchAgent and will start again after a reboot. Logs: `~/agentdata/jason/logs/` on the Mini.

## Local Run (MacBook)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m core.agent --profile jason
```

In another terminal:

```bash
curl http://127.0.0.1:8600/health
curl http://127.0.0.1:8600/status
```

## Deploy Tomorrow (Single Node)

```bash
chmod +x scripts/*.sh
./scripts/deploy.sh jason 192.168.1.50
```

This will:

1. Copy repo to `~/agentbase` on target
2. Bootstrap python/venv/dependencies
3. Create `~/agentdata/<profile>/` tree
4. Install LaunchAgent for auto-start
5. Start the runtime

Verify from MacBook:

```bash
curl http://192.168.1.50:8600/health
```

## GitHub + Backup Setup (Pepper-style)

Pepper uses hourly cron backups for code + data. Family Agent now follows the same approach.

### What runs automatically on each Mini

- `scripts/install_backup_cron.sh` is executed during bootstrap.
- It installs profile-scoped cron jobs:
  - `:05` every hour -> `scripts/backup_code.sh <profile>` (git commit + push if changes)
  - `:10` every hour -> `scripts/backup_data.sh <profile>` (local `memory.db` snapshot, 7-day retention)

Logs:

- `~/agentdata/<profile>/logs/backup_code.log`
- `~/agentdata/<profile>/logs/backup_data.log`

### Connect node code to GitHub

Option A (recommended): configure during deploy:

```bash
GITHUB_REPO_URL="git@github.com:<org-or-user>/<repo>.git" \
GITHUB_REPO_BRANCH="main" \
./scripts/deploy.sh jason <MINI_IP> <mini_user>
```

Option B: configure directly on the Mini:

```bash
~/agentbase/scripts/setup_github_backup.sh jason "git@github.com:<org-or-user>/<repo>.git" "main"
```

If GitHub auth fails, ensure the Mini user has valid SSH keys for the target repo.

## Telegram Setup (Single Node)

Create one Telegram bot token with BotFather, then deploy with token:

```bash
./scripts/deploy.sh jason 192.168.1.50 "$USER" "<TELEGRAM_BOT_TOKEN>"
```

Alternative:

```bash
TELEGRAM_BOT_TOKEN="<TELEGRAM_BOT_TOKEN>" ./scripts/deploy.sh jason 192.168.1.50
```

With pairing code (recommended for first secure binding):

```bash
TELEGRAM_BOT_TOKEN="<TELEGRAM_BOT_TOKEN>" TELEGRAM_PAIRING_CODE="<PAIRING_CODE>" ./scripts/deploy.sh jason 192.168.1.50
```

Token and pairing files on Mini:

```bash
~/agentdata/<profile>/secrets/telegram_bot_token.txt
~/agentdata/<profile>/secrets/telegram_pairing_code.txt
```

Basic commands in Telegram:

- `/start`
- `/help`
- `/ping`
- `/status`
- `/whoami`
- `/health`
- `/logs`
- `/mode [chat|command]`

### Pairing and Allowlist workflow

If `telegram_allowlist_chat_ids.txt` is empty or missing, the bot runs in locked pairing mode:

1. Deploy with `TELEGRAM_PAIRING_CODE` or argument 5.
2. In Telegram, send:
   - `/pair <PAIRING_CODE>`
3. Bot stores your chat id in:
   - `~/agentdata/<profile>/secrets/telegram_allowlist_chat_ids.txt`
4. Only allowlisted chat ids can talk to the bot.

To add more people later (Jennifer, Kiera, Scarlet), append one chat id per line to:

```bash
~/agentdata/<profile>/secrets/telegram_allowlist_chat_ids.txt
```

You can remove `telegram_pairing_code.txt` after initial pairing if desired.

## LLM-backed replies (optional)

Non-command Telegram messages can be answered by an LLM instead of echoed. Requires an API key; uses OpenAI-compatible HTTP API (no local model on the Mini).

Create on the Mini (or add via deploy):

- `~/agentdata/<profile>/secrets/llm_api_key.txt` — your API key (or `openai_api_key.txt`)
- Optional: `~/agentdata/<profile>/secrets/llm_base_url.txt` — override endpoint (e.g. another OpenAI-compatible provider)
- Optional: `~/agentdata/<profile>/secrets/llm_model.txt` — model name (default `gpt-4o-mini`)

The bot keeps the last 10 turns per chat when calling the API. Token usage is tracked in `/api-usage`.

## Deploy Tomorrow (All Nodes)

1. Fill in real IPs in `config/nodes.yaml`
2. Optional: create local token files:
   - `secrets/jason.telegram.token`
   - `secrets/jennifer.telegram.token`
   - `secrets/kiera.telegram.token`
   - `secrets/scarlet.telegram.token`
   - `secrets/<profile>.telegram.pairing_code`
   - `secrets/<profile>.llm_api_key`
3. Run:

```bash
chmod +x scripts/*.sh
./scripts/deploy_all.sh
```

Only nodes with non-TBD host values are deployed.

## Data Isolation Convention

- Code: `~/agentbase/`
- Data: `~/agentdata/<profile>/`
  - `memory.db`
  - `logs/`
  - `secrets/`
  - `sandbox/`

No cross-profile database or secret sharing is implemented.

## Tomorrow Runbook (One Mini At A Time)

1. Power on one Mini and connect it to network.
2. Confirm SSH access from MacBook: `ssh <user>@<mini-ip>`.
3. Deploy profile (and token if using Telegram).
4. Verify `http://<mini-ip>:8600/health`.
5. Send `/start` and `/ping` to the node's Telegram bot.
6. Repeat for next Mini.

## Jcore Locked Baseline

Jcore is considered locked and handoff-ready when these checks pass:

```bash
# Health + control
curl -s http://<JCORE_IP>:8600/health
curl -s http://<JCORE_IP>:8600/status
curl -s http://<JCORE_IP>:8600/api-usage
curl -s http://<JCORE_IP>:8600/backup/status
curl -s http://<JCORE_IP>:8600/approvals
curl -s http://<JCORE_IP>:8600/fleet/status
curl -s http://<JCORE_IP>:8600/interop/messages

# Backup/GitHub sanity (on jcore)
~/agentbase/scripts/backup_code.sh jason
~/agentbase/scripts/backup_data.sh jason
crontab -l

# Approval lifecycle sanity
curl -s -X POST http://<JCORE_IP>:8600/tools/execute \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"request_email","payload":{"to":"verify@example.com","subject":"check","body":"smoke"}}'
```

Expected baseline:

- Agent process is up and `/health` is `ok`
- Telegram responds to `/start`, `/ping`, `/mode`, and normal chat text
- `/backup/status` reports both code and data backups as `ok`
- GitHub push works non-interactively from `backup_code.sh`
- Tier1 approval flow works: queue -> resolve -> execute (idempotent on re-execute)

After this lock, move to `jencore` onboarding.

## Onboarding Jencore (Jennifer node)

**Do it from here.** Use this same Family_Agent repo; no separate project. The jencore Mac Mini runs the same codebase with profile `jennifer` and gets its own data, Telegram bot, and (optional) GitHub backup repo. You keep full access from your MacBook and from jcore.

### What Jennifer gets (on the jencore Mini)

- **Profile:** `jennifer` (config already in `config/profiles/jennifer.yaml`).
- **Data:** `~/agentdata/jennifer/` on jencore (secrets, logs, memory.db, backups).
- **Own Telegram bot:** Create a new bot via BotFather; use its token and pairing code only for jencore.
- **Own GitHub backup repo (optional):** e.g. `AGT_jencore_ai_agent`; add jencore’s deploy key to that repo.
- **Own credentials:** Telegram token, pairing code, optional LLM API key; all live under `~/agentdata/jennifer/secrets/` on jencore.

### Access from here

- **Deploy from MacBook:** Run `deploy.sh jennifer <jencore_ip> <jencore_user> ...` from this repo. Code is rsync’d to jencore; you never need a second “project” on your machine.
- **Health from MacBook:** `curl http://<jencore_ip>:8600/health`.
- **Fleet from jcore:** Once jencore’s host is set in `config/nodes.yaml`, jcore’s `/fleet/status` can show jencore’s health (and interop when configured).

### Checklist

1. **Jencore Mini:** Power on, same network as MacBook, SSH works: `ssh <user>@<jencore_ip>`.
2. **Telegram:** Create a new bot for Jennifer (BotFather) → get token and pairing code.
3. **GitHub (optional):** Create a repo for jencore backups; you’ll add jencore’s SSH deploy key after first deploy or during `setup_github_backup.sh`.
4. **This repo:** Set jennifer’s host in `config/nodes.yaml` to jencore’s IP (replace `192.168.1.TBD`).
5. **Deploy from MacBook (this repo):**

```bash
./scripts/deploy.sh jennifer <jencore_ip> <jencore_user> \
  "<TELEGRAM_TOKEN>" "<PAIRING_CODE>" \
  "<LLM_API_KEY>" "git@github.com:USER/AGT_jencore_ai_agent.git" main
```

   Omit optional args if not ready; you can add Telegram/LLM/GitHub later and re-run deploy or run bootstrap/setup scripts on jencore.
6. **On jencore (if using GitHub backup):** After first deploy, generate SSH key on jencore, add the public key to the jencore backup repo, then run `~/agentbase/scripts/setup_github_backup.sh jennifer <repo_url> main` (or re-deploy with GitHub args).
7. **Verify:** `curl http://<jencore_ip>:8600/health`, then `/start` and `/ping` in Jennifer’s Telegram bot.

### After a significant deploy: notify the user

When you add new features or do a significant deploy to a sub-agent (e.g. jencore):

1. **Update release notes:** Edit `release_notes/<profile>.txt` (e.g. `release_notes/jennifer.txt`) with a short, human-readable list of new capabilities.
2. **Deploy:** Run `./scripts/deploy.sh jennifer <ip> <user> ...` as usual. The deploy script copies `release_notes/<profile>.txt` to the Mini as `~/agentdata/<profile>/release_notes_latest.txt`.
3. **Send notification:** Run `./scripts/notify_agent_user.sh <profile> [host] [user]` to send the user a Telegram message with the new feature set and an invitation to ask questions.
   - If you have `secrets/<profile>.telegram_chat_id` (one chat id per line), the script uses it and you can omit host/user.
   - Otherwise: `./scripts/notify_agent_user.sh jennifer 192.168.7.198 jencore` so the script SSHs to the Mini and reads the first allowed chat id from `~/agentdata/<profile>/secrets/telegram_allowlist_chat_ids.txt`.
4. **In Telegram:** The user can ask "what's new?" or use `/whatsnew`; the bot uses the latest release notes in context to answer.

## New node runbook (Kiera, Scarlet, or any node)

**One repo, no template repo.** Use this same Family_Agent repo for every Mini. Each node only needs a profile (already there for Kiera/Scarlet) and its host/user in `config/nodes.yaml`.

### Quick path

- **Set the node** (from this repo on MacBook):

```bash
./scripts/add_node.sh <node_name> <mini_ip> [mini_username]
```

   Example: `./scripts/add_node.sh kiera 192.168.1.50 kiera`  
   This updates `config/nodes.yaml` and prints the one-time Mini setup and deploy command.

- **On the Mini (one-time):** Same as jencore: Remote Login ON, install Homebrew, add your MacBook SSH key to `~/.ssh/authorized_keys`.

- **Deploy from MacBook:**

```bash
./scripts/deploy.sh <node_name> <mini_ip> <mini_username>
```

   (Or use the exact command printed by `add_node.sh`.)

- **Verify:** `curl http://<mini_ip>:8600/health` and Telegram `/start` if you added a bot.

Profiles for Kiera and Scarlet already exist in `config/profiles/`. No new repo or template needed.

## Agent SSH (deploy key)

A dedicated SSH key in `secrets/deploy_key` lets the agent (or any automation) deploy to Minis without your MacBook. `deploy.sh` uses it automatically when present.

**One-time setup from your MacBook** (you must have password or existing key access to each Mini):

```bash
./scripts/install_deploy_key.sh jennifer
./scripts/install_deploy_key.sh scarlet
./scripts/install_deploy_key.sh kiera
# Optional: ./scripts/install_deploy_key.sh jason
```

Each command SSHs to that node (using your existing key), adds `secrets/deploy_key.pub` to the Mini's `~/.ssh/authorized_keys`, and exits. After that, runs that use `secrets/deploy_key` (e.g. from Cursor or CI) can deploy without a password.

Keep `secrets/deploy_key` private; `secrets/` is in `.gitignore`.

## Family network (Master + sub-agents, secure tunnel)

jcore = Family Agent (Master); jencore, score, kcore = sub-agents. Each person's agent is theirs; you deploy from Family_Agent and can jump in to help. All four can talk over a **secure tunnel** (signed messages, replay protection). See [docs/FAMILY_NETWORK.md](docs/FAMILY_NETWORK.md) for the full model, shared knowledge tunnel, and shareable skills.

**One-time:** Ensure `secrets/interop_shared_key.txt` exists (a single shared secret for the family). Deploy copies it to each profile's secrets on every node you deploy. After that, agents can use `delegate_node_task` and `/interop/inbox` to communicate; only nodes with that key can join.

### Hub-routed reliability mode

If a sub-agent cannot directly reach another sub-agent, send with route-via-hub:

```json
{
  "tool_name": "delegate_node_task",
  "payload": {
    "target_profile": "kiera",
    "task_type": "skills_checkin",
    "route_via": "hub",
    "task_payload": {"question": "Any new skills today?"}
  }
}
```

`auto` mode tries direct first and falls back through jcore.

### Skill transfer governance

- Manifests: `~/agent_skills/manifest.yaml`
- Bundle transfer: `tar.gz` + SHA256 checksum
- Risky permissions (`screen`, `filesystem_write`, `network_external`, `secrets_access`) require explicit override approval.
- Rate limit: max 1 successful new skill install per node per 24h unless override is approved.

### Identity signing migration

Profile config supports:

- `interop_identity_mode: compat` (default)
- `interop_identity_mode: provenance`
- `interop_identity_mode: strict`

When enabled, runtime generates per-node Ed25519 keys in profile secrets and adds identity signatures on envelopes while preserving shared-key compatibility.

## Master credentials (this repo)

You keep **one copy of everyone’s credentials** in this repo so you can deploy any node from your MacBook. Runtime data stays isolated per user on each Mini; only the **master** secrets live here.

**Neither `secrets/` nor `.env` is committed** (both are in `.gitignore`).

**Option A — `.env` (single file, not committed)**

Create a `.env` file at the repo root. Use uppercase profile name + `_TELEGRAM_TOKEN`, `_TELEGRAM_PAIRING_CODE`, `_OPENAI_API_KEY`. `deploy_all.sh` sources `.env` automatically if present.

```bash
# .env (do not commit)
JENNIFER_TELEGRAM_TOKEN=...
JENNIFER_TELEGRAM_PAIRING_CODE=...
JENNIFER_OPENAI_API_KEY=...
```

**Option B — `secrets/` (one file per secret, not committed)**

**Convention (one set per profile):**

| File | Purpose |
| --- | --- |
| `secrets/<profile>.telegram.token` | Telegram bot token for that node |
| `secrets/<profile>.telegram.pairing_code` | Pairing code for that bot |
| `secrets/<profile>.llm_api_key` or `secrets/<profile>.openai_api_key` | OpenAI/LLM key (optional) |

Examples: `secrets/jennifer.telegram.token`, `secrets/jennifer.openai_api_key`, `secrets/kiera.llm_api_key`.

- **Deploy one node:** pass tokens/keys as arguments to `deploy.sh`, or use `deploy_all.sh` which reads from `.env` (Option A) or `secrets/` (Option B).
- **Deploy all nodes:** `./scripts/deploy_all.sh` sources `.env` if present, then per node uses env vars (e.g. `JENNIFER_OPENAI_API_KEY`) or falls back to `secrets/` files.

Users stay separated per Mini; you get master access via `.env` or `secrets/` in this repo.

## Idea Engine Foundation (Jennifer first, reusable for Kiera/Scarlet)

The runtime now supports durable transcript + semantic memory foundations:

- Full Telegram inbound/outbound text is persisted in `telegram_messages` within `~/agentdata/<profile>/memory.db`.
- Vector embeddings are stored in `message_embeddings` for semantic retrieval.
- Ideas can be captured as first-class records in `project_memory` with `status=idea`.
- API usage is persisted in `api_usage` (survives restart), not just in-memory.

### New Telegram commands

- `/idea <text>`: Save an idea record immediately.
- `/ideas [N]`: List latest idea records (default 10).
- `/idea_search <query>`: Semantic search over idea vectors (falls back to keyword search if embeddings are unavailable).
- `#ideaengine` in normal chat text: auto-captures the message as an idea.

### LLM + embedding secrets

Per profile under `~/agentdata/<profile>/secrets/`:

- `llm_api_key.txt` (or `openai_api_key.txt`)
- `llm_model.txt` (optional override)
- `llm_base_url.txt` (optional OpenAI-compatible endpoint)
- `embedding_model.txt` (optional, default `text-embedding-3-small`)

### API usage endpoint

`/api-usage` now supports an optional query window:

```bash
curl -s "http://<NODE_IP>:8600/api-usage?window_days=7"
```

Returns totals plus `by_model`, `by_caller`, and recent calls.

## Public read-only mode for ngrok

Each profile can run in strict read-only API mode:

- Set `public_readonly_mode: true` in `config/profiles/<name>.yaml`
- Set `public_readonly_get_endpoints` allowlist (defaults include `/health`, `/status`, `/api-usage`, `/backup/status`, `/dashboard`, `/dashboard/data`)

When enabled:

- Non-allowlisted GET endpoints return `403`
- All POST endpoints return `403`

This is intended for public ngrok URLs while keeping mutating/admin endpoints private.

## Family dashboard (graphic live view)

The master node (Family Agent / jcore) now serves a live dashboard:

- `GET /dashboard` - visual page with node cards + tunnel graph
- `GET /dashboard/data` - JSON feed used by the page

It visualizes configured nodes from `config/nodes.yaml` (including Pepper if configured) and shows:

- Health and runtime state per node
- API usage enabled/disabled per node
- Backup status (code/data) per node
- Recent interop traffic (`/interop/messages`) as graph edges + activity feed

For ngrok/public sharing, use read-only mode on jcore so only approved GET routes are exposed and all POST endpoints stay blocked.

## Collaboration workflow (Jennifer builds, Jason oversees)

Recommended branch strategy:

- `jennifer/<feature>` for Jennifer-specific work
- `kiera/<feature>` and `scarlet/<feature>` for future nodes
- `core/<feature>` for shared runtime changes

Review policy:

1. Node owner can build and open PRs for their branch.
2. Shared runtime (`core/*`, deploy scripts, security, policy, approvals) requires Jason review.
3. Tier1/Tier2 tool behavior changes require explicit approval and test notes in PR.

Rollout pattern:

1. Merge to main
2. Deploy to one target node
3. Verify `/health`, `/status`, Telegram `/ping`, and `/api-usage`
4. Roll to additional nodes via `deploy.sh` or `deploy_all.sh`
