#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <profile>"
  exit 1
fi

PROFILE="$1"
BASE_DIR="$HOME/agentbase"
DATA_DIR="$HOME/agentdata/$PROFILE"
MARK_BEGIN="# BEGIN FAMILY_AGENT_BACKUPS_$PROFILE"
MARK_END="# END FAMILY_AGENT_BACKUPS_$PROFILE"

mkdir -p "$DATA_DIR/logs"

TMP_EXISTING="$(mktemp)"
TMP_NEW="$(mktemp)"
trap 'rm -f "$TMP_EXISTING" "$TMP_NEW"' EXIT

crontab -l 2>/dev/null >"$TMP_EXISTING" || true

awk -v begin="$MARK_BEGIN" -v end="$MARK_END" '
  $0 == begin {skip=1; next}
  $0 == end {skip=0; next}
  skip != 1 {print}
' "$TMP_EXISTING" >"$TMP_NEW"

{
  echo "$MARK_BEGIN"
  echo "5 * * * * $BASE_DIR/scripts/backup_code.sh $PROFILE >> $DATA_DIR/logs/backup_code.log 2>&1"
  echo "10 * * * * $BASE_DIR/scripts/backup_data.sh $PROFILE >> $DATA_DIR/logs/backup_data.log 2>&1"
  echo "$MARK_END"
} >>"$TMP_NEW"

if crontab "$TMP_NEW"; then
  echo "Installed backup cron jobs for profile: $PROFILE"
else
  echo "WARNING: Unable to install cron jobs for profile: $PROFILE (permission denied)."
  echo "Run this script from an interactive Terminal session on the Mini after granting Terminal Full Disk Access."
fi
