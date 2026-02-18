#!/usr/bin/env bash
# Send a post-deploy notification to the agent user's Telegram.
# Usage: ./scripts/notify_agent_user.sh <profile> [host] [user]
# If host/user omitted, reads from config/nodes.yaml for that profile.
# Message is built from release_notes/<profile>.txt and a short invite.
set -euo pipefail

PROFILE="${1:?Usage: $0 <profile> [host] [user]}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS_DIR="$REPO_ROOT/secrets"
NOTES_FILE="$REPO_ROOT/release_notes/$PROFILE.txt"
TOKEN_FILE="$SECRETS_DIR/$PROFILE.telegram.token"
CHAT_ID_FILE="$SECRETS_DIR/$PROFILE.telegram_chat_id"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing token file: $TOKEN_FILE"
  exit 1
fi
TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"

CHAT_ID=""
if [[ -f "$CHAT_ID_FILE" ]]; then
  CHAT_ID="$(tr -d '\r\n' < "$CHAT_ID_FILE")"
fi

if [[ -z "$CHAT_ID" && -n "${2:-}" ]]; then
  TARGET="${3:-$PROFILE}@$2"
  SSH_OPTS=(-o ConnectTimeout=8 -o BatchMode=yes)
  ALLOWLIST="$REPO_ROOT/secrets/.allowlist_${PROFILE}.tmp"
  ssh "${SSH_OPTS[@]}" "$TARGET" "cat ~/agentdata/$PROFILE/secrets/telegram_allowlist_chat_ids.txt 2>/dev/null | head -1" > "$ALLOWLIST" 2>/dev/null || true
  if [[ -s "$ALLOWLIST" ]]; then
    CHAT_ID="$(tr -d '\r\n' < "$ALLOWLIST")"
  fi
  rm -f "$ALLOWLIST"
fi

if [[ -z "$CHAT_ID" ]]; then
  echo "Could not get chat_id. Add $CHAT_ID_FILE with the user's Telegram chat id (e.g. from /whoami or allowlist on Mini), or run with: $0 $PROFILE <host> [user]"
  exit 1
fi

BODY=""
if [[ -f "$NOTES_FILE" ]]; then
  BODY="$(cat "$NOTES_FILE")
---
You can ask me what's new, what I can do, or how to use any of this. Just chat or use /whatsnew."
else
  BODY="Your assistant was just updated. You can ask me what's new or what I can do. Try /whatsnew or just ask in chat."
fi

# Telegram API: sendMessage (payload as form to avoid URL length limits)
TMP_BODY="$(mktemp)"
trap 'rm -f "$TMP_BODY"' EXIT
printf '%s' "$BODY" > "$TMP_BODY"
if curl -sS -f -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -F "chat_id=${CHAT_ID}" \
  -F "text=<$TMP_BODY" >/dev/null 2>&1; then
  echo "Notification sent to $PROFILE (chat_id=$CHAT_ID)"
else
  echo "Failed to send Telegram message. Check token and chat_id."
  exit 1
fi
