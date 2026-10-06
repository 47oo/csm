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

> 状态：**未执行**（TEST_DESIGN 阶段，实现尚不存在）。以下为 TEST 阶段预留结构，执行时在同一文件追加，并标注执行版本、实现 commit 与 Test Design 引用版本（TD-2）。

### E.0 执行环境

- 待填：日期、实现 commit、Compose 镜像版本、PostgreSQL 版本、`TEST_DATABASE_URL` 来源、Docker 版本。

### E.1 验收映射执行结果

| 验收 | 验证项 | 结果（PASS/FAIL/BLOCKED/NOT TESTED） | 证据 |
| --- | --- | --- | --- |
| 1 | V1 | 待执行 | |
| 2 | V2 | 待执行 | |
| 3 | V3 / V3b | 待执行 | |
| 4 | V4 | 待执行 | |
| 5 | V5 | 待执行 | |
| 6 | V6 | 待执行 | |
| 7 | V8 | 待执行 | |

### E.2 边界与并发结果（B1–B11）

待执行。

### E.3 数据库 / 接口 / 前端 / 集成结果

待执行。

### E.4 Defects

待填（格式：ID、Severity、Layer、Location、证据、期望与实际、影响、Owner、是否必须修复）。

### E.5 未验证项

待填。

### E.6 结论

待填（`READY FOR REVIEW` / `RETURN TO IMPLEMENTATION` / `TEST BLOCKED` / `PARTIAL TEST ONLY`）。