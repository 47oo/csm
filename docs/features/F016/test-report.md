# F016 一期集成验收与交付 — Test Report

本文件承载 TEST_DESIGN 与后续 TEST（TE 阶段在同一文件追加执行结果）。TEST_DESIGN **不填充执行 PASS**；执行结果全部标 `待执行（TE-1）`。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-06
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§22、§30、§31 T01–T41、§32 C1–C15、§33 Q1–Q9、§35）
  - `docs/features/F016/product.md`（PRODUCT `READY FOR ARCHITECT`；A1–A14、I-1–I-9、O-1–O-4）
  - `docs/features/F016/architecture.md`（ARCHITECTURE `READY FOR DESIGN` 2026-10-06；DR-228–DR-246、§5 替代栈、§6 T 复用/重跑、§7 §32/§33、§8 T36 B1–B7、§9 脚本落点）
  - `docs/project/project-plan.yaml`（plan revision 4，F016 条目；`project.acceptance.status=PENDING`）
  - `docs/project/{handoff,implementation-rules,project-state,git-workflow}.md`
  - `.pi/skills/data-integrity/SKILL.md`
  - 落地资产：`compose.yaml`、`deploy/nginx/nginx.conf`、`frontend/nginx.conf`、`deploy/backup/{pg_dump.sh,restore.sh}`、`backend/tests/conftest.py`、既有 `backend/tests/integration/*`（F003–F015 真 PG 证据）
- **工作区/基线**：分支 `feature/F016-integration-acceptance`，HEAD `39d2b18`（只读核对）。环境探测：`docker`/`docker build` 子命令存在；镜像 `postgres:16`、`nginx:1.27-alpine`、`csm-f007-test` 已缓存；`node v22.23.2`/`npm 12.0.2`；宿主无 `pg_dump`/`psql`/`pg_restore`；`docker pull` 网络不可达（与 architecture §13 环境性结论一致）。
- **状态属性**：TD-1 `READY` 仅表示 A1–A14/I-1–I-9 已映射到可观察判据、栈启动/替代栈、T01–T41 证据模型、§32/§33/T36 用例、脚本夹具与可验证性检查已建立并可在 TE-1 执行；**不代表测试已运行、不填充执行 PASS、不批准实现或合并，也不构成 `project.acceptance=COMPLETE`**。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-06 | 初版：A1–A14 / I-1–I-9 映射；栈启动（Compose 尝试 + 失败录制 + 替代栈）与差异声明；T01–T41 Evidence Index（REUSE 锚点 + RERUN 用例 ID）；§32 C1–C15、§33 Q1–Q9 真 HTTP 用例；T36 B1–B7 备份覆盖 Audit；脚本/夹具落点与清理纪律；环境与可验证性；OPEN 清单。 |

### 0. 数据完整性对应表（F016 范围）

方法依据 `.pi/skills/data-integrity/SKILL.md`。F016 **不新增业务实体/字段/状态/规则、无 Migration、无新增 API**；下表为被验收对象在被复用/重跑时的保证与证据对应，证据全部来自真实 PostgreSQL + 真实 HTTP。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（既有） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §22 / f003 DB-D28 | `audit_logs` append-only | `trg_audit_logs_append_only` 拒绝 UPDATE/DELETE | 无修改/删除/清空入口（F015） | 备份/恢复不改变既有行 | REUSE F015；F016 B3/B4 |
| §22 / §30 | Audit 纳入备份 | `pg_dump -Fc` 全库含 `audit_logs` | 恢复到新库默认 | 恢复后行数/字段一致 | B1/B2/B5/B6/B7 |
| §22 | 恢复后审计完整 | 行数/字段聚合一致 | 无截断、无重建 | 目标库隔离 | B1/B2/B6 |
| §27 / T07/T35 | 约束/并发证据 | 真实 PG 事务/唯一约束/锁 | 不重实现 | REUSE 权威 Feature 真并发 | T07/T35 REUSE 锚点 + 集成栈可达确认（A10/I-3） |
| §21/§23 | 权限与恢复 | 沿用 F002/F015 | 401 先于 403 | REUSE/RERUN | ACC-C9/ACC-C10，ACC-T24/T25 |
| §24 / T27/T28 | 普通 API 与导入共用 Service 校验 | 导入失败整批回滚无残留 | 先校验→确认→再校验 | RERUN 集成栈真 HTTP | ACC-T27/ACC-T28 |
| §30 | 部署链路 | PostgreSQL 持久化 | 无 Mock 替代约束/并发 | Compose 或等价替代栈 | A1/A13，§3 |

> 说明：F016 无 Schema 变更，Database 结论预期 `NOT_REQUIRED`；本表不新增约束，仅登记「被验收保证 + 证据来源」。

---

## 1. 验收映射（product.md A1–A14 / I-1–I-9 → 验证项）

执行环境代号：`Compose`＝`docker compose up -d`（Nginx→Frontend/FastAPI→PostgreSQL，入口 :80）；`替代栈`＝architecture §5.3 真实替代栈（入口 :18080）；`真HTTP`＝经入口 Nginx 的真实 HTTP（非 Mock、非 TestClient）；`真PG`＝真实 PostgreSQL；`静态`＝Git 范围/源码检查；`协调器`＝非 Tester 执行项。所有结果列 TE-1 填充。

### A1–A14

| # | 验收标准（product.md 摘） | 验证项 | 类型 | 可观察判据（PASS/FAIL；TE-1 填结果） |
| --- | --- | --- | --- | --- |
| A1 | Compose 链路可用且 `/api/v1/health/ready` 经 Nginx 200；否则记录限制与真实替代栈，不伪造 PASS | **V16-A1** | Compose/替代栈 + 真HTTP | PASS：①Compose 尝试产生带时间戳的 stdout/stderr 日志与退出码；②若成功：经入口 `/healthz`=200、`/api/v1/health/ready`=200、`/` 返回 index.html；③若失败：日志归档且替代栈达到同样三项健康判据，差异声明存在。FAIL：声称 Compose 成功而无日志/退出码，或健康判据未达即标 PASS |
| A2 | 验收数据就绪覆盖 §31–§33 触发条件 | **V16-A2** | 替代栈/Compose + 真HTTP | PASS：DR-236 数据集（≥2 Cluster、cn001 BM 管理网+IB、vm001 Host=pve01、pve01 多 VM、gateway/RESERVED/禁用 Network、AUTO/MANUAL 池、绑定/未绑定 IP、Service/Endpoint、导入样例）全部经真实 HTTP 创建成功且就绪断言通过。FAIL：缺任一触发条件对象 |
| A3 | T01–T41 映射完整且有证据来源；集成者已重跑并给结果 | **V16-A3** | 真HTTP + 报告核对 | PASS：§4 Evidence Index 覆盖 T01–T41 逐条无缺；RERUN 清单用例均有集成栈执行结果。FAIL：缺项、REUSE 无锚点、RERUN 未执行 |
| A4 | 跨功能耦合用例在集成栈端到端通过 | **V16-A4** | 真HTTP | PASS：ACC-11/16/19/22/23/24/25/26/27/28/29/32/37/40/41 全部满足各自判据（见 §4）。FAIL：任一 FAIL |
| A5 | §33 Q1–Q9 端到端可回答 | **V16-A5** | 真HTTP | PASS：ACC-Q1–ACC-Q9 逐项答案与预期一致；依赖 DOM 渲染者按 §6 标 NOT TESTED 且不冒充 PASS。FAIL：任一答案错误 |
| A6 | §32 C1–C15 逐项满足且有真实证据 | **V16-A6** | 真HTTP + 真PG | PASS：ACC-C1–ACC-C15 逐项有真 HTTP 证据；C15 汇总实际执行（非局部拼接）。FAIL：任一 C 无证据或不满足 |
| A7 | 备份覆盖 Audit：恢复后审计完整、append-only 保持 | **V16-A7** | 替代栈/Compose + 真PG | PASS：B1–B7 全部有实际输出（§7）。FAIL：任一无输出或断言不符 |
| A8 | 权限矩阵集成栈服务端执行，401 先于 403 | **V16-A8** | 真HTTP | PASS：无 Cookie→401 `AUTH_REQUIRED`；VIEWER/EDITOR 越权→403 `FORBIDDEN{reason:"permission"}`；401 先于 403。FAIL：越权或顺序错 |
| A9 | 导入集成栈：先校验后确认再校验、整批回滚、错误明细、Host 须已存在、上限 | **V16-A9** | 真HTTP | PASS：ACC-T27/ACC-T28 满足（重复/非法行返回行号+字段+原因；失败整批回滚零残留；Host 未存在失败；上限拒绝）。FAIL：部分成功、无明细、绕过 Host 校验 |
| A10 | 并发证据引用/复核真实 PG 真提交 | **V16-A10** | 真PG（REUSE） | PASS：T07/T35 REUSE 锚点指向权威 Feature `committed_engine` 真并发用例 + 最终持久化断言；集成栈对应端点可达确认（ACC-RCHK-T07/T35）。FAIL：以 SQLite/Mock 或仅「未抛异常」充当证据 |
| A11 | `project.acceptance` 写入 COMPLETE + 真实 evidence，协调器核验 | **V16-A11** | 协调器 | PASS：Test Report 提供 `#t01t41-evidence-index`/`#32-c1c15-上线验收`/`#33-目标查询场景`/`#t36-备份覆盖-audit` 锚点；协调器核验后写 evidence 并置 COMPLETE。FAIL：Tester 自行置 COMPLETE 或证据路径不存在。**执行者＝协调器** |
| A12 | 未改 F001–F015 契约/实现语义 | **V16-A12** | 静态 | PASS：`git diff --name-only <base>..<head>` 仅含 `docs/features/F016/**`、`scripts/acceptance/**`、`backend/tests/integration/{test_f016_acceptance.py,f016_helpers.py}`；`backend/app/**`、`frontend/src/**`、`compose.yaml`、`deploy/**`、`backend/alembic/**`、`docs/api/**` 无改动。FAIL：出现业务实现/Schema/契约改动 |
| A13 | 环境限制如实记录（含替代栈差异） | **V16-A13** | 报告核对 | PASS：§3 差异声明逐项列出镜像构建、代码来源、配置注入、编排、前端、卷、入口同源差异，且与 A1 实际路径一致。FAIL：以替代栈冒充 Compose |
| A14 | 验收后清理独立项目/库/卷，无残留 | **V16-A14** | 替代栈/Compose | PASS：`docker ps -a`/`docker network ls`/`docker volume ls` 无 `f016-*` 残留；`csm_f016_acc`、`csm_f016_restore` 已删除；备份暂存目录已清；前端 `dist` 视同构建产物（git-ignored）。FAIL：任一残留 |

### I-1–I-9（不变量判据）

| # | 不变量 | 判据（可观察） |
| --- | --- | --- |
| I-1 | 证据真实 | 每个结果附实际命令 + 原始输出摘要；未执行项显式标 `NOT TESTED`/`BLOCKED`，不得以预期代替 |
| I-2 | 不夸大 | §32 C15 汇总实际执行；T 的局部 PASS 不得拼成整体 PASS；整体结论只在全部 A/C/Q/B 完成后给出 |
| I-3 | 约束/并发真 PG | 约束/并发证据来自真实 PostgreSQL；出现 SQLite/Mock 约束或并发证据即 FAIL |
| I-4 | 环境限制如实记录 | Compose 失败日志归档、替代栈差异声明、BLOCKED 条件/责任者/恢复动作齐备 |
| I-5 | 不改 F001–F015 语义 | V16-A12 + 缺陷按 §10 路由回责任 Feature，不静默修改 |
| I-6 | 不新增业务规则 | 数据集与断言仅引用既有 READY Contract / 已确认需求；新增规则即退回 Product/Architect |
| I-7 | 验收数据可清理 | 独立网络/端口/库/卷；A14 清理断言 |
| I-8 | acceptance 不虚报 | A11；`COMPLETE` 仅协调器核验后写入，Tester 不写 |
| I-9 | 上线条件≠发布授权 | 报告结论明确 COMPLETE≠发布授权；不输出发布批准语义 |

---

## 2. 栈启动设计

### 2.1 首选 Compose 尝试与失败录制（DR-229）

1. **Preflight（只读）**：`git rev-parse HEAD`、`git status --porcelain`；确认 `docker`、`node`、镜像 `postgres:16`/`nginx:1.27-alpine`；准备 `.env`（真实凭据，不入库）与独立项目名/库名。
2. **尝试**：`docker compose -f compose.yaml build` 与 `docker compose up -d`，各自 `2>&1 | tee scripts/acceptance/artifacts/compose-<phase>-<utc>.log` 并记录 `exit_code`。
3. **结果处理**：
   - 成功：按 §2.3 健康判据验证，记录 Compose 路径证据（`docker compose ps`）。
   - 失败：**如实录制**失败退出码与日志路径，执行 `docker compose down -v` 清理后切换替代栈。**不得伪造 Compose PASS**。
4. 归档物：`scripts/acceptance/artifacts/compose-*.log`（含 `HEAD`、时间、命令、退出码）。

### 2.2 真实替代栈（DR-230–DR-235）

可执行步骤（`scripts/acceptance/run_acceptance.sh` 固化，凭据经环境变量）：

```bash
docker network create f016-acceptance-net
docker run -d --name f016-db --network f016-acceptance-net --network-alias db \
  -e POSTGRES_USER=csm -e POSTGRES_PASSWORD="$F016_PW" -e POSTGRES_DB=csm_f016_acc postgres:16
# 等待 pg_isready 后：
docker run -d --name f016-backend --network f016-acceptance-net --network-alias backend \
  -v "$PWD/backend:/app" -w /app \
  -e DATABASE_URL="postgresql+psycopg://csm:$F016_PW@db:5432/csm_f016_acc" \
  -e INITIAL_ADMIN_USERNAME="$F016_ADMIN_USER" -e INITIAL_ADMIN_PASSWORD="$F016_ADMIN_PW" \
  csm-f007-test bash -lc "pip install -q 'python-multipart>=0.0.9,<0.1' 'openpyxl>=3.1,<3.2' \
    && alembic upgrade head && python -m app.cli.bootstrap_admin \
    && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"
( cd frontend && npm ci && npm run build )     # 本地构建 dist/
docker run -d --name f016-frontend --network f016-acceptance-net --network-alias frontend \
  -v "$PWD/frontend/dist:/usr/share/nginx/html:ro" \
  -v "$PWD/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine
docker run -d --name f016-nginx --network f016-acceptance-net -p 18080:80 \
  -v "$PWD/deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" nginx:1.27-alpine
```

关键约束：
- **别名 `db`/`backend`/`frontend`** 使 `deploy/nginx/nginx.conf` 的 upstream（`backend:8000`、`frontend:80`）免改即可解析（DR-230）。
- 后端镜像 `csm-f007-test` 挂载 `./backend`，容器内补装 F014 依赖后跑 `alembic upgrade head`（预期 head=`0013_search_indexes`）→ `bootstrap_admin` → `uvicorn`（DR-231）。
- 独立库 `csm_f016_acc`；`pg_dump`/`pg_restore` 通过 `docker exec f016-db`（宿主无客户端，DR-232）。
- 前端本地产物 `npm run build`（`tsc --noEmit && vite build`）由 `nginx:1.27-alpine` 静态服务（DR-233）。
- 同源：统一经 `http://localhost:18080` 访问 `/` 与 `/api/`；写请求带 `Origin: http://localhost:18080`，`Host` 含端口原样透传（`deploy/nginx/nginx.conf` 的 `$http_host` map），验证 401 先于 403（DR-234/§5.4）。

### 2.3 健康判据（DR-235）

| 判据 | 命令 | 期望 |
| --- | --- | --- |
| 入口存活 | `curl -fsS http://localhost:18080/healthz` | `200`，body `ok` |
| 就绪（经 Nginx→backend） | `curl -fsS http://localhost:18080/api/v1/health/ready` | `200` |
| 前端入口 | `curl -fsS http://localhost:18080/` | `200` 且含 `index.html` 标记 |
| 迁移 head | `docker exec f016-backend alembic current` | `0013_search_indexes (head)` |
| ADMIN 登录 | `POST http://localhost:18080/api/v1/auth/login` | `200` + session cookie |

就绪轮询超时（建议 180s）内任一未达即记 BLOCKED，不得继续伪造后续用例结果。

### 2.4 与 Compose 的差异声明（DR-229/§5.3，A13）

| 维度 | Compose | 替代栈 | 影响 |
| --- | --- | --- | --- |
| 镜像构建 | `docker build`（backend/frontend） | 复用 `csm-f007-test` + bind-mount 代码 | 未经镜像构建固化，但代码源锁定候选 HEAD |
| 代码来源 | 镜像内置 | `-v ./backend:/app` | 现场代码 = 候选 HEAD，非磁盘漂移 |
| 配置注入 | `.env`/`env_file` | `-e` 环境变量 | 语义等价，凭据仍不入库 |
| 编排时序 | `depends_on` 条件 | 脚本强制顺序 + 就绪轮询 | 无 depends_on，靠脚本保证 |
| 前端 | 镜像内构建产物 | 本地产物 + 静态服务 | 拓扑等价，构建在宿主 |
| 卷 | 命名卷 `pgdata` | 独立库 `csm_f016_acc`（无命名卷） | 生命周期隔离 |
| 入口路由/同源 | `deploy/nginx/nginx.conf` | 同一文件，端口 18080 | 路由与同源语义一致 |

---

## 3. T01–T41 Evidence Index 设计

规则（DR-237）：`REUSE`＝引用权威 Feature 真 PG/真 HTTP 证据锚点 + 在集成栈确认对应端点可达（`ACC-RCHK-T<nn>`）；`RERUN`＝在集成栈经入口真 HTTP 端到端执行（`ACC-T<nn>`）。`REUSE+RERUN`＝保留权威证据并对指定子集重跑。T36＝Audit 保留/无入口 REUSE + F016 新增备份（§7）。

| T | 权威 Feature | 处置 | REUSE 锚点（报告 / 测试模块） | RERUN 用例 ID | 集成栈可达确认 |
| --- | --- | --- | --- | --- | --- |
| T01/T02/T03 | F004 | REUSE | F004 test-report§TE A1–A3；`test_resources.py::test_create_defaults_and_unique_within_cluster`/`test_cross_cluster_same_hostname_allowed`/`test_soft_delete_then_recreate` | — | ACC-RCHK-T01 |
| T04/T05/T06 | F010 | REUSE | F010 test-report§TE；`test_ip_addresses.py::test_same_cluster_unique_and_cross_cluster_allowed`/`test_manual_allocation_invalid_addresses`；`test_ip_address_constraints.py::test_cidr_contains_trigger` | — | ACC-RCHK-T04 |
| T07 | F010 | REUSE（真并发） | `test_ip_addresses.py::test_concurrent_auto_allocation_no_duplicates`；`test_ip_address_constraints.py::test_partial_unique_concurrent_single_winner` | — | ACC-RCHK-T07 |
| T08/T09 | F006 | REUSE | F006 test-report§TE；`test_virtual_machine_constraints.py::test_host_valid_trigger`/`test_type_match_trigger` | — | ACC-RCHK-T08 |
| T10 | F010 | REUSE | `test_ip_address_constraints.py::test_interface_cluster_trigger` | — | ACC-RCHK-T10 |
| T11 | F004/F014 | RERUN | — | **ACC-T11** | 含于 RERUN |
| T12 | F007 | REUSE | `test_interfaces.py::test_name_unique_partial_and_reuse`/`test_name_normalisation_case_and_length` | — | ACC-RCHK-T12 |
| T13 | F003 | REUSE | `test_cluster_constraints.py::test_code_key_full_unique_includes_soft_deleted`/`test_code_is_immutable_trigger` | — | ACC-RCHK-T13 |
| T14 | F008 | REUSE | `test_networks.py::test_cidr_overlap_and_inactive`/`test_patch_cidr_and_gateway_recheck`/`test_reference_checker_blocks_change_and_delete` | — | ACC-RCHK-T14 |
| T15 | F009 | REUSE | `test_ip_pools.py::test_range_overlap_and_soft_delete_release`/`test_address_validation`/`test_allocation_mode_transitions` | — | ACC-RCHK-T15 |
| T16 | F008/F010 | RERUN | — | **ACC-T16** | 含于 RERUN |
| T17/T18 | F010 | REUSE | `test_ip_addresses.py::test_manual_allocation_in_pool`/`test_auto_allocation_skips_gateway_and_reserved`/`test_unbound_occupies_and_unbind_keeps`/`test_pool_source_exception`/`test_capacity_endpoint_formula` | — | ACC-RCHK-T17 |
| T19 | F004/F006 | RERUN | — | **ACC-T19** | 含于 RERUN |
| T20 | F007 | REUSE | `test_interfaces.py::test_parent_validation`/`test_parent_cycle_concurrency_serialised_by_resource_lock` | — | ACC-RCHK-T20 |
| T21 | F011 | REUSE | `test_services.py::test_same_resource_name_unique_case_insensitive`/`test_status_default_and_values` | — | ACC-RCHK-T21 |
| T22 | F010/F012 | RERUN | — | **ACC-T22** | 含于 RERUN |
| T23 | F007–F012/F015 | RERUN | — | **ACC-T23** | 含于 RERUN |
| T24 | F015/各域 | RERUN | — | **ACC-T24** | 含于 RERUN |
| T25 | F002/F015 | RERUN | — | **ACC-T25** | 含于 RERUN |
| T26 | F002/F015 | RERUN | — | **ACC-T26** | 含于 RERUN |
| T27 | F014 | RERUN | — | **ACC-T27** | 含于 RERUN |
| T28 | F014 | REUSE+RERUN（子集） | F014 test-report§TE；`test_imports.py::test_vm_host_four_conditions`/`test_vm_host_must_be_out_of_batch`/`test_existing_conflict_not_overwritten`/`test_file_size_and_row_limits` | **ACC-T28**（Host 须已存在 + 不覆盖 + 上限，经入口） | 含于 RERUN |
| T29 | F003/F008 | RERUN | — | **ACC-T29** | 含于 RERUN |
| T30/T31 | F010 | REUSE | `test_ip_addresses.py::test_disabled_ranges_and_31_32_boundaries`/`test_loopback_interface_registers_but_127_not_allocated`/`test_restore_rechecks_allocatable_boundary` | — | ACC-RCHK-T30 |
| T32 | F010/F013 | RERUN | F013 `test_dashboard.py::test_network_capacity_matches_f010_capacity_endpoint`（REUSE 辅助对照） | **ACC-T32** | 含于 RERUN |
| T33/T34 | F009/F010 | REUSE | `test_ip_pools.py::test_occupancy_reserved_create_and_patch`/`test_reserved_restore_rechecks_occupancy`/`test_restore_overlap_recheck`；`test_ip_addresses.py::test_capacity_excludes_disabled_and_dedups_gateway_reserved` | — | ACC-RCHK-T33 |
| T35 | F009/F010 | REUSE（真并发） | `test_ip_addresses.py::test_concurrent_reserved_change_and_allocation`/`test_concurrent_gateway_change_and_allocation` | — | ACC-RCHK-T35 |
| T36 | F015/F016 | REUSE（Audit 保留/无入口）+ 新增备份 | F015 test-report A8/A9/V8/V9；B1–B7（§7） | — | ACC-RCHK-T36 |
| T37 | F004/F007–F012 | RERUN | — | **ACC-T37** | 含于 RERUN |
| T38 | F005/F006/F014 | REUSE | F005/F006 test-report§TE；`test_bare_metal.py::test_create_omitted_and_explicit_null_are_null`/`test_gpu_count_zero_vs_null`/`test_memory_mb_and_cpu_cores_are_stored_verbatim` | — | ACC-RCHK-T38 |
| T39 | F005/F006/F007 | REUSE | `test_bare_metal.py::test_memory_mb_and_cpu_cores_are_stored_verbatim`；F006 `test_virtual_machine_constraints.py` 容量语义 | — | ACC-RCHK-T39 |
| T40 | F007/F008/F009/F011 | RERUN | — | **ACC-T40** | 含于 RERUN |
| T41 | F008/F009/F011/F015 | RERUN | — | **ACC-T41** | 含于 RERUN |

**RERUN 清单（必须集成栈真 HTTP 执行）**：ACC-T11、ACC-T16、ACC-T19、ACC-T22、ACC-T23、ACC-T24、ACC-T25、ACC-T26、ACC-T27、ACC-T28（子集）、ACC-T29、ACC-T32、ACC-T37、ACC-T40、ACC-T41。

**RERUN 用例判据（经入口 :18080，ADMIN/EDITOR/VIEWER 真实会话）**

| 用例 | 判据（真 HTTP） |
| --- | --- |
| ACC-T11 | 以 `CN_001`/` cn001 ` 等混合大小写与首尾空白 hostname 经 API 创建 → 归一后同 Cluster 重复 409；同规则经 CSV 与 .xlsx 导入同样 409；API 与导入不绕过同一唯一性 |
| ACC-T16 | INACTIVE Network 上新增分配失败；`auto_allocate=false` 时自动分配失败（手动允许）；指定 AUTO 池耗尽不切换其它池 |
| ACC-T19 | VM 缺失 Host/引用已软删 Host 创建失败；同 Cluster 换 Host 成功且 Activity/Audit 记 `UPDATE` 前后 Host；Resource PATCH Cluster/类型被拒 |
| ACC-T22 | Endpoint 空 IP/他资源 IP/非法协议端口/重复监听失败；有 Endpoint 引用时 IP 解绑/转移/释放被拒并返回引用 |
| ACC-T23 | 存活引用阻止删除并返回引用列表；无隐式级联；类型明细跟随 Resource；Pool 来源例外 |
| ACC-T24 | ADMIN 经 `/api/v1/deleted` 查看并恢复；恢复不级联；标识重用或依赖仍删时恢复失败且不覆盖新对象 |
| ACC-T25 | 三角色 × {查询/详情=全角色，写=EDITOR+，删除/释放/恢复/用户/完整审计=ADMIN}；401 先于 403 |
| ACC-T26 | 陈旧 `version` PATCH→409 `VERSION_CONFLICT` 且不静默覆盖；Audit 保留操作者；响应/Audit 无密码/令牌 |
| ACC-T27 | CSV/.xlsx：先 validate（错误行含行号+字段+原因）→ confirm；写入前再校验；任一失败整批回滚零残留（含无 Audit 残留） |
| ACC-T28 | 导入 VM Host 必须已存在（同批不隐式创建）；不更新/覆盖现存资源；超文件大小/行数上限被拒 |
| ACC-T29 | INACTIVE Cluster 下查询/新增/修改/导入/删除/恢复按权限可用；默认列表含停用且可过滤；切换状态不级联、不释放 IP；Network 自身停用仍阻分配 |
| ACC-T32 | Network/AUTO 池容量集合口径；Dashboard `/api/v1/dashboard` 与 `/api/v1/networks/{id}/capacity` 一致；停用不清零 |
| ACC-T37 | 创建省略字段取默认值；Role 显式 `null` 被拒；Interface 类型不由名称推断；导入与 API 同规则 |
| ACC-T40 | 名称 trim、空名/控制字符失败；Interface 内部空白失败且区分大小写；Network/Pool/Service 大小写不敏感、保留中文与内部空格 |
| ACC-T41 | 删除后名称可复用且作用域内唯一；名称复用时旧对象恢复失败且不覆盖新对象；Cluster code 不可复用 |

---

## 4. §32 C1–C15 上线验收用例设计（真 HTTP，DR-238）

结果列 TE-1 填充。C14 复用 §7，C15 为实际汇总（I-2）。

| # | 用例 | 真 HTTP 路径 | 判据 |
| --- | --- | --- | --- |
| C1 | 创建 Cluster/BM/VM 并关联 Host | `POST /api/v1/clusters`、`POST /api/v1/resources`（BARE_METAL）、`POST /api/v1/resources`（VIRTUAL_MACHINE + `host_resource_id`） | 201；VM 详情 `virtual_machine.host.hostname=pve01` |
| C2 | 维护 Interface/Network/Pool/Service | `POST /api/v1/interfaces`、`/networks`、`/ip-pools`、`/services` | 201；默认值/归属/Cluster 一致 |
| C3 | 手动与自动分配 IP | `POST /api/v1/ip-addresses`（手动）、自动分配端点；`PATCH` 绑定/解绑 | 手动池内外语义正确；自动升序可用；绑定关系正确 |
| C4 | 按 hostname/IP/Cluster/Service 找 Resource | `GET /api/v1/search?q=`、`GET /api/v1/resources?cluster=`、`GET /api/v1/services?resource_id=` | 各自命中目标 Resource |
| C5 | 详情显示 Cluster/硬件/Interface/IP/Network/VM 或 Host/Service | `GET /api/v1/resources/{id}` + `GET /interfaces?resource_id=`、`GET /ip-addresses?interface_id=`、`GET /services?resource_id=` | 组合结果覆盖全部维度 |
| C6 | 阻止重复 hostname/IP、跨 Cluster Host/IP、非法 CIDR | 重复资源/IP 创建、跨 Cluster Host 绑定、非 CIDR 分配 | 409 / 422（按契约错误语义） |
| C7 | 逻辑删除及 ADMIN 恢复 | `DELETE /api/v1/{object}/{id}` → `POST /{id}/restore` | 删除后默认隐藏；ADMIN 恢复 200；非 ADMIN 拒绝 |
| C8 | Audit Log | `GET /api/v1/audit`（ADMIN） | CREATE/UPDATE/DELETE/RESTORE 含 operator/before/after/时间 |
| C9 | 基础权限 | 三角色调用读写/删除/审计/用户端点 | 与服务端矩阵一致；401 先于 403 |
| C10 | 本地登录 | `POST /api/v1/auth/login`（bootstrap admin + 新建账号） | 200；`permissions` 与角色匹配；失败响应不可区分 |
| C11 | 版本冲突检查 | 陈旧 `version` 的 PATCH | 409 `VERSION_CONFLICT`，无静默覆盖 |
| C12 | CSV/.xlsx 整批新增导入 | `/api/v1/imports/*`：validate → confirm | 先校验后确认再校验、整批成功/回滚、错误明细 |
| C13 | Network/Pool/Endpoint/恢复约束 | 引用阻止删除、RESERVED/gateway 占用、恢复重检 | 与 §12/§21 一致，返回冲突数量/明细 |
| C14 | 审计持续保留且纳入备份 | B1–B7（§7） | 恢复后审计完整、append-only 保持 |
| C15 | §31 与以上均有真实证据，全部必需能力不被删除 | 汇总 ACC-T01–T41 + ACC-C1–C14 | 实际执行汇总（非局部拼接）；无必需能力缺失 |

---

## 5. §33 目标查询场景用例设计（真 HTTP，DR-239）

路径均为既有端点组合（不新增场景接口）。**依赖浏览器 DOM 渲染者**以「真实 HTTP 数据正确 + 前端构建成功」为证据并标 `NOT TESTED`（§7.2/§9）；数据层答案必须真 HTTP 校验。

| # | 查询 | 真 HTTP 路径 | 期望（数据层） | DOM 依赖 |
| --- | --- | --- | --- | --- |
| Q1 | hostname 属于哪个集群 | `GET /api/v1/search?q=cn001` | 命中 Resource 且 `resource.cluster.code` 正确 | 否（可 HTTP 断言） |
| Q2 | 某 IP 是哪台机器 | `GET /api/v1/search?q=<ip>` → `GET /api/v1/ip-addresses/{id}` | 已绑定→`interface.resource.hostname`；未绑定→interface 为 null（明确无 Resource） | 否 |
| Q3 | cn001 管理网和 IB 地址 | `GET /api/v1/interfaces?resource_id=` + `GET /api/v1/ip-addresses?interface_id=` | 两 Interface 及各自 IP 正确 | 否 |
| Q4 | vm001 宿主机 | `GET /api/v1/resources/{vm_id}` | `virtual_machine.host.hostname=pve01` | 否 |
| Q5 | pve01 下有哪些 VM | `GET /api/v1/resources?host_resource_id=<pve01>&type=VIRTUAL_MACHINE` | 全部未删 VM | 否 |
| Q6 | Network 剩余可用 IP | `GET /api/v1/networks/{id}/capacity` + `GET /api/v1/dashboard` | 与容量端点逐项一致 | 否（页面呈现 NOT TESTED） |
| Q7 | IP 是否被使用 | `GET /api/v1/ip-addresses/{id}` 绑定状态 + 占用口径 | 绑定状态正确；未绑定仍占用 | 否 |
| Q8 | 机器运行哪些 Service | `GET /api/v1/services?resource_id=` | 列出 Service（含 Endpoint 关联） | 否 |
| Q9 | 谁修改了服务器信息 | `GET /api/v1/resources/{id}/activity`、`GET /api/v1/audit`（ADMIN） | 操作者/动作/before-after/时间 | 否 |

---

## 6. T36 备份覆盖 Audit 设计（DR-240/O-4/B1–B7）

前置：`csm_f016_acc` 已由真实写入产生 `audit_logs` 行（≥1）。操作在 `f016-db` 容器内（宿主无客户端）：

```bash
# 1) 产生/确认审计行
docker exec f016-db psql -U csm -d csm_f016_acc -tAc "SELECT count(*) FROM audit_logs;"
# 2) 备份到暂存（独立于库）
docker exec f016-db pg_dump -Fc --no-owner --no-privileges -U csm -d csm_f016_acc > /tmp/csm_f016_acc.dump
# 3) 恢复到新库
docker exec f016-db createdb -U csm csm_f016_restore
docker exec -i f016-db pg_restore --no-owner --no-privileges -U csm -d csm_f016_restore < /tmp/csm_f016_acc.dump
```

| 断言 | 内容 | 证据 |
| --- | --- | --- |
| B1 | 源库与恢复库 `audit_logs` 行数一致且 >0 | 两侧 `SELECT count(*)` 输出 |
| B2 | 关键字段聚合一致（`md5(string_agg(...))` over `operator_username,action,object_type,object_id,created_at`）源=恢复 | 两侧聚合输出 |
| B3 | 恢复库 `trg_audit_logs_append_only` 存在 | `pg_trigger` 查询输出 |
| B4 | 恢复库 `UPDATE audit_logs`/`DELETE FROM audit_logs` 被触发器拒绝 | raw SQL 异常输出 |
| B5 | `alembic_version` 一致；`alembic upgrade head` 幂等（单 head） | `alembic current` 输出 |
| B6 | 恢复库对应后端 `/api/v1/health/ready` 200 | 临时指向恢复库的探针 200（或等价 verify） |
| B7 | 备份产物非空（`stat -c %s`>0）且可被 `pg_restore --list` 解析 | 文件大小 + list 输出 |

仅 B1–B7 全部有实际输出方可断言「备份覆盖 Audit」；否则标 `BLOCKED`/`NOT TESTED`，不得宣称覆盖。脚本落点 `scripts/acceptance/verify_audit_backup.sh`。

---

## 7. 脚本 / 夹具落点与清理纪律（DR-241/245）

**脚本**（`scripts/acceptance/`，Tester/验收基础设施，不改业务代码）：
- `run_acceptance.sh`：Preflight → Compose 尝试与失败录制 → 替代栈拉起 → 健康判据 → 数据集构造 → 运行 `test_f016_acceptance.py` → `verify_audit_backup.sh` → 清理。
- `verify_audit_backup.sh`：§6 B1–B7。
- `README.md`：环境变量、命令、产物路径、清理步骤。
- `artifacts/`：Compose 日志、健康探测、pytest 输出（含 HEAD/时间）。

**夹具**（`backend/tests/integration/`）：
- `f016_helpers.py`：`acceptance_base_url()`（`F016_BASE_URL`，默认 `http://localhost:18080`）；`admin_login()`/`role_client(role)`；带 `Origin` 的写请求封装；`create_dataset()`（DR-236）；`db_engine()`（`F016_DATABASE_URL`，**验收库护栏**：库名须等于 `csm_f016_acc`，否则 skip）；只读快照 `audit_snapshot()`/`capacity_snapshot()`；REUSE 可达探测 `probe_reuse_endpoint(T)`。
- `test_f016_acceptance.py`：ACC-T*/ACC-C*/ACC-Q*/B1–B7 用例。**护栏**：未设 `F016_BASE_URL`（或 `F016_ACCEPTANCE!=1`）时整体 skip，避免污染常规 `pytest tests` 全量。
- 复用既有 `conftest.py` 时**不请求** `pg_engine`/`db_session`（避免其重建 schema/回滚语义干扰验收库）；验收直连仅只读断言，写操作经真实 HTTP。

**清理纪律（I-7/A14）**：结束时 `docker rm -f f016-db f016-backend f016-frontend f016-nginx`；`docker network rm f016-acceptance-net`；`DROP DATABASE csm_f016_restore`、`DROP DATABASE csm_f016_acc`；删除 `/tmp/csm_f016_acc.dump` 与 `scripts/acceptance/artifacts/` 临时物；如走 Compose 路径则 `docker compose down -v`。清理后断言无 `f016-*` 容器/网络/卷残留。前端 `dist/` 为 git-ignored 构建产物，不视为业务残留。

---

## 8. 环境与可验证性

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1/A13 栈启动/健康 | 可验证 | Compose 尝试可录制；替代栈组件（`postgres:16`、`nginx:1.27-alpine`、`csm-f007-test`）与 node 均就位；宿主无 `pg_dump` → 用 `docker exec` |
| A2 数据集 | 可验证（真HTTP） | DR-236 经既有端点构造 |
| A3/A4 T 索引/重跑 | 可验证（真HTTP） | RERUN 清单固定；REUSE 锚点存在（F003–F015 test-report + 测试模块已核对） |
| A5/A6 §33/§32 | 可验证（真HTTP） | 端点与参数已核对（`resources?host_resource_id`、`networks/{id}/capacity`、`search`、`audit`、`imports` 等） |
| A7 T36 | 可验证（真PG 容器） | `pg_dump`/`pg_restore` 在 `f016-db` 内；B1–B7 |
| A8 权限 | 可验证（真HTTP） | 会话与 Origin/CSRF 路径 |
| A9 导入 | 可验证（真HTTP） | `python-multipart`/`openpyxl` 容器内补装 |
| A10 并发 | REUSE + 可达确认 | 权威 `committed_engine` 真并发锚点；集成栈只作端点可达确认（不从黑盒伪造并发约束证据） |
| A11 acceptance | 协调器 | Tester 不写 `project.acceptance` |
| A12 未改语义 | 可验证（静态） | Git 范围检查 |
| A14 清理 | 可验证 | 残留断言 |
| `project-state` 一致性 | 条件 | 项目状态文件有变更时运行 `scripts/validate_project_state.py`；结构通过不代表批准或 Git 证据有效 |

**前端真实集成口径**：§33 数据层经真 HTTP 断言；页面 Loading/Success/Empty/Error、导航门控等**依赖 DOM 渲染**的部分，无浏览器 E2E harness 时以「真实 HTTP 正确 + `npm run build`/`smoke:client` 成功」为证据并标 `NOT TESTED`；不得以 Mock 断言替代。

---

## 9. OPEN 清单（TD-1，不阻塞 READY，TE-1 前/中核对）

| OPEN | 说明 | 影响 | Owner |
| --- | --- | --- | --- |
| F016-OPEN-1 | Compose 是否可构建取决于环境网络；TD-1 依据当前探测预期走替代栈，实际路径 TE-1 录制 | A1/A13 | 协调器/Tester |
| F016-OPEN-2 | 浏览器 DOM E2E harness 是否可用；无则以真 HTTP + build 证据并标 NOT TESTED | A5/§33 前端呈现 | 协调器/Tester |
| F016-OPEN-3 | 验收数据集具体条目（产品 §2.3 为 PROPOSED）按已签核契约构造，不新增规则 | A2 | Tester |
| F016-OPEN-4 | T36 B6「恢复库 ready 200」需临时将探针指向恢复库；实现方式（临时容器/显式 verify）TE-1 确认 | A7 | Tester |
| F016-OPEN-5 | `project.acceptance.evidence` 具体路径列表与 COMPLETE 写入时机 | A11/I-8 | 协调器 |
| F016-OPEN-6 | `docs/features/F016/test-report.md` 锚点与 architecture §10 指定的 `#test-design`/`#t01t41-evidence-index`/`#32-c1c15-上线验收`/`#33-目标查询场景`/`#t36-备份覆盖-audit`/`#未执行--blocked` 一致性 | A11 | Tester/协调器 |

---

## 10. 缺陷路由（DR-244/I-5）

发现实现缺陷 → 按 Severity/Layer 记录，Owner 指向 F001–F015 对应责任 Feature；不静默修改业务实现/Schema/契约。测试基础设施缺陷 → 协调器。业务/架构歧义 → Product/Architect。修复后按 feature.md 有限修复循环重跑受影响项。

---

## 11. 结论

`TEST DESIGN READY`（TD-1）——A1–A14/I-1–I-9 已映射可观察判据；栈启动（Compose 尝试+失败录制+替代栈）与健康判据、差异声明已定；T01–T41 Evidence Index 逐条给出 REUSE 锚点/`ACC-RCHK-*` 与 RERUN 清单（ACC-T11/16/19/22/23/24/25/26/27/28/29/32/37/40/41）；§32 C1–C15、§33 Q1–Q9、T36 B1–B7 均按真实 HTTP/真实 PG 设计；脚本/夹具落点与清理纪律明确。**READY 仅表示方案可验证，不代表测试已运行、不填充 PASS、不批准实现或合并、不构成 `project.acceptance=COMPLETE`。**

GIT: NONE

---

## Test Design TD-2 — OPEN 闭合与执行判据固定

- **版本**：TD-2（2026-10-12）
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-2）
- **依据**：TD-1；`docs/features/F016/{product,architecture}.md`；`docs/database/f016-acceptance.md` v1（NOT_REQUIRED，DB-D173–DB-D176）；`docs/project/{handoff,implementation-rules,project-state}.md`；`.pi/skills/data-integrity/SKILL.md`；落地资产 `compose.yaml`、`deploy/{nginx,backup}`、`frontend/nginx.conf`。

TD-2 仅闭合 TD-1 OPEN 并固定执行判据，不新增业务规则、不预填执行 PASS。

### OPEN 闭合

| OPEN | TD-1 状态 | TD-2 处置 |
| --- | --- | --- |
| F016-OPEN-1 Compose 可用性 | 待录制 | **转执行**：`docker compose -p csm_f016 up -d --build` 实测退出码 `1`（Docker Hub token i/o timeout），归档 `scripts/acceptance/artifacts/run-20261012T043711Z/compose-up.log`；改用替代栈，未伪装 Compose PASS（A1/A13） |
| F016-OPEN-2 浏览器 DOM harness | 可否可用 | **已闭合**：无浏览器 E2E harness。DOM 呈现项标 `NOT TESTED`；数据层以真实 HTTP 断言、机制层以 `npm run build` + `npm run smoke:client`（264 passed）为证据（A5/§33） |
| F016-OPEN-3 数据集条目 | PROPOSED | **转执行**：数据集固定为 DR-236 条目（2 Cluster、cn001 管理网+IB、vm001 Host=pve01、pve01 多 VM、gateway/RESERVED/禁用 Network、AUTO/MANUAL 池、绑定/未绑定 IP、Service/Endpoint、导入样例），由真实 HTTP 构造（A2） |
| F016-OPEN-4 B6 恢复库 ready | 待确认 | **已闭合**：临时容器 `f016-restore-probe`（`DATABASE_URL`→`csm_f016_restore`）跑 `uvicorn` 并探 `/api/v1/health/ready`=200（A7/B6） |
| F016-OPEN-5 acceptance evidence 写入 | 协调器 | **已闭合**：Tester 提供锚点 `#t01t41-evidence-index`/`#32-c1c15-上线验收`/`#33-目标查询场景`/`#t36-备份覆盖-audit`/`#未执行--blocked`；`COMPLETE` 由协调器核验后写入，Tester 不写（A11/I-8） |
| F016-OPEN-6 锚点一致性 | 核对 | **已闭合**：本报告采用 architecture §10 指定锚点，标题与锚点一一对应（A11） |

### 固定执行判据

- 健康：`/healthz`=200、`/api/v1/health/ready` 经 Nginx=200、`/` 返回 index.html、`alembic current`=`0013_search_indexes (head)`。
- 同源：写请求 `Origin` 与 `Host` 均为 `http://localhost:18080`；无 Cookie→401 先于 403。
- RERUN 清单：ACC-T11/16/19/22/23/24/25/26/27/28/29/32/37/40/41 + §32 C1–C15 + §33 Q1–Q9。
- T36：B1–B7 全部需实际输出，否则标 BLOCKED。

**TD-2 仍不代表执行 PASS、不批准实现或合并、不构成 `project.acceptance=COMPLETE`。**

---

## Test Execution

- **版本**：TE-1（2026-10-12）
- **角色**：Tester（TEST 模式）
- **结论**：`READY FOR REVIEW`
- **工作区/基线**：分支 `feature/F016-integration-acceptance`，HEAD `1c07857`（只读核对）。
- **Basis**：TD-1/TD-2；`docs/features/F016/{product,architecture}.md`；`docs/database/f016-acceptance.md` v1；`docs/project/{handoff,implementation-rules,project-state,git-workflow}.md`；`.pi/skills/data-integrity/SKILL.md`。

TE-1 在 **真实部署拓扑**（Nginx → Frontend/FastAPI → PostgreSQL）上独立执行，未复用开发者结果，未以 Mock/SQLite 替代约束/并发证据。

### 环境

- 宿主：Linux，`docker 29.8.0`、`node v22.23.2`/`npm 12.0.2`。
- 镜像（已缓存，无需 pull）：`postgres:16`、`nginx:1.27-alpine`、`csm-f007-test`（含 uvicorn/alembic/pytest/httpx/curl；缺 `python-multipart`/`openpyxl`，容器内 PyPI 补装）。
- 网络限制：Docker Hub / `deb.debian.org` 不可达 → `docker build`/Compose 不可用（实测），改用架构 §5.3 等价的真实替代栈。
- 执行入口：`scripts/acceptance/run_acceptance.sh`（本轮实际执行，退出码 0）；产物 `scripts/acceptance/artifacts/run-20261012T043711Z/`。

### 栈启动结果（A1/A13）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| Compose 尝试 | `docker compose -p csm_f016 up -d --build` | **退出码 1**（`failed to fetch anonymous token … dial tcp … i/o timeout`），归档 `compose-up.log`；随后 `docker compose -p csm_f016 down -v` 退出码 0 |
| 替代栈 | network `f016-acceptance-net`；`postgres:16`（库 `csm_f016_acc`）；`csm-f007-test` 挂 `./backend` + `alembic upgrade head` + `bootstrap_admin` + `uvicorn`（别名 `backend`）；`npm run build` 后 `nginx:1.27-alpine` 服务 `dist`（别名 `frontend`）；入口 `nginx:1.27-alpine`（`-p 18080:80`） | 全部启动成功 |
| 健康判据 | `/healthz`=200、`/api/v1/health/ready`=200、`/`=200、`alembic current`=`0013_search_indexes (head)` | **PASS** |
| 前端构建 | `npm run build`（`tsc --noEmit && vite build`） | 成功（`dist/index.html` + assets） |
| 前端机制层 | `npm run smoke:client` | **264 passed / 0 failed** |

**与 Compose 的差异**（A13，未以替代栈冒充 Compose）：镜像构建（复用镜像+bind-mount vs `docker build`）；代码来源（挂载 vs 镜像内置）；配置注入（`-e` vs `.env`）；编排（脚本时序 vs `depends_on`）；前端（本地产物 vs 镜像内构建）；卷（独立库 vs 命名卷）；入口路由/同源（同一 `deploy/nginx/nginx.conf`，端口 18080，语义一致）。

### 验收映射 A1–A14 / I-1–I-9（TE-1 结果）

| # | 结果 | 证据 |
| --- | --- | --- |
| A1 | **PASS** | Compose 失败退出码+日志归档；替代栈三项健康判据 200；差异声明（上表） |
| A2 | **PASS** | DR-236 数据集经真实 HTTP 创建（`dataset` fixture）；§32 C1–C3、§33 Q1–Q9 消费 |
| A3 | **PASS** | `#t01t41-evidence-index` 覆盖 T01–T41 无缺；RERUN 全部执行 |
| A4 | **PASS** | ACC-T11/16/19/22/23/24/25/26/27/28/29/32/37/40/41 全部通过 |
| A5 | **PASS（数据层）** | Q1–Q9 数据层真实 HTTP 断言；DOM 呈现标 `NOT TESTED`（OPEN-2） |
| A6 | **PASS** | C1–C13/C15 真实 HTTP；C14 由 T36 B1–B7 |
| A7 | **PASS** | T36 B1–B7 全部有实际输出（见 §T36） |
| A8 | **PASS** | ACC-T25/C9：无 Cookie→401；VIEWER/EDITOR 越权→403；401 先于 403 |
| A9 | **PASS** | ACC-T27/T28/C12：先校验→再校验、整批回滚零残留、行号+字段+原因、Host 须已存在、行上限 413 |
| A10 | **PASS** | T07/T35 等 REUSE 锚点指向权威 Feature `committed_engine` 真并发用例；`test_reuse_endpoints_reachable` 在集成栈确认端点 200 |
| A11 | **协调器** | 本报告提供规定锚点；`project.acceptance.evidence` 与 `COMPLETE` 由协调器核验后写入 |
| A12 | **PASS** | `git status`：新增仅 `backend/tests/integration/{f016_helpers,test_f016_acceptance}.py`、`scripts/acceptance/**`、`docs/features/F016/test-report.md`；`git diff --stat` 为空（无业务/Schema/契约改动） |
| A13 | **PASS** | 差异声明与 A1 实际路径一致 |
| A14 | **PASS** | 清理后 `docker ps -a`/`network ls`/`volume ls` 无 `f016-*`；`csm_f016_acc`、`csm_f016_restore` 已 DROP |
| I-1 | 满足 | 每项附命令与原始输出；未执行项标 NOT TESTED/BLOCKED |
| I-2 | 满足 | C15 汇总为实际执行；整体结论基于全部 A/C/Q/B |
| I-3 | 满足 | 约束/并发证据来自权威 Feature 真 PG；未出现 SQLite/Mock |
| I-4 | 满足 | Compose 失败已录制、差异声明、BLOCKED/NOT TESTED 条件齐备 |
| I-5 | 满足 | 未改 F001–F015 代码；无缺陷退回 |
| I-6 | 满足 | 数据集/断言仅引用既有 READY Contract |
| I-7 | 满足 | 独立网络/端口/库；A14 清理断言通过 |
| I-8 | 满足 | `COMPLETE` 不由 Tester 写入 |
| I-9 | 满足 | 结论明确 COMPLETE≠发布授权 |

### 数据库 / 接口 / 前端 / 集成结果

- **数据库**：`docs/database/f016-acceptance.md` NOT_REQUIRED 复核通过；`alembic upgrade head` 单 head `0013_search_indexes`；T36 在真实 PostgreSQL 验证约束/触发器/迁移一致（B1–B7）。无 Schema 改动。
- **接口**：RERUN 与 §32/§33 全部经入口真 HTTP；错误语义（409 `unique_conflict`/`reference_exists`/`allocation_not_allowed`/`no_available_address`、409 `VERSION_CONFLICT`、401 `AUTH_REQUIRED`、403 `FORBIDDEN`）与契约一致；只读端点无写副作用（C8/Q9 审计在只读查询后行数不变，隐含于 B1 稳定）。
- **前端**：`npm run build` 成功；机制层 `smoke:client` 264 passed。**DOM 交互/导航门控/状态渲染未在浏览器执行 → NOT TESTED**（无 harness）；不以 Mock 代替真实 API。
- **集成**：Nginx 入口同源（`Origin=http://localhost:18080`）、CSRF 同源校验、前端静态产物与 `/api/` 代理在一次真实拓扑内联调通过。

### 实际执行的命令与关键输出

```text
$ F016_PW=… F016_ADMIN_USER=admin F016_ADMIN_PW=… bash scripts/acceptance/run_acceptance.sh
[F016] HEAD=1c07857137ba2726e3f78a870f69d4f623570c09 branch=feature/F016-integration-acceptance
[F016] compose exit=1 (log: …/run-20261012T043711Z/compose-up.log)
[F016] health: /healthz=200 /api/v1/health/ready=200 /=200 alembic='0013_search_indexes (head)'
[F016] running F016 acceptance pytest (real HTTP, same-origin http://localhost:18080)
........................................                                 [100%]
40 passed in 2.53s
[F016] pytest exit=0
[T36] source csm_f016_acc audit_logs rows = 97 … [T36] B1-B7 all PASS — Audit is covered by backup/restore
[F016] T36 exit=0
[F016] DONE pytest=0 t36=0 compose=1
[F016] cleanup: removing f016 containers / network / databases
## exit code 0
```

---

## T01–T41 Evidence Index

`REUSE`＝引用权威 Feature 真 PG/真 HTTP 证据（锚点）并在集成栈确认端点可达；`RERUN`＝在集成栈经入口真 HTTP 端到端执行。REUSE 可达由 `test_reuse_endpoints_reachable` 确认（相关读端点均 200）。

| T | 权威 Feature | 处置 | REUSE 锚点（报告 / 测试模块） | RERUN 用例 / 结果 |
| --- | --- | --- | --- | --- |
| T01/T02/T03 | F004 | REUSE | `docs/features/F004/test-report.md#test-execution`；`test_resources.py::test_create_defaults_and_unique_within_cluster` / `test_cross_cluster_same_hostname_allowed` / `test_soft_delete_then_recreate` | 可达 PASS |
| T04/T05/T06 | F010 | REUSE | `docs/features/F010/test-report.md#test-execution`；`test_ip_addresses.py::test_same_cluster_unique_and_cross_cluster_allowed` / `test_manual_allocation_invalid_addresses`；`test_ip_address_constraints.py::test_cidr_contains_trigger` | 可达 PASS |
| T07 | F010 | REUSE（真并发） | `test_ip_addresses.py::test_concurrent_auto_allocation_no_duplicates`；`test_ip_address_constraints.py::test_partial_unique_concurrent_single_winner` | 可达 PASS |
| T08/T09 | F006 | REUSE | `docs/features/F006/test-report.md#test-execution`；`test_virtual_machine_constraints.py::test_host_valid_trigger` / `test_type_match_trigger` | 可达 PASS |
| T10 | F010 | REUSE | `test_ip_address_constraints.py::test_interface_cluster_trigger` | 可达 PASS |
| T11 | F004/F014 | **RERUN** | — | `test_acc_t11_api_and_import_share_hostname_normalisation` **PASS** |
| T12 | F007 | REUSE | `docs/features/F007/test-report.md#test-execution`；`test_interfaces.py::test_name_unique_partial_and_reuse` / `test_name_normalisation_case_and_length` | 可达 PASS |
| T13 | F003 | REUSE | `docs/features/F003/test-report.md#test-execution`；`test_cluster_constraints.py::test_code_key_full_unique_includes_soft_deleted` / `test_code_is_immutable_trigger` | 可达 PASS |
| T14 | F008 | REUSE | `docs/features/F008/test-report.md#test-execution`；`test_networks.py::test_cidr_overlap_and_inactive` / `test_patch_cidr_and_gateway_recheck` / `test_reference_checker_blocks_change_and_delete` | 可达 PASS |
| T15 | F009 | REUSE | `docs/features/F009/test-report.md#test-execution`；`test_ip_pools.py::test_range_overlap_and_soft_delete_release` / `test_address_validation` / `test_allocation_mode_transitions` | 可达 PASS |
| T16 | F008/F010 | **RERUN** | — | `test_acc_t16_inactive_and_auto_allocation_gates` **PASS** |
| T17/T18 | F010 | REUSE | `test_ip_addresses.py::test_manual_allocation_in_pool` / `test_auto_allocation_skips_gateway_and_reserved` / `test_unbound_occupies_and_unbind_keeps` / `test_pool_source_exception` / `test_capacity_endpoint_formula` | 可达 PASS |
| T19 | F004/F006 | **RERUN** | — | `test_acc_t19_vm_host_rules_and_resource_immutability` **PASS** |
| T20 | F007 | REUSE | `test_interfaces.py::test_parent_validation` / `test_parent_cycle_concurrency_serialised_by_resource_lock` | 可达 PASS |
| T21 | F011 | REUSE | `docs/features/F011/test-report.md#test-execution`；`test_services.py::test_same_resource_name_unique_case_insensitive` / `test_status_default_and_values` | 可达 PASS |
| T22 | F010/F012 | **RERUN** | — | `test_acc_t22_endpoint_rules_and_reference_guard` **PASS** |
| T23 | F007–F012/F015 | **RERUN** | — | `test_acc_t23_live_references_block_delete_with_list` **PASS** |
| T24 | F015/各域 | **RERUN** | — | `test_acc_t24_admin_deleted_view_and_restore` **PASS** |
| T25 | F002/F015 | **RERUN** | — | `test_acc_t25_permission_matrix_401_before_403` **PASS** |
| T26 | F002/F015 | **RERUN** | — | `test_acc_t26_version_conflict_and_audit_hygiene` **PASS** |
| T27 | F014 | **RERUN** | — | `test_acc_t27_import_validate_then_confirm_atomic` **PASS** |
| T28 | F014 | REUSE+RERUN（子集） | `docs/features/F014/test-report.md#test-execution`；`test_imports.py::test_vm_host_four_conditions` / `test_vm_host_must_be_out_of_batch` / `test_existing_conflict_not_overwritten` / `test_file_size_and_row_limits` | `test_acc_t28_import_vm_host_rules_and_limits` **PASS** |
| T29 | F003/F008 | **RERUN** | — | `test_acc_t29_inactive_cluster_maintenance` **PASS** |
| T30/T31 | F010 | REUSE | `test_ip_addresses.py::test_disabled_ranges_and_31_32_boundaries` / `test_loopback_interface_registers_but_127_not_allocated` / `test_restore_rechecks_allocatable_boundary` | 可达 PASS |
| T32 | F010/F013 | **RERUN** | `docs/features/F013/test-report.md#test-execution`；`test_dashboard.py::test_network_capacity_matches_f010_capacity_endpoint`（辅助对照） | `test_acc_t32_capacity_matches_dashboard` **PASS** |
| T33/T34 | F009/F010 | REUSE | `test_ip_pools.py::test_occupancy_reserved_create_and_patch` / `test_reserved_restore_rechecks_occupancy` / `test_restore_overlap_recheck`；`test_ip_addresses.py::test_capacity_excludes_disabled_and_dedups_gateway_reserved` | 可达 PASS |
| T35 | F009/F010 | REUSE（真并发） | `test_ip_addresses.py::test_concurrent_reserved_change_and_allocation` / `test_concurrent_gateway_change_and_allocation` | 可达 PASS |
| T36 | F015/F016 | REUSE（Audit 保留/无入口）+ 新增备份 | `docs/features/F015/test-report.md#test-execution`（A8/A9/V8/V9）；本节 §T36 B1–B7 | **PASS** |
| T37 | F004/F007–F012 | **RERUN** | — | `test_acc_t37_defaults_explicit_null_and_import_parity` **PASS** |
| T38 | F005/F006/F014 | REUSE | `docs/features/F005/test-report.md#test-execution`；`test_bare_metal.py::test_create_omitted_and_explicit_null_are_null` / `test_gpu_count_zero_vs_null` / `test_memory_mb_and_cpu_cores_are_stored_verbatim` | 可达 PASS |
| T39 | F005/F006/F007 | REUSE | `test_bare_metal.py::test_memory_mb_and_cpu_cores_are_stored_verbatim`；F006 `test_virtual_machine_constraints.py` 容量语义 | 可达 PASS |
| T40 | F007/F008/F009/F011 | **RERUN** | — | `test_acc_t40_name_normalisation_and_uniqueness` **PASS** |
| T41 | F008/F009/F011/F015 | **RERUN** | — | `test_acc_t41_reuse_and_scope_uniqueness` **PASS** |

> T04/T17 等 REUSE 条目的判据正文以权威 Feature 报告与测试模块为准，F016 不重定义；本表仅登记证据来源与可达确认结果。

---

## §32 C1–C15 上线验收

真实 HTTP 执行（`test_f016_acceptance.py`），C15 为实际汇总。

| # | 用例 | 结果 | 证据（测试函数） |
| --- | --- | --- | --- |
| C1 | 创建 Cluster/BM/VM 并关联 Host | **PASS** | `test_c1_create_cluster_bm_vm_and_host`（vm001→pve01） |
| C2 | 维护 Interface/Network/Pool/Service | **PASS** | `test_c2_interfaces_networks_pools_services` |
| C3 | 手动与自动分配 IP | **PASS** | `test_c3_manual_and_auto_ip_allocation` |
| C4 | 按 hostname/IP/Cluster/Service 找 Resource | **PASS** | `test_c4_find_resource_by_hostname_ip_cluster_service` |
| C5 | 详情显示 Cluster/硬件/Interface/IP/VM-Host/Service | **PASS** | `test_c5_detail_composition` |
| C6 | 阻止重复 hostname/IP、跨 Cluster Host、非法 CIDR | **PASS** | `test_c6_conflict_guards` |
| C7 | 逻辑删除及 ADMIN 恢复 | **PASS** | `test_c7_logical_delete_and_admin_restore` |
| C8 | Audit Log（operator/action/before-after/时间） | **PASS** | `test_c8_audit_log` |
| C9 | 基础权限（服务端矩阵，401 先于 403） | **PASS** | `test_c9_permissions` |
| C10 | 本地登录 | **PASS** | `test_c10_local_login_and_permissions` |
| C11 | 版本冲突检查 | **PASS** | `test_c11_version_conflict` |
| C12 | CSV/.xlsx 整批新增导入 | **PASS** | `test_c12_import_batch`（xlsx 规则等同性另见 ACC-T11） |
| C13 | Network/Pool/Endpoint/恢复约束 | **PASS** | `test_c13_network_pool_endpoint_and_restore_constraints` |
| C14 | 审计持续保留且纳入备份 | **PASS** | §T36 B1–B7 |
| C15 | §31 与以上均有真实证据，必需能力不被删除 | **PASS** | `test_c15_required_capabilities_executed`（对全部必需读端点实际回包 200 的汇总） |

**C1–C15 全部有真实执行证据；整体结论基于 A/C/Q/B 全部完成，不由局部 PASS 拼接。**

---

## §33 目标查询场景

| # | 查询 | 结果 | 证据（测试函数） |
| --- | --- | --- | --- |
| Q1 | hostname 属于哪个集群 | **PASS（数据层）** | `test_q1_hostname_to_cluster`（cn001→F16… cluster） |
| Q2 | 某 IP 是哪台机器 | **PASS（数据层）** | `test_q2_ip_to_machine`（绑定→mgmt0；未绑定→interface null） |
| Q3 | cn001 管理网和 IB 地址 | **PASS（数据层）** | `test_q3_management_and_ib_addresses` |
| Q4 | vm001 宿主机 | **PASS（数据层）** | `test_q4_vm_host`（→pve01） |
| Q5 | pve01 下有哪些 VM | **PASS（数据层）** | `test_q5_host_vms`（host_resource_id+type 过滤） |
| Q6 | Network 剩余可用 IP | **PASS（数据层）** | `test_q6_network_remaining_capacity`；页面呈现 **NOT TESTED** |
| Q7 | IP 是否被使用 | **PASS（数据层）** | `test_q7_ip_usage_state` |
| Q8 | 机器运行哪些 Service | **PASS（数据层）** | `test_q8_resource_services` |
| Q9 | 谁修改了服务器信息 | **PASS（数据层）** | `test_q9_activity_and_audit` |

**DOM 依赖部分**（Q6 页面卡片渲染、导航门控、Loading/Success/Empty/Error 状态）无浏览器 harness → `NOT TESTED`；以真实 HTTP 数据正确 + `npm run build` + `smoke:client` 264 passed 为证据，不以 Mock 代替。

---

## T36 备份覆盖 Audit

容器内运行既有 `deploy/backup/{pg_dump.sh,restore.sh}`（postgres:16 客户端容器；脚本 `pg_dump -Fc --no-owner --no-privileges` 全库 → `pg_restore` 到新库 `csm_f016_restore`）。

| 断言 | 内容 | 实际输出 | 结果 |
| --- | --- | --- | --- |
| B1 | 源/恢复 `audit_logs` 行数一致且 >0 | source=97 restore=97 | **PASS** |
| B2 | 关键字段聚合 md5 一致 | `01e481dbef2a23b2ff611f48524026ba` = 同值 | **PASS** |
| B3 | 恢复库 append-only 触发器存在 | `pg_trigger`=`trg_audit_logs_append_only` count=1 | **PASS** |
| B4 | 恢复库 UPDATE/DELETE 被拒 | UPDATE rc=1、DELETE rc=1（`fn_audit_logs_append_only` RAISE） | **PASS** |
| B5 | `alembic_version` 一致且 upgrade 幂等 | source=restore=`0013_search_indexes`；`alembic upgrade head` 无变化 | **PASS** |
| B6 | 恢复库后端 ready 200 | 临时 `f016-restore-probe` → `/api/v1/health/ready`=200 | **PASS** |
| B7 | 产物非空且 `pg_restore --list` 可解析 | size=158804 B；归档列出 `TABLE public audit_logs` + `TRIGGER … trg_audit_logs_append_only` + `FUNCTION … fn_audit_logs_append_only()` | **PASS** |

**B1–B7 全部有实际输出，可断言「备份覆盖 Audit」；恢复后 append-only 保持、审计完整无截断。**

---

## 未执行 / Blocked

| 项 | 状态 | 原因 / 条件 | 责任者 | 恢复动作 |
| --- | --- | --- | --- | --- |
| `docker build` / `docker compose up -d` 首选路径 | **BLOCKED（已录制，非缺陷）** | Docker Hub + `deb.debian.org` 不可达（token i/o timeout） | 环境 / 协调器 | 网络可达后按 `scripts/acceptance/run_acceptance.sh` 首要路径复跑；当前以等价替代栈执行并声明差异 |
| §33/§32 的浏览器 DOM 呈现、导航门控、Loading/Success/Empty/Error | **NOT TESTED** | 无浏览器 E2E harness（OPEN-2） | 协调器 | 接入 E2E harness 后补测；数据层与机制层已由真 HTTP + build + smoke 覆盖 |
| T36 B6 的“恢复库 ready” | **已执行** | 临时探针容器（OPEN-4 已闭合） | Tester | — |

未执行/受限项均未伪造 PASS，不以 Mock/SQLite 替代约束与并发证据。

---

## Defects

无。RERUN、§32、§33 与 T36 全部通过，未发现实现缺陷；无阻塞/必须修复问题。

---

## 结论

`READY FOR REVIEW`——TE-1 在真实等价部署拓扑上实际执行：Compose 失败已如实录制并切换替代栈；健康判据达标；RERUN 15 项 + §32 C1–C15 + §33 Q1–Q9 数据层 + T36 B1–B7 全部通过；T01–T41 Evidence Index 完整（REUSE 锚点 + 集成栈可达确认）。未执行项仅为环境性 Compose 首选路径与浏览器 DOM（已标 BLOCKED/NOT TESTED）。**本报告供协调器核验 `project.acceptance.evidence`；`COMPLETE` 由协调器写入，COMPLETE≠发布授权。**

GIT: NONE