#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <profile>"
  exit 1
fi

PROFILE="$1"
BASE_DIR="$HOME/agentbase"
DATA_DIR="$HOME/agentdata/$PROFILE"
LOG_FILE="$DATA_DIR/logs/backup_code.log"
BRANCH_FILE="$DATA_DIR/secrets/github_backup_branch.txt"

mkdir -p "$DATA_DIR/logs"
touch "$LOG_FILE"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $*" | tee -a "$LOG_FILE"
}

if [[ ! -d "$BASE_DIR" ]]; then
  log "SKIP: missing repo dir $BASE_DIR"
  exit 0
fi

if [[ ! -d "$BASE_DIR/.git" ]]; then
  log "SKIP: git repo not initialized in $BASE_DIR"
  exit 0
fi

if ! git -C "$BASE_DIR" remote get-url origin >/dev/null 2>&1; then
  log "SKIP: git remote 'origin' not configured"
  exit 0
fi

BRANCH="main"
if [[ -f "$BRANCH_FILE" ]]; then
  raw="$(tr -d '\r\n' < "$BRANCH_FILE")"
  [[ -n "$raw" ]] && BRANCH="$raw"
fi

if [[ -z "$(git -C "$BASE_DIR" status --porcelain)" ]]; then
  log "No code changes detected"
  exit 0
fi

log "Changes detected. Committing backup snapshot."
git -C "$BASE_DIR" add -A
git -C "$BASE_DIR" commit -m "Auto-backup ${PROFILE} $(date '+%Y-%m-%d %H:%M:%S')" >>"$LOG_FILE" 2>&1 || true

if git -C "$BASE_DIR" push origin "$BRANCH" >>"$LOG_FILE" 2>&1; then
  log "Code backup pushed to origin/$BRANCH"
else
  log "ERROR: git push failed (check auth/remote)"
  exit 1
fi
