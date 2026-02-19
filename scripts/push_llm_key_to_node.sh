#!/usr/bin/env bash
# Push LLM key from repo to a node (e.g. jcore for skills_checkin replies).
# Usage: $0 <profile> <host> [user]
# Requires: secrets/<profile>.openai_api_key or secrets/<profile>.llm_api_key
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${1:?profile}"
HOST="${2:?host}"
USER_NAME="${3:-$USER}"
TARGET="$USER_NAME@$HOST"

KEY_FILE=""
for f in "$REPO_ROOT/secrets/$PROFILE.llm_api_key" "$REPO_ROOT/secrets/$PROFILE.openai_api_key"; do
  if [[ -f "$f" ]]; then
    KEY_FILE="$f"
    break
  fi
done
if [[ -z "$KEY_FILE" ]]; then
  echo "No key found. Add secrets/$PROFILE.openai_api_key or secrets/$PROFILE.llm_api_key" >&2
  exit 1
fi

BASE_SSH_OPTS=(-o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new)
SSH_OPTS=("${BASE_SSH_OPTS[@]}")
DEPLOY_KEY="$REPO_ROOT/secrets/deploy_key"
if [[ -f "$DEPLOY_KEY" ]]; then
  KEY_SSH_OPTS=("${BASE_SSH_OPTS[@]}" -i "$DEPLOY_KEY" -o IdentitiesOnly=yes)
  if ssh "${KEY_SSH_OPTS[@]}" "$TARGET" "echo 'ssh_ok'" >/dev/null 2>&1; then
    SSH_OPTS=("${KEY_SSH_OPTS[@]}")
  fi
fi

ssh "${SSH_OPTS[@]}" "$TARGET" "mkdir -p ~/agentdata/$PROFILE/secrets"
ssh "${SSH_OPTS[@]}" "$TARGET" "umask 077 && cat > ~/agentdata/$PROFILE/secrets/llm_api_key.txt && chmod 600 ~/agentdata/$PROFILE/secrets/llm_api_key.txt" < "$KEY_FILE"
echo "Pushed LLM key to $TARGET (~/agentdata/$PROFILE/secrets/llm_api_key.txt)"
