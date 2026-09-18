# Review Report — F014 逻辑删除与数据一致性治理

> Status: **APPROVED WITH FOLLOW-UP**
> Author Role: reviewer
> Date: 2026-09-16
> Feature: F014（ENABLER，E07，P0，`depends_on: [F012]`）
> Feature Branch: `feature/F014-soft-delete`
> Base Branch: `develop` = `897b32539927c137b933aa0ebed700d3bc26be5b`
> start_commit: `897b32539927c137b933aa0ebed700d3bc26be5b`
> Reviewed HEAD: `d2805f5e2a7fd9c88df981c4db90c5f6f38b09a8`
> merge-base(develop, HEAD): `897b32539927c137b933aa0ebed700d3bc26be5b`（= start_commit，HEAD 为其后代）
> Tester Test Report: `docs/test-reports/f014-soft-delete.md`（`READY FOR REVIEW`）

---

## Feature

逻辑删除与数据一致性治理（F014）— CSM V1 的逻辑删除领域基座：系统内**唯一**软删写入路径、删除守卫（父删子拦 / 不级联 / 单事务先锁后检查）、`clusters` 的产品删除路径 `DELETE /api/clusters/{cluster_id}`，以及前端删除入口与状态接线。

## Review Status

**`APPROVED WITH FOLLOW-UP`**

不存在 BLOCKER / HIGH；不存在必须在当前 Feature 修复的 MEDIUM。存在 3 项 LOW（均不阻塞 Merge：REV-01 计划归属未落盘、REV-02 计划元数据陈旧、F014-T-01 guard 覆盖面）与 2 项 NOTE。AC-01 ~ AC-13 核心验收满足，测试可信，实现未超范围、未引入未经确认的能力。

## Scope Reviewed

### Git 证据（Reviewer 独立核对）

```text
git status --short                → 空（工作区 clean；无未暂存 / 未跟踪交付物）
git ls-files --others --exclude-standard → 空
git diff / git diff --cached      → 空
git rev-parse HEAD                → d2805f5e2a7fd9c88df981c4db90c5f6f38b09a8
git rev-parse develop             → 897b32539927c137b933aa0ebed700d3bc26be5b
git merge-base develop HEAD       → 897b32539927c137b933aa0ebed700d3bc26be5b
git merge-base --is-ancestor 897b325 HEAD → 成立（起点正确，无分叉/缺失）
git log --oneline develop..HEAD   → d8b35b8 / 1c88797 / d3d220f / 592e96e / a87ff04 / d2805f5
git diff --shortstat develop...HEAD → 28 files changed, 2899 insertions(+), 91 deletions(-)
```

- Feature HEAD、Base SHA、start_commit 与协调器输入一致；`start_commit` 为 HEAD 祖先；完整分支 diff（含已提交的实现、测试、文档）均在审查范围内，非仅未提交改动。
- 候选实现与测试均已提交、工作区 clean，满足正式 Review 前提。
- Reviewer 未执行任何 `add` / `commit` / `switch` / `merge` / `stash`，未修改 Git 状态；本报告为 Review 交付物（新文件）。

### 独立执行的验证（不采信 Tester 结论）

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端全量测试 | `CSM_TEST_DATABASE_URL=…csm_review .venv/bin/python -m pytest -q`（本轮新建 PG 实例 `/tmp/csm_review_pgdata`、库 `csm_review`） | **155 passed, 2 warnings in 103.32s**（与 Tester 一致，无 skip 伪造） |
| 前端全量测试 | `cd frontend && npm run test` | **11 files / 105 tests passed** |
| 前端类型检查 | `cd frontend && npm run typecheck` | exit 0 |
| 迁移完整性 | `git diff develop...HEAD -- backend/migrations/` | **空**（无新增 / 改动 migration，基线 `0001_f012_baseline` 未动） |
| G-3 guard 可失败性（对抗注入） | 在仓库**外部**临时目录构造 dict 写入样例并调用 `scan_deleted_at_writes()` | 见 Findings F014-T-01（确认漏洞） |

实际检查内容：`app/deletion/`（service / checks / __init__）、`app/clusters/`（router / service / deletion）、`app/db/active.py`、`app/common/errors.py`、`app/db/base.py`、`app/api/deps.py`、`app/models/cluster.py`、全部新增 / 修改测试、前端 `api/clusters.ts` / `composables/useClusterDelete.ts` / 列表与详情页 / 三份前端 spec、`README.md` / `frontend/README.md`、`docs/project/*` 元数据、契约与 Handoff 一致性；并核对既有 A15 / G-E / `test_a15_delete_endpoint_does_not_soft_delete` 的演进。

未审查内容见「Unreviewed Areas」。

## Product Compliance

- **AC-01 ~ AC-13 全部满足**，且有可判定证据（见 Test Review 与各层小节）。逐条核对 `docs/product/handoffs/f014-soft-delete.md` 的 AC 与实现行为，未发现削弱。
- **未引入未经确认的能力**：无 Undelete / Restore、无批量删除、无已删资源查看 / `include_deleted`、无审计字段、无 purge（T-12 负向路由 / 参数断言；`create_app` 的 OpenAPI 路径集合不含 `restore/undelete/purge/trash/batch/deleted`）。
- **NQ-1（R-DELETE-004 真实场景归 F002）**：实现层已按 Product Handoff 澄清 1 落成「可判定的中间形态」——守卫在删除路径上**真实被调用**（T-05）、**失败即拒绝且无部分写入**（T-05）、**锁后同事务执行**（T-06）、**阻塞行锁**（T-13）；真实 `Cluster + 活跃 BareMetal → 409` 与并发孤立记录不变式显式记为 F002 义务（Architecture Handoff 问题 7 / Test Report Unverified Areas）。**未被静默丢失**，但归属未写入 `project-plan.yaml`（见 REV-01）。
- **NQ-2（`ip_address.cluster_id` 归 F005）**：`ip_addresses` 表不存在，F014 仅交付可复用统一服务机制，未越界实现；交接记录于 Product Handoff NQ-2 / Architecture Handoff 问题 10 / Test Report Unverified Areas。**未被静默丢失**，归属同样未写入计划（见 REV-01）。
- 交付边界（`clusters` 是当前唯一资源、`database: false`）与 Product Handoff 一致；未把「代码能做更多」当优点。

## Architecture Compliance

- **唯一软删写入路径**：`app/deletion/service.py::soft_delete()` 是系统内唯一写 `deleted_at` 的函数；`clusters` 删除经 `app/clusters/service.delete_cluster()` 显式委托，并显式传入资源模块声明的 `CLUSTER_ACTIVE_CHILD_CHECKS`（`app/clusters/deletion.py`），非硬编码。符合 ADR-0004 §1/§3 与 Architecture 问题 1。
- **结构性约束**：以 G-3 静态 allow-list（`tests/test_deletion_guards.py` + 共享扫描器）把「写入文件集合恰好为 `{backend/app/deletion/service.py}`」做成可失败断言，并含「无 `deleted_at = None`」与「服务确被删除路径使用」的正向断言；符合 Architecture 问题 1 / 问题 11「演进而非删除」。
- **先锁后检查、同事务**：`soft_delete` 先 `select_active(...).with_for_update()`（未命中 → 404），再跑声明检查（命中 → 409 且不写），最后仅改目标行；事务边界由既有 `app/api/deps.py`（成功 commit / 异常 rollback）承担。符合 ADR-0004 §5 与 Architecture 问题 3。
- **声明机制无硬编码 / 无 EAV / 无多态 / 无通用表**：`ActiveChildCheck` 为 `Callable[[Session, int], bool]`；服务不出现「某资源无子资源」分支。`app/db/base.py` 仅横切 mixin，未引入 Resource 基类。符合 §4 / §24 与 F012 Q3 元数据 guard（既有 guard 全绿）。
- **无 schema / migration 变更**：`database: false` 判定正确（依据是「是否需要 schema 变更」，非「是否存在 DB 断言」）。
- **API 契约落点正确**：新增 `docs/api/f014-soft-delete.md`（单一权威）；`docs/api/f001-cluster.md` 未被修改（约束 #11）。契约 Status = READY。

## Database Review

- `clusters` 结构未变：列集合 `{id, name, created_at, updated_at, deleted_at}`、`pk_clusters`、`ck_clusters_name_no_slash`、`ux_clusters_name_active`（partial unique，`WHERE deleted_at IS NULL`）与 F012 基线逐项一致；**无新增列 / 索引 / 约束 / 触发器 / COLLATE**。
- 无 `ON DELETE CASCADE`：G-1 对 `pg_constraint.confdeltype='c'` 计数为 0，且断言全部 FK 为 RESTRICT / NO ACTION（当前为空真，随 F002+ 持续生效）。
- 认证表 `users` / `sessions` **无** `deleted_at` 列（G-4）；未扩大软删语义。
- 逻辑删除仅置 `deleted_at = now()`，`updated_at` 由 ORM `onupdate` 维护（符合 DB 设计决策 8）；未依赖 `create_all`。
- 未把任何 PROPOSED / OPEN 静默实现为不可逆数据库规则。

## Backend Review

- **API 层职责**：`router.delete_cluster` 仅编排（无 `response_model`，`204`）；业务在 `service.delete_cluster`；软删语义收敛于 `app/deletion`。分层清晰，无「业务逻辑写进 Router」。
- **只改目标行、不级联**：`soft_delete` 只对一个已锁定实例赋值并 `flush()`，无遍历、无 `DELETE`、无批量；T-07 全表快照（`clusters`）证明仅目标行 `deleted_at` 变化，其余行逐字段不变。
- **错误语义**：`NotFoundError`（404，不存在/已删不区分）、`ConflictError`（409，`details[].code == "ACTIVE_CHILDREN_EXIST"`）复用 `app/common/errors.py` 既有信封与全局 handler，未另立第二套映射。
- **无部分写入**：检查在赋值之前；T-05 断言守卫命中时目标行 `deleted_at` 仍 NULL。
- **未认证不改数据**：`DELETE` 位于 `/api` 前缀，由 F013 认证中间件 fail-closed 覆盖；T-10 真实原始连接断言 401 后 `deleted_at` 仍 NULL。
- **认证表无软删**：`app/auth/**` 无 `deleted_at` 写入（G-E 演进后）+ 模型无该属性。
- **事务边界**：服务内不 commit / rollback，符合基座约定。
- 未发现 SQL 注入 / 危险 DB 操作；`cluster_id` 为整数路径参数，非整数 → `400 VALIDATION_ERROR`（T-12）。

## Frontend Review

- **严格使用契约**：`api/clusters.ts::deleteCluster` 仅 `DELETE /api/clusters/{id}`，不发送请求体、不携带 `Content-Type`，`204` 归一为 `undefined`；未新建请求层，未新增依赖（`package.json` / lock **无 diff**）。
- **状态完整且互不混淆**：Loading（提交中）/ Empty（`200 + items==[]`，删空后）/ Not Found（详情独立 `state==='not-found'`）/ 409（保留行/详情 + 提示）/ 404（与成功同构刷新）/ 401（交全局会话失效，本层不渲染）；按 `error.code`（必要时 `details[].code`）分支，**显式断言不解析 `message`**（冲突文案使用「与展示无关的后端冲突文案」反向验证）。
- **不重复实现后端守卫**（§21）：前端不禁用、不隐藏任何行的删除入口，不预判活跃子资源；由其组件测试断言空闲时入口全部可触发。
- **防重复提交**：`useClusterDelete` 以 `deletingId` 拦截并发/连点；测试以 gate 延迟响应证明重复确认不产生第二个 `DELETE`。
- 未偷偷增加 CRUD / 批量删除 / 恢复入口；未引入 vue-router 等新能力。

## Test Review

- **AC 覆盖**：T-01 ~ T-13 / G-1 ~ G-4 / T-FE-01 与 AC-01 ~ AC-13 逐条映射，无遗漏、无 FAIL、无 skip。Reviewer 以真实 PG **独立重跑 155 passed**、前端 **105 passed** 复现。
- **测试本身可信**：
  - G-3 allow-list guard **真实可失败**（Tester 以越权文件对抗注入、随后逐字节还原；Reviewer 独立确认扫描器对 dict 形态存在缺口 → F014-T-01，但不影响当前生产结论）。
  - 锁序（T-06）与阻塞锁（T-13）为真实 DB 并发断言（第二原始连接 `FOR UPDATE NOWAIT` / 持锁阻塞），非 mock。
  - 数据库断言经**绕过应用层**的原始 psycopg 连接，未用 ORM 自证。
  - 未发现「为了让测试通过而迎合实现」的断言：错误渲染用例刻意使用与展示无关的后端文案，证明不解析 `message`；不级联用例做全表快照而非只查目标行。
- **既有 guard 演进未削弱**：
  - `test_a15_no_deleted_at_assignment_in_app_source`（写入数 = 0）→ `test_a15_deleted_at_write_paths_are_allowlisted`（恰好 1 个文件），并新增「无 undelete」与「服务确被使用」正向断言 → **增强**。
  - `test_g_e_no_deleted_at_assignment_in_app_source`（全 app = 0）→ 收窄为 `app/auth/**`，全量扫描能力由 G-3 承接 → **不降**（其原意即「认证代码不写」）。
  - `test_a15_delete_endpoint_does_not_soft_delete`（DELETE 不软删）→ 语义随 F014 合法反转，由更强的 T-01（+204、行仍物理存在、`deleted_at` 非空）取代 → **合理演进**。
- **F001 / F012 / F013 既有测试保持全绿**（含认证测试与 F012 数据库结构 guard）。
- 前端测试为「组件 → composable → apiRequest（fetch 桩）→ 契约响应 → 渲染」的整链路断言，非仅 UI 快照。

## Findings

### REV-01

**Severity:** LOW

**Layer:** Project Plan / Traceability（`docs/project/project-plan.yaml`）

**Location:** `docs/project/project-plan.yaml`：F002 条目（`acceptance_criteria` 无删除/孤立记录义务）、F005 条目（`acceptance_criteria` 无 `ip_address.cluster_id` 推导一致性）、`requirements_coverage` 的 `R-DELETE-004.covered_by: [F014]`。

**Problem:** Product Handoff NQ-1 / NQ-2 与 Architecture Handoff 问题 7 / 问题 10 明确请求 Project Manager 在 F014 阶段把 R-DELETE-004 的真实业务场景归属 F002、把 `ip_address.cluster_id` 一致性治理归属 F005，但 `develop...HEAD` 对 `project-plan.yaml` 的改动**仅含 F014 自身的 git / layers / stage 元数据**，未落 F002 / F005 的义务与 AC。R-DELETE-004 仍仅 `covered_by: [F014]`。

**Evidence:**
- `git diff develop...HEAD -- docs/project/project-plan.yaml` 仅包含 F014 条目与 `planning_status` / `execution` 的 IN_REVIEW 更新，无 F002 / F005 条目改动。
- F002 `acceptance_criteria`（project-plan.yaml:379-386）未含「Cluster 有活跃 BareMetal → 删除 409」「创建侧 `FOR SHARE`」「孤立记录不变式 = 0」；F005 `acceptance_criteria`（project-plan.yaml:424-430）未含 cluster_id 受控写入/漂移测试。
- 义务仅在 `docs/product/handoffs/f014-soft-delete.md` NQ-1/NQ-2、`docs/architecture/f014-soft-delete-handoff.md` 问题 7/问题 10、`docs/test-reports/f014-soft-delete.md` Unverified Areas 记录（信息未丢失，但权威计划未承接）。

**Impact:** R-DELETE-004 的**真实业务验收**可能在 F002 阶段被遗漏（F014 仅验证机制）；F005 的 `ip_addresses.cluster_id` 一致性可能无归属。属未来 Feature 的计划归属风险，不影响 F014 当前实现的正确性，不阻塞 F014 Merge。

**Expected:** Project Manager / Coordinator 在关闭 F014 前，将上述义务补入 F002 / F005 的 `acceptance_criteria` / `requirements`，并按 NQ-2 调整 `R-DELETE-004` / `ip_address.cluster_id` 的 `covered_by`（或在计划中显式记录归属迁移）。

**Suggested Owner:** Project Manager / Coordinator

### REV-02

**Severity:** LOW

**Layer:** Project Plan Metadata

**Location:** `docs/project/project-plan.yaml` F014 `git.head_commit`。

**Problem:** `head_commit: 592e96e2cce091b481e13ad030462546b387d6a1` 落后于分支实际 HEAD `d2805f5`（其后还有 `a87ff04` 元数据检查点与 `d2805f5` 测试提交）。Test Report 亦以 `592e96e` 为「实现 HEAD」。

**Evidence:** `git rev-parse HEAD` = `d2805f5…`，而 plan 中 `head_commit` = `592e96e…`；`git log --oneline develop..HEAD` 含 `d2805f5`。

**Impact:** 计划元数据与真实提交不一致，影响 Merge Gate 的候选树核对与追溯（不影响代码正确性）。同类问题在 F013 Review REV-02 已按 LOW 处理。

**Expected:** Coordinator 在 Review / Merge Gate 阶段把 `head_commit` 更新为最终已审查 HEAD（本轮为 `d2805f5`）及 `merge_commit`。

**Suggested Owner:** Coordinator

### NOTE-01（非缺陷）

**Layer:** Backend / Guard 机制

**Location:** `backend/app/clusters/deletion.py`、`app/deletion/service.py`

**Problem:** 声明式检查的默认值为空元组 `CLUSTER_ACTIVE_CHILD_CHECKS = ()`。当 F002 引入 `bare_metals` 时，若忘记在该常量追加活跃子检查，删除会**静默放行**（fail-open），而机制本身不会报警。

**Evidence:** `app/clusters/deletion.py` 显式声明空元组；`soft_delete` 仅遍历传入的 `active_children`，无「未知子资源」兜底。

**Impact:** 未来回归风险；当前无子资源表，F014 时点无实际影响；该取舍为 Architecture 问题 2 的有意选择（显式常量优于全局注册表的 import 副作用）。

**Expected:** F002 落地时，除追加检查外，增加「`CLUSTER_ACTIVE_CHILD_CHECKS` 非空 / 含 BareMetal 检查」的断言，并把端到端 409 与孤立记录不变式写入 F002 的 AC（与 REV-01 同批处理）。

**Suggested Owner:** Backend（F002 阶段）/ Architect

### NOTE-02（非缺陷）

**Layer:** API Contract（继承 follow-up）

**Location:** `docs/architecture/f014-soft-delete-handoff.md` OPEN #2；F001 Review F-01。

**Problem:** 未映射的 4xx（如非契约路径 / 方法不允许）统一为 `INTERNAL_ERROR` 的通用映射缺口仍在。

**Impact:** 不影响 F014 契约内端点（`400/401/404/409/500` 均正确）；属既有基座遗留，F014 明确不修通用映射表。

**Expected:** 作为继承 follow-up 保留，由后续基座 Feature 处理。

**Suggested Owner:** Architect / Backend（后续基座）

## Existing Defects

### F014-T-01（Tester 报告）— Reviewer 重新评估：**维持 LOW，不阻塞 Merge**

- **严重程度裁定**：Tester 判 LOW 合理。理由：(a) 当前生产代码**不存在** dict / `**` 映射写入路径，G-3 对全部实际写入形态成立；(b) 行为测试 T-01（行仍在、`deleted_at` 非空）、T-07（只改目标行）为运行时兜底；(c) 该缺口对应 Architecture Handoff 已登记的残余风险 R2（静态 guard 可被动态 SQL 绕过）。故不构成 HIGH/MEDIUM。
- **独立复现**：Reviewer 在仓库外部临时目录构造 `values({"deleted_at": …})`、`values(**{"deleted_at": …})` 与裸 SQL `UPDATE … SET deleted_at = …`，调用 `tests/deletion_guard_helpers.scan_deleted_at_writes()`，结果仅裸 SQL 命中，两种 dict 形态**未命中**——确认 Tester 描述属实。
- **与 Architecture 的一致性**：Architecture Handoff 问题 1 / G-3 明列需扫描「`.deleted_at =`、`values(deleted_at=`、`setattr(...)`、`mappings 中的 deleted_at`」四类，实现覆盖前三类、缺第四类。属**部分未达成 G-3 枚举形态**，但因无现实暴露面且被运行时测试兜底，仍判 LOW（Follow-up）。
- **层级 / Owner**：Test / Guard（`tests/deletion_guard_helpers.py::_WRITE_RE`）；`Suggested Owner: Backend`。
- **建议**：扩展扫描器覆盖 dict-key 形态（正则匹配 `values(`/`update(` 参数中出现字符串字面量 `"deleted_at"`/`'deleted_at'`），或改为 AST 扫描。
- **是否阻塞 Merge**：否。

## Non-blocking Follow-ups

1. REV-01：把 NQ-1 / NQ-2 义务落盘到 `project-plan.yaml` 的 F002 / F005（含 R-DELETE-004 真实场景 AC 与 `ip_addresses.cluster_id` 归属）。
2. REV-02：更新 F014 `git.head_commit` / `merge_commit` 元数据。
3. F014-T-01：扩展 G-3 扫描器覆盖 mappings（dict）写入与 `deleted_at = None` 的 dict 形态。
4. NOTE-01：F002 落地时补「活跃子检查非空」断言，避免 fail-open 静默放行。
5. NOTE-02：继承 F-01 的通用 4xx→`INTERNAL_ERROR` 映射缺口，后续基座 Feature 处理。
6. F014-T-01 / NOTE-01 建议与 F002 阶段一并收口（两者同属「子资源守卫」链路的验证完整性）。

## Unreviewed Areas

1. **AC-04 / AC-09 的真实业务端到端**（`Cluster + 活跃 BareMetal → 409`、并发「创建子 vs 删除父」的孤立记录不变式 = 0、创建侧 `FOR SHARE` 协议）：`bare_metals` 表属 F002（未落地），Reviewer 仅复核机制层证据（T-05 / T-06 / T-13），未做真实子资源端到端。显式归 F002 义务（NQ-1 / REV-01）。
2. **F005 `ip_addresses.cluster_id` 一致性治理**：表不存在，未验证（NQ-2 / REV-01）。
3. **真实浏览器 DOM / 网络 / 视觉 E2E**：环境无浏览器自动化；Reviewer 以 vitest（happy-dom）+ 组件整链路断言 + 前端类型检查为准，未复跑 Tester 的「真实 uvicorn + 真实前端 client」临时探针（该探针运行后已删除，无法直接复现，但其断言的契约结果已被 T-01/T-02/T-05/T-10 与前端 spec 覆盖）。
4. **生产构建产物在真实 nginx + 内网下部署**（属 F015）；`npm run build` 的 chunk 体积告警未单独评估（非 F014 范围）。
5. **多 uvicorn worker / 跨进程并发**：未做多 worker 压测（V1 单机内网，无产品需求）。
6. **静态 guard 对全部动态 SQL 构造方式的穷举**：已知残余（Architecture R2 / F014-T-01），未穷举。

---

## Review Verdict

不存在 BLOCKER / HIGH；不存在必须在当前 Feature 修复的 MEDIUM。AC-01 ~ AC-13 核心验收满足；测试可信（Reviewer 以真实 PostgreSQL 独立全量重跑 **155 passed**、前端 **105 passed**、`typecheck` 通过、`backend/migrations/` 无 diff、G-3 guard 可失败性独立确认）；实现未超范围、未引入未经确认的能力；无 schema / migration 变更（`database: false` 成立）；唯一软删写入路径 + 单事务先锁后检查 + 声明式子资源检查忠实于 ADR-0004 与 Architecture Handoff；前端严格按契约与 `error.code` 接线且未重复实现后端守卫。

存在 3 项 LOW（REV-01 计划归属未落盘、REV-02 计划元数据陈旧、F014-T-01 guard 覆盖面，均不阻塞 Merge）与 2 项 NOTE。

**`APPROVED WITH FOLLOW-UP`** — 可进入 Merge Gate。Merge 前建议 Coordinator 处理 REV-01 / REV-02（计划归属与元数据），F014-T-01 与 NOTE-01 可并入 F002 批次收口。

---

GIT: NONE
