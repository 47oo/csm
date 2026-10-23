# F031 F030 Review 非阻塞项收尾 — Architecture

- 状态：READY FOR IMPLEMENTATION（CONTRACT Gate 已签核；Database/Contract NOT_REQUIRED）
- 版本：v1（Architect，2026-10-23）
- Feature：F031（ENABLER，P2，M22）；plan_revision 17；分支 `feature/F031-review-closeout`；Base/start_commit `2c827fb`
- 需求依据：`docs/product/requirements-v3.md` revision 11（§23.2 CONFIRMED、§31、§32、§35）
- 产品依据：`docs/features/F031/product.md`（READY FOR ARCHITECT）
- 上游缺陷源：`docs/features/F030/review-report.md`（F030-RV-03…RV-10、F030-T03、Follow-up 4–7）
- 既有已签核设计（复用，不重开）：`docs/features/F030/architecture.md` v1 + §16；`docs/api/F026.md` v3；`docs/database/f026-cluster-authorization.md` v1（DB-D401–D420）；`docs/features/F030/test-report.md` TEST-1
- layers：database=false、backend=true、frontend=true；api_required=false

## 1. 方案摘要与边界

F031 只关闭 F030 Review 的 10 项非阻塞跟进，不改变任何已确认业务行为：不新增对象、关系、状态、唯一性、生命周期、权限项、错误码、reason、错误顺序、端点、参数、字段或 Schema；不重开 F026–F030 已交付范围；不修改需求正文。

| # | 跟进项 | 落点 | 类型 |
| --- | --- | --- | --- |
| ① | RV-03 `canSubmitGrant` 签名 errata | `docs/features/F030/architecture.md` | 设计记载 |
| ② | RV-04 候选空态因中性文案 | `frontend/src/components/ClusterAuthorizationPanel.tsx` | 文案 |
| ③ | RV-05 后端注释精确化 | `backend/app/services/cluster_authorization.py` | 注释 |
| ④ | RV-06 并发用例尝试次数/失败语义 | `backend/tests/integration/test_cluster_authorizations.py` | 测试可靠性 |
| ⑤ | RV-07 static 日志路径笔误 | `docs/features/F030/artifacts/p3-p6-static.log` | 证据说明 |
| ⑥ | RV-08 F026 头部 plan_revision 14 历史属性 | `docs/api/F026.md` 头部 | 记载澄清 |
| ⑦ | RV-09 悬空「架构评审 I-2」引用 | Panel/smoke 注释 | 追溯引用 |
| ⑧ | RV-10 `real_scope` 守卫范围 | 本文件 + F031 test-report | 边界记录 |
| ⑨ | T03 grant 路径端到端 500 信封 | `backend/tests/integration/test_cluster_authorizations.py` | 测试补充 |
| ⑩ | 不新增端点/字段/错误码/权限/Schema | §9 核对矩阵 | 核对 |

## 2. Layers 与 api_required

| 字段 | 值 | 理由 |
| --- | --- | --- |
| `layers.database` | false | 无 Schema/Migration 变更；T03 只为既有 FK 补端到端证据（测试）。`implementation.database=NOT_REQUIRED`。 |
| `layers.backend` | true | 注释 1 处 + 并发用例参数 + 新增集成用例。无生产逻辑变更。 |
| `layers.frontend` | true | 空态文案 1 处 + 注释 2 处。无 JSX 结构/API 调用/状态机变更。 |
| `api_required` | false | 无端点/参数/请求体/响应 Schema/错误码/reason/错误顺序/权限/Audit 变化。 |
| Contract | NOT_REQUIRED | 唯一触碰为 F026 头部新增 1 行历史依据说明；不升版本、不改 §1–§13 正文、不重签。 |

## 3. 逐项设计

### 3.1 RV-03：`canSubmitGrant` 签名 errata（仅文档）

实际签名（权威实现 `frontend/src/components/authorizationCandidates.ts`）：

```ts
canSubmitGrant(active: ActiveGrantLoad, candidates: GrantCandidates, selectedClusterId: string, busy: boolean): boolean
```

规则：`!busy && selectedClusterId !== "" && active.kind === "success" && candidates.kind === "success" && selectedClusterId ∈ candidates.clusters`。比 F030 §7.2 草案多 `candidates` 参数与候选成员校验，**更严格、不放宽**。

处理：在 `docs/features/F030/architecture.md` 头部追加 1 行指针，并在文末追加 `## 17. F031 errata（2026-10-23，Architect，F031 签核）`，包含：

- 17.1 实际签名与规则（取代 §7.2 code block 行 211 / 规则行 218）；
- 17.2 空态文案（取代 §7.2 表「候选为空」行 226）；
- 17.3 追溯引用口径（取代三处「架构评审 I-2」）；
- 17.4 §8.1 注释字面（取代 §8.1 行 245–255）；
- 17.5 结论：§16.1「实现与最终设计一致」以 §17 为准；erratas 不改变 Contract/行为，不使 F030 P1–P9 失效。

不改 §7.2/§8.1/§16 既有正文，不改代码。

### 3.2 RV-04：空态文案改回因中性

`ClusterAuthorizationPanel.tsx` 当前：

```tsx
<EmptyState description="该账号已拥有全部匹配集群的有效授权" />
```

改为 Base 的因中性字面：

```tsx
<EmptyState description="没有可授予的集群（已有效授权的集群不会重复出现）" />
```

不改门控逻辑；不调整 smoke 断言（smoke 只加载纯逻辑模块，面板 JSX 不参与；断言数保持 328）。不按成因分支显示不同文案（属产品新决定，超出 F031）。

验证：`grep` 限定 `frontend/src`，旧字面命中 0、新字面命中 1；`tsc --noEmit` exit 0；smoke 328。

### 3.3 RV-05：后端注释精确化（仅注释）

`backend/app/services/cluster_authorization.py::list_authorizations` 注释改为：

```python
    # Contract §3/§5 P-1: path object first — an unknown or non-UUID account is
    # 404 before any semantic query validation, so `q` is only validated after
    # the account exists. Typed query params (status/cluster_id/page/page_size/
    # sort/order) are rejected by the route before the handler; undeclared
    # params are rejected by `_reject_unknown_query` as the handler's first
    # step, before path and semantic validation — hence 422 even for an unknown
    # account. This is not an information-leak hardening measure: the endpoint
    # is USER_ADMIN only.
```

边界：不得改变任何可执行行；保留三条结论（路径对象优先 404 / `q` 在账号存在后校验 / 未知账号 + 非法参数 422）。验证：diff 非注释增删行为 0；`existence oracle` 命中 0。

### 3.4 RV-06：并发用例尝试次数

`test_concurrent_grant_two_connections_single_winner`：

- 引入 `MAX_ATTEMPTS = 5`，循环 `for attempt in range(1, MAX_ATTEMPTS + 1)`；
- 保持全部断言不变（201+409、409 reason、201 ACTIVE/effective、DB ACTIVE=1/总行=1/Audit=1/id 对齐）；
- 保持 `assert overlap_observed`（失败而非 skip；禁止顺序证据）；
- docstring 声明失败语义；
- 输出 `attempts used: n/5`。

证据强度不降低；日常仍 attempt 1 相交。

### 3.5 RV-07：static 日志路径笔误（仅追加 errata）

`docs/features/F030/artifacts/p3-p6-static.log` 第 8 行路径笔误（`backend/app/api/cluster_authorizations.py`，实际为 `backend/app/api/v1/...`）。处理：仅在文件末尾追加 errata 块，原文逐字节保留；说明路径笔误、结论由集成用例 TD2-P3.4 承担，并粘贴更正路径后的只读 grep 输出。不改 F030 test-report 历史证据。

### 3.6 RV-08：F026 头部历史依据说明

在 `docs/api/F026.md` 头部「上游依据」行之后新增 1 行：

```markdown
- **历史依据说明（F031 记载澄清，2026-10-23，Architect）**：「上游依据」中的 `plan_revision 14` 是 F026 v1/v2 的**历史批准依据**；本文件 v3 的签核依据为「确认来源」行的 `plan_revision 16`。本行仅澄清记载，不改变正文、版本及任何端点 / 字段 / 错误码 / 权限 / 错误顺序；因不改契约语义故版本保持 v3。
```

不升 v4（避免 12 份域 Contract 的 v3 引用失效）。验证：F026 diff 删除行 0；其余 `docs/api/` diff 空。

### 3.7 RV-09：悬空「架构评审 I-2」引用

三处引用改指向真实规则位置，不新造 I-2 条目：

- `ClusterAuthorizationPanel.tsx` 注释：`// 旧选中集群不在新候选中时，选择框不呈现该脏值且不可提交（规则见 authorizationCandidates.ts::canSubmitGrant；F030 architecture §17.1）。`
- `smoke-client.mjs` 文件头 F030 说明：`…旧选中集群已不在候选中时不可提交（规则见 canSubmitGrant；F030 architecture §17.1）…`
- `smoke-client.mjs` 断言内注释：`// 已授权集群不在候选中 → 即使被旧选中也不可提交（canSubmitGrant 候选成员校验）`

F030 test-report 为已 Review 历史证据，不改写；在 F031 test-report 登记正确指向。验证：`frontend/` 中「架构评审 I-2 / 架构 I-2」命中 0；smoke 328；tsc exit 0。

### 3.8 RV-10：`real_scope` 守卫范围（接受边界）

`conftest.py::auth_app` 的 legacy shim 只对 `tests/integration` 生效；`tests/smoke` 不使用 scope 符号，且没有 override 时走真实依赖，不存在「静默 legacy 通过」。因此守卫范围维持 `tests/integration`，不改代码；接受边界与 reopen 条件写入本文件与 F031 test-report。

reopen 条件：若未来 legacy shim 扩展到 `tests/integration` 以外，必须同步扩展守卫 `INTEGRATION_DIR`。

### 3.9 T03：grant 路径端到端 500 信封（测试专用）

新增集成用例 `test_grant_path_internal_error_envelope_end_to_end`，放在已标记 `real_scope` 的 `test_cluster_authorizations.py`：

- 用真实 Contract 路径 `POST /api/v1/users/{id}/cluster-authorizations`，真实 `require_permission`、真实服务层、真实 DB；
- 通过测试级 `auth_app.dependency_overrides[get_current_operator] = lambda: ghost` 注入 users 表中不存在的 `user_id`，使 `granted_by` FK 在 flush 时产生真实 23503；
- `TestClient(auth_app, raise_server_exceptions=False)`；
- 断言：500、精确 `{"error":{"code":"INTERNAL_ERROR","message":"Internal server error","details":{}}}`、无 Traceback/约束名/幽灵用户名泄漏、无授权行/无 Audit；随后真实操作者同一 pair 授予 201 作为归因对照；
- 断言 `auth_app.routes` 无 `/_test*` 路由；
- `try/finally` 清理 override；
- 不新增端点、不改生产代码。若 `get_current_operator` override 不可行，回退 F002 式测试专用路由，并在 Test Report 记录形态。

### 3.10 不新增项核对矩阵

| 检查 | 判据 |
| --- | --- |
| 端点 | `backend/app/api/**` diff=0；`auth_app.routes` 无 `/_test*` |
| 字段/Schema | `backend/app/schemas/**`、`models/**` diff=0 |
| 权限 | `permissions.py` diff=0；新增行无 `ROLE_PERMISSIONS`/`permission:` |
| 错误码/reason | 新增行无新 code/reason；仅复述既有 `already_granted`/`INTERNAL_ERROR` |
| DB | `backend/alembic/**` diff=0；head 仍 0015 |
| 前端契约层 | `frontend/src/api/**` diff=0；API 调用计数不变 |
| 需求正文 | `docs/product/**` diff=0 |
| Contract | `docs/api/` 仅 F026 头部 +1 行、删除行 0；除 F026 外的 15 份（含 F027）diff=0 |

## 4. Contract / 文档影响

- 端点/方法/参数/请求体/响应 Schema/字段类型/nullable/错误码/reason/错误顺序（401→403→422→404→409→500）/权限/Audit/分页排序过滤：全部不变。
- 数据库无 Schema/Migration/索引/约束/触发器变更；DB-D401–D420 有效。
- 唯一 Contract 文件触碰：`docs/api/F026.md` 头部新增 1 行历史依据说明；版本保持 v3；§1–§13 不变；不重签。除 F026 外的 15 份 Contract（含 F027）不改。

## 5. Implementation Layers

- L1 文档（协调器独占）：F030 architecture §17 + 头部指针；F026 头部 1 行；F030 p3-p6-static.log errata；F031 architecture/test-report；plan 字段。
- L2 Backend：`cluster_authorization.py` 注释；`test_cluster_authorizations.py` 并发参数 + 新增 T03 用例。
- L3 Frontend：Panel 文案 1 处 + 注释 1 处；smoke 注释 2 处。

L2 与 L3 文件不重叠，可并行；L1 共享文档由协调器独占。

## 6. Test Work

- 文档/静态：RV-03/04/05/07/08/09/10、⑩。
- 真实 PostgreSQL：RV-06 并发用例、T03 新用例；其余沿用既有套件。
- 必跑：
  1. 定向 3 文件 → 期望 **29 passed**；
  2. `-k "test_concurrent_grant_two_connections_single_winner or test_grant_path_internal_error_envelope_end_to_end"` → **2 passed**，含 `overlap=True` 与 attempts 计数（不要用宽泛 `concurrent_grant or internal_error_envelope`，会命中 F002 用例得 3）；
  3. `--collect-only` → **734 + 1 module skip**；
  4. 全量 → **729 passed / 6 skipped**（skip 原因集合不变）；
  5. 前端 `npx tsc --noEmit` exit 0、`npm run build` exit 0、`npm run smoke:client` **328 passed**；
  6. `validate_project_state.py` / `render_project_views.py`（不带 --write）。
- 不可声明：真实浏览器 DOM/焦点/窄屏、ACTIVE>2000 真机、并发压力、Compose 启动。

## 7. 技术决策（DR-F031）

| ID | 决策 |
| --- | --- |
| DR-F031-01 | T03 用真实 Contract 路径 + 测试级 `get_current_operator` override；不新增 `/_test` 路由、不改生产代码；回退 F002 式测试路由 |
| DR-F031-02 | F030 architecture 采用追加 §17 errata + 头部指针，不改写已签核正文 |
| DR-F031-03 | 空态文案采用 Base 因中性字面 |
| DR-F031-04 | 不因文案调整 smoke 断言、不抽模块 |
| DR-F031-05 | 悬空引用改指真实规则位置，不新造 I-2；F030 test-report 不改写 |
| DR-F031-06 | `real_scope` 守卫范围维持 `tests/integration`，记录接受边界与 reopen 条件 |
| DR-F031-07 | 并发用例仅提高尝试上限 3→5，失败语义与 DB 断言不变 |
| DR-F031-08 | static 日志与 F026 头部纯追加，删除行 0；F026 不升 v4 |

## 8. 风险与待决

| ID | 风险/待决 | 处置 |
| --- | --- | --- |
| R1 | T03 绕过认证，可能误读为认证证据 | docstring/Test Report 明示不透传 401/403 语义 |
| R2 | dependency override 污染 | try/finally pop；auth_app fixture teardown |
| R3 | 已签核文本被改写 | 只追加；删除行 0；不升版本 |
| R4 | 历史文档旧文案/I-2 残留 | 接受边界；grep 限定 `frontend/src`；F031 test-report 声明取代关系 |
| R5 | 计数变化误判回归 | 明确基线 28→29、728→729、733→734；smoke 328 不变 |
| R6 | 未来 legacy shim 范围扩展 | reopen 条件：同步扩展守卫目录 |
| R7 | 并发用例高负载仍可能红 | 保持红，记录 attempt/spans，不降级 |
| O1 | 空态按成因分文案 | 本 Feature 不做；如需由 Product 另裁 |

## 9. Gate 声明

本阶段只读设计分析，未修改仓库文件。layers/api_required 与 10 项实施设计明确，可交 TEST_DESIGN；Database NOT_REQUIRED；Contract NOT_REQUIRED（仅 1 行记载澄清）。

**Status：READY FOR IMPLEMENTATION**

## 10. 最终设计签核（CONTRACT Gate）

- **签核者**：Architect
- **日期**：2026-10-23
- **Gate**：CONTRACT（F031 最终设计定稿）
- **结论**：**READY FOR IMPLEMENTATION**
- **Contract 状态**：**NOT_REQUIRED**（唯一 Contract 触碰为 `docs/api/F026.md` 头部新增 1 行历史依据说明，不改端点/参数/请求体/响应 Schema/字段类型/nullable/错误码/reason/错误顺序/权限/Audit/分页排序过滤，不升版本、不重签）
- **Database**：**NOT_REQUIRED**（无 Schema/Migration/索引/约束/触发器变更；DB-D401–D420 继续有效）

### 10.1 核对对象版本

| 对象 | 版本 / 状态 | 核对结论 |
| --- | --- | --- |
| `docs/product/requirements-v3.md` | revision 11 | 有效，未改写 |
| `docs/features/F031/product.md` | READY FOR ARCHITECT | 10 项复用结论与 §1 一致，无新增业务规则 |
| 本文件 | v1 + §10 定稿 | 本文段为定稿 |
| `docs/features/F031/test-report.md` | TD-1 v1（TEST DESIGN READY） | 10 项已映射为 P1–P10 + TD-PROD/REG/PLAN |
| `docs/features/F030/review-report.md` | APPROVED WITH FOLLOW-UP，批准 HEAD `891206a` | F031 输入清单闭合口径一致 |
| `docs/features/F030/architecture.md` | v1 + §16（467 行） | 仅追加 §17 errata + 头部指针，不改写既有正文 |
| `docs/api/F026.md` | v3 | 头部 +1 行、版本保持 v3、§1–§13 不变、不重签 |
| `docs/api/` 其余 15 份（含 F027） | 既有版本 | diff = 0 |
| `docs/database/f026-cluster-authorization.md` | v1（DB-D401–D420） | 无变更 |
| `docs/project/project-plan.yaml` | plan_revision 17；用户 2026-10-23 授权 | 批准覆盖 F031；layers/api_required/not_required 与 §2 一致 |

### 10.2 覆盖范围

- 10 项跟进：①RV-03 签名 errata（§3.1）②RV-04 空态文案（§3.2）③RV-05 注释（§3.3）④RV-06 并发尝试（§3.4）⑤RV-07 日志 errata（§3.5）⑥RV-08 F026 头部（§3.6）⑦RV-09 引用（§3.7）⑧RV-10 守卫边界（§3.8）⑨T03 500 信封（§3.9）⑩不新增矩阵（§3.10）。
- layers：database=false、backend=true、frontend=true；api_required=false。
- 测试策略与 TD-1 T5 一致；计数基线 28→29、728→729、733→734、smoke 328 不变。

### 10.3 TD-1 缺陷处置

| ID | 处置 |
| --- | --- |
| F031-TD1-01 | **已修正**：§6 第 2 条改为精确 `-k "test_concurrent_grant_two_connections_single_winner or test_grant_path_internal_error_envelope_end_to_end"` → 2 passed |
| F031-TD1-02 | **已修正**：§3.7 注释同时覆盖「选择框不呈现脏值」与「不可提交」 |
| F031-TD1-03 | **已修正**：§3.10/§4 改为「除 F026 外的 15 份（含 F027）diff=0」；§3.6「12 份引用 F026 v3 的域 Contract」为另一集合，保留 |
| F031-TD1-04/05/06/07 | 非设计缺陷，Coordinator/Tester 落实，不阻塞 |

### 10.4 不变项

- 不新增/不改变：业务规则、对象、关系、状态、唯一性、生命周期、权限项、错误码、CONFLICT reason、错误顺序（401→403→422→404→409→500）、端点、HTTP 方法、参数、请求体、响应 Schema、字段类型、nullable。
- §23.2 授权与 Audit、F027 范围语义、F026 §5 非唯一完整性错误语义不变。
- 无 Schema/Migration/索引/约束/触发器变更；alembic 单 head 0015；DB-D401–D420 有效。
- F030 architecture §7.2/§8.1/§16、F026 §1–§13、F030 test-report 历史证据不改写（仅追加/头部 +1 行）。

### 10.5 接受边界

- F026 头部 +1 行以 TD-1 P6（版本/签核行字节不变、其余 15 份空 diff、code/reason 计数不变）作等价回归覆盖。
- T03 通过测试级 `get_current_operator` override 绕过认证，仅作 500 信封与零残留证据，不作为 401/403 语义证据。
- `real_scope` 守卫维持 `tests/integration`；reopen 条件：legacy shim 扩展到其它目录时必须同步扩展 `INTEGRATION_DIR` 与 AST 扫描。
- 空态按成因分文案不在本 Feature 范围。

### 10.6 遗留项（非阻塞）

| ID | 内容 | Owner |
| --- | --- | --- |
| L1 | 定向 3 文件在 TEST-1 具名并记录实际命令 | Tester |
| L2 | 不可声明项（浏览器 DOM/焦点/窄屏、ACTIVE>2000 真机、并发压力、Compose）在 TEST-1 明示 NOT TESTED | Tester |
| L3 | TD-1 P3-A3 旧短语 grep 处理注释换行，避免假阴性 | Tester |
| L4 | plan scope ⑨ 的「测试专用路由」以设计主路径 override 为准；回退路由仅在不可行时使用并记录 | Coordinator |
| L5 | F026 头部 +1 行按 §3.6 原文落盘 | Coordinator |
| L6 | TEST 显式覆盖 55432；artifacts `git add -f`；acceptance 恢复口径 | Coordinator |

### 10.7 绑定与复核

- 本签核绑定 10.1 所列版本；上游变化时仅复核受影响部分。
- 放行后触及端点/字段/错误码/权限/错误顺序/Schema 的变更即超出边界，须回 Product/用户。
- 实现必须逐项满足 §3 与 §6；未执行项不得声明为已验证。

**Status：READY FOR IMPLEMENTATION**
