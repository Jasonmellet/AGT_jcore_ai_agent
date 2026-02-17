#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <profile> <repo_url> [branch]"
  exit 1
fi

PROFILE="$1"
REPO_URL="$2"
BRANCH="${3:-main}"
BASE_DIR="$HOME/agentbase"
DATA_DIR="$HOME/agentdata/$PROFILE"
SECRETS_DIR="$DATA_DIR/secrets"

mkdir -p "$SECRETS_DIR"

if [[ ! -d "$BASE_DIR/.git" ]]; then
  git -C "$BASE_DIR" init
fi

if ! git -C "$BASE_DIR" config user.name >/dev/null; then
  git -C "$BASE_DIR" config user.name "Family Agent Backup"
fi
if ! git -C "$BASE_DIR" config user.email >/dev/null; then
  git -C "$BASE_DIR" config user.email "family-agent@local"
fi

if git -C "$BASE_DIR" remote get-url origin >/dev/null 2>&1; then
  git -C "$BASE_DIR" remote set-url origin "$REPO_URL"
else
  git -C "$BASE_DIR" remote add origin "$REPO_URL"
fi

git -C "$BASE_DIR" branch -M "$BRANCH"
printf "%s\n" "$BRANCH" >"$SECRETS_DIR/github_backup_branch.txt"
chmod 600 "$SECRETS_DIR/github_backup_branch.txt"

echo "GitHub backup configured:"
echo "  repo: $(git -C "$BASE_DIR" remote get-url origin)"
echo "  branch: $BRANCH"
