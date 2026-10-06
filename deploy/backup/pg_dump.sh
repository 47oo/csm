#!/usr/bin/env bash
# CSM database backup skeleton (database design DB-D12).
#
# - Reads DATABASE_URL (never echoes credentials).
# - Uses `pg_dump -Fc --no-owner --no-privileges`.
# - Writes to an atomically renamed timestamped file; non-zero exit on failure.
# - Supports execution where no host `pg_dump` exists (finalized note A3):
#   it falls back to running pg_dump inside the Compose `db` container using
#   that container's own POSTGRES_* environment, so no secret appears on the
#   host command line.
#
# Usage: ./pg_dump.sh
# Env:   DATABASE_URL, BACKUP_DIR (default ./backups),
#        COMPOSE_FILE, COMPOSE_DB_SERVICE (default db)
set -euo pipefail

log() { printf '[pg_dump] %s\n' "$*" >&2; }
die() { printf '[pg_dump] ERROR: %s\n' "$*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DATABASE_URL="${DATABASE_URL:-}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/compose.yaml}"
COMPOSE_DB_SERVICE="${COMPOSE_DB_SERVICE:-db}"

DB_LABEL="${POSTGRES_DB:-csm}"
if [ -n "${DATABASE_URL}" ]; then
  DB_LABEL="${DATABASE_URL##*/}"
  DB_LABEL="${DB_LABEL%%\?*}"
fi

mkdir -p "${BACKUP_DIR}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR}/csm-${DB_LABEL}-${TS}.dump"
TMP="${OUT}.tmp"
trap 'rm -f "${TMP}"' EXIT

if command -v pg_dump >/dev/null 2>&1; then
  # --- Local mode: pg_dump present (host or inside a client container) ---
  [ -n "${DATABASE_URL}" ] || die "DATABASE_URL is required when running pg_dump locally"

  normalized="${DATABASE_URL#*://}"
  userinfo="${normalized%%@*}"
  rest="${normalized#*@}"
  [ "${rest}" != "${normalized}" ] || die "DATABASE_URL must include credentials and host"

  PGUSER="${userinfo%%:*}"
  if [ "${userinfo}" != "${userinfo#*:}" ]; then
    PGPASSWORD="${userinfo#*:}"
  else
    PGPASSWORD=""
  fi
  hostport="${rest%%/*}"
  PGDATABASE="${rest#*/}"
  PGDATABASE="${PGDATABASE%%\?*}"
  PGHOST="${hostport%%:*}"
  if [ "${hostport}" != "${hostport#*:}" ]; then
    PGPORT="${hostport#*:}"
  else
    PGPORT=5432
  fi

  export PGPASSWORD
  log "dumping database '${PGDATABASE}' via local pg_dump"
  pg_dump -Fc --no-owner --no-privileges \
    -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" > "${TMP}"
elif command -v docker >/dev/null 2>&1; then
  # --- Compose mode: run pg_dump inside the db container ---
  [ -f "${COMPOSE_FILE}" ] || die "compose file not found: ${COMPOSE_FILE}"
  log "dumping via 'docker compose exec ${COMPOSE_DB_SERVICE}' (in-container pg_dump)"
  docker compose -f "${COMPOSE_FILE}" exec -T "${COMPOSE_DB_SERVICE}" sh -c \
    'exec pg_dump -Fc --no-owner --no-privileges -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    > "${TMP}"
else
  die "neither pg_dump nor docker is available; cannot produce a backup"
fi

[ -s "${TMP}" ] || die "backup output is empty"
mv "${TMP}" "${OUT}"
trap - EXIT
log "backup written: ${OUT}"