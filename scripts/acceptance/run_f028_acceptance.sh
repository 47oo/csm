#!/usr/bin/env bash
# F028 cluster-access integration acceptance driver (equivalent real stack).
# Attempts Compose (recorded), then runs postgres + current backend code +
# built frontend + nginx on host port 18081, and executes the real-HTTP F028
# acceptance tests. Artifacts under scripts/acceptance/artifacts/f028-*.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"
PW="${F028_PW:-csmf028pw_local}"
ADMIN_USER="${F028_ADMIN_USER:-admin}"
ADMIN_PW="${F028_ADMIN_PW:-f028Admin_local1}"
PORT="${F028_HOST_PORT:-18081}"
NET="f028-acceptance-net"
DB="csm_f028_acc"
BASE="http://localhost:${PORT}"
APP_IMAGE="csm-backend-f019test:latest"
RUN_DIR="${REPO_ROOT}/scripts/acceptance/artifacts/f028-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${RUN_DIR}"
log(){ printf '[F028] %s\n' "$*" | tee -a "${RUN_DIR}/run.log"; }
cleanup(){
  [ "${F028_KEEP:-0}" = "1" ] && return
  docker rm -f f028-nginx f028-frontend f028-backend f028-db >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "HEAD=$(git rev-parse HEAD) branch=$(git branch --show-current)"
for img in postgres:16 nginx:1.27-alpine "${APP_IMAGE}"; do
  docker image inspect "${img}" >/dev/null 2>&1 || { log "missing image ${img}"; exit 2; }
done

log "compose attempt (recorded)"
set +e
docker compose -p csm_f028 up -d --build > "${RUN_DIR}/compose-up.log" 2>&1
COMPOSE_RC=$?
set -e
docker compose -p csm_f028 down -v >/dev/null 2>&1 || true
log "compose exit=${COMPOSE_RC}"

log "building frontend"
( cd frontend && npm run build ) > "${RUN_DIR}/frontend-build.log" 2>&1

docker network create "${NET}" >/dev/null 2>&1 || true
docker run -d --name f028-db --network "${NET}" --network-alias db \
  -e POSTGRES_USER=csm -e POSTGRES_PASSWORD="${PW}" -e POSTGRES_DB="${DB}" postgres:16 >/dev/null
for _ in $(seq 1 30); do docker exec f028-db pg_isready -U csm -d "${DB}" >/dev/null 2>&1 && break; sleep 1; done

docker run -d --name f028-backend --network "${NET}" --network-alias backend \
  -v "${REPO_ROOT}/backend:/app" -w /app \
  -e DATABASE_URL="postgresql+psycopg://csm:${PW}@db:5432/${DB}" \
  -e INITIAL_ADMIN_USERNAME="${ADMIN_USER}" -e INITIAL_ADMIN_PASSWORD="${ADMIN_PW}" \
  "${APP_IMAGE}" bash -lc "python -c 'import multipart, openpyxl' || pip install -q 'python-multipart>=0.0.9,<0.1' 'openpyxl>=3.1,<3.2'; alembic upgrade head && python -m app.cli.bootstrap_admin && exec uvicorn app.main:app --host 0.0.0.0 --port 8000" >/dev/null

docker run -d --name f028-frontend --network "${NET}" --network-alias frontend \
  -v "${REPO_ROOT}/frontend/dist:/usr/share/nginx/html:ro" \
  -v "${REPO_ROOT}/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine >/dev/null
docker run -d --name f028-nginx --network "${NET}" -p "${PORT}:80" \
  -v "${REPO_ROOT}/deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" nginx:1.27-alpine >/dev/null

for _ in $(seq 1 90); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/v1/health/ready" || true)"
  [ "${code}" = "200" ] && break; sleep 1
done
HZ="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/healthz")"
RD="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/v1/health/ready")"
IDX="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/")"
ALE="$(docker exec f028-backend alembic current 2>/dev/null | tail -1)"
log "health: /healthz=${HZ} ready=${RD} /=${IDX} alembic='${ALE}'"
{ echo "healthz=${HZ}"; echo "ready=${RD}"; echo "index=${IDX}"; echo "alembic=${ALE}"; } >> "${RUN_DIR}/run.log"
[ "${HZ}" = "200" ] && [ "${RD}" = "200" ] && [ "${IDX}" = "200" ] || { log "health gate failed"; exit 3; }

log "running F028 acceptance pytest (real HTTP ${BASE})"
set +e
docker run --rm --network host -v "${REPO_ROOT}/backend:/app" -w /app \
  -e F016_ACCEPTANCE=1 -e F016_BASE_URL="${BASE}" -e F016_ORIGIN="${BASE}" \
  -e F016_ADMIN_USERNAME="${ADMIN_USER}" -e F016_ADMIN_PASSWORD="${ADMIN_PW}" \
  "${APP_IMAGE}" bash -lc "python -m pytest tests/integration/test_f028_acceptance.py -p no:cacheprovider -q" \
  2>&1 | tee "${RUN_DIR}/pytest.log"
PYTEST_RC=${PIPESTATUS[0]}
set -e
log "pytest exit=${PYTEST_RC}"

log "running T36 backup/Audit verification"
set +e
F016_PW="${PW}" F016_DB="${DB}" F016_RESTORE_DB="${DB}_restore" \
  F016_DB_CONTAINER=f028-db F016_NET="${NET}" APP_IMAGE="${APP_IMAGE}" \
  BACKUP_DIR="${RUN_DIR}/backup" \
  bash scripts/acceptance/verify_audit_backup.sh 2>&1 | tee "${RUN_DIR}/t36.log"
T36_RC=${PIPESTATUS[0]}
set -e
log "T36 exit=${T36_RC}"

docker exec f028-db psql -U csm -d postgres -c "DROP DATABASE IF EXISTS ${DB}_restore WITH (FORCE);" >/dev/null 2>&1 || true
docker exec f028-db psql -U csm -d postgres -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE);" >/dev/null 2>&1 || true
log "DONE pytest=${PYTEST_RC} t36=${T36_RC} compose=${COMPOSE_RC} artifacts=${RUN_DIR}"
[ "${PYTEST_RC}" = "0" ] && [ "${T36_RC}" = "0" ]
