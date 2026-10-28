#!/usr/bin/env bash
# F016 T36 backup-covers-Audit verification (architecture §8, DR-240, O-4).
#
# Runs the repo's real backup/restore scripts (in a postgres:16 client
# container, since the host has no pg_dump/pg_restore) and asserts B1-B7.
# Never changes Git state and never touches a production database: it operates
# on the dedicated acceptance database csm_f016_acc / csm_f016_restore.
#
# Usage:
#   F016_PW=... ./verify_audit_backup.sh
#
# Env:
#   F016_PW          acceptance DB password (required)
#   F016_DB          source database       (default csm_f016_acc)
#   F016_RESTORE_DB  restore target        (default csm_f016_restore)
#   F016_DB_CONTAINER (default f016-db)
#   F016_NET         docker network        (default f016-acceptance-net)
#   BACKUP_DIR       host dir for the dump (default scripts/acceptance/artifacts/backup)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
F016_PW="${F016_PW:?F016_PW is required}"
DB="${F016_DB:-csm_f016_acc}"
RESTORE_DB="${F016_RESTORE_DB:-csm_f016_restore}"
DB_CONTAINER="${F016_DB_CONTAINER:-f016-db}"
NET="${F016_NET:-f016-acceptance-net}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/scripts/acceptance/artifacts/backup}"
PG_IMAGE="postgres:16"
APP_IMAGE="${APP_IMAGE:-csm-f007-test}"

mkdir -p "${BACKUP_DIR}"
log()  { printf '[T36] %s\n' "$*"; }
fail() { printf '[T36] FAIL: %s\n' "$*" >&2; exit 1; }

psql_src()  { docker exec -i "${DB_CONTAINER}" psql -U csm -d "${DB}" -tAc "$1"; }
psql_dst()  { docker exec -i "${DB_CONTAINER}" psql -U csm -d "${RESTORE_DB}" -tAc "$1"; }

# --- B0: source has real Audit rows -----------------------------------------
SRC_COUNT="$(psql_src 'SELECT count(*) FROM audit_logs;' | tr -d '[:space:]')"
log "source ${DB} audit_logs rows = ${SRC_COUNT}"
[ "${SRC_COUNT:-0}" -gt 0 ] || fail "source audit_logs is empty; produce writes before backup"

# --- Backup via the repo's pg_dump.sh (postgres client container) -----------
log "running deploy/backup/pg_dump.sh in ${PG_IMAGE}"
docker run --rm --network "${NET}" \
  -v "${REPO_ROOT}:/repo:ro" -v "${BACKUP_DIR}:/backups" \
  -e DATABASE_URL="postgresql://csm:${F016_PW}@db:5432/${DB}" \
  -e BACKUP_DIR=/backups \
  "${PG_IMAGE}" bash /repo/deploy/backup/pg_dump.sh

DUMP="$(ls -1t "${BACKUP_DIR}"/csm-"${DB}"-*.dump 2>/dev/null | head -1 || true)"
[ -n "${DUMP}" ] || fail "no dump produced in ${BACKUP_DIR}"
log "dump = ${DUMP}"

# --- B7: non-empty + pg_restore --list parses -------------------------------
SIZE="$(stat -c %s "${DUMP}")"
log "B7 dump size = ${SIZE} bytes"
[ "${SIZE}" -gt 0 ] || fail "B7 dump is empty"
LIST_OUT="$(docker run --rm -v "${DUMP}:/dump.dump:ro" "${PG_IMAGE}" pg_restore --list /dump.dump)"
printf '%s\n' "${LIST_OUT}" | grep -qE 'TABLE public audit_logs' || fail "B7 archive list missing audit_logs"
printf '%s\n' "${LIST_OUT}" | grep -qE 'TRIGGER public audit_logs trg_audit_logs_append_only' || fail "B7 archive list missing append-only trigger"
printf '%s\n' "${LIST_OUT}" | grep -qE 'FUNCTION public fn_audit_logs_append_only' || fail "B7 archive list missing append-only function"
log "B7 PASS (size ${SIZE}, archive lists audit_logs + trigger + function)"

# --- Restore via the repo's restore.sh to a brand-new database --------------
log "running deploy/backup/restore.sh -> ${RESTORE_DB}"
docker run --rm --network "${NET}" \
  -v "${REPO_ROOT}:/repo:ro" -v "${BACKUP_DIR}:/backups" \
  -e DATABASE_URL="postgresql://csm:${F016_PW}@db:5432/${DB}" \
  "${PG_IMAGE}" bash /repo/deploy/backup/restore.sh "/backups/$(basename "${DUMP}")" "${RESTORE_DB}"

# --- B1: row counts equal and > 0 -------------------------------------------
DST_COUNT="$(psql_dst 'SELECT count(*) FROM audit_logs;' | tr -d '[:space:]')"
log "B1 source=${SRC_COUNT} restore=${DST_COUNT}"
[ "${SRC_COUNT}" = "${DST_COUNT}" ] && [ "${DST_COUNT}" -gt 0 ] || fail "B1 row counts differ"
log "B1 PASS"

# --- B2: key-field aggregate md5 identical ----------------------------------
AGG_SQL="SELECT md5(string_agg(operator_username||'|'||action||'|'||object_type||'|'||object_id||'|'||created_at, ',' ORDER BY id)) FROM audit_logs;"
SRC_MD5="$(psql_src "${AGG_SQL}" | tr -d '[:space:]')"
DST_MD5="$(psql_dst "${AGG_SQL}" | tr -d '[:space:]')"
log "B2 source md5=${SRC_MD5} restore md5=${DST_MD5}"
[ "${SRC_MD5}" = "${DST_MD5}" ] || fail "B2 audit aggregate md5 differs"
log "B2 PASS"

# --- B3: append-only trigger present on the restore -------------------------
TRG="$(psql_dst "SELECT count(*) FROM pg_trigger WHERE tgname='trg_audit_logs_append_only';" | tr -d '[:space:]')"
log "B3 append-only trigger count on restore = ${TRG}"
[ "${TRG}" = "1" ] || fail "B3 append-only trigger missing on restore"
log "B3 PASS"

# --- B4: UPDATE / DELETE are rejected on the restore ------------------------
set +e
UPD_OUT="$(docker exec "${DB_CONTAINER}" psql -v ON_ERROR_STOP=1 -U csm -d "${RESTORE_DB}" -c "UPDATE audit_logs SET action='TAMPER' WHERE action IS NOT NULL;" 2>&1)"
UPD_RC=$?
DEL_OUT="$(docker exec "${DB_CONTAINER}" psql -v ON_ERROR_STOP=1 -U csm -d "${RESTORE_DB}" -c "DELETE FROM audit_logs WHERE action IS NOT NULL;" 2>&1)"
DEL_RC=$?
set -e
log "B4 UPDATE rc=${UPD_RC} DELETE rc=${DEL_RC}"
printf '%s\n' "${UPD_OUT}" | tail -1
printf '%s\n' "${DEL_OUT}" | tail -1
[ "${UPD_RC}" -ne 0 ] || fail "B4 UPDATE was accepted"
[ "${DEL_RC}" -ne 0 ] || fail "B4 DELETE was accepted"
printf '%s' "${UPD_OUT}${DEL_OUT}" | grep -qi 'append-only' || fail "B4 rejection not attributable to append-only trigger"
log "B4 PASS"

# --- B5: alembic version identical + upgrade idempotent ---------------------
SRC_VER="$(psql_src 'SELECT version_num FROM alembic_version;' | tr -d '[:space:]')"
DST_VER="$(psql_dst 'SELECT version_num FROM alembic_version;' | tr -d '[:space:]')"
log "B5 source=${SRC_VER} restore=${DST_VER}"
[ "${SRC_VER}" = "${DST_VER}" ] && [ -n "${SRC_VER}" ] || fail "B5 alembic_version differs"
docker run --rm --network "${NET}" -v "${REPO_ROOT}/backend:/app" -w /app \
  -e DATABASE_URL="postgresql+psycopg://csm:${F016_PW}@db:5432/${RESTORE_DB}" \
  "${APP_IMAGE}" bash -lc "alembic upgrade head" >/dev/null
DST_VER2="$(psql_dst 'SELECT version_num FROM alembic_version;' | tr -d '[:space:]')"
[ "${DST_VER2}" = "${DST_VER}" ] || fail "B5 alembic upgrade head was not idempotent"
log "B5 PASS (head=${DST_VER}, upgrade head idempotent)"

# --- B6: restore database serves /api/v1/health/ready 200 -------------------
docker rm -f f016-restore-probe >/dev/null 2>&1 || true
docker run -d --name f016-restore-probe --network "${NET}" \
  -e DATABASE_URL="postgresql+psycopg://csm:${F016_PW}@db:5432/${RESTORE_DB}" \
  "${APP_IMAGE}" uvicorn app.main:app --host 0.0.0.0 --port 8000 >/dev/null
READY=""
for _ in $(seq 1 60); do
  if docker exec f016-restore-probe curl -fsS http://localhost:8000/api/v1/health/ready >/dev/null 2>&1; then
    READY="200"; break
  fi
  sleep 1
done
docker rm -f f016-restore-probe >/dev/null 2>&1 || true
[ "${READY}" = "200" ] || fail "B6 restore DB backend did not become ready"
log "B6 PASS (restore DB /api/v1/health/ready 200)"

log "B1-B7 all PASS — Audit is covered by backup/restore"