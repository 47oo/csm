# F030 Review 跟进收敛：Contract 签核、边界测试与前端交互修正 — Architecture

- 状态：READY FOR DESIGN（交 Test Design / Contract；未放行编码）
- 版本：v1（Architect，2026-10-23）
- Feature：F030（ENABLER，P2，M21）；计划 plan_revision 16；分支 `feature/F030-review-followup-closeout`
- 需求依据：`docs/product/requirements-v3.md` revision 11（§23.2 CONFIRMED、§28、§31 T85–T99、§32、§35.1 revision 11 行、§35.2 BQ01–BQ17 CONFIRMED / BQ18–BQ19 DESIGN_INPUT、§35.3 D01–D03）
- 产品依据：`docs/features/F030/product.md`（READY FOR ARCHITECT；§3 不新增规则声明、§5 P1–P9、§7 N1–N5）
- 批准依据：`docs/project/project-plan.yaml` plan_revision 16；`project.approval`（用户 2026-10-23，feature_ids 含 F030）；`execution.authorization`（plan_revision 16 / SINGLE / F030）
- 上游 Review：`docs/features/F029/review-report.md`（APPROVED WITH FOLLOW-UP；RV-01…RV-11，Follow-up 1/2/3/5/6/7）
- 既有已签核设计（复用，不重开）：`docs/features/F026/architecture.md` v1 §2/§3/§4 + §10；`docs/features/F027/architecture.md` §1–§2；`docs/database/f026-cluster-authorization.md` v1（DB-D401–D420，Database 2026-10-21）；`docs/api/F026.md` v2；`docs/api/F027.md` v1
- layers：database=false、backend=true、frontend=true；api_required=true
- F031 errata（2026-10-23）：§7.2 的 `canSubmitGrant` 签名、候选空态文案与 §8.1 注释字面已被 §17 更正；以 §17 为准（依据 plan_revision 17、F030-RV-03/04/05/09）。

## 1. 方案摘要与边界

F030 只做四类工作（Product §3）：批准/签核记载、专业设计输入收敛、测试与测试规范、文档/注释与前端交互。**不改变任何已确认业务行为**：不新增对象、关系、状态、唯一性、生命周期、权限项、错误码或错误顺序；不改 §23.2 授权/范围/可见性/Audit 语义；不改已批准端点、参数、Schema、Migration；不重开 F026–F029 已交付范围。

七项设计的落点：

| # | 内容 | 落点层 | 是否改变行为 |
| --- | --- | --- | --- |
| ① | Contract 签核记载 | 文档 | 否（只补记载） |
| ② | BQ18/BQ19 收敛 | 计划 | 否（只改状态与依据） |
| ③ | `q` 边界断言 | 测试 | 否（断言既有语义） |
| ④ | 真并发 / 非唯一完整性错误 | 测试 | 否（断言既有语义） |
| ⑤ | 前端候选门控 / 重试 / 超大授权量 | 前端 | 否（消除误导性中间态；服务端 409 与唯一约束仍是最终事实） |
| ⑥ | 注释 + Contract 现状语义 | 后端注释 / 文档 | 否（记录现状，不调整映射） |
| ⑦ | `real_scope` 默认规则约束 | 测试规范 | 否（约束测试夹具，不改生产行为） |

## 2. Layers 与 api_required 判定

| 字段 | 值 | 判定理由 |
| --- | --- | --- |
| `layers.database` | false | 无表/列/索引/约束/触发器/迁移变更；DB-D401–D420 全部继续有效。F030 与数据相关的工作仅是为既有 DB 约束补**并发与完整性错误证据**（属测试）。`implementation.database = NOT_REQUIRED`，理由记入 `not_required.database`。 |
| `layers.backend` | true | `app/services/cluster_authorization.py` 注释修正；`tests/conftest.py` docstring 与 `pyproject.toml` marker 说明；4 类后端测试新增。 |
| `layers.frontend` | true | `ClusterAuthorizationPanel.tsx` 候选门控/重试/超大授权量提示；新增纯逻辑模块与 smoke 断言。 |
| `api_required` | true | 不新增端点/参数/字段/错误码/权限，但 Contract 文件必须修订：`docs/api/F026.md` → v3（§5 非唯一完整性错误现状语义 + 签核记载补齐）、12 份域 Contract 追加节补正文签核行。Contract 状态 **READY**（本 Gate 签核字面，CONTRACT Gate 落盘核验）。 |

本 Gate 不需要修改 plan 的 layers / api_required（plan revision 16 已记录为 database=false、backend=true、frontend=true、api_required=true）。

## 3. 设计 ①：Contract 签核记载格式

依据 `change-control.md` §2「批准者、日期、具体对象路径及 revision / 内容版本、覆盖范围和确认来源」。两类记载，**都落在权威正文**：

### 3.1 Kind A — `docs/api/F026.md` 升 v3（正文签核块 + 修订记录）

头部块（替换现头部四行中的状态/版本/签核，并新增覆盖范围与确认来源）：

```markdown
- **状态**：READY
- **版本**：v3
- **签核**：Architect，2026-10-21（v1）；2026-10-22（v2，F029 跟进：P-1 / q 顺序澄清）；2026-10-23（v3，F030 跟进：§5 记录非唯一完整性错误现状语义，补齐签核记载；**端点 / 字段 / 错误码 / 权限 / 错误顺序不变**）
- **覆盖范围 / 对象**：本文件 v3 全文（§1–§13）；三个仅 ADMIN 的授权管理端点
- **确认来源**：`docs/features/F030/product.md`（READY FOR ARCHITECT）；`docs/project/project-plan.yaml` plan_revision 16，`project.approval`（用户 2026-10-23，feature_ids 含 F030，basis「按建议合并」）；上游 `docs/features/F029/review-report.md` F029-RV-01 / F029-RV-08、Follow-up 1 与 6
- **上游依据**：requirements revision 11（§23.2、§31 T85–T99、§32）；`docs/database/f026-cluster-authorization.md` v1（DB-D401–D420）；`docs/features/F026/architecture.md` v1
```

§12 签核块追加：

```markdown
- v3（2026-10-23，Architect）：核对 §5 非唯一完整性错误语义与实现一致；补齐 §1–§13 的批准者/日期/版本/覆盖范围/确认来源；关闭 F029-RV-01、F029-RV-08。端点/字段/错误码/权限/错误顺序不变。
```

§13 修订记录追加一行：

```markdown
| v3 | 2026-10-23 | F030 跟进：§5 记录「非唯一完整性错误 → 原始异常上抛 → 500 `INTERNAL_ERROR`」的现状语义；补齐签核者/日期/版本/覆盖范围/确认来源；不改变端点/字段/错误码/权限与既有 409/422 映射。 | F030 P1/P6；F029-RV-01、F029-RV-08 |
```

### 3.2 Kind B — 12 份域 Contract 追加节签核行

对象：`docs/api/F002.md`、`F003.md`、`F004.md`、`F007.md`、`F008.md`、`F009.md`、`F010.md`、`F011.md`、`F012.md`、`F013.md`、`F014.md`、`F023.md`。

在既有「## F027 范围语义（加法引用）」节**末尾**追加一行（不改上文与既有版本号）：

```markdown
签核：Architect，2026-10-23；对象：`docs/api/<Fxxx>.md` §「F027 范围语义（加法引用）」（增补节 v1，独立于上文正文版本）；覆盖范围：仅该增补节的范围语义交叉引用、错误顺序与不泄露说明；本文件端点、字段、错误码、权限矩阵、版本冲突与软删语义保持不变；确认来源：F030（plan_revision 16；`docs/features/F029/review-report.md` F029-RV-01、Follow-up 1）；上游依据：`docs/api/F027.md` v1、requirements revision 11 §23.2、`docs/api/F026.md` v3。
```

并在各自「修订记录」表追加一行（4 列表直接把来源写进「原因」格；3 列表合并入「变更」格）：

```markdown
| F027 引用节 v1 | 2026-10-23 | 补记 F027 范围语义增补节签核（Architect）：端点/字段/错误码/权限不变 | F030 P1；F029-RV-01 |
```

### 3.3 判定与不做项

- **为什么不是「编辑维护」**：追加节陈述 404/422/409 顺序与不泄露等**行为约束**，超出 change-control §2「纯排版/链接修订」；且 Product P1 明确要求 12 份正文含签核五要素。
- **不做**：不改 `docs/api/F027.md` v1 头部（已含批准者/日期/版本/覆盖范围/依据；补「确认来源」属 PROPOSED，非 Product ① 列明对象，避免 P9 范围漂移，见 §14 O1）。
- **不做**：不改任何既有正文语义；任何正文改写视为内容语义变化，须回 Product。

## 4. 设计 ②：CHG010-BQ18 / BQ19 收敛

### 4.1 收敛结论（在既有已签核设计边界内）

| ID | 已签核设计 | 收敛结论 |
| --- | --- | --- |
| CHG010-BQ18（Architect / Database） | `docs/database/f026-cluster-authorization.md` v1（Database 2026-10-21；DB-D401–D420，含 DB-D407 索引修订）、`docs/features/F026/architecture.md` v1 §2/§3.2、`docs/features/F027/architecture.md` §1–§2、`docs/api/F026.md` v3 §8 | 表名/列/FK RESTRICT/CHECK/部分唯一索引 `uq_user_cluster_authorizations_user_id_cluster_id` 为有效行唯一权威；迁移 0015 手写 DDL + 幂等回填 + 计数断言；`AccessScope` 位于 `app/core/access_scope.py`，逐请求解析、`request.state` 复用、不跨请求缓存；范围过滤使用 SQL 谓词（`cluster_predicate` / `EXISTS` 归属谓词）；**无物化、无缓存**。F030 不改变该设计。 |
| CHG010-BQ19（Architect / Backend） | `docs/api/F026.md` v3 §2/§3/§9/§10（D-7 默认 `sort=granted_at` / `order=desc` / `page=1` / `page_size=20`、同刻 `id` 升序；D-8 未知查询参数 422、请求体 `extra=forbid`）、`docs/features/F026/architecture.md` v1 §3.3/§4、本文件 §7 | 分页/排序/过滤沿用既有列表契约口径，`total` 与 `items` 同 filters；System 授权 Tab 仅展示与逐条授予/撤销，**不提供批量授予或批量撤销**（属一期未纳入范围，需另行走变更控制）；F030 前端交互修正不新增端点/参数/权限。 |

### 4.2 记录格式（仅 `decisions_required` 的 `status` 与 `basis`）

`id` / `source` / `kind` / `affects` / `owner` **保持不变**；`status: OPEN → CONFIRMED`，`basis` 写入真实签核者与对象版本。协调器按以下字面落盘：

```yaml
- id: CHG010-BQ18
  source: docs/project/proposals/CHG-010-cluster-access.md#专业设计输入
  status: CONFIRMED
  kind: DESIGN_INPUT
  affects:
  - F026
  - F027
  owner: Architect / Database
  basis: 专业设计已在既有批准边界内签核收敛（F030 P2）。Architect 2026-10-23 核对
    docs/database/f026-cluster-authorization.md v1（Database 2026-10-21；DB-D401–D420，含 DB-D407
    全量 (user_id) 索引修订）、docs/features/F026/architecture.md v1 §2/§3.2、
    docs/features/F027/architecture.md §1–§2、docs/api/F026.md v3、docs/api/F027.md v1：
    表 user_cluster_authorizations 的列/FK RESTRICT/CHECK/部分唯一索引
    uq_user_cluster_authorizations_user_id_cluster_id 是有效行唯一权威；迁移 0015 手写 DDL + 幂等回填 +
    计数断言；AccessScope 位于 app/core/access_scope.py，逐请求解析、request.state 复用、不跨请求缓存、
    不物化；范围过滤用 SQL 谓词（cluster_predicate / EXISTS 归属谓词）。未新增业务限制，
    requirements §35.2/§35.3 正文未改写；F030 不改变该设计。
- id: CHG010-BQ19
  source: docs/project/proposals/CHG-010-cluster-access.md#专业设计输入
  status: CONFIRMED
  kind: DESIGN_INPUT
  affects:
  - F026
  - F027
  owner: Architect / Backend
  basis: 专业设计已在既有批准边界内签核收敛（F030 P2）。Architect 2026-10-23 核对
    docs/api/F026.md v3 §2/§3/§9/§10（D-7 列表默认与同刻 id 升序、D-8 未知查询参数 422 与
    extra=forbid）、docs/features/F026/architecture.md v1 §3.3/§4、docs/features/F030/architecture.md §7：
    授权列表分页/排序/过滤沿用既有列表契约口径，total 与 items 同 filters；System 授权 Tab 仅展示与
    逐条授予/撤销，不提供批量授予或批量撤销（属一期未纳入范围，需变更控制）。F030 前端交互修正
    不新增端点/参数/权限；实现责任为 Backend / Frontend。
```

### 4.3 边界

- **不改写** `requirements-v3.md` §35.2 / §35.3 正文（含表中「由 Architect / Database 在 F026–F027 签核」的说明）。计划状态变更不构成需求修订，也不把 DESIGN_INPUT 升格为业务裁定（§35.2 末段）。
- 不虚构签核者：BQ19 的实现责任记 Backend / Frontend，但**签核者是 Architect**；Database 的日期沿用 DB 设计 v1 的 2026-10-21，不写 2026-10-23。
- 不改 `project.approval`、`execution.authorization`、`pending_changes`（保持 `[]`）。

## 5. 设计 ③：`q` 边界断言

新增于 `backend/tests/integration/test_cluster_authorizations.py`（模块已 `pytestmark = pytest.mark.real_scope`），真实 PostgreSQL + 真实 HTTP。

| 场景 | 期望 | 断言要点 |
| --- | --- | --- |
| 已知用户 `q=""` | 422 | `error.code == "VALIDATION_ERROR"`、`details.fields[0].field == "q"` |
| 已知用户 `q="   "` | 422 | 同上（trim 后空） |
| 已知用户 `q="a\x07b"`（Cc） | 422 | 同上 |
| 已知用户 `q="a\u200bb"`（Cf） | 422 | 同上（覆盖控制字符分支的另一类） |
| 已知用户 `q` = 65 字符 | 422 | 同上（>64 上限） |
| **已知用户 `q="f26g"`（正向对照）** | 200 且 `total == 1` | 防止「对所有 q 一律 422」的空洞通过 |
| 未知用户 `q=""` | 404 | `error.code == "NOT_FOUND"`（P-1 路径对象优先） |
| 未知用户 `q="a\x07b"` | 404 | 同上 |
| 未知用户 + 未声明参数 `unexpected="x"` | 422 | `details.fields` 含 `field == "unexpected"`（`_reject_unknown_query` 在路径/语义前） |
| 未知用户 + 未声明参数 + `q=""` | 422 | 同上（未声明参数优先，仍非 404） |

**反空洞性（对应 P3）**：`q="f26g"` → 200 与 `q=""`/控制字符 → 422 的组合，使删除 `_validate_q` 时前者仍 200、后者变 200 → 断言失败；未知用户组（404）与已知用户组（422）互斥，调换「路径 404 / 语义 422」顺序后未知用户组返回 422 → 断言失败。无需在交付分支做变异改动。

## 6. 设计 ④：真并发授予与非唯一完整性错误

### 6.1 真并发（关闭 F026-RV-03 的并发缺口）

`test_concurrent_grant_two_connections_single_winner`（真实 PG，真实提交）：

1. ADMIN 客户端建 Cluster `F30C1`，`make_user(role="VIEWER", username="f030.concurrent")`。
2. **两个独立登录的 ADMIN 客户端**（`role_client_factory("ADMIN")` 调用两次），保证两条独立数据库连接（`auth_session_factory` 绑定 `committed_engine`，`NullPool`）。
3. `barrier = threading.Barrier(2)`；两个线程各自 `barrier.wait()` 后 `POST /users/{id}/cluster-authorizations`；`join(timeout=30)` 并断言线程已结束（防挂起）。
4. 断言状态码集合 `== {201, 409}`；409 体 `code == "CONFLICT"`、`details.reason == "already_granted"`；201 体 `status == "ACTIVE"`。
5. DB 断言（`auth_session_factory` 真实查询）：该 `(user_id, cluster_id)` **ACTIVE 行 == 1**、该对**总行数 == 1**（无残留撤销行）；`audit_logs` 中 `object_type="user_cluster_authorization"` 且 `object_id == 胜方授权 id` 的行 **== 1** 且 `action == "CREATE"`；胜方 201 返回的 `id` 等于 DB 的 ACTIVE 行 id。

不满足项：顺序调用两条请求不计为并发证据（Product N3）。

### 6.2 非唯一完整性错误（关闭 F029-RV-08 的证据缺口）

`test_grant_non_unique_integrity_error_is_not_mapped_to_409`（服务层，真实 DB，**不使用 monkeypatch**）：

1. 建真实 VIEWER 目标账号与真实 Cluster。
2. 构造 `Operator(user_id=uuid.uuid4(), username="f030.ghost", role=Role.ADMIN)`（`granted_by` 指向不存在的账号）。
3. 调 `grant_authorization(session, op, user_id=<真实>, cluster_id=<真实>)`：
   - 断言抛出 **`sqlalchemy.exc.IntegrityError`，且不是 `core.errors.Conflict`**（即未被映射为 409 `already_granted`）；
   - 断言 `exc.orig.sqlstate == "23503"`、`exc.orig.diag.constraint_name == "fk_user_cluster_authorizations_granted_by_users"`。
4. 残留断言：该 `(user, cluster)` 授权行 **== 0**；`audit_logs` 中 `object_type="user_cluster_authorization"` 行 **== 0**（服务层 `rollback` 生效）。

说明：这是「校验通过之后的非唯一完整性失败」，与 F029-RV-08 描述的形态等价（唯一索引冲突以外的 `IntegrityError`）；它证明 `except` 分支的收窄是**精确的**。Contract 侧对应记录见 §8.2（现状：原样上抛 → 500 `INTERNAL_ERROR`）。框架级 500 信封已由 F002 `test_version_conflict_and_internal_error_envelopes` 证明，本 Feature 不重复实现 500 用例；若 Tester 需要端到端串联，可用故障注入构造（不得改生产代码），并在 Test Report 标注为实现层证据。

## 7. 设计 ⑤：前端候选加载门控 / 失败重试 / 超大 ACTIVE 授权量

### 7.1 现状问题（F029-RV-05）

`openGrant()` 先 `setGrantOpen(true)` 再 `await loadActiveGrantIds(...)`；加载期间 `activeGrantIds` 为空或上一轮值 → 已授权 Cluster 短暂呈现为可选且可提交；加载失败时置空集并仅显示错误，仍可提交（依赖服务端 409 兜底）；`page <= 20` 上限在 ACTIVE > 2000 条时使排除不完整且无提示；「仅显示前 50 个候选」的判据（`clustersState.total > candidates.length + activeGrantIds.size`）语义错误。

### 7.2 交互设计（不新增端点/参数，不静默截断）

新增纯逻辑模块 `frontend/src/components/authorizationCandidates.ts`（无 JSX，供面板与 `smoke:client` 共用）：

```ts
export type ActiveGrantLoad =
  | { kind: "idle" } | { kind: "loading" }
  | { kind: "success"; ids: ReadonlySet<string>; loaded: number; total: number; truncated: boolean }
  | { kind: "error"; message: string };

export type GrantCandidates =
  | { kind: "loading" } | { kind: "error"; message: string }
  | { kind: "success"; clusters: Cluster[]; truncated: boolean };

export function computeGrantCandidates(active: ActiveGrantLoad, clusters: ClustersState): GrantCandidates;
export function canSubmitGrant(active: ActiveGrantLoad, selectedClusterId: string, busy: boolean): boolean;
export function clusterListTruncated(clusters: ClustersState): boolean; // total > items.length
```

规则（**不变量**）：

- `computeGrantCandidates`：`active.kind !== "success"` 时**永不返回候选**（`idle`/`loading` → `loading`，`error` → `error`）；`clusters` 非 `success` 时同样不返回候选；仅在两者均 `success` 时过滤 `!ids.has(cluster.id)`，`truncated = active.truncated || clusters.total > clusters.clusters.length`。
- `canSubmitGrant`：`active.kind === "success" && !busy && selectedClusterId !== ""`。

面板状态与文案：

| 状态 | 呈现 | 提交 |
| --- | --- | --- |
| `active` 加载中 | `LoadingState`「正在加载该账号已有的有效授权…（加载完成前不可提交）」；不渲染可选项 | 禁用 |
| `active` 加载失败 | `ErrorState` + **「重试」按钮**（重新执行加载）；**不置空集**、不伪装为「无授权」 | 禁用 |
| 加载成功、候选为空 | `EmptyState`「该账号已拥有全部匹配集群的有效授权」 | 禁用 |
| 加载成功、`active.truncated` | `InfoState` 显式说明：「该账号有效授权数量为 N（已加载 M）。为限制请求量，候选可能仍包含已授权集群；重复提交会被服务端以 409 `already_granted` 拒绝，不会重复建立授权。」 | 允许（服务端唯一约束与 409 是最终事实） |
| 集群列表被截断（`total > items.length`） | 「仅显示前 N 个匹配集群，请用搜索缩小范围」（替换现行错误判据） | — |
| 提交成功 | 关闭模态 + `SuccessState` + 刷新列表与候选集合（现有行为保留） | — |
| 提交 409 `already_granted` | **保持模态打开**、内联呈现 `describeClusterAuthorizationError` 文案、并重新加载候选集合（错误项消失）；**不当作成功**、不关闭 | 恢复可提交 |
| 提交其他错误（422/403/404/500） | 内联呈现，不自动重试 | 恢复可提交 |

`loadActiveGrantIds` 调整（分页仍在已批准 `page_size=100` 内）：按 `total` 计算所需页数，保留绝对安全上限 `MAX_PAGES = 20`；循环结束后若 `ids.size < total` → `truncated = true`（**显式提示**，不静默截断）；请求失败 → `active.kind = "error"`。

撤销路径不变：`already_revoked` 关闭 + 提示 + `reloadToken+1`（Contract D-5 / §4.3）。

### 7.3 前端验证

`tsc --noEmit`、`vite build`、`npm run smoke:client` 新增断言（`computeGrantCandidates` / `canSubmitGrant`）：loading、error、success 过滤、`truncated` 传播、`canSubmitGrant` 在非 `success` 时恒 `false`。**真实浏览器 DOM/焦点/窄屏仍不在覆盖范围**，Test Report 必须如实声明为「机制级 + 静态核对」，不得声称完成浏览器验证（F029-RV-06 教训）。

## 8. 设计 ⑥：`list_authorizations` 注释与 Contract 现状语义

### 8.1 注释修正（`backend/app/services/cluster_authorization.py`）

删除「This also removes the 422-vs-404 existence oracle for unknown users combined with an invalid q」这一与事实不符的结论，改为：

```python
    # Contract §3/§5 P-1: path object first — an unknown or non-UUID account is
    # 404 before any semantic query validation, so `q` is only validated after
    # the account exists. Typed query params (status/cluster_id/page/page_size/
    # sort/order) and undeclared params are rejected by the route before the
    # handler, hence 422 even for an unknown account. This is not an
    # information-leak hardening measure: the endpoint is USER_ADMIN only.
```

### 8.2 `docs/api/F026.md` §5 追加（v3，记录现状，不改变映射）

```markdown
**非唯一完整性错误语义（v3 补记，记录既有实现，不改变任何映射）**

授予端点在 §4.2 的 `IntegrityError` 处理中，**仅**当违反部分唯一索引
`uq_user_cluster_authorizations_user_id_cluster_id` 时返回 409 `CONFLICT{reason:"already_granted"}`。
其他完整性失败——例如校验通过后瞬态竞态导致的外键或触发器失败——**不被改写成 409 或 422**，
而是原样上抛，由统一异常处理返回 500 `INTERNAL_ERROR{}`，且不新增授权行、不写 Audit。
§4.2 的「cluster_id 不存在或已软删 → 422」是校验阶段结论，与上述校验后兜底不冲突；
该情形不构成 §1/§5 P-1 错误顺序的放宽，也不新增 error code 或 reason。
证据：F030 服务层用例（外键违约不被映射为 `already_granted`、无授权行与 Audit 残留）+
F002 500 信封用例。
```

边界：把该语义改判为 409/422 或调整错误顺序属**已确认错误语义变更**，须回 Product/用户（Product §3 边界守卫）。

## 9. 设计 ⑦：`real_scope` 默认规则约束机制

### 9.1 声明（文档 + 代码旁注，单一权威表述）

`backend/tests/conftest.py` 的 `auth_app` docstring 重写为规则说明：

```text
Integration scope convention (F030):
- default: modules under tests/integration/ WITHOUT ``pytest.mark.real_scope`` run with a
  test-only unrestricted AccessScope override (legacy pre-F027 coverage). This shim never
  changes production behaviour and is not evidence for §23.2 scope enforcement.
- real scope: any module that imports ``app.core.access_scope`` symbols, calls
  ``resolve_access_scope``, or overrides/asserts ``get_access_scope`` MUST declare
  ``pytestmark = pytest.mark.real_scope``.
- guard: tests/integration/test_f030_test_harness.py enforces the rule (§9.2).
```

`backend/pyproject.toml` marker 说明同步为「未标记的 `tests/integration` 模块默认走 legacy unrestricted 覆盖（F030 ⑦）」。

### 9.2 机制（新增 `backend/tests/integration/test_f030_test_harness.py`，本模块**不打** `real_scope`）

| 用例 | 断言 | 作用 |
| --- | --- | --- |
| `test_unmarked_module_gets_legacy_scope(auth_app)` | `get_access_scope in auth_app.dependency_overrides` 且其返回 `AccessScope(unrestricted=True, cluster_ids=frozenset())` | 证明「默认 legacy」是**事实**而非仅文档声明（canary 正向） |
| `test_real_scope_usage_requires_marker()` | AST 扫描 `tests/integration/test_*.py`：凡出现 `AccessScope` / `resolve_access_scope` / `get_access_scope` 的模块必须有模块级 `pytestmark` 或装饰器标记 `real_scope`，否则列入 `offenders` 并 `assert offenders == []` | **未来漏标记不会被静默放行** |
| 同上（反空洞断言） | `len(scanned) >= 20`；`{"test_cluster_authorizations.py", "test_f027_access_scope.py"} <= marked` | 防止 glob 失效或标记识别失效导致的空洞通过 |

补充 canary（放入已标记的 `test_cluster_authorizations.py`）：`test_marked_module_has_no_legacy_scope_override(auth_app)` 断言 `get_access_scope not in auth_app.dependency_overrides`。

边界：扫描用 AST（`Import`/`ImportFrom` + `Name`/`Attribute`），不匹配注释与 docstring，避免误报；**仅**排除守卫模块自身（`Path(__file__).name`），不提供通用豁免名单，如需放行必须显式修改守卫代码（可见、可 Review）。

## 10. Contract / 数据影响

### 10.1 不变项（明确声明）

- Endpoint / HTTP Method / Path 参数 / Query 参数 / Request Body / Response Schema / 字段类型 / nullable：**全部不变**。
- 错误码、`reason`、错误顺序（401 → 403 → 422 → 404 → 409）、403 CSRF/角色语义：**不变**。
- 权限：仍仅 `USER_ADMIN`，不新增 Permission / ROLE_PERMISSIONS / 角色。
- 审计：`object_type` / action / 白名单 / 同事务：**不变**。
- 数据库：无 Schema / Migration / 索引 / 约束 / 触发器变更；DB-D401–D420 有效。

### 10.2 需补正文

| 文件 | 变更 | 状态 |
| --- | --- | --- |
| `docs/api/F026.md` | 头部签核块 → v3；§5 追加「非唯一完整性错误语义」；§12 签核 v3 行；§13 修订记录 v3 行 | Contract **READY**（本 Gate 签核字面；CONTRACT Gate 落盘） |
| 12 份域 Contract | 追加节末尾 1 行签核注记 + 修订记录 1 行（见 §3.2） | 同上 |
| `docs/api/F027.md` | **不改**（见 §14 O1） | 不变 |

### 10.3 数据完整性对应（引用 `implementation-rules.md` / data-integrity Skill，不重复业务规则）

| 规则依据 | DB 保证 | F030 动作 | 证据 |
| --- | --- | --- | --- |
| §23.2 有效授权唯一 | 部分唯一索引 `uq_…_user_id_cluster_id` | 只补真并发用例 | §6.1 |
| §23.2 撤销历史不删除 | 成对 CHECK + 单向 UPDATE + DELETE 触发器 | 无变更（F029 已断言 23514/23001/23505） | 既有用例 |
| 非唯一完整性错误语义 | 无 Schema 变化 | 记录现状 + 服务层证据 | §6.2、§8.2 |

## 11. Backend / Frontend 工作与文件

**Layer 1（文档/记录；协调器执行或指派 Backend，Architect 只提供字面）**
- `docs/api/F026.md`（v3）、`docs/api/{F002,F003,F004,F007–F014,F023}.md`（各追加 2 行）
- `docs/project/project-plan.yaml`：`decisions_required` 中 CHG010-BQ18 / BQ19 → CONFIRMED + `basis`（§4.2 字面）；`execution`、`evidence`、`implementation.*`、`not_required.database` 由协调器维护
- `docs/features/F030/architecture.md`（本文件）、`docs/features/F030/test-report.md`（Tester）

**Layer 2（Backend 注释）**
- `backend/app/services/cluster_authorization.py`：`list_authorizations` 注释（§8.1，仅注释）

**Layer 3（Backend 测试基础）**
- `backend/tests/conftest.py`：`auth_app` docstring（§9.1，仅文档字符串）
- `backend/pyproject.toml`：`real_scope` marker 说明文本
- `backend/tests/integration/test_cluster_authorizations.py`：新增 4 个用例（`q` 边界、并发、非唯一完整性错误、marked-canary）
- `backend/tests/integration/test_f030_test_harness.py`：新增（守卫，3 个用例）

**Layer 4（Frontend）**
- `frontend/src/components/authorizationCandidates.ts`（新增，纯逻辑）
- `frontend/src/components/ClusterAuthorizationPanel.tsx`（候选门控/重试/truncated 提示/错误判据修正）
- `frontend/scripts/smoke-client.mjs`：新增 `computeGrantCandidates` / `canSubmitGrant` 断言

**并行与所有权**：Layer 1 与 Layer 2–4 可并行；Layer 3 与 Layer 4 文件不重叠；Layer 1 的共享文档由协调器独占写入。

## 12. Test Work

### 12.1 验收映射（交 Test Design 细化）

| Product | 判据 | 证据类型 |
| --- | --- | --- |
| P1 | 13 份正文含签核五要素；F026.md §13 有 v3 行；12 份修订记录有新增行；正文声明「端点/字段/错误码/权限不变」 | 文档核对（read/grep 记录进 Test Report） |
| P2 | `validate_project_state.py` 通过；BQ18/BQ19 为 CONFIRMED，basis 含设计路径+版本+签核者+日期；`requirements-v3.md` §35.2/§35.3 无 diff | 计划读取 + 差异核对 |
| P3 | §5 十条断言通过；反空洞性成立 | 真实 PG 定向 |
| P4 | §6.1 并发（201+409、ACTIVE=1、Audit=1）；§6.2 非唯一完整性错误不被映射为 409 | 真实 PG 定向 |
| P5 | smoke 断言（门控/重试/truncated 传播/`canSubmitGrant`）+ typecheck + build；无新增端点/参数 | 前端机制级 |
| P6 | 注释与实际一致；F026.md §5 记录现状语义且映射未变 | 代码/文档核对 |
| P7 | 守卫 3 用例（legacy canary、AST 扫描、反空洞）+ marked-canary | 真实 PG 定向 |
| P8 | 定向套件；全量后端 = F029 基线 721 passed / 6 skipped + 新增；前端 322 passed + 新增；`tsc` / `vite build` 通过 | 日志归档 |
| P9 | 变更文件清单不含业务规则/授权语义/范围过滤/Audit/前端功能新增；无 Schema/Migration | 差异核对 |

### 12.2 环境与基线

- 真实 PostgreSQL（`TEST_DATABASE_URL`，`csm_test`），`-p no:cacheprovider`，SQLite/Mock 不作约束/并发证据。
- 后端基线：F029 `721 passed / 6 skipped`（收集数一致性 726 + 1 module skip）。
- 前端基线：F029 `322 passed`。

### 12.3 不可声明项

真实浏览器 DOM/焦点/窄屏；超大 ACTIVE 授权（>2000）真机压测；并发压力测试；全量 Compose 成功启动（环境限制沿用 F029 记录）。这些项必须在 Test Report 的「未验证」段如实列出。

## 13. 技术决策（DR-F030）

| ID | 决策 | 依据 |
| --- | --- | --- |
| DR-F030-01 | ①采用「Kind A 正文签核块 + Kind B 追加节签核行」，两者都落正文，均配修订记录行 | change-control §2；Product P1；F029-RV-01 |
| DR-F030-02 | 不改 `docs/api/F027.md` v1 | 避免 P9 范围漂移；v1 已含批准者/日期/版本/覆盖范围 |
| DR-F030-03 | BQ18/BQ19 只改 `decisions_required.status`/`basis`，`source`/`kind`/`affects`/`owner` 不变 | requirements §35.2 末段；change-control §2 |
| DR-F030-04 | 非唯一完整性错误用**真实 FK 违约**驱动（幽灵 `granted_by`），不 monkeypatch 生产函数 | 保留真实 DB 证据；可重复 |
| DR-F030-05 | 并发证据用两个独立 ADMIN 客户端 + `Barrier` + 真实提交，DB 断言为主判据 | Product N3；F019/F015 既有并发范式 |
| DR-F030-06 | 前端把候选计算抽为纯逻辑模块，交互正确性以 smoke 断言保障（不引入 DOM 测试框架） | AGENTS §2.6；现有 smoke 范式 |
| DR-F030-07 | 超大 ACTIVE 授权量：保留分页安全上限 + **显式 truncated 提示** + 服务端 409 为最终事实 | Product §3 边界守卫、N2 |
| DR-F030-08 | `real_scope` 守卫用 AST 扫描 + 双向 canary + 反空洞断言，不设通用豁免名单 | Product P7；避免静默放行 |
| DR-F030-09 | F030 不需要 Database Gate（`database=false`，`not_required.database` 记录理由） | 无 Schema/Migration 变化 |

## 14. 风险与待决

| ID | 类型 | 内容 | 处置 |
| --- | --- | --- | --- |
| R1 | 风险 | TestClient 双客户端并发在 CI 环境可能不稳定 | 主判据放在 DB 断言；若线程化 HTTP 客户端不稳定，退回**服务层两连接**（仍须保留同样的 DB 断言），**不得**用顺序调用替代；Tester 在 Test Report 记录采用形态 |
| R2 | 风险 | 12 份 Contract 编辑可能夹带语义变化 | 仅允许「追加行」；Review 逐文件 diff 核对；任何正文改写回退 |
| R3 | 风险 | 计划状态变更可能写入不实签核者/日期 | 仅写 Architect 2026-10-23、Database 2026-10-21；不写 Backend 签核 |
| R4 | 风险 | AST 扫描误报/漏报 | 用 AST 而非正则；反空洞断言（扫描数、已知标记模块集合） |
| R5 | 风险 | 前端无 DOM 测试，可能夸大覆盖 | 只声明机制级；Test Report 列「未验证」 |
| R6 | 风险 | `already_granted` 后重新加载候选若失败可能叠加错误 | 重新加载失败仅内联提示，不阻塞关闭；`SuccessState` 不误报 |
| O1 | 待决（PROPOSED，非阻塞） | 是否给 `docs/api/F027.md` v1 头部补「确认来源」一行 | 本设计判定**不做**；若协调器认为 BQ18 引用要件不足，仅加一行记载不改正文 |
| O2 | 待决（协同） | `decisions_required`、Contract 正文、plan evidence 的落盘执行者 | 协调器（或指派 Backend），Architect 只供字面 |
| O3 | 待决（协同） | 落盘日期须与 plan 记录一致 | 不得编造日期 |
| O4 | 观察 | requirements §35.2 仍写「DESIGN_INPUT…在 F026–F027 签核」 | 正文不改；计划状态变更不构成需求修订 |

## 15. Gate 声明

本阶段为只读设计分析，**未修改任何仓库文件**。方案、layers、api_required、Contract 字面（F026 v3 与 12 份签核行）与验证策略已明确，可交 Test Design 核对可验证性并交 CONTRACT Gate 落盘。

- 下一责任角色：Tester（TEST_DESIGN）；随后 Architect 定稿（`READY FOR IMPLEMENTATION`）+ 协调器落盘 Contract/计划。
- Database：按 §2 判定 NOT_REQUIRED；若 Database 认为触及 Schema 语义，返回 Architect，不得直接改设计。

**Status：READY FOR DESIGN**

## 16. 最终设计定稿（CONTRACT Gate）

- **签核者**：Architect
- **日期**：2026-10-23
- **结论**：**READY FOR IMPLEMENTATION**（本 Feature 设计定稿；Contract 已按 §3/§4/§8/§10 字面落盘并逐项核对）

### 16.1 核对对象版本

| 对象 | 版本 / 状态 | 核对结论 |
| --- | --- | --- |
| `docs/api/F026.md` | **v3**（READY） | 头部状态/版本/签核/覆盖范围/确认来源齐全；§5「非唯一完整性错误语义」与 §8.2 字面一致且未改变既有 409/422 映射；§12 v3 行与 §13 v3 行日期一致；端点/字段/错误码/权限/错误顺序不变 |
| `docs/api/{F002,F003,F004,F007,F008,F009,F010,F011,F012,F013,F014,F023}.md` | 各「F027 范围语义（加法引用）」增补节 **v1**（独立于正文版本） | 12/12 节末含签核五要素（签核者/日期/对象路径/覆盖范围/确认来源+上游依据）；修订记录各新增 1 行且列数与表头一致（F002 3 列、其余 4 列）；未发现正文语义变化 |
| `docs/api/F027.md` | v1（**不变**，DR-F030-02） | 头部批准要素自足；本 Feature 不改其正文 |
| `docs/database/f026-cluster-authorization.md` | v1（Database 2026-10-21；DB-D401–D420） | F030 不改设计；DB 层无表/列/索引/约束/迁移变更 |
| `docs/features/F030/test-report.md` | TD-1 v1（TEST DESIGN READY） | P1–P9 全覆盖，断言/反空洞与最终 Contract 字面一致 |
| `docs/project/project-plan.yaml` | plan_revision 16 | CHG010-BQ18 / BQ19 = **CONFIRMED**，`source/kind/affects/owner` 不变，basis 引用已签核设计正文路径+版本+签核者+日期；`pending_changes=[]`；`acceptance.status=PENDING`；layers（database=false/backend=true/frontend=true）、api_required=true、`implementation.database=NOT_REQUIRED` 与本文件 §2 一致 |
| `docs/product/requirements-v3.md` | revision 11 | §35.2（BQ18/BQ19 仍为 DESIGN_INPUT 原句）与 §35.3 未改写；未新增业务规则 |

### 16.2 覆盖范围

- 本文件 §3–§10 的全部设计落点：①Contract 签核记载（Kind A + Kind B）；②BQ18/BQ19 计划状态与依据收敛；③`q` 边界断言；④真并发与非唯一完整性错误；⑤前端候选门控/重试/超大授权量提示；⑥`list_authorizations` 注释与 F026 §5 现状语义；⑦`real_scope` 默认规则约束。
- 不变项确认：Endpoint / HTTP Method / 参数 / Request / Response Schema / 字段类型 / nullable、错误码与 error 顺序（401→403→422→404→409）、权限（仅 `USER_ADMIN`）、Audit 口径、数据库 Schema 与 Migration（DB-D401–D420 继续有效）。
- **Contract 状态：READY**（`docs/api/F026.md` v3 与 12 份域 Contract 增补节 v1 已落盘并被本 Gate 核验接收）。

### 16.3 关闭项

| 项 | 状态 | 依据 |
| --- | --- | --- |
| F030 P1（Contract 签核完整） | 设计面 CLOSED | 13 份正文签核五要素 + 版本/修订记录一致性核对通过（测试证据待 TEST） |
| F030 P2（设计输入收敛） | 设计面 CLOSED | BQ18/BQ19 = CONFIRMED，basis 引用 DB v1 / F026.md v3 / F027.md v1 / F026/F027/F030 architecture；需求正文未改写 |
| F029-RV-01（Contract 签核记载缺失） | **CLOSED**（合同面） | F026 v3 §12/§13 + 12 份签核行 |
| F029-RV-08（非唯一完整性错误语义缺证据/记载） | 记载面 **CLOSED**；证据待 TEST | F026 §5 现状语义 + §6.2 服务层用例设计 |
| F029-RV-03（并发缺口）、RV-05/RV-06（前端交互与覆盖声明） | 设计面 CLOSED，证据待 TEST | §6.1 / §7 |
| CHG010-BQ18 / BQ19 | **CONFIRMED** | plan `decisions_required` + requirements §35.2 未改写 |

### 16.4 遗留（不阻塞实现）

- I-1：TD-1 引用未定义的「Issue I-1 / I-3」，须由 Tester 在 TEST 判定前补齐 PASS/FAIL 口径。
- I-2：已同批修正：`F026.md` §12 首条 bullet 已改为 v1/v2/v3 历史记载。
- I-3：TD2-P3.1 文案计数（「四条」实为 5 条）与 TD2-P3.2 正向对照细化，须在 TEST Report 记录与 §5 字面的差异。
- I-4：已同批补充：`F026.md` §13 v3 行含「F029-RV-01/RV-08」追溯 token。
- I-5（沿用 §14 O1）：`docs/api/F027.md` v1 头部「确认来源」一行仍不补；若后续认为 BQ18 引用要件不足，仅加一行记载。
- I-6：纯追加性（删除行 = 0）、requirements 空 diff、收集数一致性由 TEST 阶段按 TD2-P1.4 / P2.3 / TD-3 命令实地核验；本 Gate 未执行 git/脚本核对。

### 16.5 绑定与复核

- 本定稿绑定：requirements revision 11；`docs/api/F026.md` v3；12 份域 Contract 增补节 v1；`docs/api/F027.md` v1；DB 设计 v1（2026-10-21）；TD-1 v1；plan_revision 16。
- 上游发生变更时仅复核受影响部分，不要求无变化内容重复设计。
- 实现放行后任何涉及端点/字段/错误码/权限/错误顺序/Schema 的变更即超出本设计边界，须回 Product/用户按 `docs/project/change-control.md` 处理。

**Status：READY FOR IMPLEMENTATION**


## 17. F031 errata（2026-10-23，Architect，F031 签核）

本节由 F031 追加，用于记录 F030 Review 的非阻塞跟进（F030-RV-03/04/05/09）。**不改变 Contract、不改变行为、不使 F030 验收 P1–P9 失效**；与 §7.2/§8.1/§16 冲突时以本节为准。

### 17.1 `canSubmitGrant` 实际签名（取代 §7.2 code block 与规则行）

```ts
export function canSubmitGrant(
  active: ActiveGrantLoad,
  candidates: GrantCandidates,
  selectedClusterId: string,
  busy: boolean,
): boolean
```

判定规则：`busy === false` 且 `selectedClusterId !== ""` 且 `active.kind === "success"` 且 `candidates.kind === "success"` 且选中集群仍存在于 `candidates.clusters` 时为 `true`。实现比 §7.2 草案多 `candidates` 参数与候选成员校验，**更严格，不放松任何已签核语义**。权威实现位置：`frontend/src/components/authorizationCandidates.ts::canSubmitGrant`。

### 17.2 候选空态文案（取代 §7.2 表「加载成功、候选为空」行）

```tsx
<EmptyState description="没有可授予的集群（已有效授权的集群不会重复出现）" />
```

该文案在「全部已授权」「搜索无匹配」「系统无 Cluster」三种成因下均成立；不按成因分支显示不同文案（属后续产品决定）。

### 17.3 追溯引用口径（取代三处「架构评审 I-2」）

`ClusterAuthorizationPanel.tsx` 与 `frontend/scripts/smoke-client.mjs` 中关于「旧选中集群」的注释统一指向 `authorizationCandidates.ts::canSubmitGrant` 与本文件 §17.1，不再引用不存在的「架构评审 I-2」。F030 test-report 中 F030-T02 的历史措辞不改写，由 F031 test-report 记录正确指向。

### 17.4 §8.1 注释字面（取代 §8.1 引用的注释文本）

`backend/app/services/cluster_authorization.py::list_authorizations` 注释明确：路径对象优先（未知/非 UUID 账号先 404，`q` 仅在账号存在后校验）；类型化查询参数在 route/handler 前拒绝；未声明参数由 `_reject_unknown_query` 在 handler 第一步拒绝，先于路径与语义校验；该端点仅 `USER_ADMIN`，注释结论不构成信息泄露加固承诺。

### 17.5 结论

§16.1「实现与最终设计一致」的表述以 §17 为准。上述 errata 仅为记载/文案/注释层面修订，不改变端点、参数、字段、错误码、错误顺序、权限、Audit 或 Schema。
