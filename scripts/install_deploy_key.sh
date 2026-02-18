#!/usr/bin/env bash
# One-time: add the repo's deploy public key to a Mini so the agent can SSH without a password.
# Usage: $0 <node_name>   (reads host/user from config/nodes.yaml)
#    or: $0 <node_name> <host> [user]
set -euo pipefail

NODE="${1:-}"
HOST="${2:-}"
USER_NAME="${3:-}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUBKEY="$REPO_ROOT/secrets/deploy_key.pub"

if [[ ! -f "$PUBKEY" ]]; then
  echo "Missing $PUBKEY (run from repo that has secrets/deploy_key generated)."
  exit 1
fi

if [[ -z "$NODE" ]]; then
  echo "Usage: $0 <node_name> [host] [user]"
  echo "  node_name: jason, jennifer, kiera, scarlet"
  echo "  If host/user omitted, reads from config/nodes.yaml"
  exit 1
fi

if [[ -z "$HOST" ]]; then
  NODES_FILE="$REPO_ROOT/config/nodes.yaml"
  if [[ ! -f "$NODES_FILE" ]]; then
    echo "Missing $NODES_FILE"
    exit 1
  fi
  # Parse node block (simple YAML: key: value)
  in_block=0
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*${NODE}:[[:space:]]*$ ]]; then
      in_block=1
      continue
    fi
    [[ $in_block -eq 0 ]] && continue
    [[ "$line" =~ ^[[:space:]]*[a-z_]+:[[:space:]] ]] || break
    if [[ "$line" =~ host:[[:space:]]*(.+)$ ]]; then
      HOST="${BASH_REMATCH[1]}"
    elif [[ "$line" =~ user:[[:space:]]*[\"\']?([^\"\' ]+)[\"\']?[[:space:]]*$ ]]; then
      USER_NAME="${BASH_REMATCH[1]}"
    fi
  done < "$NODES_FILE"
  USER_NAME="${USER_NAME:-$NODE}"
fi

if [[ -z "$HOST" ]]; then
  echo "Could not get host for node $NODE. Pass: $0 $NODE <host> [user]"
  exit 1
fi

USER_NAME="${USER_NAME:-$NODE}"
TARGET="$USER_NAME@$HOST"
echo "Adding deploy key to $TARGET (use your existing SSH key when prompted)..."
ssh -o ConnectTimeout=10 "$TARGET" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys" < "$PUBKEY"
echo "Done. Deploy key is now authorized on $TARGET."
