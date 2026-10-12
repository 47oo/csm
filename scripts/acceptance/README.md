# F016 phase-1 integration acceptance (TEST infrastructure)

Tester-owned acceptance fixtures/scripts for `F016` (architecture §5–§9). They do
not touch business code, Schema, `compose.yaml`, `deploy/**` or Git state.

## Files

| File | Purpose |
| --- | --- |
| `run_acceptance.sh` | Full driver: compose attempt (recorded) → equivalent real stack → health → pytest → T36 → cleanup. |
| `verify_audit_backup.sh` | T36 backup/restore Audit verification, assertions **B1–B7**. |
| `artifacts/` | Per-run logs: `run.log`, `compose-up.log`, `frontend-build.log`, `pytest.log`, `t36.log`. |

Test fixtures (imported by the driver):

* `backend/tests/integration/f016_helpers.py` — real-HTTP `httpx` client + dataset/import helpers.
* `backend/tests/integration/test_f016_acceptance.py` — ACC-T*/C*/Q*/REUSE cases (skipped unless `F016_ACCEPTANCE=1`).

## Run

```bash
F016_PW='<pg password>' F016_ADMIN_USER=admin F016_ADMIN_PW='<admin password>' \
  bash scripts/acceptance/run_acceptance.sh
```

Env: `F016_HOST_PORT` (default `18080`), `F016_PW`, `F016_ADMIN_USER`,
`F016_ADMIN_PW`, `F016_KEEP=1` (leave the stack up for debugging).

## Environment constraints

`docker build` / `docker compose up` require Docker Hub + `deb.debian.org`, which
are unreachable in this environment; the Compose attempt is executed and its
failure (exit code + log) is archived, then the **equivalent real stack** is used:
`postgres:16` (`db`) + `csm-f007-test` FastAPI (`backend`) + locally built
frontend served by `nginx:1.27-alpine` (`frontend`) + nginx entry (`:18080`),
all aliased so the unmodified `deploy/nginx/nginx.conf` upstreams resolve. The
same-origin `Origin` is `http://localhost:18080` (via `--network host` test
runner). See `docs/features/F016/test-report.md` for the full difference table.

## Cleanup

The driver removes `f016-*` containers/network and, before doing so, DROPs
`csm_f016_acc` and `csm_f016_restore`. No named volume is created, so no volume
residue remains. `frontend/dist` is a git-ignored build artifact.