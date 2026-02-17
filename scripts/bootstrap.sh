#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <profile>"
  exit 1
fi

# Ensure Homebrew is on PATH when running via non-interactive SSH
if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi
for f in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc"; do
  [[ -f "$f" ]] && source "$f" 2>/dev/null || true
done
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

PROFILE="$1"
BASE_DIR="$HOME/agentbase"
DATA_DIR="$HOME/agentdata/$PROFILE"
VENV_PATH="$BASE_DIR/.venv"
PLIST_TEMPLATE="$BASE_DIR/launchagents/com.familyagent.core.plist"
PLIST_TARGET="$HOME/Library/LaunchAgents/com.familyagent.core.$PROFILE.plist"
TMP_PLIST="$(mktemp)"

ensure_python312() {
  if command -v python3 >/dev/null 2>&1; then
    if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
      return
    fi
  fi

  BREW=""
  command -v brew >/dev/null 2>&1 && BREW=brew
  [[ -z "$BREW" && -x /opt/homebrew/bin/brew ]] && BREW=/opt/homebrew/bin/brew
  [[ -z "$BREW" && -x /usr/local/bin/brew ]] && BREW=/usr/local/bin/brew
  if [[ -z "$BREW" ]]; then
    echo "Homebrew is required to install Python 3.12+"
    exit 1
  fi

  "$BREW" install python@3.12
  # Ensure brew's python3 is on PATH for venv
  if [[ -x /opt/homebrew/bin/python3.12 ]]; then
    export PATH="/opt/homebrew/bin:$PATH"
  elif [[ -x /usr/local/bin/python3.12 ]]; then
    export PATH="/usr/local/bin:$PATH"
  fi
}

ensure_python312

PYTHON="python3"
for p in python3.12 python3; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    PYTHON="$p"
    break
  fi
done

mkdir -p "$DATA_DIR/logs" "$DATA_DIR/secrets" "$DATA_DIR/sandbox" "$HOME/Library/LaunchAgents"

cd "$BASE_DIR"
"$PYTHON" -m venv "$VENV_PATH"
source "$VENV_PATH/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [[ ! -f "$PLIST_TEMPLATE" ]]; then
  echo "Missing LaunchAgent template: $PLIST_TEMPLATE"
  exit 1
fi

python - "$PLIST_TEMPLATE" "$TMP_PLIST" "$PROFILE" "$BASE_DIR" "$USER" <<'PY'
from pathlib import Path
import sys

template = Path(sys.argv[1]).read_text(encoding="utf-8")
profile = sys.argv[3]
base_dir = sys.argv[4]
username = sys.argv[5]
rendered = (
    template.replace("__PROFILE__", profile)
    .replace("__BASE_DIR__", base_dir)
    .replace("__USER__", username)
)
Path(sys.argv[2]).write_text(rendered, encoding="utf-8")
PY

cp "$TMP_PLIST" "$PLIST_TARGET"
rm -f "$TMP_PLIST"
launchctl unload "$PLIST_TARGET" >/dev/null 2>&1 || true
launchctl load "$PLIST_TARGET"

"$BASE_DIR/scripts/install_backup_cron.sh" "$PROFILE"

echo "Bootstrap completed for profile: $PROFILE"
