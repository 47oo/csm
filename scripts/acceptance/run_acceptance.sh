#!/usr/bin/env bash
# F016 phase-1 integration acceptance — real execution driver.
#
# Architecture §5/§6/§7/§8. This is TEST INFRASTRUCTURE (Tester-owned); it does
# not change business code, Schema or Git state.
#
# Flow:
#   1. preflight (HEAD, images);
#   2. try `docker compose up -d`, record exit code + log, then `down -v`
#      (network to Docker Hub is unreachable here, so this is expected to fail);
#   3. bring up the equivalent real stack on docker network f016-acceptance-net
#      (postgres:16 + FastAPI + built frontend + nginx entry) on host port 18080;
#   4. wait for health (/healthz, /api/v1/health/ready, /, alembic head);
#   5. run backend/tests/integration/test_f016_acceptance.py over REAL HTTP from
#      a host-network container so the same-origin Origin is http://localhost:18080;
#   6. run scripts/acceptance/verify_audit_backup.sh (T36 B1-B7);
#   7. clean up containers/network/databases (unless F016_KEEP=1).
#
# Env: F016_PW, F016_ADMIN_USER, F016_ADMIN_PW, F016_HOST_PORT (default 18080).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

F016_PW="${F016_PW:-csmf016pw_local}"
F016_ADMIN_USER="${F016_ADMIN_USER:-admin}"
F016_ADMIN_PW="${F016_ADMIN_PW:-f016Admin_local1}"
F016_HOST_PORT="${F016_HOST_PORT:-18080}"
NET="f016-acceptance-net"
DB="csm_f016_acc"
RESTORE_DB="csm_f016_restore"
BASE="http://localhost:${F016_HOST_PORT}"
PG_IMAGE="postgres:16"
NGINX_IMAGE="nginx:1.27-alpine"
APP_IMAGE="csm-f007-test"
RUN_DIR="${REPO_ROOT}/scripts/acceptance/artifacts/run-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${RUN_DIR}"

log() { printf '[F016] %s\n' "$*" | tee -a "${RUN_DIR}/run.log"; }

cleanup() {
  [ "${F016_KEEP:-0}" = "1" ] && { log "F016_KEEP=1: leaving stack up"; return; }
  log "cleanup: removing f016 containers / network / databases"
  docker rm -f f016-nginx f016-frontend f016-backend f016-db f016-restore-probe >/dev/null 2>&1 || true
  if docker exec f016-db true >/dev/null 2>&1; then :; fi
  docker network rm "${NET}" >/dev/null 2>&1 || true
  rm -rf "${RUN_DIR}/backup"
}
trap cleanup EXIT

# --- 1. preflight -----------------------------------------------------------
log "HEAD=$(git rev-parse HEAD) branch=$(git branch --show-current)"
for img in "${PG_IMAGE}" "${NGINX_IMAGE}" "${APP_IMAGE}"; do
  docker image inspect "${img}" >/dev/null 2>&1 || { log "missing cached image ${img}"; exit 2; }
done

# --- 2. compose attempt (recorded, expected to fail offline) -----------------
log "compose attempt: docker compose -p csm_f016 up -d --build"
set +e
docker compose -p csm_f016 up -d --build > "${RUN_DIR}/compose-up.log" 2>&1
COMPOSE_RC=$?
set -e
echo "EXIT_CODE=${COMPOSE_RC}" >> "${RUN_DIR}/compose-up.log"
docker compose -p csm_f016 down -v > "${RUN_DIR}/compose-down.log" 2>&1 || true
log "compose exit=${COMPOSE_RC} (log: ${RUN_DIR}/compose-up.log)"

# --- 3. equivalent real stack ----------------------------------------------
log "building frontend (npm run build)"
( cd frontend && npm run build ) > "${RUN_DIR}/frontend-build.log" 2>&1

docker network create "${NET}" >/dev/null 2>&1 || true
docker rm -f f016-db >/dev/null 2>&1 || true
docker run -d --name f016-db --network "${NET}" --network-alias db \
  -e POSTGRES_USER=csm -e POSTGRES_PASSWORD="${F016_PW}" -e POSTGRES_DB="${DB}" \
  "${PG_IMAGE}" >/dev/null
for _ in $(seq 1 30); do docker exec f016-db pg_isready -U csm -d "${DB}" >/dev/null 2>&1 && break; sleep 1; done

docker rm -f f016-backend >/dev/null 2>&1 || true
docker run -d --name f016-backend --network "${NET}" --network-alias backend \
  -v "${REPO_ROOT}/backend:/app" -w /app \
  -e DATABASE_URL="postgresql+psycopg://csm:${F016_PW}@db:5432/${DB}" \
  -e INITIAL_ADMIN_USERNAME="${F016_ADMIN_USER}" -e INITIAL_ADMIN_PASSWORD="${F016_ADMIN_PW}" \
  "${APP_IMAGE}" bash -lc "pip install -q 'python-multipart>=0.0.9,<0.1' 'openpyxl>=3.1,<3.2' && alembic upgrade head && python -m app.cli.bootstrap_admin && exec uvicorn app.main:app --host 0.0.0.0 --port 8000" >/dev/null

docker rm -f f016-frontend f016-nginx >/dev/null 2>&1 || true
docker run -d --name f016-frontend --network "${NET}" --network-alias frontend \
  -v "${REPO_ROOT}/frontend/dist:/usr/share/nginx/html:ro" \
  -v "${REPO_ROOT}/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  "${NGINX_IMAGE}" >/dev/null
docker run -d --name f016-nginx --network "${NET}" -p "${F016_HOST_PORT}:80" \
  -v "${REPO_ROOT}/deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" \
  "${NGINX_IMAGE}" >/dev/null

# --- 4. health --------------------------------------------------------------
for _ in $(seq 1 90); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/v1/health/ready" || true)"
  [ "${code}" = "200" ] && break
  sleep 1
done
HZ="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/healthz")"
RD="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/v1/health/ready")"
IDX="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/")"
ALE="$(docker exec f016-backend alembic current 2>/dev/null | tail -1)"
log "health: /healthz=${HZ} /api/v1/health/ready=${RD} /=${IDX} alembic='${ALE}'"
{ echo "healthz=${HZ}"; echo "ready=${RD}"; echo "index=${IDX}"; echo "alembic=${ALE}"; } >> "${RUN_DIR}/run.log"
[ "${HZ}" = "200" ] && [ "${RD}" = "200" ] && [ "${IDX}" = "200" ] || { log "health gate failed"; exit 3; }

# --- 5. real-HTTP acceptance tests -----------------------------------------
log "running F016 acceptance pytest (real HTTP, same-origin ${BASE})"
set +e
docker run --rm --network host -v "${REPO_ROOT}/backend:/app" -w /app \
  -e F016_ACCEPTANCE=1 -e F016_BASE_URL="${BASE}" -e F016_ORIGIN="${BASE}" \
  -e F016_ADMIN_USERNAME="${F016_ADMIN_USER}" -e F016_ADMIN_PASSWORD="${F016_ADMIN_PW}" \
  "${APP_IMAGE}" bash -lc "pip install -q 'openpyxl>=3.1,<3.2' >/dev/null 2>&1 && python -m pytest tests/integration/test_f016_acceptance.py -p no:cacheprovider -q" \
  2>&1 | tee "${RUN_DIR}/pytest.log"
PYTEST_RC=${PIPESTATUS[0]}
set -e
log "pytest exit=${PYTEST_RC}"

# --- 6. T36 backup/restore audit -------------------------------------------
set +e
F016_PW="${F016_PW}" BACKUP_DIR="${RUN_DIR}/backup" \
  bash scripts/acceptance/verify_audit_backup.sh 2>&1 | tee "${RUN_DIR}/t36.log"
T36_RC=${PIPESTATUS[0]}
set -e
log "T36 exit=${T36_RC}"

# --- 7. drop acceptance databases before removing the db container ----------
docker exec f016-db psql -U csm -d postgres -c "DROP DATABASE IF EXISTS ${RESTORE_DB} WITH (FORCE);" >/dev/null 2>&1 || true
docker exec f016-db psql -U csm -d postgres -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE);" >/dev/null 2>&1 || true

log "DONE pytest=${PYTEST_RC} t36=${T36_RC} compose=${COMPOSE_RC} artifacts=${RUN_DIR}"
[ "${PYTEST_RC}" = "0" ] && [ "${T36_RC}" = "0" ]