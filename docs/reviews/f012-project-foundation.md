# Review Report — F012 项目基础框架与运行环境

> Review Status: `APPROVED WITH FOLLOW-UP`
> Author Role: reviewer
> Date: 2026-09-15
> Feature: F012（ENABLER，E07，P0）
> Reviewed Branch: `feature/F012-project-foundation`
> Base（develop）: `2c2a7531fa1dfe9e9f6205ff49a15c7cadcd01da`
> Candidate HEAD: `966d56a480bd2d8282009c7969f5ac3b7bee3aca`
> Merge Commit: `3b8646c7e78b7d86fc813fe3661b3214c57a9e9a`

---

## Feature

F012 — 项目基础框架与运行环境（ENABLER，E07，P0）。

## Scope Reviewed

- **Feature Branch**: `feature/F012-project-foundation`
- **Base (develop)**: `2c2a7531fa1dfe9e9f6205ff49a15c7cadcd01da`
- **Candidate HEAD**: `966d56a480bd2d8282009c7969f5ac3b7bee3aca`
- **merge-base**: `2c2a753…`（= Base；线性历史，无分叉）
- **Feature commits**: `7c93657` docs(start) → `16e79d6`/`e93f69d` docs(req/arch) → `9764326` impl → `dff6536` chore → `dbff989` test → `966d56a` chore
- **Working tree**: clean；`git ls-files --others --exclude-standard` 为空。交付物均已提交，满足正式 Review 前提。
- **单独审查**: 完整分支 diff（77 文件 / +6999 行）逐文件阅读，而非仅未提交改动。
- **测试证据（Reviewer 独立重跑）**:
  - 启动真实 PostgreSQL 16（pgserver，`zh_CN.UTF-8` / UTF8，`('cluster-a'='Cluster-A')=false`）
  - `CSM_TEST_DATABASE_URL=… pytest -q` → **38 passed**（无 skip）
  - `.venv/bin/ruff check backend tests` → All checks passed；`ruff format --check` → 40 files already formatted
  - `cd frontend && npm run typecheck` → 0；`npm run test` → **32 passed (5 files)**；`npm run build` → 成功
  - `alembic check` → No new upgrade operations detected
  - 独立 DB 断言：`id` = `is_identity=YES / ALWAYS`；`ux_clusters_name_active` = `UNIQUE (name) WHERE (deleted_at IS NULL)`；`ck_clusters_name_no_slash` = `CHECK ((strpos(name,'/')=0))`；仅 `alembic_version` + `clusters`
  - 独立对抗性结构 guard 注入（`resources` 表 / JSON 列 / 多态 mapper / EAV 形态）→ guard **全部真实失败**，非空转
  - 独立 HTTP 探针（真实 DB）：`POST /api/health`→405、未知路由→404、`{}`/类型错→400+`field=name`、`23505`→409 CONFLICT+`field=name`、`23514`→400+`field=name`、`page=0`/`page_size=abc`→400+正确 field、`/_foundation/error`→500 信封
- **未审查**: 浏览器级 E2E、F015 生产部署、23502/23503 经 API 的端到端路径（实测不可达）。

## Product Compliance

| AC | 判定 | 依据 |
|---|---|---|
| AC-01 可运行骨架与文档 | **满足（计时未独立验证）** | README §3.1–3.7 + `frontend/README.md` + `.env.example` + `Makefile` + `docker-compose.dev.yml` 齐全且步骤自洽。30 分钟 pristine-checkout 计时无法在当前环境验证，属 Unverified。 |
| AC-02 健康检查 200 | **满足** | 真实连接 `GET /api/health`→200 `{"status":"ok","database":"ok"}`；DB 不可达→500 信封。 |
| AC-03 显式资源建模 | **满足** | `Base.metadata.tables == {"clusters"}`；迁移后表集合白名单；guard 对 4 类违规注入均真实失败。 |
| AC-04 冲突保存前阻止（不依赖 UI） | **满足** | 原始 psycopg 直连：活跃重名→`23505`；含 `/`→`23514`；NULL name→`23502`。 |
| AC-05 大小写敏感在数据层成立 | **满足** | `cluster-a` 与 `Cluster-A` 共存；`('cluster-a'='Cluster-A')=false`；第二活跃同名→`23505`。 |
| AC-06 错误可见字段与原因 | **满足** | 所有 400 均含 `error.code=VALIDATION_ERROR` 且 `details[].field` 正确（name/page/page_size）；23505→409 `CONFLICT`+`field=name`。 |
| AC-07 中文往返 | **满足** | DB 与 HTTP 双侧写入/读出/等值命中一致；`encoding=UTF8`。 |
| AC-08 基座可复用、契约单一权威 | **满足（复用待后续验证）** | 信封仅由 `common/errors.error_envelope` 构造；分页/pagination、active 过滤、SQLSTATE 映射均单点实现，无第二套约定。多 Feature 真实复用只能待 F001+。 |
| AC-09 不承载资源业务规则 | **满足** | 逐文件确认见下。 |

**AC-09 专项确认（无领域规则混入）**：`grep` 全量核实 `by-name`/`by_name`/`RUNNING`/`READY`/`ACTIVE`/`IDLE`/`validate_name`/`lower(` 在 `backend/`、`frontend/src/`、`tests/` 中**无任何领域实现**；`/_foundation` 路由**无** `/` 预检、无唯一性预检、无状态、无父删子拦、无 `by-name`（`foundation/router.py:41-90`）；`clusters` 的 `ck_clusters_name_no_slash` 是 Database Handoff 明确分配给 F012 基线的 DB 约束（`docs/database/f012-baseline-migration.md` §2），非 API 层领域校验。ORM 模型 `Cluster` 仅含 `id/name/created_at/updated_at/deleted_at`，与数据库设计逐列一致。`foundation/repository.soft_delete` 明确标注为 fixture-only，不是 F014 领域服务。

## Architecture Compliance

- **无通用表 / EAV / STI / 多态 / JSONB**：结构 guard（`tests/test_structure_guard.py`）直接检查 `Base.metadata`，Reviewer 独立注入违规结构验证其**真实失败**；`test_only_expected_tables_registered` 用白名单断言兜底。**guard 有效，非空转。**
- **`0001_f012_baseline` 严格符合数据库设计**：`sa.Identity(always=True)`✓；partial unique index 显式 `postgresql_where=sa.text("deleted_at IS NULL")`✓；`NAMING_CONVENTION` 与 DB Handoff §5.2 逐字一致✓；无 `COLLATE`✓；无 extension✓；无触发器✓；`updated_at` 由应用层维护✓；`server_default=sa.text("now()")`+`TIMESTAMPTZ`✓。`downgrade` 顺序正确。
- **F012 机制 / F014 语义边界**：`db/active.py` 只提供 `active_filter`/`select_active` **原语**，未实现统一软删除领域服务、父删子拦或并发加锁，边界正确。
- **无 F013 越界**：无 `add_middleware`、无 `current_user` 桩、无 `users`/`sessions` 表、无认证/会话/口令代码（grep 仅命中前端预留分支与错误码枚举）。符合 Architecture Handoff Q6「不引入占位用户 / current_user 桩」。
- **无未批准框架/中间件**：依赖仅 fastapi/uvicorn/pydantic(+settings)/sqlalchemy/alembic/psycopg 与 vue/element-plus/vite/vitest 等，均在 ADR-0001 栈内。
- **UNCONFIRMED 关系未固化**：未创建 `virtual_machines`/`containers`/`services` 表或任何承载/关系列。
- **文档同步**：`docs/architecture/csm-v1-foundation-architecture.md` 的「显式 collation」措辞更新为 ADR-0002 裁定的「默认 collation、不写 COLLATE」——属单一权威源的正当同步，非 scope creep。

## Database Review

Schema 与 `docs/database/csm-v1-schema-design.md`、`f012-baseline-migration.md` §4 逐项一致（在真实库独立查询确认）：列类型 / NULL 约束 / PK 名 / CHECK / partial unique index predicate / identity ALWAYS / 无 collation。Migration 与 ORM 无 drift（`alembic check` 无输出）。Migration 仅含当前设计，未提前建 F001~F015 的表。`downgrade` 破坏性属既定设计（生产禁用，已文档化）。无逻辑删除误导：partial predicate 与查询过滤基座语义一致。

## Backend Review

分层清晰：HTTP（`api/`/`foundation/router`）→ schema 校验 → fixture/领域访问（`foundation/repository`）→ DB（`db/`）。`common/` 只放横切关注点（errors/error_handlers/sqlstate/pagination）。事务边界由 `deps.get_db_session` 单点提供（成功 commit、异常 rollback）。SQLSTATE→HTTP 映射为单一实现，未识别 SQLSTATE 走 500 信封。错误处理**所有路径结构一致**（实测 400/404/405/409/500 均为 `{"error":{code,message,details}}`）。`deleted_at` 不出现在任何对外 schema。无 SQL 注入面（无拼接 SQL，均为参数化/ORM）。

## Frontend Review

严格使用契约：`http.ts` 统一解析信封，`ApiError` 保留 `code`/`details`，未知后端 code 原样保留不改写。`ErrorState` 分支**仅**由 `props.error.code` 驱动（源码 switch + 测试「同 message 不同 code→不同标题」佐证），`message` 仅展示。`ListStates` 三态互斥，Error 优先于 Empty；404 `NOT_FOUND` 与 Empty 渲染不同文案。Empty 与 Not Found 为不同状态。未偷偷增加 CRUD；仅调用契约 §4 的自检端点；`useAsyncQuery` 无额外状态库。未引入不必要依赖。

## Test Review

- **T1~T14 均有对应测试**：T1 `test_migrations`、T2 `test_schema`、T3–T6 `test_constraints`、T7 `test_unicode`+`test_foundation_roundtrip`、T8 `test_error_envelope`、T9 `test_foundation_roundtrip`、T10 `test_structure_guard`、T11 `test_lint`、T12 前端 5 个 spec、T13 `test_foundation_isolation`、T14 `test_health`。
- **测试会真实失败**：独立注入违规结构证明 guard 非恒真；DB 约束测试用原始 psycopg 绕应用层，测的是数据库而非应用；缺 DSN 时明确 `pytest.skip`，不伪造通过。
- **测试未迎合实现**：断言直接来自契约（字段集合、状态码、predicate 文本、白名单表集合）。
- 唯一弱点：`tests/test_lint.py::test_database_constraint_assertions_exist` 仅文本 grep `23505`/`23514`，无 DSN 时 T11 的「真实数据库断言」实际被 skip 而该 meta-test 仍通过 → 见 N-01。不影响本次结论，因已在真实库重跑全部 38 项。

## Findings

### MEDIUM

```
F-03  ⚠ 升级：CSM_ENVIRONMENT 未设置时自检面 fail-open 可达
Severity:  MEDIUM（Tester 原评 LOW，Reviewer 上调）
Layer:     Backend / 配置默认值 + Architecture 默认策略
Location:  backend/app/config.py:27,39-45；backend/app/main.py:43-44
Problem:   environment 默认 "dev"，foundation_enabled 因此默认 True。生产部署若遗漏
           CSM_ENVIRONMENT=prod，/_foundation/* 将以 dev 语义挂载。
Evidence:  不设置环境变量启动 → GET /_foundation/clusters 可达（200 而非 404）；
           该面提供对 clusters 载体表的未认证写端点（POST/PATCH/DELETE）。
           该面刻意位于 /api 之外，F013 的 /api/* 认证不会覆盖它（契约 §6）。
           prod 显式配置时实测 12 条请求全部 404（正确）。
Impact:    纵深防御缺口：单个漏配的环境变量即可让未认证写面在生产可达。
           架构 REQUIRED「不得让非产品自检面在生产可达」在字面上仅以"生产配置"为条件，
           实现与契约字面一致，故非契约违约，但属真实部署风险。
Expected:  fail-closed 默认（未显式设 dev/test 时不挂载），或引入显式
           CSM_FOUNDATION_ENABLED 开关；至少 F015 必须强制显式 prod 并加部署断言。
Owner:     Architect（默认策略裁定）/ Backend（实现）/ F015（部署强制）
处置:      非阻塞 F012 merge；作为 F015 的进入条件记录。
```

### LOW

```
F-01  未映射状态码统一标为 INTERNAL_ERROR（与 Tester 一致，确认）
Layer: Backend / 错误语义
Location: backend/app/common/error_handlers.py:20-27,61-64
Evidence: POST /api/health → 405 {"error":{"code":"INTERNAL_ERROR","message":"Method Not Allowed"}}；
          前端 ErrorState 会渲染为「服务器内部错误」，语义误导。
Impact: 仅畸形请求；契约 §6 未定义 405，故非契约违约。
Expected: 未映射的 4xx 应给客户端错误码（如通用 CLIENT_ERROR / VALIDATION_ERROR），
          不落入 INTERNAL_ERROR。
Owner: Backend
```

```
F-02  FK 违规字段回退解析截断多词列名（与 Tester 一致，确认）
Layer: Backend / 错误语义
Location: backend/app/common/sqlstate.py:84-99（_field_from_constraint_name 返回 tokens[0]）
Evidence: 约束 …_cluster_id_fkey / fk_…_cluster_id 在表不在 metadata 时回退得 field="cluster"（实际 cluster_id）。
Impact: F012 无 FK 表、API 不可达；对 F002/F004/F005 是潜在风险。真实场景通常先命中
        _field_from_metadata 可得到 cluster_id，故影响有限。
Expected: 回退返回完整列名或使用 diag.column_name 优先。
Owner: Backend
```

```
D-01  Test Report 的 F-04 与 Candidate HEAD 不符（文档陈旧）
Layer: Documentation / Test Handoff
Evidence: 报告将 F-04 列为现存 LOW 缺陷，但该问题已在同批提交 dbff989 修复。
处置: ✅ 已在合并后的状态提交中修正（F-04 标记 RESOLVED，保留原文供追溯）。
```

```
D-02  README §8 FAQ 仍提及已移除的 DSN 回退
Layer: Documentation
Evidence: 文案写「未设置 CSM_TEST_DATABASE_URL（或 CSM_DATABASE_URL）」，与 helpers.get_dsn() 相反。
处置: ✅ 已在合并后的状态提交中修正。
```

```
D-03  project-plan.yaml 的 head_commit 未更新
Layer: Project metadata
Evidence: head_commit 仍为 start_commit 2c2a753…，而候选 HEAD 为 966d56a…。
处置: ✅ 已在合并后的状态提交中填入 head_commit = 966d56a 与 merge_commit = 3b8646c。
```

### NOTE

```
N-01  T11 的 lint 门禁较弱
Location: tests/test_lint.py:26-31
说明: 该测试仅文本 grep test_constraints.py 是否含 "23505"/"23514"。无 DSN 时真正断言
      数据库约束的用例被 skip，而该 meta-test 仍通过。建议直接标记/收集 DB 用例，
      而非 grep 源码；不阻塞本次。
```

## Existing Defects（对 Tester 4 项 finding 的独立复核）

| Tester | Reviewer 评级 | 复核结论 |
|---|---|---|
| F-01 405→INTERNAL_ERROR | **LOW（同意）** | 复现并确认；结构一致，仅语义错配；契约未定义 405，故 LOW。 |
| F-02 FK field 截断 | **LOW（同意）** | F012 无 FK 表、API 不可达；对后续 Feature 是潜在风险，非当前缺陷。 |
| F-03 fail-open | **MEDIUM（上调）** | 不同意 LOW。该面是**未认证写入口**且位于 `/api` 认证范围之外，漏配单个环境变量即在生产可达，属纵深防御缺口；架构 REQUIRED 的意图是「生产不可达」。非契约字面违约，故不阻塞 F012 merge，但应在 F015 前解决。**不需要用户/产品决策**——这是工程硬化取舍。 |
| F-04 测试夹具破坏性 reset | **已解决（报告陈旧）** | HEAD 代码已移除 DSN 回退并加 `assert_safe_to_reset` → D-01。 |

## Non-blocking Follow-ups

1. **解决 F-03**（fail-closed 或显式启用开关；F015 强制 `CSM_ENVIRONMENT=prod` + 部署断言）。**已记为 F015 进入条件。**
2. 修复 F-01（未知 4xx 的兜底 code）。
3. 修复 F-02（FK 回退解析完整列名）。
4. ✅ 更正 Test Report 的 F-04 状态（D-01）。
5. ✅ 更正 README §8（D-02）。
6. ✅ 更新 project-plan 的 `head_commit`（D-03）。
7. （N-01）强化 T11 门禁，使无 DSN 时不被 meta-test 掩盖。

## Unreviewed Areas

- AC-01「30 分钟」pristine-checkout 计时（无干净机器）。
- 浏览器级 E2E / 视觉；生产构建产物在 nginx 下部署（属 F015）。
- 23502/23503 经 API 的端到端路径（F012 不可达，仅映射函数级覆盖）。
- 多资源 Feature 对基座的真实复用（待 F001+）。
- 真实内网虚拟机 + Internal IP + HTTP 部署形态（属 F015）。

## Review Verdict

不存在 BLOCKER / HIGH；不存在必须在本 Feature 修复的 MEDIUM（F-03 为非阻塞 MEDIUM，属 F015 部署前硬化）；AC-01~AC-09 核心验收满足（AC-01 计时为 Unverified）；测试可信且在真实数据库独立重跑；实现未超范围、未越界 F001/F013/F014。

**`APPROVED WITH FOLLOW-UP`**