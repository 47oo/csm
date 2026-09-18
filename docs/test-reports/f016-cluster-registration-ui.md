# Test Report — F016「Cluster 登记与改名 UI」

> Status: `READY FOR REVIEW`（前端实现层；Integration = **NOT TESTED**）
> Author Role: tester
> Date: 2026-09-18
> Feature Branch: `feature/F016-cluster-registration-ui` ｜ start_commit `67a498f` ｜ 候选 HEAD `6388134`

> **协调器注记**：本报告由 Tester 独立产出。协调器**不采信其测试声明**，已另行独立复核（见文末「协调器独立复核」）。
> Tester 的 14 条对抗探针为**临时**文件并在验证后删除（该决定与理由见「Unverified Areas」与「观察项」）。

## Feature

F016「Cluster 登记与改名 UI」— 为已冻结的 `POST /api/clusters` / `PATCH /api/clusters/{id}` 补上前端登记与改名入口，两者共用同一 `ClusterFormDialog.vue`。纯前端 Feature（`database: false` / `backend: false` / `frontend: true`）。

## Test Basis

- 产品验收基准：`docs/product/handoffs/f016-cluster-registration-ui.md`（AC-01 ~ AC-17）。
- 架构基准：`docs/architecture/f016-cluster-registration-ui-handoff.md`（REQUIRED #1~#10、Risks R1~R9、「需要 Tester 独立验证的关键点」6 条、Verification Strategy）。
- API 契约（只读）：`docs/api/f001-cluster.md` §2 / §3.1 / §3.5 / §5 / §7。
- 领域规则：R-CLUSTER-001/002/003/005、§6 / §13 / §17 / §21 / §22、R-QUERY-004。
- 全局规则：`AGENTS.md` §7（未验证不得声称正确）、§21（前端不重复实现业务校验）。

## Environment

- Node `v24.14.0`、npm `11.9.0`；`vitest 5.0.1` / `happy-dom`；前端测试以 `fetch` 桩替换，**不触达真实后端**。
- 未启动真实 Backend / 数据库；无浏览器自动化环境。
- 测试均在 `feature/F016-cluster-registration-ui` 工作树内执行；本 Tester 未执行任何 Git 命令。

## Acceptance Criteria Mapping

| AC | Test | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 登记入口可达 | `clusterListPage.spec.ts` F016 describe + 自写 T-PROBE-5 | PASS | 列表页头部 `[data-testid=open-create-dialog]` 存在，`loading`/`empty`/`error` 三态下均可达；点击后 `ClusterFormDialog` `modelValue=true` |
| AC-02 改名入口可达 + 预填 | `clusterDetailPage.spec.ts` F016 describe | PASS | 内容态 `[data-testid=open-edit-dialog]`，edit 模式 `cluster-form-name` 值为 `cluster-a` |
| AC-03 同一对话框 | 源码审查 + 两页组件断言 | PASS | `frontend/src/components/` 仅 `ClusterFormDialog.vue` 一个 Cluster 表单；被 `ClusterListPage`(create) / `ClusterDetailPage`(edit) 各引用一次，无第二套表单 |
| AC-04 仅一个字段 | `clusterFormDialog.spec.ts` + 自写 T-PROBE-4 | PASS | `.el-form-item` 恰 1；`.el-select` / `.el-input-number` / `.el-date-editor` 均 0；文案不含 状态/DataCenter/机柜/上级/deleted_at |
| AC-05 零客户端业务校验/变换 | 静态 guard + 组件探针 + **对抗注入（3 组）** | PASS | guard 4 例通过；空名可提交、` a/b ` 逐字节原样、同名 GET 桩仍只 1 次 POST；注入 A/B/C 均使 guard/探针失败 |
| AC-06 登记请求与成功反映 | `clusterFormDialog.spec.ts` + `clusterListPage.spec.ts` | PASS | `POST /api/clusters` body `{"name":...}`；201 → 关闭 + `emit openDetail(9)`；`App.vue` 既有 `@open-detail="openClusterDetail"` 接线跳新集群详情，无需手工刷新 |
| AC-07 登记失败按 `error.code` | 自写 T-PROBE-2/3 + `clusterFormDialog.spec.ts` | PASS | 400 渲染 `请求校验失败`+字段 `name`；409 渲染 `已存在活跃的同名集群`+不关闭/不清空；401 仅全局处理无本地提示；500/网络/未知码走 default；矛盾 message 不参与分支 |
| AC-08 登记失败不误报成功 | `clusterListPage.spec.ts` F016 describe | PASS | 409 时无 `openDetail`、对话框保持打开、列表未刷新（恰 1 GET + 1 POST） |
| AC-09 改名请求与成功反映 | `clusterFormDialog.spec.ts` + `clusterDetailPage.spec.ts` | PASS | `PATCH /api/clusters/1` body `{"name":...}`；200 → 关闭 + `run()` 重读，展示新 `name` 与新 `updated_at` |
| AC-10 改名失败按 `error.code` | 自写 T-PROBE-2 + `clusterDetailPage.spec.ts` | PASS | 400/409/404/401/其他 分支文案与「保持打开」行为符合架构固定文案表；404 create/edit 文案分流正确 |
| AC-11 改为自身名不误报 | `clusterFormDialog.spec.ts` + `clusterDetailPage.spec.ts` | PASS | 不修改预填名直接提交 → 按 200 成功，无 `[data-error-code]` |
| AC-12 旧名释放前端不维护 | `clusterFormDialog.spec.ts`（改后以旧名 create） | PASS | 改 `cluster-a→cluster-b` 后，create 以 `cluster-a` 仍直发 POST，无本地占用状态 |
| AC-13 提交中保护 | `clusterFormDialog.spec.ts` + 探针 | PASS | 提交中按钮 `is-loading`，连点不产生第二个写请求 |
| AC-14 取消不写入 | `clusterFormDialog.spec.ts` + `clusterListPage.spec.ts` | PASS | 取消仅关闭，`fetch` 未被调用、列表行数不变 |
| AC-15 错误可关闭/表单不锁死 | `clusterFormDialog.spec.ts` | PASS | 关闭 alert 后再次修改并提交成功（第二次 POST body 为新值） |
| AC-16 既有三态 / Empty vs Not Found 不变 | 重跑既有 spec + 自写 T-PROBE-5/6 | PASS | 列表 loading/empty/error 三态互异、请求计数正确；详情 404 为 `not-found` 且与列表 Empty 文案不同 |
| AC-17 既有删除 / F009 入口不变 | 重跑 `clusterListPage.spec.ts` / `clusterDetailPage.spec.ts` / `f009ClusterResourceView.spec.ts` | PASS | F014 行内/详情删除、409 文案、F002 `open-bare-metals`、F009 静态无恢复语义 token 全绿 |

## Database / Migration

不适用（`database: false`）。无 migration、无 Schema/约束变更；`clusters` 表 `ck_clusters_name_no_slash`、`ux_clusters_name_active` 未被触碰。

## Backend / API

- **无后端改动**（`backend: false`）；未启动后端、未执行后端测试。
- 静态一致性核对（非集成）：`frontend/src/api/clusters.ts` 与 `backend/app/clusters/router.py` / `schemas.py` 对齐：
  - `createCluster` → `POST /api/clusters`，body `{name:str}`，201 `ClusterRead`；
  - `updateCluster` → `PATCH /api/clusters/{cluster_id}`，body `{name:str}`，200；
  - `ClusterRead = {id,name,created_at,updated_at}` 封闭集合，与 `schemas.ClusterRead` 一致。
- 结论：静态签名/路径/方法/请求体一致；**未做真实 HTTP 联调**（见 Integration / Unverified）。

## Frontend

- 新组件 `ClusterFormDialog.vue`：create/edit 双模式、`name` 单字段、打开不请求、失败按 `error.code` 分支、401 交全局、提交中防重复。
- 接线为**纯加法**：列表页新增登记入口 + 对话框 + 成功 `emit openDetail`；详情页新增改名入口 + 对话框 + 成功 `run()` 重读。既有三态 computed、分页、F014 删除、F002 入口均未改。

## Integration

- **真实前后端 Integration Verification：NOT TESTED。** 未运行真实 Backend + 浏览器，未将前端接入真实 API。所有前端验证均基于 `fetch` 桩（严格按 `docs/api/f001-cluster.md` 构造响应），据此**不得**声称浏览器级端到端集成通过。
- 替代性核对：`api/clusters.ts` 与后端路由/schema 的**静态**一致性核对；`App.vue` 既有 `@open-detail` 接线的存在性确认（AC-06 成功导航链路完整）。

## Tester 自写探针清单（与既有测试不同的部分；**临时，验证后已删除**）

临时文件 `tests/__tester_probe_f016.spec.ts`（14 例）：

1. **T-PROBE-2** 错误分支精确条件与 message 无关性：
   - 400 顶层 `message` 与 `details[].message` 均写成「已存在活跃的同名集群」→ 仍渲染 `请求校验失败`；
   - 400 `details[].field` 缺失 → 回退渲染 `details[].code`；
   - 409 `field='name'` 但 `details[].code≠DUPLICATE` → 渲染通用「数据冲突」，**不**误报同名；
   - 409 `details[].code='DUPLICATE'` 但 `field≠name` → 同样渲染通用「数据冲突」。
2. **T-PROBE-3** 未知/未来错误码（`SERVICE_UNAVAILABLE`）→ default 分支渲染 code，不崩溃。
3. **T-PROBE-4** 恰一个 `el-form-item`、无 select/number/date；空名提交按钮未 disabled、POST body 恰为 `{"name":""}`。
4. **T-PROBE-4b** ` a/b ` 逐字节原样提交；同名已在 GET 响应中仍恰 1 次 POST、0 次 GET（零预检）。
5. **T-PROBE-5** 列表页在登记对话框已挂载时：`loading`（期间请求数恰 1）→ `empty`；`error` 态入口仍可达；翻页仅新增 1 次 GET。
6. **T-PROBE-6** 详情 404 → `not-found` 且无 `open-edit-dialog` / `open-bare-metals`。
7. **T-PROBE-7** edit 401：`setUnauthenticatedHandler` spy 被调用 1 次，无本地 `[data-error-code]`，对话框保持打开。

## 注入证伪记录（对抗注入 → 命中锚点 → 失败 → 还原）

基线 `ClusterFormDialog.vue` sha256 = `7f3cecd9ee69c140c8f7f048d5da9a2749375225ec82192aa47cb76249a3cccd`。每组注入前确认锚点真实命中，注入后运行 guard + 自写探针，随后从 pristine 副本还原并重算 sha256。

| 注入 | 内容（锚点确认） | 静态 guard | 组件/自写探针 | 还原后 sha256 |
| --- | --- | --- | --- | --- |
| A | `handleSubmit` 内 `if (form.name.includes('/')) return` + `form.name = form.name.trim()`（命中 149/150 行） | **FAIL**（`includes('/')`、`.trim`） | **3 FAIL**：原样提交、两条 400（提交被 `a/b` 拦截） | `7f3cecd9…cccd` ✅ |
| B | import 加 `listClusters` + create 前 `listClusters()` 重名预检 + `toLowerCase()`（命中 5/154/157 行） | **FAIL**（`toLowerCase`；import 集合非法；引用读 API） | **5 FAIL**：零预检、空名、两条 409 条件探针 | `7f3cecd9…cccd` ✅ |
| C | 提交按钮 `:disabled="submitting \|\| form.name === ''"`（命中 224 行） | **FAIL**（`disabled` 依赖 `form.name`） | **1 FAIL**：空名提交 | `7f3cecd9…cccd` ✅ |

三组注入均**同时**被静态 guard 与组件/自写探针捕获，证明 AC-05 保障具备可失败性，而非空转断言。还原后与 pristine 副本 sha256 逐字节一致，无注入残留（`grep` 0 命中）。

## 工程门禁真实输出摘要

- `npm run typecheck`（`vue-tsc --noEmit`）：**通过**，无输出/无错误。
- `npm run test` 第 1 次：**Test Files 40 passed (40)，Tests 604 passed (604)**，57.0s。
- `npm run test` 第 2 次：**Test Files 40 passed (40)，Tests 604 passed (604)**，56.9s。
- （还原后补跑）`npm run test` 第 3 次：**40 / 604 passed**，57.6s。
- F016 专项：`clusterFormDialog.spec.ts` + `clusterFormNoClientValidation.spec.ts` = **2 files, 27 passed**；连同回归 5 个 spec = **5 files, 92 passed**。
- 自写探针：**14 passed**（删除前）。
- `npm run build`：`✓ 1694 modules transformed`，`✓ built in 6.44s`（仅既有 chunk>500kB 警告，与 F016 无关）。

## 范围 / 冻结面核对（无 Git）

> 任务禁止执行任何 Git 命令，因此**无法**计算 `start_commit 67a498f → 6388134` 的逐字节 diff。以下为不依赖 Git 的最佳努力核对：

- `frontend/` 下本次涉及变更的文件恰为 7 个（3 个 `src`：`ClusterFormDialog.vue` 新增、两页加法；4 个 `tests`），其余 F016 表面文件 sha256 稳定。
- 冻结面内容核对：`docs/api/f001-cluster.md`、`backend/**`、`frontend/src/api/**`、`frontend/src/App.vue`、`frontend/package.json` 中**无任何 F016 / ClusterFormDialog / 登记集群 / 集群改名 引用**（`grep` NONE）。
- mtime 核对：上述冻结面文件均为检出时间 `2026-09-18 09:32:47`。
- **结论**：为「无 F016 触碰」的静态 / mtime 证据，**不等于** `git diff` 逐字节验证通过。

## Defects

**None。**

**观察项（Observation，非 Defect）**：`VALIDATION_ERROR` 分支把 `details[].field`（回退 `details[].code`）与 `details[].message` 作为**展示文本**透传；与架构 Handoff「details 仅展示、不参与分支」及既有 6 个 FormDialog 形态一致，**分支判定完全不读取 message**，不构成 AC-05 / §13 违规。

**覆盖缺口（Observation，非 Defect，供 Reviewer 权衡）**：Tester 的 14 条临时探针中，以下**边界分支**未被永久测试覆盖（Frontend 的 23 条永久探针覆盖了主路径，但未覆盖这些「细节不匹配」情形）：
- `409` 且 `details[].field === 'name'` 但 `details[].code ≠ 'DUPLICATE'` → 应走通用「数据冲突」而非同名文案；
- `409` 且 `details[].code === 'DUPLICATE'` 但 `field ≠ 'name'` → 同上；
- 未知 / 未来错误码（如 `SERVICE_UNAVAILABLE`）→ default 分支；
- `400` 的 `details[].field` 缺失 → 回退渲染 `details[].code`。

这些分支**当前实现正确**（Tester 已用临时探针实测 PASS），但缺失永久回归保护。**Owner：Frontend**。（协调器列为 LOW follow-up。）

## Unverified Areas

1. **浏览器级 E2E / 真实前后端 Integration**：未执行（无浏览器自动化环境、未启动真实 Backend）。前端全部验证基于 `fetch` 桩，严格不得声称端到端集成通过。
2. **逐字节 diff（`67a498f → 6388134`）与冻结面 byte-identity vs start_commit**：未执行（任务禁止 Git）；仅有内容 + mtime 证据。
3. **视觉 / 可访问性 / 响应式布局**：未做视觉回归与人工目视。
4. **真实浏览器下 Element Plus `el-dialog` 首开挂载行为**：测试基于 happy-dom + VTU，与真实浏览器存在差异。
5. `undefined_constraints`（空串 / trim / 长度 / NFC）的**业务**合法性未验证——按契约本就不予承诺，前端不得实现。

---

## Test Handoff

### Status

`READY FOR REVIEW`（前端实现层）；含明确的 Integration = NOT TESTED。

### Verified

- AC-01 ~ AC-17 全部 PASS。
- AC-05 零客户端业务校验：静态 guard 4 例 + 组件探针 + 3 组对抗注入全部有效证伪，还原 sha256 一致。
- 错误分支按 `error.code`（必要时 `details[].field`/`details[].code`）而非 `message`；401 仅触发全局处理器且无本地提示。
- 既有三态 / Empty vs Not Found / F014 删除 / F009 入口重跑通过。
- `typecheck` + `test ×2`（604/604）+ `build` 全绿。

### Not Verified

- 真实前后端 HTTP 集成 / 浏览器 E2E（无环境）；仅完成静态一致性核对。
- 逐字节 `git diff`（任务禁止 Git）；冻结面以内容 + mtime 证据核对。
- 视觉 / 可访问性 / 真实浏览器行为。

### Blocking Issues

None。

### Defect Owner

None（无 Defect）。

### 变更声明

未修改任何 `frontend/src/**` 或 `frontend/tests/**` 交付文件；注入均为临时且已逐字节还原（sha256 前后一致）。临时探针 `tests/__tester_probe_f016.spec.ts` 已删除。

---

## 协调器独立复核（不采信 Tester 声明，2026-09-18）

| 复核项 | 结果 |
|---|---|
| 工作树是否被 Tester 留下痕迹 | `git status --porcelain` **空**（无临时探针残留、无注入残留） |
| 组件是否逐字节还原 | `ClusterFormDialog.vue` sha256 = `7f3cecd9…cccd`，与已提交 `6388134` **`git diff` 无输出**（逐字节一致） |
| 临时探针文件是否已删 | `ls frontend/tests/ \| grep tester_probe` → **无** |
| 全量套件（协调器第 3 次独立运行） | **40 files / 604 tests passed** |
| 协调器自做注入（4 组：斜杠提前 return / trim / `listClusters` 重名预检 / 按空串禁用） | **全部被检出**，随后逐字节还原（sha256 前后一致）并复跑 604 passed |
| 冻结面 | `App.vue` / `frontend/src/api/**` / `package.json` / `backend/**` / `docs/api/**` **逐字节未改**（`git status` 印证）；受保护路径无任何改动 |
| 提交范围 | `6388134` 恰含 7 个预期文件（1485 insertions / **2 deletions**——1 处 import、1 处按钮移入 actions 容器） |

**协调器与 Tester 的独立结论一致**：AC-01~AC-17 PASS、无缺陷、无注入残留。差异仅在覆盖范围：Tester 额外用临时探针验证了 4 个「细节不匹配」错误分支（见「覆盖缺口」），协调器未重复该部分，而是记录为 LOW follow-up。
