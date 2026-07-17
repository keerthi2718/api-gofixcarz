#!/usr/bin/env bash
# ─── Garage Management API — Database Restore ─────────────────────────────────
# Usage: ./scripts/restore_db.sh <path/to/backup.sql>
# Restores the database from a SQL dump file.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <path/to/backup.sql>" >&2
  exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "ERROR: Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  source "$PROJECT_ROOT/.env"
  set +a
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not set." >&2
  exit 1
fi

echo "Restoring from: $BACKUP_FILE"
echo "WARNING: This will overwrite existing data. Press Ctrl+C within 5 seconds to cancel."
sleep 5

psql "$DATABASE_URL" --no-password < "$BACKUP_FILE"

echo "Restore complete."
