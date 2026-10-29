# F045 CHG-015 变更集整体回归与部署等价验收 — ARCHITECTURE + CONTRACT

- **状态**：READY FOR TEST DESIGN｜v1（2026-10-29）｜FEATURE / P0 / M31｜分支 `feature/F045-change-set-acceptance`（start_commit `fa8a568`）；plan rev25 / requirements rev16
- **Basis**：`F045/product.md` v1（A1–A12 / N1–N8 / ON-1…5）；requirements rev16 §31/§32/§20/§30 与 T27、T28、T32、T72、T88、T107–T116、T126；plan rev25 F045（`layers` 全 false、`api_required=false`）；`project.acceptance=PENDING` + 52 条历史证据
- **已读核对**：`compose.yaml`（db/migrate/bootstrap/backend/frontend/nginx）、`compose.test.yaml`（`--no-build` + 本地镜像）、`.env.test`（`NGINX_HTTP_PORT=18080`、`INITIAL_ADMIN_*`）、`backend/pyproject.toml`（`testpaths=["tests"]`；markers integration/real_scope/smoke）、`backend/tests/{integration,smoke}` + `conftest.py`（`TEST_DATABASE_URL` DB-D10 守卫）、`scripts/test_*.py`、`frontend/package.json`、`alembic head=0015`

## 1. 性质与分层

验收型：零产品代码、零 Schema、零契约。`layers={database:false, backend:false, frontend:false}`、`api_required=false`；Database / Backend / Frontend / Contract 均 **NOT_REQUIRED**（§9）。禁止把局部 PASS 拼成整体结论（N5），禁止回写 F001–F036 证据与判定（N4）。

## 2. ON-1 部署等价栈口径

**必须由真实 Compose 承载、不可由等价栈替代**：① nginx 入口代理（未改 `deploy/nginx/nginx.conf`，HTTP :18080）；② 容器内 `alembic upgrade head`（`migrate` 一次性服务）；③ 首个 ADMIN 初始化（`bootstrap`，`service_completed_successfully` 串序）；④ compose 网络内 API↔DB（`DATABASE_URL` host=`db`）；⑤ §32 关键路径全部经 nginx 同源真实 HTTP（不得用 TestClient 直连代替）。

- **主路径**：`docker compose --env-file .env.test -f compose.yaml -f compose.test.yaml -p csmtest up -d --no-build`（镜像 `csm-csm-backend:test` / `csm-csm-frontend:test`；:18080 避端口冲突）。镜像缺失允许一次 `up --build`；构建失败即记 `COMPOSE_BLOCKED`。
- **降级等价栈**（仅当主路径不可用；须记录失败原因 + exit code + 原始日志）：`postgres:16` 容器 + 容器内 `uvicorn app.main:app`（同容器先 `alembic upgrade head`、再 `bootstrap_admin`）+ `npm run build` 产物由 `nginx:1.27-alpine` 挂载未改的 `deploy/nginx/nginx.conf` 承载 + 真实 HTTP 全走该代理。
- **等价栈必须登记未覆盖项**：镜像构建可复现性、`depends_on`+healthcheck 顺序语义、`env_file` 注入与 `pgdata` 命名卷持久化、frontend 容器内构建。等价栈通过**不得**写成「Compose 通过」。

## 3. ON-2 全量 pytest 规则

- 命令统一加 `-p no:cacheprovider`：`cd backend && TEST_DATABASE_URL='postgresql+psycopg://csm:***@127.0.0.1:55432/csm_f045_test' python -m pytest -p no:cacheprovider -ra -q 2>&1 | tee ../docs/features/F045/artifacts/full-pytest.log`。必须真实 PostgreSQL；SQLite/mock 不构成证据。
- 范围：`tests/` 全覆盖（含 `smoke/`）；不加 `-k`/`-m` 过滤、不按目录裁剪、**不因耗时才裁剪**；`-ra` 的 skip 清单与逐条原因原文入日志。
- 允许排除类别（逐条列 nodeid + 原因 + 影响用例数）：需外部网络/Docker Hub、缺可选依赖（如 `lxml`）、真实 OOM/资源上限、已复现并登记的 flaky。除此四类不得排除。
- 重跑上限：1 次全量 + 仅失败/错误项按 nodeid 重跑 1 次；第二次仍失败即判 FAIL。

## 4. ON-3 证据结构

`docs/features/F045/artifacts/`：`env.md`、`full-pytest.log`、`scripts-pytest.log`、`a02-import-parse.log`、`a03-capacity.log`、`a04-scope.log`、`a09-review-classification.md`、`frontend-{typecheck,build,smoke,interactions}.log`、`compose-up.log`、`compose-ps.log`、`http-acceptance.log`、`alembic.log`、`plan-validate.log`、`plan-render.log`（`frontend/dist` 不入库）。

- **日志 header 必含字段**：`cmd:`｜`start_commit:`｜`head:`｜`env:`（口令 `***`）｜`started_at`/`finished_at`（UTC ISO8601）｜`tool_versions:`（Python/pytest/httpx/Node/npm/Docker/Compose + PG `SELECT version()`）｜`exit_code:`。
- **`.log` 入库**：`.gitignore` 命中 `*.log` ⇒ `git add -f docs/features/F045/artifacts/*.log`，以 `git ls-files` 证明；禁止改 `.gitignore`，禁止因被忽略而丢弃日志；凭据一律 `***`。

## 5. ON-4 acceptance 恢复措辞（协调器执行，A12）

- **最小证据类型（5 类，缺一不恢复）**：① backend 全量 pytest 日志；② Compose 或等价栈运行 + HTTP 关键路径日志；③ frontend 四入口日志；④ `scripts/` 单测日志；⑤ `validate_project_state.py` VALID + `render_project_views.py` 无漂移日志。
- **追加不删**：向 `project.acceptance.evidence` **追加** 6–8 条锚点，既有 52 条一条不删、顺序不动。
- **basis 新措辞**：「evidence 覆盖 plan revision 25：F001–F036（52 条，revision 24）历史证据保持不变；F037–F041 / F043 变更集由 F045 全量回归与部署等价验收补充，见 `docs/features/F045/**`。」
- **status**：仅当 A1–A11 全通过且无 BLOCKER/HIGH 时 `PENDING → COMPLETE`；任一项不通过保持 PENDING 并在 plan `last_result` 登记缺陷。

## 6. ON-5 验收脚本

不新增 `scripts/acceptance/`（F016 已有同类驱动，新增即重复维护）。命令写入 `test-report.md` 与 `artifacts/env.md`；临时脚本只放 `/tmp` 且用后清理；不得引入浏览器/E2E 依赖（AQ-4=B）。

## 7. A1–A12 → 验证手段

| A | 命令 / 操作 | 证据落点 | 执行 |
| --- | --- | --- | --- |
| A1 | §3 全量 pytest（真实 PostgreSQL，含 skip 原因） | `full-pytest.log` | Tester |
| A2 | `pytest -v tests/integration/test_f037_import_parse_errors.py tests/integration/test_imports.py tests/integration/test_import_tester_acceptance.py tests/integration/test_f034_csv_text_carrier.py tests/integration/test_f023_resource_interface_ip_import.py` | `a02-import-parse.log` | Tester |
| A3 | `pytest -v tests/integration/test_f039_query_count.py tests/integration/test_f039_scope.py tests/integration/test_dashboard.py` | `a03-capacity.log` | Tester |
| A4 | `pytest -v tests/integration/test_f027_access_scope.py tests/integration/test_search_related.py tests/integration/test_search_related_tester_acceptance.py tests/integration/test_f041_candidate_scope.py` | `a04-scope.log` | Tester |
| A5 | `cd frontend && npm run typecheck && npm run build && npm run smoke:client && npm run test:interactions`（需 352 / 14） | `frontend-*.log` | Tester |
| A6 | `pytest -q scripts/test_render_project_views.py scripts/test_validate_project_state.py scripts/test_collect_host_info.py` | `scripts-pytest.log` | Tester |
| A7 | §2 主路径起栈，经 nginx 真实 HTTP 走完 §32 关键路径 | `compose-up.log`、`compose-ps.log`、`http-acceptance.log` | Tester |
| A8 | `validate_project_state.py --feature F045`；`render_project_views.py`（无漂移）；`alembic heads`=`0015` | `plan-validate.log`、`plan-render.log`、`alembic.log` | **协调器** |
| A9 | 六份 review-report 的 NOT TESTED / BLOCKED 逐条归类 | `a09-review-classification.md` | Tester |
| A10 | 证据入库（`git ls-files`）+ plan F045 `evidence` | 同目录 | Tester→协调器 |
| A11 | 未执行项标 NOT TESTED / BLOCKED，任何位置不得写 PASS | 各报告 | Tester |
| A12 | 按 §5 恢复 `project.acceptance` | plan diff | **协调器** |

## 8. 风险

| ID | 风险 | 级别 | 处理 |
| --- | --- | --- | --- |
| R1 | Compose 起不来（缺镜像/构建需外网/端口冲突/healthcheck）⇒ A7 退化 | HIGH | 先 `--no-build` + 本地镜像、:18080；失败记 `COMPOSE_BLOCKED` 并按 §2 列未覆盖项 |
| R2 | 全量 pytest 时间与资源 | MEDIUM | 后台执行 + `tee`；耗时不作为裁剪理由 |
| R3 | `.log` 被 gitignore ⇒ 证据不入库 | MEDIUM | `git add -f` + `git ls-files` 证明 |
| R4 | 真实 PG 与容器 PG 版本差异 | LOW | `SELECT version()` 入日志，不宣称版本兼容性结论 |
| R5 | 跨功能交互用例缺口 | MEDIUM | A1 全量覆盖既有交叉用例；仍缺处标 NOT TESTED，不新增产品测试 |
| R6 | 等价栈被写成「Compose 通过」 | HIGH | §2 禁止条款 + A11 措辞核对（Review 重点） |

## 9. Contract / Database / Backend / Frontend

- **Contract `NOT_REQUIRED`**（Architect 签核 2026-10-29）：无端点/字段/错误码/权限/分页/Schema 变化；被验收行为来自既有已签核契约（`docs/api/F014.md`、`F023.md`、`F013.md`、`F020.md` 等）；本 Feature 不产出也不修改 `docs/api/**`。
- **Database `NOT_REQUIRED`**：零 DDL；仅验证既有迁移链 `up` 与 `head=0015`（A8）。
- **Backend / Frontend `NOT_REQUIRED`**：零代码改动；仅执行既有命令与既有测试。

## 10. 零 diff 守卫、执行层与签核

```text
签核：Architect，2026-10-29；绑定 requirements rev16、plan rev25、product.md v1、A1–A12；Database/Contract/Backend/Frontend = NOT_REQUIRED。
零 diff（git diff --stat fa8a568 -- <path> 逐项为空）：backend/app/**、backend/alembic/**、frontend/src/**、frontend/package.json、docs/api/**、docs/product/**、docs/database/**、compose*.yaml、.gitignore。
若 Compose 确有缺陷需修：停止并回报协调器，不自行修改（N2/N3）。
执行层：L1 = Tester（A1–A7、A9、A11 证据）；L2 = 协调器（A8、A10、A12 及 .log 入库核验）。
放行写入：仅 docs/features/F045/**。
结论：READY FOR TEST DESIGN。
```
