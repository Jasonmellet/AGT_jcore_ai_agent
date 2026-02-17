#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <profile>"
  exit 1
fi

PROFILE="$1"
PATTERN="core.agent --profile $PROFILE"

pkill -f "$PATTERN" 2>/dev/null || true
sleep 1
pkill -9 -f "$PATTERN" 2>/dev/null || true
exit 0
