#!/usr/bin/env bash
# Set a node's host (and optional user) in config/nodes.yaml and print next steps.
# Usage: ./scripts/add_node.sh <node_name> <host> [user]
# Example: ./scripts/add_node.sh kiera 192.168.1.50 kiera
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <node_name> <host> [user]"
  echo "Example: $0 kiera 192.168.1.50 kiera"
  exit 1
fi

NODE="$1"
HOST="$2"
USER="${3:-$NODE}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NODES_FILE="$REPO_ROOT/config/nodes.yaml"
PROFILE_FILE="$REPO_ROOT/config/profiles/${NODE}.yaml"

if [[ ! -f "$NODES_FILE" ]]; then
  echo "Missing: $NODES_FILE"
  exit 1
fi

if [[ ! -f "$PROFILE_FILE" ]]; then
  echo "Missing profile: $PROFILE_FILE (create it from config/profiles/jennifer.yaml)"
  exit 1
fi

python3 - "$NODES_FILE" "$NODE" "$HOST" "$USER" <<'PY'
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1])
node = sys.argv[2]
host = sys.argv[3]
user = sys.argv[4]
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
nodes = data.setdefault("nodes", {})
if node not in nodes:
    print(f"Node '{node}' not in nodes.yaml; add it first.")
    sys.exit(1)
nodes[node]["host"] = host
nodes[node]["user"] = user
path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
PY

echo "Updated config/nodes.yaml: $NODE -> host=$HOST, user=$USER"
echo ""
echo "--- One-time on the Mini (if not done yet) ---"
echo "1. Remote Login ON (System Settings → Sharing)"
echo "2. Install Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
echo "3. Add to shell: echo 'eval \"\$(/opt/homebrew/bin/brew shellenv)\"' >> ~/.zprofile && eval \"\$(/opt/homebrew/bin/brew shellenv)\""
echo "4. SSH key from MacBook: on MacBook run: cat ~/.ssh/id_ed25519.pub"
echo "   On Mini: mkdir -p ~/.ssh && chmod 700 ~/.ssh"
echo "   Then: echo 'PASTE_KEY_HERE' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
echo ""
echo "--- Deploy from MacBook (this repo) ---"
echo "./scripts/deploy.sh $NODE $HOST $USER"
echo ""
echo "Optional: add Telegram/LLM/GitHub as extra args; see README."
