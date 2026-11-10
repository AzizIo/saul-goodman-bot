#!/usr/bin/env bash
# Ежедневный бэкап SQLite. Добавить в cron:
#   0 3 * * * /opt/saul-goodman-bot/deploy/backup.sh
set -euo pipefail

DB_PATH="${DB_PATH:-/opt/saul-goodman-bot/data/saul.db}"
BACKUP_DIR="${BACKUP_DIR:-/opt/saul-goodman-bot/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/saul-$STAMP.db"

# .backup — консистентный снимок даже при работающем боте
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$TARGET'"
else
  python3 - "$DB_PATH" "$TARGET" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
    s.backup(d)
PY
fi

find "$BACKUP_DIR" -name 'saul-*.db' -mtime +"$KEEP_DAYS" -delete
echo "backup: $TARGET"