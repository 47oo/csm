# F045 验收环境与命令（artifacts/env.md）

- **基线**：start_commit `fa8a568b912d7aea9806a58616e98867a5786808`（short `fa8a568`）；head `9941f923d153dfa97e2766fce47811aaf8064082`（short `9941f92`，仅 F045 docs/plan 提交；`backend/app`、`backend/alembic`、`frontend/src`、`docs/api|product|database`、`compose*.yaml`、`.gitignore` 相对 start_commit 零 diff）
- **记录时间**：2026-10-29T15:05Z–15:40Z（UTC）；时区 UTC
- **凭据**：一律 `***`（`.env.test` 的 `POSTGRES_PASSWORD` / `INITIAL_ADMIN_PASSWORD`、`TEST_DATABASE_URL` 口令均已脱敏）

## 1. 工具版本（实测）

| 工具 | 版本 |
| --- | --- |
| Python / pytest | 3.12.7 / 7.4.4 |
| httpx / requests | 0.27.0 / 2.32.3 |
| openpyxl / lxml | 3.1.5（`openpyxl.LXML=True`）/ 5.2.1 |
| ruff | 0.15.17 |
| Node / npm | v22.23.3 / 10.9.9 |
| Docker / Compose | 26.1.2 / v5.6.0 |
| PostgreSQL（A1–A6 测试库，容器 `csm-f037-pg`，`127.0.0.1:55432`） | `PostgreSQL 16.15 on x86_64-pc-linux-musl`（postgres:16-alpine） |
| PostgreSQL（A7 部署栈内 `db`，服务名 `db`） | `PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2) on x86_64-pc-linux-gnu`（postgres:16） |
| nginx（A7 入口代理，未改 `deploy/nginx/nginx.conf`） | nginx:1.27-alpine |

## 2. 数据来源与隔离

- A1–A6：真实 PostgreSQL 测试库 `csm_f045_test`（本轮 `createdb` 新建，owner `csm`；`TEST_DATABASE_URL=postgresql+psycopg://csm:***@127.0.0.1:55432/csm_f045_test`；DB-D10 守卫要求库名含 `test` 且 ≠ `DATABASE_URL`）。非生产库、非未知库；测试夹具自建/自清 `public` schema。
- A7：Compose 项目 `csmtest`（`compose.yaml` + `compose.test.yaml`，`--env-file .env.test`），nginx 宿主端口 `:18080`；`pgdata` 命名卷独立于宿主与测试库；收尾 `down -v` 已删除容器与卷。
- 未对任何生产/未知数据库执行测试。`csm_f037_test` 未使用、未修改。

## 3. 命令表（全部已执行，日志见本目录）

| A | 命令 | 日志 |
| --- | --- | --- |
| A1 | `cd backend && TEST_DATABASE_URL='...csm_f045_test' python -m pytest -p no:cacheprovider -ra -q`（全量 `tests/` 含 `smoke/`）+ 失败 nodeid 重跑 1 次 + 6 条 skip 的补充重跑 | `full-pytest.log` |
| A2 | `pytest -v tests/integration/test_f037_import_parse_errors.py test_imports.py test_import_tester_acceptance.py test_f034_csv_text_carrier.py test_f023_resource_interface_ip_import.py` | `a02-import-parse.log` |
| A3 | `pytest -v tests/integration/test_f039_query_count.py test_f039_scope.py test_dashboard.py` | `a03-capacity.log` |
| A4 | `pytest -v tests/integration/test_f027_access_scope.py test_search_related.py test_search_related_tester_acceptance.py test_f041_candidate_scope.py` | `a04-scope.log` |
| A5 | `cd frontend && npm run typecheck && npm run build && npm run smoke:client && npm run test:interactions`（+ `test:interactions` run#2 重复性） | `frontend-{typecheck,build,smoke,interactions}.log` |
| A6 | `python -m pytest -q -p no:cacheprovider scripts/test_render_project_views.py scripts/test_validate_project_state.py scripts/test_collect_host_info.py` | `scripts-pytest.log` |
| A7 | `docker compose --env-file .env.test -f compose.yaml -f compose.test.yaml -p csmtest up -d --no-build` → 一次 `up -d --build`（镜像陈旧）→ `down -v` → 空卷 `up -d --no-build` → `ps` → `down -v`；HTTP 走 `http://127.0.0.1:18080` | `compose-up.log`、`compose-ps.log`、`http-acceptance.log`、`a07-image-staleness.txt` |
| A9 | 六份 review-report 逐条归类 + `F016_ACCEPTANCE=1 ... test_f016_acceptance.py`、`test_f028_acceptance.py` 复核 | `a09-review-classification.md`、`a09-f016-acceptance.log` |
| A8 | Tester 未执行（协调器职责）：`python scripts/validate_project_state.py --feature F045`；`python scripts/render_project_views.py`（无漂移）；`cd backend && alembic heads`（期望 `0015`） | 待协调器：`plan-validate.log`、`plan-render.log`、`alembic.log` |

## 4. A7 镜像陈旧事实（影响口径，详见 `a07-image-staleness.txt`）

- 复用镜像 `csm-csm-backend:test` 原构建于 `2026-10-27T05:34Z`，早于 start_commit（`2026-10-29T14:31Z`）：`backend/app/services/{dashboard,ip_capacity,resource_import,resource_interface_ip_import}.py` 4 文件 md5 与基线不同（缺 F037/F039 代码）。
- 因此 `--no-build` 栈不承载变更集代码，按 architecture §2「镜像不可用」执行一次 `up -d --build`；重建后 `backend/app/**.py` md5 与基线**逐文件一致**，`csm-csm-frontend:test` 的 `dist/assets/index-*.js` md5 与本地 `npm run build` 产物一致（`build` 退出 0）。
- A7 判定只采用重建后（基线代码）栈的 HTTP 证据；round-1 `--no-build` 栈仅用于验证 Compose 拓扑/串序本身，不作为 §32 行为证据。

## 5. 临时脚本与清理

- `/tmp/f045_acceptance.py`（§32 42 步驱动）、`/tmp/f045_acceptance_delete.py`（逻辑删除/恢复 15 步，修正 `?version=` 签名后重跑）；仅为本次执行，`/tmp` 下不入库，用后已删除（§6 不新增 `scripts/acceptance/`）。
- 收尾：`docker compose ... down -v`（容器与 `pgdata` 卷已删除）；`csm_f045_test` 保留供协调器复核/复测，临时角色 `csm_f045n` 与库 `csm_f045_test_nonsuper` 已 DROP。
