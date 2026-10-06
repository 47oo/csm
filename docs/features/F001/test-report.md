# F001 工程与部署底座 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据，TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-2
- **日期**：2026-10-06
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§22、§25–§31、§35.3 D02）
  - `docs/features/F001/product.md`（READY FOR ARCHITECT；7 项可观察验收）
  - `docs/features/F001/architecture.md`（READY FOR DESIGN；验证策略 V1–V7，fixture 要点）
  - `docs/database/f001-baseline.md` v1（Database 签核；DB-D1–DB-D12）
  - `docs/project/project-plan.yaml` plan_revision 4，F001 条目（已批准，CONTINUOUS）
  - `docs/project/implementation-rules.md`（验证与交付）、`AGENTS.md`（数据安全、Git）、`.pi/skills/data-integrity/SKILL.md`
- **状态属性**：READY 仅表示方案可验证、验收项可映射到可观察判据；**不表示测试通过、不批准实现或合并**。TD-2 已完成与 DATABASE Gate 定稿（`docs/database/f001-baseline.md`）的差异复核；若最终实现或 Contract 再变更导致判据差异，将再升版并注明失效范围。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-06 | 初版：验收 7 项映射 V1–V8、B1–B10、夹具与可验证性检查；含对 DATABASE Gate 的 4 项 OPEN 假设 |
| TD-2 | 2026-10-06 | 依据 DATABASE Gate 定稿复核并收紧判据：①V2/B1/B4 由“downgrade 对称/清除对象”改为 **DB-D4 非对称**（downgrade 不 drop 扩展，仅清 `alembic_version`，再 upgrade 幂等收敛 head）；②V3/B3 扩展断言收敛为 **DB-D2 仅 `pg_trgm`**，`btree_gist` 基线断言**不存在**（推迟 F008/F009），删除“downgrade 对称性佐证”表述；③新增 **V3b/B11** 非 superuser owner 安装 `pg_trgm`（DB-D11 trusted 假设）；④V4/B9 及夹具按 **DB-D10 独立测试库**（重建 public schema + 安全护栏）与 **DB-D12 备份5 项冒烟判据/脚本参数**对齐；⑤§5 OPEN 4 项标记已裁定。TD-1 相应判据失效，不再作为执行依据。 |

### 0. 数据完整性对应表（F001 范围）

仅列 F001 已确认且在实现后需验证的完整性/持久化项；F001 不建业务表，业务约束对应项留给后续 Feature。方法依据 `.pi/skills/data-integrity/SKILL.md`。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §26 revision 3（基线仅 pg_trgm；btree_gist 推迟） | Alembic 基线迁移 | `CREATE EXTENSION IF NOT EXISTS pg_trgm`（版本化） | N/A（无业务写入） | downgrade **非对称**：不 drop 扩展（DB-D4） | V3/V3b：迁移后查 `pg_extension`；计划验证 |
| §26 / §27（真实 PG 验证，不用 SQLite 作约束证据） | 集成 fixture | 真实 PostgreSQL 建 schema/迁移 | N/A | 会话级建库、函数级 savepoint | V2/V4：迁移一致性与重复运行；计划验证 |
| §22 / §30（凭据不入仓、不落日志） | 配置注入 | N/A | 日志/错误不输出连接串；仓库无真实凭据 | N/A | V6：静态检查 + 启动冒烟；计划验证 |
| §22 / §31 T36（备份边界，Audit 覆盖由 F016） | pg_dump 骨架 | 备份含 `alembic_version`；`-Fc --no-owner --no-privileges`（DB-D12） | 恢复文档 | 恢复后实例可用（5 项冒烟） | V5：pg_dump + 恢复冒烟；计划验证（**不宣称 Audit 覆盖**） |
| §31 T07/T35 并发前提（§12.1） | 多连接写测试 | 事务提交可见性 | N/A | 真实提交 + 最终持久化断言 | V7：并发 fixture；计划验证（非业务并发用例本身） |

### 1. 验收映射（product.md 7 项 → 验证项）

执行环境：`Compose` = 干净环境 `docker compose up -d`；`真实 PG` = PostgreSQL 实例（经 Compose `db` 服务或本机 PG）；`静态` = 仓库/脚本静态检查；`文档` = 签核记录核对。

| 验收标准（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| 1. `docker compose up -d` 启动全链路；Nginx 健康检查成功；前端页面可达 | **V1** Compose 冒烟 | Compose | PASS：`docker compose up -d` 退出码 0；`db/migrate/backend/frontend/nginx` 均达到预期状态（migrate `Exited(0)`，其余 running）；`curl -fsS http://localhost/api/v1/health` = 200 且 body 含 `{"status":"ok","service":"csm-backend"}`；`/api/v1/health/ready` = 200；`curl -fsS http://localhost/` = 200 且返回前端 HTML。FAIL：任一服务未起、健康端点非 200、路由错误（`/api/*` 落到前端或 `/` 落到后端）、ready 在 DB 可达时仍非 200 |
| 2. Alembic 基线在真实 PG 建库成功并可回滚（upgrade→downgrade→再 upgrade 一致） | **V2** 迁移 up/down/up 一致性 | 真实 PG | PASS：`alembic upgrade head` 退出码 0；`alembic current` = 基线 head revision；`alembic downgrade base` 退出码 0、`alembic current` 为空且 `alembic_version` 表无行；downgrade 后 **pg_trgm 扩展仍存在**（DB-D4 非对称，不视为残留）、无业务表；再次 `upgrade head` 后 revision 与首次一致且 `pg_extension` 收敛。FAIL：任一步报错、revision 不一致、再 upgrade 后未收敛 head |
| 3. 基线迁移显式启用 pg_trgm（及 Database 选定扩展），签核记录可查 | **V3** 扩展存在断言 + **V8** 签核核对 | 真实 PG + 文档 | PASS：迁移后 `SELECT extname FROM pg_extension` **含且仅含基线声明的 `pg_trgm`**；`btree_gist` 在基线**不存在**（DB-D2，推迟 F008/F009）；扩展由基线 migration 执行（非 initdb/手工，DB-D3），其非对称 downgrade 行为由 V2/B4 佐证；签核记录（`docs/database/f001-baseline.md`）可查。FAIL：`pg_trgm` 缺失、由非迁移途径创建、基线误启 `btree_gist`、签核记录缺失 |
| （验收 3 支撑） | **V3b** 非 superuser 扩展安装验证 | 真实 PG | PASS：以**非 superuser 的数据库 owner**（拥有目标库 CREATE 权限）执行 `CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public`（或 `alembic upgrade head`）成功，证实 DB-D11 trusted 假设。FAIL/BLOCKED：权限不足安装失败——**不降低验收**，记录失败证据并转 DBA 预装扩展备选（迁移 `IF NOT EXISTS` 变 no-op），偏离记入测试报告 |
| 4. pytest 集成 fixture 可在真实 PG 建 schema、执行 Alembic、事务级清理，重复运行无残留 | **V4** fixture 可重复无残留 | 真实 PG | PASS：集成套件连续运行两次均退出码 0；两次运行前后测试库对象集合一致（除预期持久对象），无残留测试表/数据；**独立测试库**（DB-D10，非 schema 隔离）会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head` 生效；安全护栏断言库名含 `test` 且 `TEST_DATABASE_URL != DATABASE_URL`；函数级事务/savepoint 回滚不污染后续用例。FAIL：第二次运行失败、存在残留对象或跨用例污染、护栏未生效 |
| 5. 备份骨架可执行 pg_dump 并按文档恢复到可用实例（冒烟级） | **V5** 备份恢复冒烟 | 真实 PG + 脚本 | PASS（DB-D12 5 项判据）：①`deploy/backup/pg_dump.sh`（`pg_dump -Fc --no-owner --no-privileges`）退出码 0 并产出 dump；②`restore.sh` 默认恢复**全新目标库**（`--clean --if-exists` 仅显式 `--force`）退出码 0；③恢复库 `SELECT 1` 成功；④`pg_extension` 含 `pg_trgm` 且 `alembic_version` 与源库一致、`alembic current` = head 且再 upgrade 幂等；⑤后端连恢复库 `/api/v1/health/ready` 返回 200。FAIL：脚本失败、恢复报错、5 项任一不满足 |
| 6. 启动所需真实凭据经环境/密钥注入，仓库无真实凭据 | **V6** 凭据不入仓静态检查 | 静态 + Compose | PASS：`.env.example` 仅为占位符且被版本控制；`.env` 被 `.gitignore` 排除且未被 git 跟踪；仓库全文检索无真实数据库口令/令牌；启动日志与错误响应不出现连接串/密码（含 DB 不可达场景）。FAIL：仓库存在真实凭据、`.env` 被跟踪、日志或错误响应泄露敏感串 |
| 7. D02 基础部分（软件版本、目录结构、迁移基线、扩展、测试基线）由 Architect/Database 签核 | **V8** 签核记录核对 | 文档 | PASS：软件版本、目录结构、迁移基线、扩展策略、测试基线均在设计/签核文档中记录且状态明确（CONFIRMED 或有 Gate 记录）；与实现一致。FAIL：任一项无签核记录或与实现不符 |
| （验收 7 之外的并发前提） | **V7** 多连接并发提交可见性与最终持久化断言 | 真实 PG | PASS：≥2 条独立连接并发提交后，新连接可观察到已提交数据；teardown 后最终持久化状态与断言一致（无部分写入）。FAIL：提交不可见、部分变更留存 |

### 2. 边界与并发场景（TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | 迁移循环幂等 | `upgrade head` → `downgrade base` → `upgrade head` → 再 `downgrade base` → `upgrade head` | 每轮再 upgrade 后 revision 与对象集合一致；downgrade 后 `alembic_version` 为空、`pg_trgm` 仍存在（DB-D4 非对称，不计为残留）；无累积残留 |
| B2 | 迁移可重复 upgrade | 连续两次 `upgrade head` | 第二次为 no-op，退出码 0，无副作用 |
| B3 | 扩展存在断言 | 迁移后发现 `pg_extension` | 见 V3；断言 `pg_trgm` 存在，`btree_gist` 基线**不存在**（DB-D2，推迟 F008/F009） |
| B4 | 扩展回滚非对称性 | `downgrade base` 后查 `pg_extension` | 按 DB-D4：`pg_trgm` **仍存在**（不 drop）、`alembic_version` 为空；非对称有 `docs/database/f001-baseline.md` §4 文档依据 |
| B5 | 并发提交可见性 | 2+ 真实连接各自事务提交，另开新连接读取 | 新连接读到全部已提交行；未提交行不可见 |
| B6 | 最终持久化状态 | 并发写入后关闭连接、重开校验 | 持久化状态等于所有成功提交的并集，无部分/丢失写入 |
| B7 | ready 端点在 DB 不可达 | 停止 `db` 服务后请求 `/api/v1/health/ready` | 返回 503 `{"status":"not_ready","db":"down"}`；不返回 200，不泄露连接串；恢复 db 后回到 200 |
| B8 | health 不触库 | 停止 `db` 后请求 `/api/v1/health` | 仍返回 200 `{"status":"ok"}`（liveness 不依赖 DB） |
| B9 | 备份恢复冒烟（版本一致 + 可用） | 备份→恢复到全新实例→按 DB-D12 5 项判据核对 | ①`SELECT 1` 成功；②`pg_extension` 含 `pg_trgm`；③`alembic_version` 与源库一致；④`alembic current` = head 且再 upgrade 幂等；⑤`/api/v1/health/ready` = 200 |
| B10 | 凭据静态边界 | 检查 `.env.example`、`.gitignore`、`git ls-files`、仓库检索、启动/错误日志 | 见 V6；`.env` 未被跟踪 |
| B11 | 非 superuser owner 安装扩展（V3b） | 以非 superuser 数据库 owner（具目标库 CREATE 权限）执行 `alembic upgrade head`（含 `CREATE EXTENSION IF NOT EXISTS pg_trgm`） | 成功安装（DB-D11 trusted 假设成立）；失败则不降验收，记录证据并转 DBA 预装备选 |

并发说明：V7/B5/B6 仅为 **T07/T35 的测试前提**（多连接、真实提交、最终持久化断言能力），不执行任何业务并发用例（业务并发在相应 Feature 验证）。F001 无业务写路径，故不做业务级并发正确性结论。

### 3. 夹具 / 环境设计

- **测试库供给（`TEST_DATABASE_URL`）**：指向真实 PostgreSQL 的**独立专用测试库**（库名含 `test`；不指向生产/未知库，不引入 Testcontainers；DB-D10 选定独立数据库而非 schema 隔离）。默认经 Compose `db` 服务；允许通过环境变量指向本机 PostgreSQL。**安全护栏（DB-D10）**：conftest 断言库名含 `test` 且 `TEST_DATABASE_URL != DATABASE_URL`，否则中止。缺失 `TEST_DATABASE_URL` 时集成测试应 **skip 并显式告警**，不静默改用 SQLite（SQLite 不能提供约束证据）。
- **会话级 fixture**：重建 public schema（`DROP SCHEMA public CASCADE` + `CREATE SCHEMA public`）→ `alembic upgrade head` → 产出可用 engine/session。会话结束清理（DB-D10）。
- **函数级清理**：外层事务 + savepoint，用例结束回滚；普通用例不产生持久写入。
- **并发 fixture**：不套用 savepoint 外层事务；用例内使用真实连接**真实提交**；teardown 显式 `TRUNCATE` 清理（**排除 `alembic_version`**）；新开连接断言最终持久化状态。
- **SQLite 冒烟边界**：仅用于不依赖 PG 语义的纯逻辑冒烟；**不作任何约束/扩展/迁移/并发证据**。
- **备份脚本**：`deploy/backup/`（pg_dump.sh / restore.sh / README）。`pg_dump.sh` 采用 `pg_dump -Fc --no-owner --no-privileges`；`restore.sh` 默认恢复**全新目标库**，`--clean --if-exists` 仅显式 `--force` 启用（DB-D12）。当前仓库**无本机 `psql`/`pg_dump`**，故应设计为经容器执行（`docker compose exec db pg_dump` 或一次性 pg 客户端容器）；测试判据以“脚本可执行 + 恢复可用”为准，不要求宿主机安装 PG 客户端。
- **冒烟数据**：F001 无业务表，备份/恢复冒烟可断言 `alembic_version` 与扩展；不得以业务数据作为恢复判据。

**当前环境可执行性评估**：Docker 守护进程可用、`docker compose` v5.5.1 可用、Node v22、Python 3.12.x；本机无 `psql/pg_dump`。因此 Compose 路径（V1）与经容器的真实 PG 路径（V2/V3/V4/V5/V7）在实现完成后可执行；V5 依赖备份脚本采用容器内执行方式。若实现后 Compose 无法启动（镜像拉取/端口冲突），V1 记 BLOCKED 并按 §4 降级标注，不降低验收要求。

### 4. 可验证性检查与环境风险

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1 Compose 冒烟 | 本地 Docker 可用、可拉取镜像、主机端口可用 | 当前 Docker 可用，**可执行**；若镜像拉取失败或端口占用 → 相关子项 **BLOCKED** 风险 | 不降低验收；标注 BLOCKED 与原因，engine 就绪后补测。不用"各组件单独启动"替代全链路 Nginx 冒烟 |
| V2/V3/V3b/V4/V7 | 真实 PostgreSQL 实例 | 经 Compose `db` 可满足；本机无 PG 不影响；V3b 需一个非 superuser 测试角色 | 无 PG 时跳过并标 BLOCKED，**不得**用 SQLite 替代约束证据；V3b 无可用的非 superuser owner 时记 BLOCKED 并补充角色后重测 |
| V5 备份恢复 | pg_dump/restore 执行环境 + 一个可恢复的全新实例 | 宿主机无 pg_dump → **必须容器内执行**；脚本设计需支持 | 恢复用 Compose 临时实例/临时库；不要求宿主机 PG 客户端 |
| V6 凭据静态检查 | 无需运行时 | **可执行**（静态） | 无 |
| V8 签核核对 | 设计文档 | **可执行**（文档） | 依赖 DATABASE Gate 完成 |

### 5. 不适用项与边界声明

- **业务用例 T01–T41 不适用于 F001**：F001 为 ENABLER，不创建业务对象、不实现业务 API（`api_required = false`），不执行 T01–T41。整体上线验收（§32）与 T01–T41 的通过不由 F001 声明，留待承接 Feature 及其 TEST 阶段。
- **前端验收边界**：仅验证编译/构建成功、前端页面可达、SPA history fallback 与 `/api/v1` 代理路由正确；无业务交互、无状态/空/错误态业务验收（无业务页面）。F001 前端无需真实 API 集成业务用例，记 `NOT_REQUIRED`（理由：无业务页面与业务 API）。
- **Audit 备份**：T36 由 F016 以真实证据闭合；F001 仅 pg_dump 骨架 + 恢复文档 + 冒烟，不宣称 Audit 覆盖。
- **容器可启动 ≠ 生产上线验收**（§32 独立）。
- **API Contract**：F001 `api_required = false`，健康检查为运维端点，不建 `docs/api/F001.md`；待 CONTRACT Gate 记录 `NOT_REQUIRED` 与理由。
- **OPEN（交 DATABASE Gate 的复核项，TD-2 已核对定稿）**：①扩展清单——**DB-D2 定稿仅 `pg_trgm`，`btree_gist` 推迟 F008/F009**；②downgrade 对称性——**DB-D4 定稿为文档化非对称，不 drop 扩展**；③测试库与权限——**DB-D10 独立测试库 + 安全护栏，DB-D11 trusted 扩展待 V3b/B11 证实**；④备份脚本——**DB-D12 定稿参数与 5 项冒烟判据**。上述已并入 TD-2 判据；若实现或 Contract 再变更，再升版并注明失效范围。

---

## Test Execution

- **版本**：TE-1
- **日期**：2026-10-06（UTC）
- **角色**：Tester（TEST 模式）
- **实现基线**：commit `85cbfdb`（feature/F001-engineering-foundation；工作区在 `db72c19` 检查点，`git diff 85cbfdb HEAD` 仅新增文档与计划字段，无实现改动）
- **执行依据**：TD-2（本文件 Test Design）；已应用定稿采纳口径 **A1**（扩展断言忽略 PG 默认 `plpgsql`，断言 `pg_trgm` 存在、`btree_gist` 不存在）、**A3**（备份脚本容器内执行）、**A4**（备份判据 DB-D12 5 项 + 退出码）、**A5**（TD-2 为执行权威编号）
- **结论**：`READY FOR REVIEW`

### E.0 执行环境

| 项 | 值 |
| --- | --- |
| 日期 | 2026-10-06 UTC |
| 实现 commit | `85cbfdb` |
| Docker / Compose | Docker 29.8.0；Docker Compose v5.5.1 |
| PostgreSQL | 16.15（`postgres:16`） |
| Nginx | 1.27-alpine |
| Node（镜像内构建） | node:22-alpine；宿主 Node v22.23.2 |
| 宿主机 PG 客户端 | 无 `psql`/`pg_dump`（备份按 A3 容器内执行） |
| Compose 测试隔离 | 项目名 `csmf001test`，入口端口 `18080`（避免与既有容器/端口冲突） |
| 测试数据库来源 | Compose `db` 服务内独立库：`csm_owner_test`（owner `f001owner`，**非 superuser**）、`csm_manual_test`、`csm_restore_test`；均满足库名含 `test` 的 DB-D10 护栏 |
| 测试镜像 | `docker build --target test -t csm-f001-backend-test ./backend`（BUILD_EXIT=0） |
| 凭据 | 测试用 `.env`（git-ignored、测试后删除）注入，无真实凭据入库 |

### E.1 验收映射执行结果

| 验收 | 验证项 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 全链路 Compose + Nginx 健康检查 + 前端可达 | V1 | **PASS** | `docker compose -p csmf001test up -d --build` 退出码 0；`ps -a`：`migrate` Exited(0)，`db/backend/frontend/nginx` running（backend healthy）；`curl :18080/api/v1/health` = 200 `{"status":"ok","service":"csm-backend"}`；`/api/v1/health/ready` = 200 `{"status":"ready","db":"up"}`；`GET /` = 200 返回前端 HTML（`<div id="root">` + hashed asset）；`/some/deep/path` = 200 SPA fallback；`/api/v1/does-not-exist` = 404 由 backend 返回（`{"detail":"Not Found"}`，证明 `/api/*` 未落到前端） |
| 2 Alembic 基线真实 PG up/down/up 一致 | V2 | **PASS** | 非 superuser owner 库 `alembic upgrade head` 退出码 0 → `current` = `0001_baseline (head)`；`downgrade base` 退出码 0 → `alembic_version` 0 行、**`pg_trgm` 仍在**（DB-D4 非对称）、无业务表；再 `upgrade head` 收敛 `0001_baseline`；集成用例 `test_upgrade_downgrade_upgrade_is_consistent`/`test_upgrade_is_idempotent` PASS |
| 3 基线显式启用 pg_trgm + 签核可查 | V3 / V3b / V8 | **PASS** | 迁移后 `pg_extension` = `{plpgsql, pg_trgm}`，**`btree_gist` 不存在**（A1/DB-D2）；扩展由 `0001_baseline.py` 执行；**以非 superuser 数据库 owner `f001owner`（rolsuper=f, rolcreatedb=t）执行 `upgrade head` 成功安装 `pg_trgm`（V3b，DB-D11 trusted 证实）**；签核见 `docs/database/f001-baseline.md` v1、`docs/features/F001/architecture.md` 最终设计定稿 |
| 4 集成 fixture 真实 PG 可重复无残留 | V4 | **PASS** | 集成套件连续运行两次均 `10 passed`、退出码 0；两次运行后 `public` schema 无残留表（residue query: 0 rows）；会话级 `DROP SCHEMA public CASCADE`+`CREATE SCHEMA public`+`upgrade head` 生效；DB-D10 护栏**实测阻断**（见 E.2 B10） |
| 5 备份骨架 pg_dump + 恢复冒烟 | V5 | **PASS** | A3 容器内执行：`pg_dump.sh` 退出码 0 产出 custom-format dump（`PostgreSQL custom database dump`，magic `PGDMP`）；`restore.sh <dump> csm_restore_test` 退出码 0；重复目标库无 `--force` 拒绝（退出码 1），`--force` 成功；DB-D12 5 项全部满足（见 E.3） |
| 6 凭据经环境注入、仓库无真实凭据 | V6 | **PASS** | `git check-ignore -v .env` 命中 `.gitignore:13`；`git ls-files` 无 `.env`（仅 `.env.example`）；`.env.example` 仅 `__SET_ME__` 占位；跟踪文件密钥模式全文检索无命中；容器日志与 DB 不可达 503 响应均无连接串/口令（见 E.3） |
| 7 D02 基础部分签核可查 | V8 | **PASS** | `architecture.md`「最终设计定稿」（Architect 2026-10-06，`READY FOR IMPLEMENTATION`，核对 `f001-baseline.md` v1 与 TD-2）、`f001-baseline.md` Database 签核 v1（DB-D1–DB-D12 DESIGN）、`project-plan.yaml` plan_revision 4 F001 已批准；软件版本/目录结构/迁移基线/扩展策略/测试基线与实现一致 |

### E.2 边界与并发结果（B1–B11）

| 编号 | 结果 | 证据 |
| --- | --- | --- |
| B1 迁移循环幂等 | **PASS** | 手工循环 `upgrade→downgrade→upgrade` 在 `csm_manual_test` 每轮收敛 `0001_baseline`；集成 `test_upgrade_downgrade_upgrade_is_consistent` PASS |
| B2 可重复 upgrade | **PASS** | 连续 `upgrade head` 第二次 no-op，退出码 0，保持单 head `0001_baseline`；集成 `test_upgrade_is_idempotent` PASS |
| B3 扩展存在断言（A1 口径） | **PASS** | `pg_extension` 含 `pg_trgm`、不含 `btree_gist`；忽略默认 `plpgsql`；集成 `test_extension_set_matches_baseline_declaration` PASS |
| B4 扩展回滚非对称性 | **PASS** | `downgrade base` 后 `pg_trgm` 仍存在、`alembic_version` 为空、无业务表；集成两用例 PASS；有 `f001-baseline.md` §4 依据 |
| B5 并发提交可见性 | **PASS** | 集成 `test_committed_writes_visible_across_connections`（两条独立真实提交连接 → 新连接读到并集）、`test_uncommitted_write_is_not_visible` PASS |
| B6 最终持久化状态 | **PASS** | 并发写后 `engine.dispose()` 重开连接复核 count=2；`committed_engine` teardown TRUNCATE（排除 `alembic_version`）+ 删除 `_f001*` 探针表；运行后无残留 |
| B7 ready 在 DB 不可达 | **PASS** | `docker compose stop db` 后经 Nginx 请求 `/api/v1/health/ready` = **503** `{"status":"not_ready","db":"down"}`；响应无 `postgresql`/`psycopg`/口令；`start db` 恢复后 = 200 |
| B8 health 不触库 | **PASS** | DB 停止期间 `/api/v1/health` 仍 = 200 `{"status":"ok","service":"csm-backend"}` |
| B9 备份恢复冒烟 | **PASS** | 见 E.3 的 DB-D12 5 项 |
| B10 凭据静态边界 | **PASS** | `.env` 命中 ignore 且未被跟踪；`.env.example` 占位；仓库检索无真实口令；日志/错误响应不泄露。**护栏实测**：`TEST_DATABASE_URL` 指向非 test 库 `csm` → `AssertionError`（退出码 1）；`TEST_DATABASE_URL == DATABASE_URL` → `AssertionError`（退出码 1） |
| B11 非 superuser owner 安装扩展（V3b） | **PASS** | `f001owner` rolsuper=f；以该角色对 `csm_manual_test` 执行 `alembic upgrade head` 成功、`pg_trgm` 就位；集成 `test_trusted_extension_installed_by_non_superuser` 明确 **PASSED（非 skip）** |

### E.3 数据库 / 接口 / 前端 / 集成结果

- **数据库（真实 PG，非 SQLite）**：迁移 up/down/up 一致；基线扩展集合 = `{pg_trgm}`；`downgrade` 非对称；并发提交跨连接可见；teardown 无残留。SQLite 仅 `smoke` 4 passed（不作为约束/扩展/迁移/并发证据）。
- **V5 / B9 / DB-D12 5 项判据（恢复库 `csm_restore_test`）**：①`SELECT 1` → `1`；②`pg_extension` = `{pg_trgm, plpgsql}`；③`alembic_version` 源库与恢复库均 `0001_baseline`；④`alembic current` = `0001_baseline (head)` 且再 `upgrade head` 幂等（退出码 0）；⑤后端连恢复库 `/api/v1/health/ready` = 200 `{"status":"ready","db":"up"}`。`pg_dump.sh`/`restore.sh` 退出码分别为 0/0。
- **接口（健康端点为运维端点，非业务 Contract）**：`/api/v1/health` 不触库（依赖被覆盖为抛错仍 200），`/api/v1/health/ready` 就绪 200 / DB 不可达 503；DB 不可达既返回正确状态又不泄露凭据。集成 `test_health.py` 3 项 PASS。
- **前端**：镜像构建成功（多阶段 node:22 → nginx:1.27-alpine）；`GET /` = 200 返回 `index.html`；`/some/deep/path` = 200 SPA fallback；`/assets/*.js` = 200 `public, immutable`（30d），缺失 asset = 404，`/index.html` no-cache；产物 JS 引用同源相对路径 `/api/v1`；`src/api/client.ts` 无硬编码主机、无密钥。
- **集成（真实 API，非 Mock）**：Nginx 入口 → backend `/api/v1/health`、`/api/v1/health/ready` 均真实连通（200）；失败路径（DB 停）经入口仍得 503。
- **凭据边界日志核对**：backend 启动/请求日志无连接串或口令；全栈 `docker compose logs` 检索 `postgresql+psycopg|password|<test pw>` 无命中。
- **测试基础设施**：`tests/smoke` 4 passed；`tests/integration` 10 passed（含 V3b 非 skip）；安全护栏实测生效；测试 DB 独立、测试后随 `down -v` 清理。

### E.4 Defects

| ID | Severity | Layer | Location | 证据 | 期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F001-T-DUP-CT | LOW | Deploy | `deploy/nginx/nginx.conf` `location = /healthz` | `curl -D - /healthz` 返回两个 `Content-Type`（`application/octet-stream` + `text/plain`） | 期望单一 `Content-Type: text/plain`；实际重复 | 仅影响非验收要求的 `/healthz` 辅助探针；不影响验收 1 的 `/api/v1/health` | Backend | 否（可后续处理） |
| F001-T-TESTFIX-EXT | NOTE | Test Infra | `backend/tests/conftest.py` `_recreate_public_schema` | 集成运行 2 后测试库 `pg_extension` 仅剩 `plpgsql` | 测试会话 teardown `DROP SCHEMA public CASCADE` 连带删除安装于 `public` 的 `pg_trgm`；下一会话 `upgrade head` 重建。非产品缺陷（测试库按会话重建），扩展持久性由会话内断言及 V2/B1/B4 手工循环证明 | 无（测试库行为，不污染生产语义） | 协调器 / Tester（测试基础设施） | 否 |

未发现 BLOCKER / HIGH / MEDIUM 必须修复缺陷。

### E.5 未验证项

- **真实浏览器 DOM 渲染**：环境无浏览器，未执行 React 运行时渲染与页面内 `/api/v1/health` 的 DOM 断言；已以「产物 JS 引用同源 `/api/v1`」+「Nginx 入口真实连通 health 端点」佐证接线。属 TD-2 V1 判据之外的增强项，不影响 V1 PASS。
- **T01–T41 业务用例**：F001 为 ENABLER，`api_required=false`，无业务对象/业务 API；**不适用**，不声明通过（留待承接 Feature）。
- **Audit 备份覆盖（T36）**：F001 仅 pg_dump 骨架 + 恢复冒烟，**未验证 Audit 数据覆盖**（归 F016）。
- **§32 整体上线验收**：不在本 Feature；容器可启动 ≠ 生产上线。
- **F002+ 业务并发正确性、约束/索引/IPAM 锁**：V7/B5/B6 仅验证 T07/T35 的测试前提能力，非业务并发结论。

### E.6 结论

**`READY FOR REVIEW`**。product.md 7 项验收全部 PASS（V1–V8，其中验收 3 另由 V3b 佐证），边界 B1–B11 全部 PASS，无必须修复缺陷（仅 1 项 LOW、1 项 NOTE 非阻塞）。测试使用独立 Compose 项目名/端口与独立 test 库，未在未知/生产库执行；测试后已 `docker compose -p csmf001test down -v` 清理容器与数据卷并删除测试 `.env`。

> A1 修正记录：TD-2 的 V3/B3 原始文本为「含且仅含基线声明的 `pg_trgm`」。按定稿口径 A1，本次执行以「断言 `pg_trgm` 存在、`btree_gist` 不存在，忽略 PG 默认 `plpgsql`」为准（标记 **TD-2+A1**），不整体升版；其余 V/B 项按 TD-2 原文执行。

---

### Git 声明（只读，未改变 Git 状态）

```text
GIT: git rev-parse --short HEAD
GIT: git branch --show-current
GIT: git status --short
GIT: git check-ignore -v .env
GIT: git ls-files
GIT: git ls-files .env
GIT: git grep -nIE <secret-pattern> -- <paths>
GIT: git log --oneline -8
GIT: git show --stat 85cbfdb
GIT: git diff --stat 85cbfdb HEAD
```