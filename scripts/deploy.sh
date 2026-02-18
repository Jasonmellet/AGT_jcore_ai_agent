#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <profile> <host> [user] [telegram_token] [pairing_code] [llm_api_key] [github_repo_url] [github_branch]"
  echo "Tips:"
  echo "  - TELEGRAM_BOT_TOKEN env var supported"
  echo "  - TELEGRAM_PAIRING_CODE env var supported"
  echo "  - LLM_API_KEY env var supported"
  echo "  - GITHUB_REPO_URL env var supported"
  echo "  - GITHUB_REPO_BRANCH env var supported (default: main)"
  exit 1
fi

PROFILE="$1"
HOST="$2"
USER_NAME="${3:-$USER}"
TELEGRAM_TOKEN="${4:-${TELEGRAM_BOT_TOKEN:-}}"
TELEGRAM_PAIRING_CODE="${5:-${TELEGRAM_PAIRING_CODE:-}}"
LLM_API_KEY_VALUE="${6:-${LLM_API_KEY:-}}"
GITHUB_REPO_URL_VALUE="${7:-${GITHUB_REPO_URL:-}}"
GITHUB_REPO_BRANCH_VALUE="${8:-${GITHUB_REPO_BRANCH:-main}}"
TARGET="$USER_NAME@$HOST"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Prefer deploy key for automation; fall back to default SSH identities if needed.
BASE_SSH_OPTS=(-o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new)
SSH_OPTS=("${BASE_SSH_OPTS[@]}")
RSYNC_SSH="ssh -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new"
DEPLOY_KEY="$REPO_ROOT/secrets/deploy_key"
if [[ -f "$DEPLOY_KEY" ]]; then
  KEY_SSH_OPTS=("${BASE_SSH_OPTS[@]}" -i "$DEPLOY_KEY" -o IdentitiesOnly=yes)
  if ssh "${KEY_SSH_OPTS[@]}" "$TARGET" "echo 'ssh_ok'" >/dev/null 2>&1; then
    SSH_OPTS=("${KEY_SSH_OPTS[@]}")
    RSYNC_SSH+=" -i \"$DEPLOY_KEY\" -o IdentitiesOnly=yes"
    echo "Using deploy key for $TARGET"
  fi
fi

echo "Deploying profile '$PROFILE' to $TARGET..."
ssh "${SSH_OPTS[@]}" "$TARGET" "echo 'ssh_ok'" >/dev/null
ssh "${SSH_OPTS[@]}" "$TARGET" "mkdir -p \"\$HOME/agentbase\""
rsync -az --delete -e "$RSYNC_SSH" \
  --exclude ".git/" \
  --exclude ".venv/" \
  --exclude "__pycache__/" \
  "$REPO_ROOT/" "$TARGET:~/agentbase/"

ssh "${SSH_OPTS[@]}" "$TARGET" "chmod +x ~/agentbase/scripts/*.sh"
ssh "${SSH_OPTS[@]}" "$TARGET" "~/agentbase/scripts/bootstrap.sh \"$PROFILE\""
ssh "${SSH_OPTS[@]}" "$TARGET" "mkdir -p ~/agentdata/$PROFILE/secrets"

if [[ -n "$TELEGRAM_TOKEN" ]]; then
  ssh "${SSH_OPTS[@]}" "$TARGET" "umask 077 && cat > ~/agentdata/$PROFILE/secrets/telegram_bot_token.txt && chmod 600 ~/agentdata/$PROFILE/secrets/telegram_bot_token.txt" <<<"$TELEGRAM_TOKEN"
fi

if [[ -n "$TELEGRAM_PAIRING_CODE" ]]; then
  ssh "${SSH_OPTS[@]}" "$TARGET" "umask 077 && cat > ~/agentdata/$PROFILE/secrets/telegram_pairing_code.txt && chmod 600 ~/agentdata/$PROFILE/secrets/telegram_pairing_code.txt" <<<"$TELEGRAM_PAIRING_CODE"
fi

if [[ -n "$LLM_API_KEY_VALUE" ]]; then
  ssh "${SSH_OPTS[@]}" "$TARGET" "umask 077 && cat > ~/agentdata/$PROFILE/secrets/llm_api_key.txt && chmod 600 ~/agentdata/$PROFILE/secrets/llm_api_key.txt" <<<"$LLM_API_KEY_VALUE"
fi

if [[ -f "$REPO_ROOT/secrets/interop_shared_key.txt" ]]; then
  ssh "${SSH_OPTS[@]}" "$TARGET" "umask 077 && cat > ~/agentdata/$PROFILE/secrets/interop_shared_key.txt && chmod 600 ~/agentdata/$PROFILE/secrets/interop_shared_key.txt" < "$REPO_ROOT/secrets/interop_shared_key.txt"
fi

if [[ -n "$GITHUB_REPO_URL_VALUE" ]]; then
  ssh "${SSH_OPTS[@]}" "$TARGET" "~/agentbase/scripts/setup_github_backup.sh \"$PROFILE\" \"$GITHUB_REPO_URL_VALUE\" \"$GITHUB_REPO_BRANCH_VALUE\""
fi

if [[ -f "$REPO_ROOT/release_notes/$PROFILE.txt" ]]; then
  ssh "${SSH_OPTS[@]}" "$TARGET" "mkdir -p ~/agentdata/$PROFILE"
  rsync -az -e "$RSYNC_SSH" "$REPO_ROOT/release_notes/$PROFILE.txt" "$TARGET:~/agentdata/$PROFILE/release_notes_latest.txt"
fi

ssh "${SSH_OPTS[@]}" "$TARGET" "~/agentbase/scripts/stop_agent.sh \"$PROFILE\" || true"
sleep 2
ssh "${SSH_OPTS[@]}" "$TARGET" "nohup ~/agentbase/scripts/start_agent.sh \"$PROFILE\" > ~/agentdata/$PROFILE/logs/runtime.log 2>&1 &"
sleep 1
ssh "${SSH_OPTS[@]}" "$TARGET" "tail -n 5 ~/agentdata/$PROFILE/logs/runtime.log >/dev/null 2>&1 || true"

echo "Deployment complete for $PROFILE on $HOST"
