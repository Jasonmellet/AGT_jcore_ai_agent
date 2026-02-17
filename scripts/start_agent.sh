#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <profile>"
  exit 1
fi

PROFILE="$1"
BASE_DIR="$HOME/agentbase"
VENV_PATH="$BASE_DIR/.venv"

if [[ ! -d "$VENV_PATH" ]]; then
  echo "Virtual environment not found: $VENV_PATH"
  exit 1
fi

cd "$BASE_DIR"
source "$VENV_PATH/bin/activate"
exec python -m core.agent --profile "$PROFILE"
