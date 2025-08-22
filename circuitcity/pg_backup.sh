#!/usr/bin/env bash
set -euo pipefail
[ -f ".env" ] && source .env
TS=$(date +"%Y-%m-%d_%H-%M")
OUT_DIR=${1:-backups}
mkdir -p "$OUT_DIR"
PGPASSWORD="$DB_PASSWORD" pg_dump \
  -h "${DB_HOST:-127.0.0.1}" -p "${DB_PORT:-5432}" \
  -U "$DB_USER" -F c -b -v -f "$OUT_DIR/${DB_NAME}_${TS}.dump" "$DB_NAME"
ls -1t "$OUT_DIR"/*.dump | tail -n +15 | xargs -r rm --
echo "Backup done: $OUT_DIR/${DB_NAME}_${TS}.dump"
