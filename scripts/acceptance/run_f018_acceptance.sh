#!/usr/bin/env bash
# F018 post-UI phase-1 acceptance re-verification — real execution driver.
#
# TEST INFRASTRUCTURE (Tester-owned). Does not touch business code, Schema,
# compose.yaml, deploy/** or Git state.
#
# Flow:
#   1. preflight (HEAD, cached images);
#   2. try `docker compose -p csm_f018 up -d --build`, record exit code + log,
#      then `docker compose -p csm_f018 down -v` (Docker Hub unreachable here);
#   3. equivalent real stack on docker network f018-acceptance-net
#      (postgres:16 + FastAPI + built frontend + nginx entry) on host port 18080;
#   4. frontend mechanism checks: typecheck / build (non-empty CSS) / smoke:client
#      (assertions >= 264, no reduction);
#   5. health + entry + SPA fallback over real HTTP;
#   6. bounded headless-browser DOM checks (test-only playwright-core);
#   7. cleanup containers/network/database (unless F018_KEEP=1).
#
# Env: F018_PW, F018_ADMIN_USER, F018_ADMIN_PW, F018_HOST_PORT (default 18080),
#      F018_KEEP=1 (leave stack up), F018_SKIP_BROWSER=1, F018_BROWSER_INSTALL=1,
#      F018_BROWSER_LIBS_SRC (pre-extracted chrome system libs dir).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

F018_PW="${F018_PW:-csmf018pw_local}"
F018_ADMIN_USER="${F018_ADMIN_USER:-admin}"
F018_ADMIN_PW="${F018_ADMIN_PW:-f018Admin_local1}"
F018_HOST_PORT="${F018_HOST_PORT:-18080}"
NET="f018-acceptance-net"
DB="csm_f018_acc"
BASE="http://localhost:${F018_HOST_PORT}"
PG_IMAGE="postgres:16"
NGINX_IMAGE="nginx:1.27-alpine"
APP_IMAGE="csm-f007-test"
RUN_DIR="${REPO_ROOT}/scripts/acceptance/artifacts/run-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${RUN_DIR}"

FAILURES=0
log() { printf '[F018] %s\n' "$*" | tee -a "${RUN_DIR}/run.log"; }
note() { printf '[F018] %s\n' "$*" >> "${RUN_DIR}/run.log"; }

cleanup() {
  [ "${F018_KEEP:-0}" = "1" ] && { log "F018_KEEP=1: leaving stack up"; return; }
  log "cleanup: removing f018 containers / network / database"
  if docker exec f018-db true >/dev/null 2>&1; then
    docker exec f018-db psql -U csm -d postgres -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE);" >/dev/null 2>&1 || true
  fi
  docker rm -f f018-nginx f018-frontend f018-backend f018-db >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
  rm -rf "${RUN_DIR}/browser-libs"
  log "cleanup residue check:"
  docker ps -a --format '{{.Names}}' | grep -E '^f018-' && log "WARNING: f018 container residue" || true
  docker network ls --format '{{.Name}}' | grep -E '^f018-' && log "WARNING: f018 network residue" || true
  docker volume ls --format '{{.Name}}' | grep -E '^f018-' && log "WARNING: f018 volume residue" || true
}
trap cleanup EXIT

# --- 1. preflight -----------------------------------------------------------
log "HEAD=$(git rev-parse HEAD) branch=$(git branch --show-current)"
for img in "${PG_IMAGE}" "${NGINX_IMAGE}" "${APP_IMAGE}"; do
  docker image inspect "${img}" >/dev/null 2>&1 || { log "missing cached image ${img}"; exit 2; }
done

# --- 2. compose attempt (recorded, expected to fail offline) -----------------
log "compose attempt: docker compose -p csm_f018 up -d --build"
set +e
docker compose -p csm_f018 up -d --build > "${RUN_DIR}/compose-up.log" 2>&1
COMPOSE_RC=$?
set -e
echo "EXIT_CODE=${COMPOSE_RC}" >> "${RUN_DIR}/compose-up.log"
docker compose -p csm_f018 down -v > "${RUN_DIR}/compose-down.log" 2>&1 || true
log "compose exit=${COMPOSE_RC} (log: ${RUN_DIR}/compose-up.log)"

# --- 3. frontend mechanism checks ------------------------------------------
log "frontend typecheck"
set +e
( cd frontend && npm run typecheck ) > "${RUN_DIR}/typecheck.log" 2>&1
TC_RC=$?
log "frontend build"
( cd frontend && npm run build ) > "${RUN_DIR}/build.log" 2>&1
BUILD_RC=$?
set -e
if [ "${TC_RC}" != "0" ]; then log "FAIL typecheck exit=${TC_RC}"; FAILURES=$((FAILURES+1)); fi
if [ "${BUILD_RC}" != "0" ]; then log "FAIL build exit=${BUILD_RC}"; FAILURES=$((FAILURES+1)); fi
CSS_COUNT=$(find frontend/dist -name '*.css' -size +0c 2>/dev/null | wc -l | tr -d ' ')
log "dist non-empty CSS files = ${CSS_COUNT}"
[ "${CSS_COUNT}" -ge 1 ] || { log "FAIL dist has no non-empty CSS"; FAILURES=$((FAILURES+1)); }

log "frontend smoke:client"
set +e
( cd frontend && npm run smoke:client ) > "${RUN_DIR}/smoke.log" 2>&1
SMOKE_RC=$?
set -e
SMOKE_PASSED=$(grep -oE '[0-9]+ passed' "${RUN_DIR}/smoke.log" | head -1 | grep -oE '^[0-9]+' || echo 0)
SMOKE_FAILED=$(grep -oE '[0-9]+ failed' "${RUN_DIR}/smoke.log" | head -1 | grep -oE '^[0-9]+' || echo 0)
ASSERT_COUNT=$(grep -c "await test(" frontend/scripts/smoke-client.mjs || echo 0)
log "smoke rc=${SMOKE_RC} passed=${SMOKE_PASSED} failed=${SMOKE_FAILED} assertions=${ASSERT_COUNT}"
[ "${SMOKE_FAILED}" = "0" ] && [ "${SMOKE_PASSED}" -ge 264 ] || { log "FAIL smoke assertions reduced or failing"; FAILURES=$((FAILURES+1)); }
[ "${ASSERT_COUNT}" -ge 264 ] || { log "FAIL smoke test count < 264"; FAILURES=$((FAILURES+1)); }

# --- 4. equivalent real stack ----------------------------------------------
docker network create "${NET}" >/dev/null 2>&1 || true
docker rm -f f018-db >/dev/null 2>&1 || true
docker run -d --name f018-db --network "${NET}" --network-alias db \
  -e POSTGRES_USER=csm -e POSTGRES_PASSWORD="${F018_PW}" -e POSTGRES_DB="${DB}" \
  "${PG_IMAGE}" >/dev/null
for _ in $(seq 1 30); do docker exec f018-db pg_isready -U csm -d "${DB}" >/dev/null 2>&1 && break; sleep 1; done

docker rm -f f018-backend >/dev/null 2>&1 || true
docker run -d --name f018-backend --network "${NET}" --network-alias backend \
  -v "${REPO_ROOT}/backend:/app" -w /app \
  -e DATABASE_URL="postgresql+psycopg://csm:${F018_PW}@db:5432/${DB}" \
  -e INITIAL_ADMIN_USERNAME="${F018_ADMIN_USER}" -e INITIAL_ADMIN_PASSWORD="${F018_ADMIN_PW}" \
  "${APP_IMAGE}" bash -lc "pip install -q 'python-multipart>=0.0.9,<0.1' 'openpyxl>=3.1,<3.2' && alembic upgrade head && python -m app.cli.bootstrap_admin && exec uvicorn app.main:app --host 0.0.0.0 --port 8000" >/dev/null

docker rm -f f018-frontend f018-nginx >/dev/null 2>&1 || true
docker run -d --name f018-frontend --network "${NET}" --network-alias frontend \
  -v "${REPO_ROOT}/frontend/dist:/usr/share/nginx/html:ro" \
  -v "${REPO_ROOT}/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  "${NGINX_IMAGE}" >/dev/null
docker run -d --name f018-nginx --network "${NET}" -p "${F018_HOST_PORT}:80" \
  -v "${REPO_ROOT}/deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" \
  "${NGINX_IMAGE}" >/dev/null

# --- 5. health + entry + SPA fallback --------------------------------------
for _ in $(seq 1 90); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/v1/health/ready" || true)"
  [ "${code}" = "200" ] && break
  sleep 1
done
HZ_CODE="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/healthz")"
HZ_BODY="$(curl -s "${BASE}/healthz" | tr -d '[:space:]')"
RD="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/v1/health/ready")"
IDX="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/")"
IDX_BODY="$(curl -s "${BASE}/" )"
CLU="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/clusters")"
CLU_BODY="$(curl -s "${BASE}/clusters")"
ALE="$(docker exec f018-backend alembic current 2>/dev/null | tail -1)"
{
  echo "healthz=${HZ_CODE} body=${HZ_BODY}"
  echo "ready=${RD}"
  echo "index=${IDX}"
  echo "clusters=${CLU}"
  echo "alembic=${ALE}"
} >> "${RUN_DIR}/health.txt"
log "health: /healthz=${HZ_CODE}(${HZ_BODY}) /api/v1/health/ready=${RD} /=${IDX} /clusters=${CLU} alembic='${ALE}'"

[ "${HZ_CODE}" = "200" ] && [ "${HZ_BODY}" = "ok" ] || { log "FAIL /healthz"; FAILURES=$((FAILURES+1)); }
[ "${RD}" = "200" ] || { log "FAIL /api/v1/health/ready"; FAILURES=$((FAILURES+1)); }
[ "${IDX}" = "200" ] || { log "FAIL /"; FAILURES=$((FAILURES+1)); }
printf '%s' "${IDX_BODY}" | grep -q '<div id="root"></div>' || { log "FAIL index missing #root marker"; FAILURES=$((FAILURES+1)); }
printf '%s' "${IDX_BODY}" | grep -q '<title>CSM</title>' || { log "FAIL index missing <title>CSM</title>"; FAILURES=$((FAILURES+1)); }
[ "${CLU}" = "200" ] || { log "FAIL /clusters"; FAILURES=$((FAILURES+1)); }
[ "${CLU_BODY}" = "${IDX_BODY}" ] || { log "FAIL /clusters SPA fallback not identical to /"; FAILURES=$((FAILURES+1)); }

# --- 6. bounded headless-browser DOM checks --------------------------------
BROWSER_RC="skipped"
if [ "${F018_SKIP_BROWSER:-0}" = "1" ]; then
  log "browser checks skipped (F018_SKIP_BROWSER=1)"
else
  CHROME_EXE=""
  for cand in "${HOME}"/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell \
              "${HOME}"/.cache/ms-playwright/chromium-*/chrome-linux64/chrome; do
    [ -x "${cand}" ] && { CHROME_EXE="${cand}"; break; }
  done
  BROWSER_DIR="${REPO_ROOT}/scripts/acceptance/browser"
  if [ -z "${CHROME_EXE}" ]; then
    log "browser: no cached Chromium found -> DOM criteria NOT TESTED"
    BROWSER_RC="no-browser"
  elif [ ! -d "${BROWSER_DIR}/node_modules/playwright-core" ] && [ "${F018_BROWSER_INSTALL:-0}" != "1" ]; then
    log "browser: playwright-core not installed (set F018_BROWSER_INSTALL=1) -> DOM criteria NOT TESTED"
    BROWSER_RC="no-playwright"
  else
    ( cd "${BROWSER_DIR}" && [ -d node_modules/playwright-core ] || npm install --no-audit --no-fund ) > "${RUN_DIR}/browser-install.log" 2>&1 || true
    LIBS_PATH=""
    if ldd "${CHROME_EXE}" 2>/dev/null | grep -q 'not found'; then
      LIBS_ROOT="${RUN_DIR}/browser-libs"
      mkdir -p "${LIBS_ROOT}/debs"
      if [ -n "${F018_BROWSER_LIBS_SRC:-}" ] && [ -d "${F018_BROWSER_LIBS_SRC}" ]; then
        LIBS_PATH="${F018_BROWSER_LIBS_SRC}"
      else
        ( cd "${LIBS_ROOT}/debs" && apt-get download libnspr4 libnss3 libasound2t64 ) > "${RUN_DIR}/browser-libs.log" 2>&1 || true
        for d in "${LIBS_ROOT}/debs/"*.deb; do
          [ -f "${d}" ] && dpkg-deb -x "${d}" "${LIBS_ROOT}/root" >> "${RUN_DIR}/browser-libs.log" 2>&1 || true
        done
        LIBS_PATH="${LIBS_ROOT}/root/usr/lib/x86_64-linux-gnu"
      fi
    fi
    set +e
    LD_LIBRARY_PATH="${LIBS_PATH}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
      F018_BASE_URL="${BASE}" F018_ADMIN_USERNAME="${F018_ADMIN_USER}" F018_ADMIN_PASSWORD="${F018_ADMIN_PW}" \
      F018_OUT_DIR="${RUN_DIR}/browser" F018_CHROME_EXE="${CHROME_EXE}" F018_BACKEND_CONTAINER="f018-backend" \
      node "${BROWSER_DIR}/f018_browser_check.mjs" 2>&1 | tee "${RUN_DIR}/browser.log"
    BROWSER_RC=${PIPESTATUS[0]}
    set -e
    [ "${BROWSER_RC}" = "0" ] || { log "browser checks exit=${BROWSER_RC}"; FAILURES=$((FAILURES+1)); }
  fi
fi
log "browser exit=${BROWSER_RC}"

log "DONE compose=${COMPOSE_RC} typecheck=${TC_RC} build=${BUILD_RC} smoke=${SMOKE_RC} browser=${BROWSER_RC} failures=${FAILURES} artifacts=${RUN_DIR}"
[ "${FAILURES}" = "0" ]