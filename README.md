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
