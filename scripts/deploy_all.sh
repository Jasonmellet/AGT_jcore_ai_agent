#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NODES_FILE="$REPO_ROOT/config/nodes.yaml"
DEPLOY_SCRIPT="$REPO_ROOT/scripts/deploy.sh"
LOCAL_SECRETS_DIR="$REPO_ROOT/secrets"
[[ -f "$REPO_ROOT/.env" ]] && set -a && source "$REPO_ROOT/.env" && set +a

if [[ ! -f "$NODES_FILE" ]]; then
  echo "Missing nodes file: $NODES_FILE"
  exit 1
fi

if [[ ! -x "$DEPLOY_SCRIPT" ]]; then
  chmod +x "$DEPLOY_SCRIPT"
fi

successes=()
failures=()

while IFS='|' read -r profile host user_name; do
  [[ -z "${profile}" ]] && continue
  echo "Deploying $profile to $host as $user_name"
  token_file="$LOCAL_SECRETS_DIR/$profile.telegram.token"
  pairing_file="$LOCAL_SECRETS_DIR/$profile.telegram.pairing_code"
  llm_key_file="$LOCAL_SECRETS_DIR/$profile.llm_api_key"
  openai_key_file="$LOCAL_SECRETS_DIR/$profile.openai_api_key"
  profile_upper="$(echo "$profile" | tr '[:lower:]' '[:upper:]')"
  token_var="${profile_upper}_TELEGRAM_TOKEN"
  pairing_var="${profile_upper}_TELEGRAM_PAIRING_CODE"
  llm_var="${profile_upper}_OPENAI_API_KEY"

  token_value="${!token_var:-}"
  pairing_value="${!pairing_var:-}"
  llm_key_value="${!llm_var:-}"
  [[ -z "$token_value" && -f "$token_file" ]] && token_value="$(tr -d '\r\n' < "$token_file")"
  [[ -z "$pairing_value" && -f "$pairing_file" ]] && pairing_value="$(tr -d '\r\n' < "$pairing_file")"
  if [[ -z "$llm_key_value" ]]; then
    [[ -f "$llm_key_file" ]] && llm_key_value="$(tr -d '\r\n' < "$llm_key_file")"
    [[ -z "$llm_key_value" && -f "$openai_key_file" ]] && llm_key_value="$(tr -d '\r\n' < "$openai_key_file")"
  fi

  if "$DEPLOY_SCRIPT" "$profile" "$host" "$user_name" "$token_value" "$pairing_value" "$llm_key_value"; then
    echo "SUCCESS: $profile@$host"
    successes+=("$profile@$host")
  else
    echo "FAILURE: $profile@$host"
    failures+=("$profile@$host")
  fi
done < <(python3 - "$NODES_FILE" <<'PY'
import os
import sys
from pathlib import Path

import yaml

nodes_path = Path(sys.argv[1])
raw = yaml.safe_load(nodes_path.read_text(encoding="utf-8")) or {}
nodes = raw.get("nodes", {})

for _, spec in nodes.items():
    profile = str(spec.get("profile", "")).strip()
    host = str(spec.get("host", "")).strip()
    user_name = str(spec.get("user", os.environ.get("USER", ""))).strip()
    if not profile or not host or host.endswith(".TBD"):
        continue
    print(f"{profile}|{host}|{user_name}")
PY
)

echo ""
echo "Deployment summary:"
echo "  Successful: ${#successes[@]}"
for s in "${successes[@]}"; do
  echo "    - $s"
done
echo "  Failed: ${#failures[@]}"
for f in "${failures[@]}"; do
  echo "    - $f"
done

if [[ ${#failures[@]} -gt 0 ]]; then
  echo ""
  echo "Retry guidance:"
  echo "  1) Verify SSH connectivity: ssh <user>@<host>"
  echo "  2) Re-run single node: ./scripts/deploy.sh <profile> <host> <user>"
  echo "  3) Check remote runtime logs: ~/agentdata/<profile>/logs/runtime.log"
  exit 1
fi

echo "All configured nodes deployed."
