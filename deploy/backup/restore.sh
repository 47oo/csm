#!/usr/bin/env bash
# CSM database restore skeleton (database design DB-D12).
#
# Default behaviour: restore into a BRAND-NEW target database. If the target
# already exists the script aborts, unless --force is given. `--clean
# --if-exists` is passed to pg_restore ONLY when --force is explicitly set.
# The target database name must be provided explicitly.
#
# Supports execution where no host `pg_restore` exists (finalized note A3):
# it falls back to running pg_restore inside the Compose `db` container using
# that container's own POSTGRES_* environment.
#
# Usage: ./restore.sh <dump-file> <target-db> [--force]
# Env:   DATABASE_URL (local mode), COMPOSE_FILE, COMPOSE_DB_SERVICE (default db)
set -euo pipefail

log() { printf '[restore] %s\n' "$*" >&2; }
die() { printf '[restore] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat >&2 <<'EOF'
Usage: restore.sh <dump-file> <target-db> [--force]

  <dump-file>  pg_dump custom-format ( -Fc ) archive
  <target-db>  destination database name (created if absent)
  --force      allow restoring into an existing database; adds --clean --if-exists
EOF
  exit 2
}

[ "$#" -ge 2 ] || usage
DUMP="$1"
TARGET="$2"
FORCE=0
if [ "${3:-}" = "--force" ]; then
  FORCE=1
elif [ "${3:-}" != "" ]; then
  usage
fi

[ -f "${DUMP}" ] || die "dump file not found: ${DUMP}"
case "${TARGET}" in
  *[!A-Za-z0-9_]*) die "target database name may only contain [A-Za-z0-9_]: ${TARGET}" ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DATABASE_URL="${DATABASE_URL:-}"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/compose.yaml}"
COMPOSE_DB_SERVICE="${COMPOSE_DB_SERVICE:-db}"

if [ "${FORCE}" -eq 1 ]; then
  RESTORE_FLAGS="--clean --if-exists"
  log "force mode: existing database will be cleaned before restore"
else
  RESTORE_FLAGS=""
fi

check_sql="SELECT 1 FROM pg_database WHERE datname = '${TARGET}'"

if command -v pg_restore >/dev/null 2>&1; then
  # --- Local mode ---
  [ -n "${DATABASE_URL}" ] || die "DATABASE_URL is required when running pg_restore locally"
  normalized="${DATABASE_URL#*://}"
  userinfo="${normalized%%@*}"
  rest="${normalized#*@}"
  PGUSER="${userinfo%%:*}"
  if [ "${userinfo}" != "${userinfo#*:}" ]; then
    PGPASSWORD="${userinfo#*:}"
  else
    PGPASSWORD=""
  fi
  hostport="${rest%%/*}"
  PGHOST="${hostport%%:*}"
  if [ "${hostport}" != "${hostport#*:}" ]; then
    PGPORT="${hostport#*:}"
  else
    PGPORT=5432
  fi
  export PGPASSWORD

  exists="$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres -tAc "${check_sql}")"
  if [ -n "${exists}" ]; then
    [ "${FORCE}" -eq 1 ] || die "target database '${TARGET}' already exists; use --force to overwrite"
  else
    log "creating database '${TARGET}'"
    createdb -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" "${TARGET}"
  fi

  log "restoring into '${TARGET}'"
  # shellcheck disable=SC2086
  pg_restore ${RESTORE_FLAGS} --no-owner --no-privileges \
    -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${TARGET}" "${DUMP}"
elif command -v docker >/dev/null 2>&1; then
  # --- Compose mode: run psql/createdb/pg_restore inside the db container ---
  [ -f "${COMPOSE_FILE}" ] || die "compose file not found: ${COMPOSE_FILE}"

  exists="$(docker compose -f "${COMPOSE_FILE}" exec -T \
    -e CSM_CHECK_SQL="${check_sql}" "${COMPOSE_DB_SERVICE}" sh -c \
    'psql -tAc "$CSM_CHECK_SQL" -U "$POSTGRES_USER" -d postgres')"
  if [ -n "${exists}" ]; then
    [ "${FORCE}" -eq 1 ] || die "target database '${TARGET}' already exists; use --force to overwrite"
  else
    log "creating database '${TARGET}'"
    docker compose -f "${COMPOSE_FILE}" exec -T \
      -e CSM_TARGET="${TARGET}" "${COMPOSE_DB_SERVICE}" sh -c \
      'createdb -U "$POSTGRES_USER" "$CSM_TARGET"'
  fi

  log "restoring into '${TARGET}'"
  docker compose -f "${COMPOSE_FILE}" exec -T \
    -e CSM_TARGET="${TARGET}" -e CSM_FLAGS="${RESTORE_FLAGS}" "${COMPOSE_DB_SERVICE}" sh -c \
    'exec pg_restore $CSM_FLAGS --no-owner --no-privileges -U "$POSTGRES_USER" -d "$CSM_TARGET"' \
    < "${DUMP}"
else
  die "neither pg_restore nor docker is available; cannot restore"
fi

log "restore complete: ${TARGET}"