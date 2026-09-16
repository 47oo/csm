# Review Report — F002 BareMetal 登记与管理

> Reviewer Role: reviewer（独立审查）
> Date: 2026-09-17
> Feature: F002（E01，P0，`depends_on: [F001]`）
> Feature Branch: `feature/F002-bare-metal`
> Base Branch: `develop` @ `c8e5d910b057f96cc4864959ac802d15b75abc67`
> start_commit: `c8e5d910b057f96cc4864959ac802d15b75abc67`
> 已审查 HEAD: `03bae260a7aff5a720c14c46441b4049d77137d0`
> merge-base(develop, HEAD): `c8e5d910b057f96cc4864959ac802d15b75abc67`（与 start_commit、base 一致，祖先关系成立）
> Test Report: `docs/test-reports/f002-bare-metal.md`（`READY FOR REVIEW`）

## Feature

BareMetal 登记与管理（F002）— CSM V1 唯一有状态资源（物理服务器 / 计算节点）的登记、查询、
状态人工维护、R-BM-007 硬件字段维护与逻辑删除，并承接 R-CLUSTER-004 的 N:1 方向、F014
「父删子拦」真实业务端到端与创建侧 `FOR SHARE` 并发协议。

## Review Status

**APPROVED WITH FOLLOW-UP**

可进入 Merge Gate。不存在 BLOCKER / HIGH / 需在当前 Feature 修复的 MEDIUM；核心验收标准
AC-01 ~ AC-30 满足；测试可信且经 Reviewer 独立复跑；实现未超范围。仅存 LOW / NOTE 级
Follow-up（见 Findings）。

## Scope Reviewed

**独立复现的 Git 证据**

```text
git branch --show-current            → feature/F002-bare-metal
git status --short                   → （空；工作区 clean）
git rev-parse HEAD                   → 03bae260a7aff5a720c14c46441b4049d77137d0
git rev-parse develop                → c8e5d910b057f96cc4864959ac802d15b75abc67
git merge-base develop HEAD          → c8e5d910b057f96cc4864959ac802d15b75abc67
git merge-base --is-ancestor c8e5d91 HEAD → 祖先成立
git diff --cached --stat             → （空）
git ls-files --others --exclude-standard → （空）
git log --oneline develop..HEAD      → 7 提交（fe58cd3 需求 → 5400986 架构/契约 → 614cbac 数据库 →
                                       d964263 实现 → 861d067 检查点 → 03bae26 测试）
git diff --stat develop...HEAD       → 49 files, +7443 / -194
```

候选实现与测试均已提交（`d964263` 实现、`03bae26` 测试），Test Report 与 Test Handoff 就绪，
满足正式 Review 的 Gate 前提，非 PARTIAL REVIEW。

**实际检查范围**

- 完整分支差异 `git diff develop...HEAD`：迁移、Backend、API 契约、Frontend、测试、文档、配置。
- `backend/app/bare_metals/**`、`backend/app/models/bare_metal.py`、`backend/app/clusters/deletion.py`、
  `backend/app/main.py`、`backend/app/models/__init__.py`。
- `backend/migrations/versions/0003_f002_bare_metals.py`（并核对 `0001` / `0002` 未改）。
- `docs/api/f002-bare-metal.md`、`docs/architecture/f002-bare-metal-handoff.md`、
  `docs/database/f002-bare-metal-migration.md`、`docs/product/handoffs/f002-bare-metal.md`。
- `frontend/src/**`（api / pages / components / composables / App.vue）与 `frontend/tests/**`、
  `frontend/vite.config.ts`。
- `tests/**`（API、并发、guard、database constraint / schema guard）与既有 guard 的演进。

**独立复跑的测试证据（Reviewer 亲执行，非引用 Tester 结论）**

```text
# 自建全新 PostgreSQL 16 实例（pgserver，/tmp/rev-f002-pg）与全新库 csm_rev
CSM_TEST_DATABASE_URL=.../csm_rev pytest -q
  → 279 passed, 2 warnings in 199.44s（无 skipped）

F002 专项子集（api + guards + concurrency + db constraints + db schema guard +
deletion_schema_guard + deletion_guards）
  → 96 passed, 2 warnings in 87.54s

cd frontend && npm run test
  → Test Files 15 passed (15)，Tests 171 passed (171)
```

**未审查内容**：见 Unreviewed Areas。

## Product Compliance

对照 `docs/product/handoffs/f002-bare-metal.md` 的 AC-01 ~ AC-30：

- **登记 / 查询 / 状态 / 硬件字段 / 逻辑删除**：5 端点与契约一致；创建 `201` 字段集合恰为
  13 字段、无 `deleted_at`、无位置 / 上级字段（AC-01）；`hostname` / `cluster_id` 必填
  （AC-02/03）；同 Cluster 唯一、大小写敏感、跨 Cluster 可重（AC-04/05/06，应用预检 + partial
  unique 双保险）；默认 `IDLE`、状态封闭集合、`UNKNOWN` 可写、无 NULL 路径（AC-07/10/11）；
  七硬件字段可空且返回 `null` 不省略（AC-08）；中文往返（AC-09）；列表 Empty、详情 Not Found、
  按 Cluster Empty vs Not Found 可区分（AC-13/14/15）；软删过滤与释放唯一性（AC-17/19）。
- **范围控制**：未实现全局 `by-name`、未注册 NIC/IP/VM/Container/Service 端点、无 Cluster 视角
  专用别名、无 Rack / 位置 / 自动发现、无恢复 / 批量 / `include_deleted`（AC-21/28/29 由负向
  路由与 schema 断言固定）。未越过 F002 范围。
- **F014 端到端真实落地（非空检查点）**：`app/bare_metals/deletion.has_active_bare_metals` 由
  `app/clusters/deletion.CLUSTER_ACTIVE_CHILD_CHECKS = (has_active_bare_metals,)` 注入，并被
  `app/clusters/service.delete_cluster` 真实传入 `soft_delete()`；Cluster 有活跃 BareMetal →
  `DELETE /api/clusters/{id}` → `409 CONFLICT` + `ACTIVE_CHILDREN_EXIST` 且无部分写入
  （AC-23）；软删后可删（AC-24）；并发孤立记录不变式 = 0 行（AC-25）；创建侧 `FOR SHARE`
  锁序（AC-26）；`CLUSTER_ACTIVE_CHILD_CHECKS` 非空断言（AC-27，F014 NOTE-01 收口）。
- **R-BM-007**：七个硬件字段可选、纯文本、允许 NULL、`serial_number` 不唯一；未引入任何自动发现 /
  外部同步。

结论：满足已确认产品需求，未发现 Scope Creep（唯一未确认子行为见 REV-3，为已显式登记的
PROPOSED，非范围外能力）。

## Architecture Compliance

- 5 端点集合、路径（`/api/bare-metals` 与 `{bare_metal_id}`）、状态码与契约 `docs/api/f002-bare-metal.md`
  一致；路径参数名 `bare_metal_id` 对齐 `{resource_id}` 约定；无 `by-name` 写 / 读别名。
- 资源表示字段集合封闭，`deleted_at` 不对外暴露；可选字段空值返回 `null` 不省略。
- `?cluster_id=` 语义：非整数 → `400 VALIDATION_ERROR`（field=`cluster_id`）；父不存在 / 已删 →
  `404 NOT_FOUND`（`details == []`）；父存在但无活跃子 → `200` + `items == []`；Empty 与
  Not Found 可区分，符合 R-QUERY-004 / api-conventions §7。
- 创建在**同一事务内**对父 Cluster 行 `SELECT ... WHERE deleted_at IS NULL FOR SHARE` 并确认活跃
  （`with_for_update(read=True)`），未命中 → `404`；与 F014 的 `FOR UPDATE` + 活跃子检查锁序一致，
  两种交错均不产生「父已删 + 子活跃」（AC-25/26 以真实行锁验证）。
- 唯一软删写入路径保持恰 1 条（`app/deletion/service.py`）；BareMetal 删除显式传入
  `BARE_METAL_ACTIVE_CHILD_CHECKS`（当前显式空元组），不假定「无子资源」。
- 未新增框架 / 依赖；未使用 EAV / 通用表 / STI / 多态 / JSONB；未改 `docs/api/f001-cluster.md` /
  `f014-soft-delete.md` / `api-conventions.md` 正文。
- 无循环导入：`app.clusters.deletion → app.bare_metals.deletion → app.models.*`。

## Database Review

- `0003_f002_bare_metals` 与 `docs/database/f002-bare-metal-migration.md` 逐项一致：
  **14 列**（含 R-BM-007 七列 `TEXT NULL`）、`pk_bare_metals`、
  `fk_bare_metals_cluster`（`ON DELETE RESTRICT ON UPDATE RESTRICT`）、
  `ck_bare_metals_status`（四值封闭集合）、
  `ux_bare_metals_cluster_hostname_active`（partial unique，predicate `deleted_at IS NULL`）、
  `ix_bare_metals_cluster_id`。
- **未改基线**：`0001` / `0002` diff 为空；仅新增 `0003`，`down_revision = 0002_f013_auth`（单一线性 head）。
- **无 CASCADE / 触发器 / COLLATE**；所有列 `collation_name IS NULL`；全库 `confdeltype='c'` 计数 0。
- `serial_number` 不唯一（业务唯一索引恰为 hostname partial）；`hostname` 无长度 / trim / 空串 /
  字符 / `/` CHECK（未定义约束「不实现」以可失败 guard 固定）。
- ORM 模型与 migration 无 drift（`alembic check` 无新操作；`downgrade base && upgrade head` 可重建）。
- 约束行为经绕应用层直连验证：大小写敏感唯一 `23505`、软删释放、`status` `NOT NULL DEFAULT 'IDLE'`、
  `UNKNOWN` 可写、`NULL` → `23502`、非法 → `23514`、无效 FK → `23503`、父有子物理删除 → `23503`。

## Backend Review

- API 层职责清晰：Router 仅做依赖注入 / 序列化 / 状态码；Service 承载业务行为；Repository 负责数据访问。
- 读取路径（`get_active` / `active_hostname_exists` / `list_active` / `has_active_bare_metals`）
  一律经 `app/db/active.py` 的 `active_filter` / `select_active`，无第二份 `deleted_at.is_(None)` 谓词。
- 状态校验为**唯一一份**实现（`app/bare_metals/validation.validate_status`），POST / PATCH 共用；
  非法值 → `400 VALIDATION_ERROR` + `details[].field="status"`；`23514` 经既有映射 → `400`（非 500）。
- `PATCH` 仅接受 `status` + 七硬件字段，`extra="forbid"`（`hostname` / `cluster_id` / `id` /
  `deleted_at` → `400`）；空 body → `400`；显式 `null` 硬件字段清空；未提供字段保持不变。
- 错误语义分层正确：字段格式错误 → `400`；父 / 目标不存在或已删 → `404`；唯一性冲突 → `409`
  （含稳定 `details[].field="hostname"`、`details[].code="DUPLICATE"`）；未出现 5xx 误映射。
- 无写副作用：`GET` 路径不写 `deleted_at`、不修改行（集成复核断言前后 `status` / `updated_at` 不变）。
- `delete_bare_metal` 委托唯一 `soft_delete()`，显式传入声明检查；无第二条 `deleted_at` 写入路径。

## Frontend Review

- 严格使用 API 契约：字段集合封闭、`status` 原始值展示、硬件 `null` → 「—」、时间为不透明字符串、
  `hostname` 原样展示（不 trim / 不归一化 / 不假设非空）。
- 三态互不相同：列表 `loading / empty / error / content`（`ListStates`）；详情 `loading /
  not-found / error / content`（`data-state`）。
- **Empty 与 Not Found 可区分**：Cluster 存在但无活跃 → `200 + items==[]` 文案「该集群暂无裸金属」；
  父 Cluster / 目标 404 → `ErrorState` 的 `NOT_FOUND` 分支「未找到资源 ... 已被删除」，与 Empty 文本 / 状态均不同。
- 错误按 `error.code`（必要时 `details[].code`）分支渲染固定文案；组件测试以「与展示无关」的
  `message` 证明前端**不解析 message**；`UNAUTHENTICATED` 交由既有全局会话失效处理。
- **未在前端重复实现业务守卫**：同 Cluster `hostname` 唯一、父存在性、状态封闭集合、删除守卫全部
  由后端裁决；删除入口不禁用 / 不隐藏所有行；重复 hostname 与空 hostname 仍提交。
- 删除 / 修改失败按 `409` / `404` / `401` 分别处理；提交中 Loading 且防重复提交；`hostname` /
  `cluster_id` 无编辑输入（不在 PATCH 可变集内）。
- 无新增不必要依赖；复用既有 `http.ts` / `useAsyncQuery` / `ListStates` / `ErrorState`。

## Test Review

- **覆盖 AC**：T-01 ~ T-29、G-1 ~ G-7、T-FE-01 全覆盖 AC-01 ~ AC-30；无 FAIL / BLOCKED / NOT TESTED。
- **数据库侧由数据库保证，非应用逻辑**：约束 / 唯一性 / NULL / FK 均以绕应用层原始 psycopg 断言
  （`test_bare_metals_constraints.py` / `test_bare_metals_schema_guard.py`），并直连 `information_schema` /
  `pg_constraint` / `pg_indexes` 核验结构。
- **真实并发**：T-25（两种交错不变式 0 行）、T-26（`FOR SHARE` 阻塞与 `FOR UPDATE NOWAIT` 持锁断言）
  以真实 PostgreSQL 行锁驱动，非 mock。
- **guard 真实可失败**：Tester 对抗注入（清空 `CLUSTER_ACTIVE_CHILD_CHECKS` → T-27 FAILED；新增写
  `deleted_at` 文件 → G-4 allow-list FAILED）并逐字节还原——Reviewer 复核 guard 源码为可失败断言
  （非恒真），且 G-3 allow-list 恰为 `{backend/app/deletion/service.py}`。
- **既有 guard 演进而非削弱**：`test_migrations` / `test_schema.EXPECTED_TABLES` /
  `tests/database/helpers.MIGRATION_HEAD` / `test_structure_guard.test_only_expected_tables_registered`
  由 3 表演进为 4 表、head `0002`→`0003`；`test_auth_guards.EXPECTED_GET_ROUTES` 增加两个
  bare-metals GET 路由；`test_deletion_schema_guard` / `test_deletion_guards` 原样保留。无测试被删除后不补。
- **无迎合实现**：断言基于契约字段集合 / 状态码 / 稳定 code，而非实现内部结构；前端测试以真实
  HTTP 响应体构造。
- Reviewer 独立复跑 279 / 96 / 171 全绿，与 Tester 报告一致。

## Findings

### REV-1

Severity: **LOW**

Layer: **Git / Project Metadata**

Location: `docs/project/project-plan.yaml > features[F002].git.head_commit`

Problem: 计划记录的 `head_commit` 为 `d964263908784ab905eaa12746a473292e0f368c`（实现提交），
而候选 HEAD / 分支最新提交为 `03bae260a7aff5a720c14c46441b4049d77137d0`（测试提交 `03bae26`）。
计划元数据与分支真实 HEAD 不一致。

Evidence: `git log --oneline develop..HEAD` 末位为 `03bae26 test(F002): add acceptance and concurrency coverage`；
`docs/project/project-plan.yaml` 经 `861d067` 检查点写入的 `head_commit` 仍停留在 `d964263`。

Impact: 不改变任何产品 / 契约 / 运行时行为；仅影响计划元数据可追溯性（与 F012 D-03、F014 REV-02 同类）。

Expected: Review/Merge 前由协调器把 `head_commit` 更新为评审时的真实 HEAD，或在 DONE 时统一回填。

Suggested Owner: 协调器（Coordinator）

### REV-2

Severity: **LOW**

Layer: **Test Infra**

Location: `frontend/tests/appAuth.spec.ts`（全局 401 用例，`vi.waitFor` 默认 1000ms）；
`frontend/vite.config.ts`（新增 `maxWorkers: 4` / `fsModuleCache: true`）

Problem: Tester 报告的既有前端用例在并行全量运行下偶发超时（F002-T-01）。该用例属 F013 既有
资产，与 F002 业务实现无关；`vite.config.ts` 以限制 worker 并发与持久化模块缓存的全局手段缓解。

Evidence: Test Report §9 记录首次全量 `1 failed | 170 passed`，隔离运行与后续两次全量重跑均通过；
Reviewer 本次全量前端 `171 passed`（15 文件）。`fsModuleCache` / `maxWorkers` 均为 Vitest 5 合法配置项
（`node_modules/vitest/dist/chunks/config.d.CU_b-wJj.d.ts`）。

Impact: 纯测试时序抖动，不削弱任何 AC 结论，不影响运行时行为；但全局并发下调属「以配置换稳定」，
无法从单次运行证明其根因消除。

Expected: 保持为 Test Infra Follow-up：优先定位 `vi.waitFor` 时序或对失败用例单独放宽超时，并观察多次
全量运行确认稳定；`maxWorkers` 全局限制若影响整体测试时长可后续回收。

Suggested Owner: 协调器 / Test Infra

### REV-3

Severity: **NOTE**

Layer: **Product**

Location: `backend/app/bare_metals/schemas.py`（`BareMetalCreate.status` 可选）；
`docs/api/f002-bare-metal.md` §3.1

Problem: `POST /api/bare-metals` 接受可选 `status`（缺省仍为 `IDLE`）。产品侧对应的 NQ-3 /
PROPOSED-2 尚未由用户最终裁定，Architecture PROPOSED 7 选择了「允许显式指定」。

Evidence: Product Handoff 假设 4 与 PROPOSED-2；Architecture Handoff PROPOSED 7 与 OPEN NQ-3；
契约 §3.1 明确记载 `status` 可选并已在 T-07 验证（显式 `DOWN` → `201`）。

Impact: 不违反任何 CONFIRMED 规则，也不改变 AC-07（缺省 IDLE）的可判定性；属可逆的加性行为。
若用户裁定「登记只能 IDLE」，仅需从 POST 契约移除 `status`。

Expected: 在真实数据录入前由用户裁定 NQ-3；无论结论均不阻塞本 Feature。

Suggested Owner: Product Manager / User（Architect 承载后续回退）

### REV-4

Severity: **NOTE**

Layer: **Frontend**

Location: `frontend/src/composables/useResourceDelete.ts`（新增）、
`frontend/src/composables/useClusterDelete.ts`（由 117 行实现收敛为绑定包装）

Problem: 为同时支持 Cluster 与 BareMetal 删除流程，把 F014 既有 `useClusterDelete` 通用逻辑提取为
`useResourceDelete`。属对既有可用代码的重构。

Evidence: 提取后仅以 `resourceName` 参数化文案，204/404 同构刷新、409 CONFLICT 分支、401 全局处理、
防重复提交等行为与原实现逐条一致；`clusterDetailPage.spec.ts` 既有删除用例（含 409 / 404 / 204）保持并全绿。

Impact: 无行为变更；抽象直接服务于本 Feature 的双资源复用，非无关重构。

Expected: 无（记录为可接受的使能型重构）。

Suggested Owner: Frontend（无需动作）

### REV-5

Severity: **NOTE**

Layer: **Backend / 错误语义**

Location: `backend/app/common/sqlstate.py`（F012 F-02：FK 违规字段回退可能把 `cluster_id` 截断为 `cluster`）

Problem: NQ-9 的应用层 `23503` 字段回退解析在本 Feature 仍未验证。创建路径因 `FOR SHARE` 父预检
不可达该分支；数据库层直插无效 `cluster_id` → `23503` 已验证。

Evidence: `docs/reviews/f012-project-foundation.md` F-02；`sqlstate._field_from_constraint_name` 对
`fk_bare_metals_cluster` 回退为 `tokens[0] == "cluster"`；T-03 覆盖应用路径为 `404`（非 `23503`）。

Impact: 当前应用路径不可达，无产品行为影响；对后续直接依赖 FK 映射的 Feature 为潜在风险。

Expected: 属 F012 F-02 的既有 Follow-up，可在后续批次修复（优先 `diag.column_name` 或返回完整列名）。

Suggested Owner: Backend

### REV-6

Severity: **NOTE**

Layer: **Documentation**

Location: `docs/database/f012-baseline-migration.md` §4 `0003_f002_bare_metals` DDL

Problem: 补入七列后 `updated_at` / `deleted_at` 及后续约束行的对齐缩进未同步调整。

Evidence: `git diff develop...HEAD -- docs/database/f012-baseline-migration.md` 仅见列对齐不一致。

Impact: 纯排版，不影响语义。

Expected: 后续文档整理时统一对齐。

Suggested Owner: 协调器 / Database

## Existing Defects

Tester 报告的唯一缺陷 **F002-T-01（LOW，Test Infra）** 重新评估：

- **严重程度合理**：该失败为 F013 既有用例的时序抖动（`vi.waitFor` 1000ms），隔离与重跑均通过，
  与 F002 实现无因果关系。Reviewer 独立全量运行前端 171 passed，未复现失败，符合 LOW 判定。
- **是否符合 Contract**：不涉及任何 API 契约或领域规则，属测试基础设施时序问题。
- **是否应阻塞 Merge**：**否**。`vite.config.ts` 的并发调整已作为缓解，且不改运行时行为。
- **问题所属层 / Owner**：Test Infra，Owner 协调器（与 Tester 结论一致）。

→ Reviewer **维持 LOW，不阻塞**，见 REV-2。

## Non-blocking Follow-ups

1. 更新 `project-plan.yaml > F002.git.head_commit` 至评审 / 合并时的真实 HEAD（REV-1）。
2. 定位并根治 `appAuth.spec.ts` 全量并行偶发超时；评估 `vite.config.ts` 全局并发限制的必要性与时长代价（REV-2）。
3. 由用户裁定 NQ-3（POST 是否允许显式非 `IDLE` 状态）；若否定则按加性回退移除该字段（REV-3）。
4. 承 F012 F-02 修复 `sqlstate` FK 字段回退解析（REV-5）。
5. NQ-7 已按计划落盘：F004 / F006 / F007 / F008 落地时向 `BARE_METAL_ACTIVE_CHILD_CHECKS` 追加
   各自活跃子资源检查，并补「BareMetal 有活跃子资源 → `DELETE /api/bare-metals/{id}` → `409`」端到端
   验收（本 Feature 仅建立声明点，故意保持显式空元组）。
6. 文档对齐整理（REV-6）。

## Unreviewed Areas

1. **浏览器级前端 E2E / 视觉 / 真实 DOM**：Reviewer 仅执行 vitest（happy-dom）组件测试与静态审查，
   未在真实浏览器观察渲染。
2. **多 uvicorn worker / 跨进程并发压测**：并发以独立连接 / 线程验证行锁协议，未做多 worker 压力测试
   （无产品需求，V1 单机内网）。
3. **NQ-9 应用层 `23503` 字段回退**：应用路径不可达，未验证映射后的 `details[].field`。
4. **静态 guard 对动态 SQL 构造的穷举覆盖**：承 F014 已知残余风险。

---

GIT: NONE
