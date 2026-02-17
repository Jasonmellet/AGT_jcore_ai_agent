#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <profile>"
  exit 1
fi

PROFILE="$1"
DATA_DIR="$HOME/agentdata/$PROFILE"
DB_FILE="$DATA_DIR/memory.db"
BACKUP_ROOT="$DATA_DIR/backups"
DATE_STAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
BACKUP_DIR="$BACKUP_ROOT/$DATE_STAMP"
LOG_FILE="$DATA_DIR/logs/backup_data.log"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

mkdir -p "$DATA_DIR/logs" "$BACKUP_ROOT"
touch "$LOG_FILE"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $*" | tee -a "$LOG_FILE"
}

if [[ ! -f "$DB_FILE" ]]; then
  log "SKIP: database not found ($DB_FILE)"
  exit 0
fi

mkdir -p "$BACKUP_DIR"
cp "$DB_FILE" "$BACKUP_DIR/memory.db"
chmod 600 "$BACKUP_DIR/memory.db"

find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" -exec rm -rf {} + >/dev/null 2>&1 || true

size="$(du -sh "$BACKUP_DIR" | awk '{print $1}')"
log "Data backup complete: $BACKUP_DIR ($size)"
