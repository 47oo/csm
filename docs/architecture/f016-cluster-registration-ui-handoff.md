# Architecture Handoff

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-18
> Feature: **F016「Cluster 登记与改名 UI」**

## Feature

F016「Cluster 登记与改名 UI」— 为已冻结的 `POST /api/clusters` / `PATCH /api/clusters/{id}` 补上前端登记与改名入口，两者共用同一 `ClusterFormDialog.vue`。纯前端缺口闭合。

## Product Source

- `docs/product/handoffs/f016-cluster-registration-ui.md`（`READY FOR ARCHITECT`，AC-01 ~ AC-17，无 Blocking Open Questions）
- `docs/api/f001-cluster.md`（`READY`，已冻结；§2 资源表示、§3.1 `POST`、§3.5 `PATCH`、§5 错误语义、§7 `undefined_constraints`）
- `docs/architecture/f001-cluster-handoff.md`（Frontend Work §6 / 决策 §7 矛盾已加 F016 更正注记）
- `docs/architecture/adr/adr-0001`（技术栈）、`adr-0003`（资源标识与错误信封；R-CLUSTER-005 关系）
- `docs/database/csm-v1-schema-design.md`（只读；本 Feature 不改 schema）
- 既有前端：`frontend/src/api/clusters.ts`、`api/http.ts`、6 个 `*FormDialog.vue`、`pages/ClusterListPage.vue`、`pages/ClusterDetailPage.vue`、`App.vue`、`composables/useAsyncQuery.ts`、`useClusterDelete.ts`、`components/ListStates.vue` / `ErrorState.vue`、`frontend/tests/*`
- `docs/project/v1/project-plan.yaml`（F016 条目已存在，`depends_on: [F001, F013, F014]` 均 DONE）

## Architecture Summary

**当前系统状态（已核实，非空项目）**

| 项 | 现状 |
|---|---|
| Backend | 已存在；`POST /api/clusters` / `PATCH /api/clusters/{id}` 已实现、已测试、契约冻结 |
| API 客户端 | `frontend/src/api/clusters.ts` 的 `createCluster` / `updateCluster` / `ClusterWriteBody` / `ClusterRead` **已存在**，是契约 1:1 映射，当前 0 调用者 |
| Frontend 基座 | `api/http.ts`（`ApiError` + 全局 401）、`useAsyncQuery`、`ListStates` / `ErrorState`、6 个 `*FormDialog.vue`（`mode: 'create' \| 'edit'` 双模式 + 按 `error.code` 分支的 `failureView`，**各自内联、无公共 composable**） |
| 目标页面 | `ClusterListPage.vue`（三态 + 分页 + F014 行内删除）、`ClusterDetailPage.vue`（三态 + F014 删除 + F002「查看裸金属」） |
| 导航 | `App.vue` 极简视图状态，**无 vue-router**；`ClusterListPage` 已 emit `openDetail` 并被 App 接线；`ClusterDetailPage` 已 emit `back` / `openBareMetals` |
| Database | `clusters` 表已冻结，**本 Feature 不改** |

**方案要点**

1. 新增 `frontend/src/components/ClusterFormDialog.vue`：`create` / `edit` 双模式，**恰一个输入字段 `name`**，提交按钮**不因名称内容禁用**（与既有 FormDialog 的关键差异，见 REQUIRED）。
2. `ClusterListPage` 头部加「登记集群」入口（`mode="create"`）；`ClusterDetailPage` 内容态 actions 加「改名」入口（`mode="edit"`，预填当前 `name`）。
3. 登记成功 → `emit('openDetail', created.id)` 跳转新集群详情（**复用 App.vue 既有接线，零 App.vue 改动**）；改名成功 → `run()` 重读详情。
4. 错误渲染与既有 FormDialog 形态一致（内联 `failureView`，**不抽公共 composable**），按 `error.code`（必要时 `details[].code` / `details[].field`）分支固定文案，**不解析 `error.message`**。
5. 「前端不实现业务校验」落成**可失败的静态 guard + 组件级探针**（AC-05），并把「不得引入读/预检调用」列为最高风险。
6. 不引入任何依赖 / 不改 `App.vue` / 不动 `docs/api/f001-cluster.md` / 不动 F014 删除与三态。

## Domain Impact

**无。** 本 Feature 只消费 `Cluster`（R-CLUSTER-001/002/003/005、§21、§22）。不新增/修改领域对象、字段、关系、状态、唯一性规则；不实现 `undefined_constraints`；不实现 R-CLUSTER-004（无结构）、R-DELETE-*（读取侧后果已由既有契约保障）。

## Data Layer Impact

**无。** `database: false`。无表 / 列 / 关系 / 索引 / 唯一性约束 / migration 变更。`clusters` 表与 `ck_clusters_name_no_slash`、`ux_clusters_name_active` 保持冻结，本 Feature 不触碰。

## Backend Work

`None`（`backend: false`）。不新增 / 修改 / 删除任何端点，不改 `docs/api/f001-cluster.md` 语义，不改 `backend/**`，不新增 migration，不实现 `undefined_constraints`。

## Frontend Work

### 1. 新增 `frontend/src/components/ClusterFormDialog.vue`

**组件契约（props / model / emits）**

```ts
const props = defineProps<{
  mode: 'create' | 'edit'
  /** edit 模式：当前 Cluster（表单初值）；create 模式忽略。 */
  cluster?: ClusterRead | null
}>()

const emit = defineEmits<{
  /** 登记或更新成功，携带服务端返回的 ClusterRead（201 / 200）。 */
  success: [cluster: ClusterRead]
}>()

/** 可见性：沿用既有 FormDialog 的 defineModel 形态（v-model）。 */
const dialogVisible = defineModel<boolean>({ required: true })
```

- **不新增 cancel emit**：取消 = 仅由父组件把 `v-model` 置 false（与 6 个既有 FormDialog 一致），不发写请求、不改数据。
- **不重定义 `ClusterWriteBody` / `ClusterRead`**：它们是 `docs/api/f001-cluster.md` §2 / §3.1 / §3.5 的 1:1 映射，已存在于 `api/clusters.ts`。重定义会产生第二份契约来源并造成漂移（AGENTS §4「同一份详细信息只维护一个权威来源」）。Dialog 只 import 类型与 `createCluster` / `updateCluster`。
- **不新建请求层**：不直接 `fetch`，一律经 `apiRequest`（现有 `api/clusters.ts`）。

**内部状态与提交路径**

| 状态 | 说明 |
|---|---|
| `form = reactive({ name: '' })` | 唯一字段 |
| `submitting = ref(false)` | 提交中 Loading + 防重复 |
| `failure = ref<ApiError \| null>(null)` | 失败提示源 |

- `watch(dialogVisible, …, { immediate: true })`：打开时 `failure = null`；`edit` 且 `props.cluster` 非空 → `form.name = cluster.name`；否则 `form.name = ''`。
- `handleSubmit()`：
  - `if (submitting.value) return`
  - `create` → `await createCluster({ name: form.name })`
  - `edit` → 目标为 `props.cluster`，为空则返回；`await updateCluster(target.id, { name: form.name })`
  - 成功 → `emit('success', saved)` 后 `dialogVisible.value = false`
  - 失败 → 归一为 `ApiError`；`code === 'UNAUTHENTICATED'` 不设 `failure`（交全局会话失效）；否则 `failure = apiError`
  - `finally { submitting.value = false }`
- **`name` 原样提交**：不 trim、不折叠大小写、不检测 `/`、不做 NFC、不按空串拦截、不预检重名。
- **提交按钮禁用条件仅 `submitting`**：**不得**写成 `submitDisabled = form.name === ''`（这是既有 FormDialog 的常见写法，但 Cluster 的 `undefined_constraints` 明确空串行为未定义，前端不得据此拦截）。

**模板（与 6 个既有 FormDialog 同构）**

- `el-dialog` + 顶部 `el-alert`（`:data-error-code="failureView.code"`，`closable`，`@close="failure = null"`）。
- 仅一个 `el-form-item label="名称"`，`el-input v-model="form.name" data-testid="cluster-form-name"`。
- footer：取消按钮（`:disabled="submitting"`，`@click="dialogVisible = false"`）+ 提交按钮（`:loading="submitting"`，`data-testid="cluster-form-submit"`，`:disabled` 仅由 `submitting` 或显式禁用控制）。标题 / 提交文案按 `mode` 区分（「登记集群 / 登记」↔「集群改名 / 保存」）。
- **不在打开时拉取任何数据**（无 `listClusters` 选项加载，与 `BareMetalFormDialog` 不同）——保证挂载 / 打开不产生额外读请求，避免干扰列表页既有测试的请求计数与三态断言。

### 2. 接线 `ClusterListPage.vue`（登记入口）

- 头部 actions 增加 `<el-button type="primary" data-testid="open-create-dialog" @click="createDialogVisible = true">登记集群</el-button>`（镜像 `ContainerListPage`）。
- `const createDialogVisible = ref(false)`；`handleCreated(cluster: ClusterRead)` → `emit('openDetail', cluster.id)`（见 API Contract 与「成功导航」决策）。
- 挂载 `<ClusterFormDialog v-model="createDialogVisible" mode="create" @success="handleCreated" />`。
- **只做加法**：不改 `run()` / `isLoading` / `listEmpty` / `total` / 分页 / 表格列 / F014 删除接线，保证 `clusterListPage.spec.ts` 既有断言不变。

### 3. 接线 `ClusterDetailPage.vue`（改名入口）

- 内容态 actions（现「查看裸金属」+「删除集群」）增加 `<el-button plain data-testid="open-edit-dialog" @click="editDialogVisible = true">改名</el-button>`（镜像 `ContainerDetailPage` 的「编辑」）。
- `const editDialogVisible = ref(false)`；`handleUpdated()` → `void run()`（重读详情，展示新 `name` 与 `updated_at`）。
- 挂载 `<ClusterFormDialog v-model="editDialogVisible" mode="edit" :cluster="data" @success="handleUpdated" />`。
- **只做加法**：不改 `state` computed / `data-state` / `ErrorState` / F014 删除 / `open-bare-metals` testid。

### 4. 不改动

`App.vue`、`api/clusters.ts`、`api/http.ts`、`useAsyncQuery.ts`、`useClusterDelete.ts`、`ListStates.vue`、`ErrorState.vue`、其余 6 个 `*FormDialog.vue`、`package.json`（不引入依赖）。

**文件所有权**：`frontend/src/components/ClusterFormDialog.vue`（新）、`frontend/src/pages/ClusterListPage.vue`、`frontend/src/pages/ClusterDetailPage.vue`。

## API Contract

### Status

```text
READY
```

### Contract

**复用既有冻结契约，不新建契约文档。** 依据 `docs/api/f001-cluster.md`：

- 登记：`§3.1 POST /api/clusters`。Request `{"name": string}`（必填，非 nullable）；Response `201` 单对象 `{id, name, created_at, updated_at}`（§2 封闭集合）。
- 改名：`§3.5 PATCH /api/clusters/{cluster_id}`。Path param `cluster_id: integer`（写操作走 `id`，ADR-0003 §2）；Request `{"name": string}`（必填）；Response `200` 更新后单对象；改为自身当前名 → `200`（不得误报 409）。
- 错误语义（§3.1 / §3.5 / §5）：
  - `400 VALIDATION_ERROR`：缺 `name` / 非字符串 / 含 `/`；`details[].field == "name"`（含 `/` 时 `details[].code == "INVALID_CHARACTER"`）。
  - `409 CONFLICT`：活跃同名（大小写敏感）；`details[].field == "name"` 且 `details[].code == "DUPLICATE"`。
  - `404 NOT_FOUND`：**仅 `PATCH`** 目标不存在或已逻辑删除（两者不区分）。
  - `401 UNAUTHENTICATED`：交既有全局会话失效处理（`api/http.ts` → `App` 切回登录页），表单不渲染本地提示。
  - `5xx INTERNAL_ERROR` / 网络失败（前端本地码 `NETWORK_ERROR`）→ 通用失败提示。
- Empty / Not Found 语义：`POST` 无 Empty / Not Found；`PATCH` 的 `404` 是「目标不存在或已删除」的 Not Found（与列表 Empty 不同状态，本 Feature 不改该区分）。

**为何不需要新契约文档**：本 Feature 不改变任何请求 / 响应 / 错误结构，`createCluster` / `updateCluster` 已是契约 1:1 映射；新增契约文档会产生与 `docs/api/f001-cluster.md` 重复的权威来源。未确认协议决策：无（BLOCKED 不适用）。**`docs/api/f001-cluster.md` 保持逐字节冻结。**

## Test Work

Testing Agent 需独立验证（详见「Verification Strategy」与「需要 Tester 独立验证的关键点」）：

1. `ClusterFormDialog` 的请求构造（POST body 恒为 `{name}`；PATCH path 走 `id`）。
2. 错误分支由 `error.code` 驱动、文案固定、不解析 `message`（含注入「矛盾 message」的证伪）。
3. 前端零业务校验（静态 guard + 组件探针，经对抗注入证伪）。
4. 既有三态 / Empty vs Not Found / F014 删除入口 / F009 入口未被破坏。
5. `401` 触发全局处理器且不渲染本地提示。

## Technical Decisions

### CONFIRMED

- 契约冻结：`docs/api/f001-cluster.md`；技术栈（ADR-0001）；错误信封与按 `code` 分支（ADR-0003 §4）；写操作走 `id`（ADR-0003 §2）。
- 复用既有 `createCluster` / `updateCluster` / `ClusterWriteBody` / `ClusterRead` 与 `api/http.ts` 的 `ApiError` / 全局 401。
- 不引入依赖、不引入 `vue-router`，沿用 `App.vue` 视图状态。
- 业务校验（`/` 禁令、活跃唯一、大小写敏感、逻辑删除）由后端裁决（§21、§22、R-CLUSTER-002/005）。
- 纯前端：`database: false` / `backend: false` / `frontend: true`。

### REQUIRED

1. **登记与改名必须共用同一 `ClusterFormDialog.vue`**，仅 `mode` 不同；不得存在第二套表单（AC-03）。
2. **对话框恰有一个输入字段 `name`**；不得出现状态 / 位置 / 上级 / 计数 / 关系 / `deleted_at` 字段（AC-04）。
3. **前端不得实现任何业务守卫或名称变换**（AC-05）：不检测 `/`、不比对重名、不折叠大小写、不 `trim`、不做 NFC、不按空串拦截；`name` 原样提交。
4. **提交按钮禁用条件不得依赖 `form.name`**（空串 / 内容均不阻止提交）——`undefined_constraints` 未定义空串行为。
5. **`ClusterFormDialog` 不得引用任何读 / 预检 API**（`listClusters` / `getClusterByName` / `getCluster`）——唯一允许的调用是 `createCluster` / `updateCluster`。
6. **`ClusterFormDialog` 打开时不得发起任何请求**。
7. **错误渲染只按 `error.code` 分支**（必要时 `details[].code` / `details[].field`），固定文案，**不解析 `error.message`**。
8. **`401` 不渲染本地错误**，交 `api/http.ts` 的全局处理器；`handleSubmit` 的 catch 必须在 `code === 'UNAUTHENTICATED'` 时跳过设置 `failure`。
9. **不得改动既有三态、Empty vs Not Found、F014 删除入口**（AC-16 / AC-17）；对 `ClusterListPage` / `ClusterDetailPage` 只做加法。
10. **不得修改 `docs/api/f001-cluster.md`**、`backend/**`、`App.vue`、`api/clusters.ts`，不得引入新依赖。

### PROPOSED

1. **登记成功后导航到新集群详情**：`ClusterListPage.handleCreated(cluster)` → `emit('openDetail', cluster.id)`，复用 App.vue 既有 `@open-detail="openClusterDetail"`。理由：
   - AC-06 要求「无需手工刷新即可观察到新集群」。列表按 `id` 升序、`page_size` 默认 50，新集群 id 最大 → 在活跃集群 > 50 时不在当前页；仅刷新当前页**不保证**可观察。跳转详情用 `201` 返回的 `id` 直接展示，**必然可观察**。
   - 复用既有 emit/接线，`App.vue` **零改动**（进一步降低 `app.spec.ts` / 导航 spec 回归面）。
   - 与「登记成功后进入新资源详情」的既有产品先例（F007/F008 详情页登记 → `openDetail`）一致。
2. **改名成功后重读详情**（`run()`）展示新 `name` 与 `updated_at`（AC-09），不上抛 success 之外的事件。
3. **本 Feature 不实现列表行内改名**（PROPOSED-2 推迟）：产品仅要求详情页可达（AC-02）；列表页承载 F014 删除入口与三态的大量测试，行内新增入口会扩大 diff 与回归面，收益不足。属可逆 UI 选择，未来可无架构变更地追加。
4. **不抽公共 `failureView` composable**，在 `ClusterFormDialog` 内联同构实现。理由见「错误渲染路径取舍」。
5. 文件名 / testid 约定：`cluster-form-name` / `cluster-form-submit` / `open-create-dialog` / `open-edit-dialog`（工程约定，非产品规则）。

### OPEN

1. **`name` 的 `undefined_constraints`（NQ-1 / PROPOSED-3）**：空串 / `trim` / 长度 / NFC 是否升级为产品规则，仍待用户裁定；本 Feature 不实现（非阻塞）。
2. **列表行内改名（PROPOSED-2）**：是否后续追加（非阻塞，纯 UI）。
3. **文档同步（NQ-4，协调器职责，非实现范围）**：F001 handoff 的更正注记已存在；`project-plan.yaml` 已有 F016。协调器在落盘本 Handoff 时维持现状即可，不改产品规则。

## 错误渲染路径取舍（回应任务 #4）

**结论：不抽公共 composable，复制同构实现在 `ClusterFormDialog` 内。**

理由：

- 现有 6 个 `*FormDialog.vue` **各自内联** `interface FailureView` + `failureView` computed（已逐一确认无共享 composable）。
- 抽公共 composable 需**同时改 6 个既有文件**，会显著扩大 diff，并使既有组件测试（`bareMetalListPage.spec.ts`、`containerDetailPage.spec.ts`、`serviceListPage.spec.ts` 等大量耦合对话框内部文案 / testid 的用例）暴露在回归风险中；违反 AGENTS §5「不得顺便进行无关的大范围重构」。
- 各资源的 `failureView` 存在资源专属分支（如 create/edit 的 `NOT_FOUND` 文案、`CONFLICT` 的判别字段不同），抽象收益有限。
- 复制成本（约 40 行、形态固定）可接受；未来若确有重构需求，应作为独立 Feature / ADR 处理。

**`ClusterFormDialog` 的具体分支与固定文案**（`failureView` computed，`description` 全部为前端固定字符串；`details` 仅在 `VALIDATION_ERROR` 下透传以渲染 `details[].field` 标签）：

| `error.code` | 条件 | title | description |
|---|---|---|---|
| `VALIDATION_ERROR`（400） | — | 请求校验失败 | 提交的内容不符合要求，请根据下方字段提示修改后重试。 |
| `CONFLICT`（409） | `details.some(d => d.field === 'name' && d.code === 'DUPLICATE')` | 无法登记（create）/ 无法保存（edit） | 已存在活跃的同名集群（名称在所有当前有效集群中全局唯一、区分大小写）。 |
| `CONFLICT`（409） | 其他 | 数据冲突 | 保存的内容与现有数据冲突，请稍后重试。 |
| `NOT_FOUND`（404） | `mode === 'edit'` | 无法保存 | 该集群不存在或已被删除，可能已被其他操作移除。 |
| `NOT_FOUND`（404） | `mode === 'create'` | 提交失败 | 请求未成功（NOT_FOUND），请稍后重试。（契约下 POST 不产生 404；防御性兜底，按 code 原样展示） |
| `NETWORK_ERROR` | — | 无法连接服务器 | 请求未能送达服务器，请检查网络或服务状态后重试。 |
| `UNAUTHENTICATED`（401） | — | `null`（不渲染本地提示） | 交全局会话失效 |
| default（`INTERNAL_ERROR` / `UNKNOWN_ERROR` / 其他） | — | 提交失败 | 请求未成功（`${error.code}`），请稍后重试。 |

- `VALIDATION_ERROR` 的 details 渲染 `details[].field ?? details[].code ?? '字段'` 标签（指向 `name`）；分支判定**从不读取任何 message**（含 `error.message` 与 `details[].message`）。渲染 details 文本与既有 6 个对话框一致，仅为展示，不参与分支。
- 失败提示 `closable` + `@close="failure = null"`（AC-15「错误可关闭 / 表单不锁死」）。

## 「前端不实现业务校验」的可失败保障设计（回应任务 #5）

**形式 A：静态 guard 测试**（新文件 `frontend/tests/clusterFormNoClientValidation.spec.ts`，`readFileSync` 扫描源码，参照 `f009ClusterResourceView.spec.ts` / `ipAddressesApi.spec.ts` 的 `resolve(process.cwd(), 'src/...')` 风格）：

- 被扫描文件集合：`src/components/ClusterFormDialog.vue`、`src/pages/ClusterListPage.vue`、`src/pages/ClusterDetailPage.vue`（先剥离块注释 / 行注释，避免文档注释中的「不检测 `/`」等措辞误报）。
- 断言源码**不出现**以下 token（任一出现即失败）：
  - `/toLowerCase|toUpperCase/`（大小写折叠）
  - `/\.trim\s*\(/`（trim）
  - `/\.normalize\s*\(/`（NFC 归一化）
  - `/localeCompare/`
  - `/includes\s*\(\s*['"]\/['"]\s*\)/`、`/indexOf\s*\(\s*['"]\/['"]\s*\)/`、`/\bsplit\s*\(\s*['"]\/['"]\s*\)/`、`/\/\\\//`（`/` 检测）
  - 对 `ClusterFormDialog.vue` 额外断言：源码**不出现** `listClusters` / `getClusterByName` / `getCluster`（即无唯一性预检 / 存在性预检的读调用），且从 `'../api/clusters'` 的 import 名称集合**恰为** `{createCluster, updateCluster, ClusterRead}`。
- **它能被什么注入证伪**：注入 `if (form.name.includes('/')) return`、`form.name = form.name.trim()`、`form.name.toLowerCase()`、`form.name.normalize('NFC')`、`const existing = await listClusters(...)` 中的任意一种，guard 即失败。

**形式 B：组件级探针**（`frontend/tests/clusterFormDialog.spec.ts`）：

- 空名称提交：`setValue('')` → 断言 `cluster-form-submit` **未被 disabled** → 点击 → 断言恰好一次 `fetch`，method `POST`，body **恒为** `JSON.stringify({ name: '' })`。
- 含 `/` 与首尾空白：`setValue(' a/b ')` → 提交 → 断言 body 为 `{"name":" a/b "}`（**逐字节原样**，未被拦截、未 trim、未落为第二个请求）。
- 大小写 / 重名不预判：桩件让 `listClusters` 返回一个与输入同名的集群（若实现误加预检，会出现 GET）→ 断言提交**只有一次 POST**、且拿到 `409` 时渲染冲突文案；证明前端不预检。
- **它能被什么注入证伪**：注入空串拦截（探针 1 失败）、`trim` / 斜杠检测（探针 2 失败）、重名预检请求（探针 3 因出现额外 GET 失败）。

**边界声明（必须写入 guard docstring）**：本保障断言的是「前端未实现任何业务校验 / 变换」，**不是**「空名 / 空白名 / 含 `/` 名在业务上合法」；这些取值属 `undefined_constraints`，既不确认合法也不确认非法。若产品未来确认 PROPOSED-3，**必须由产品决策同步修改本 guard 与组件**，不得由实现方静默补校验。

## 测试面 / 文件清单与所有权（回应任务 #6）

| 文件 | 动作 | 覆盖 AC | 所有者 |
|---|---|---|---|
| `frontend/src/components/ClusterFormDialog.vue` | 新增 | —（实现） | Frontend |
| `frontend/src/pages/ClusterListPage.vue` | 修改（仅加法） | AC-01、AC-06、AC-14 | Frontend |
| `frontend/src/pages/ClusterDetailPage.vue` | 修改（仅加法） | AC-02、AC-09、AC-11 | Frontend |
| `frontend/tests/clusterFormDialog.spec.ts` | 新增 | AC-03、AC-04、AC-05、AC-06、AC-07、AC-08、AC-09、AC-10、AC-11、AC-13、AC-14、AC-15 | Frontend |
| `frontend/tests/clusterFormNoClientValidation.spec.ts` | 新增（静态 guard） | AC-05（可失败保障） | Frontend |
| `frontend/tests/clusterListPage.spec.ts` | 修改（新增 describe，保留既有全部用例） | AC-01、AC-06、AC-16、AC-17 | Frontend |
| `frontend/tests/clusterDetailPage.spec.ts` | 修改（新增 describe，保留既有全部用例） | AC-02、AC-09、AC-10、AC-16、AC-17 | Frontend |
| `frontend/tests/clustersApi.spec.ts` | **不改** | 既有请求构造 / 错误透传 | — |
| `frontend/tests/f009ClusterResourceView.spec.ts` | **不改** | AC-17 回归（ClusterDetailPage 无恢复语义 / 有 open-bare-metals） | — |
| 其余全部 `frontend/tests/*`、`src/api/*`、`App.vue` | **不改** | 既有回归 | — |

**明确保留不动的既有测试**：`clusterListPage.spec.ts` 的三态 / 分页 / 删除 describe；`clusterDetailPage.spec.ts` 的状态渲染 / A16 / 删除 describe；`f009ClusterResourceView.spec.ts` 全量；`app*` 导航 spec；`clustersApi.spec.ts`。新增用例只能是**追加**的新 `describe`，不得改写既有断言。

## 明确不做

1. 任何后端改动、端点增删、契约变更、migration。
2. 任何前端业务校验 / 名称变换（`/` 检测、重名预检、大小写折叠、`trim`、NFC、长度、空串拦截）。
3. `undefined_constraints` 的任何实现或承诺。
4. 引入 `vue-router` / 新 npm 包 / 其他 UI 框架 / 状态管理库。
5. 改 `App.vue`（导航与接线复用既有 emit）。
6. 列表行内改名（PROPOSED-2 推迟）。
7. 抽公共错误渲染 composable、重构其余 6 个 FormDialog。
8. 改动 F014 删除入口 / 三态 / Empty vs Not Found 语义。
9. 状态 / 位置 / DataCenter / 上级 / BareMetal 计数 / 关系 / `deleted_at` 字段。
10. 批量导入、导出、筛选、搜索、排序、审计、备注 / 负责人 / 标签。
11. F014 删除语义、认证实现（F013 已交付，本 Feature 只消费其全局 401 处理）。

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | **开发者拷贝 `BareMetalFormDialog` 的 `listClusters` import 做「重名预检」**（最高风险：该文件确实 import 了 `listClusters` 用于父选项） | REQUIRED #5（对话框禁引用读 API）+ 静态 guard（import 集合恰为 `{createCluster, updateCluster, ClusterRead}`）+ 组件探针（重名桩件仍只发一次 POST） |
| R2 | 拷贝既有 `submitDisabled = …` 写法，按空串禁用提交 | REQUIRED #4 + 组件探针（空名提交断言未 disabled 且 body 为 `{"name":""}`） |
| R3 | 错误分支误解析 `error.message` / `details[].message` | 组件探针注入「矛盾 message」：`409` 顶层 message 与分支文案无关；`400` 的 message 刻意写成「已存在活跃的同名集群」时**不得**渲染冲突文案（证明确按 code 分支） |
| R4 | 改 `ClusterListPage` 波及 `clusterListPage.spec.ts` 的 `[data-state]` / 分页 / 删除断言 | 仅加法（新增头部按钮 + 对话框）；对话框打开前不发起请求；不改 `run()`、三态 computed、表格与删除接线；新增用例独立 describe |
| R5 | 改 `ClusterDetailPage` 波及 `clusterDetailPage.spec.ts` 与 `f009ClusterResourceView.spec.ts`（后者静态扫描源码 token） | 仅内容态 actions 追加「改名」按钮与对话框；不改 `data-state` / `ErrorState` / 删除 / `open-bare-metals`；新增措辞不得含 `restore` / `undelete` / `include_deleted` / `回收站` / `恢复` |
| R6 | 登记成功仅刷新当前页，导致新集群在 > 50 活跃集群时不可观察（违反 AC-06） | PROPOSED #1：跳转新集群详情（`emit('openDetail', created.id)`），用 `201` 返回 `id` 保证可观察 |
| R7 | 表单引入 `el-select` 等的加载请求，干扰列表页测试请求计数 | REQUIRED #6：对话框打开不发起任何请求（无选项加载） |
| R8 | 改名成功后详情未刷新（仍显示旧名） | 改名成功 → `run()` 重读；新增用例断言重读后的新 `name` 与 `updated_at` |
| R9 | `401` 既触发全局处理又渲染本地提示 | REQUIRED #8 + 探针（`setUnauthenticatedHandler` spy 被调用，且不渲染 `[data-error-code]`） |

## Constraints

1. 不改 `docs/api/f001-cluster.md`、`backend/**`、`App.vue`、`api/clusters.ts`；不引入新依赖；不改 `package.json`。
2. 不实现前端业务校验 / 名称变换（`/`、重名、大小写、`trim`、NFC、长度、空串）；`name` 原样提交。
3. 不重定义 `ClusterWriteBody` / `ClusterRead`；不新建请求层。
4. 错误分支只按 `error.code`（必要时 `details[].code` / `details[].field`）；不解析 `error.message`。
5. 登记与改名共用同一 `ClusterFormDialog.vue`；恰一个 `name` 输入。
6. 不改既有三态、Empty / Not Found 语义、F014 删除入口与 F009 入口。
7. 不实现 `undefined_constraints`、PROPOSED-2/3；不新增任何产品规则。
8. 修改既有页面必须是加法，不得改写既有测试断言。

## Open Technical Questions

### Blocking

**无。**

### Non-blocking

1. `undefined_constraints`（NQ-1 / PROPOSED-3）：待用户裁定是否升级为规则；本 Feature 不实现。
2. 列表行内改名（PROPOSED-2）：默认不做；可逆追加，无架构变更。
3. `name` 字段是否加视觉「必填」星标（NQ-3）：纯视觉，**不得**引入客户端非空拦截。
4. 文档同步（NQ-4）：由协调器在落盘本 Handoff 与更新 `project-plan.yaml`（`current_stage` / `last_result`）时处理，不属实现范围。

## Implementation Layers

```text
database: false
backend:  false
frontend: true
```

- **database = false**：无 Schema / 索引 / 约束 / migration 变更。
- **backend = false**：无端点 / 服务 / 契约 / `backend/**` 变更。
- **frontend = true**：新增 `ClusterFormDialog.vue`；`ClusterListPage.vue`（登记入口 + 对话框 + 成功导航）与 `ClusterDetailPage.vue`（改名入口 + 对话框 + 成功重读）仅加法；新增 2 个测试文件、修改 2 个既有测试文件（新增 describe）。

## Implementation Order

```text
Architecture + API Contract（本 Handoff；契约复用 docs/api/f001-cluster.md，READY）
  └─ Frontend（唯一实现分支）
       ClusterFormDialog.vue
         ├─ ClusterListPage 接线（登记入口 + 成功导航）
         └─ ClusterDetailPage 接线（改名入口 + 成功重读）
         ↓
       新增 / 修改前端测试（组件 + 静态 guard + 页面接线用例）
                 ↓ 实现分支完成
              Tester → Reviewer
```

无 Database Design 分支，无 Backend 分支。文件所有权见「测试面」表；`App.vue` 与其余文件无所有权变更。

## Verification Strategy

1. **契约映射（AC-06 / AC-09）**：`create` → `POST /api/clusters` body `{name}`；`edit` → `PATCH /api/clusters/{id}` body `{name}`；`201` / `200` 单对象。
2. **零业务校验（AC-05）**：静态 guard（形式 A）+ 组件探针（形式 B），并经 Tester 对抗注入证伪。
3. **错误分支（AC-07 / AC-10 / AC-11）**：`400`（字段级）/ `409`（`DUPLICATE`，改为自身名 → `200` 不误报冲突）/ `404`（edit）/ `401`（全局处理，无本地提示）/ `NETWORK_ERROR` / default；注入矛盾 message 证明按 code 分支。
4. **提交态与可恢复（AC-13 / AC-14 / AC-15）**：提交中 Loading + 防重复（断言行数不变的 fetch 调用数）；取消不发写请求；失败提示可关闭后再次提交。
5. **入口可达与同一对话框（AC-01 / AC-02 / AC-03）**：列表页「登记集群」、详情页内容态「改名」且预填当前 `name`；两页挂载的是同一 `ClusterFormDialog` 组件，无第二表单。
6. **成功可观察（AC-06 / AC-09）**：登记成功 emit `openDetail(newId)`；改名成功后详情重读出现新 `name` / `updated_at`。
7. **既有行为不破坏（AC-16 / AC-17）**：重跑 `clusterListPage.spec.ts`、`clusterDetailPage.spec.ts`、`f009ClusterResourceView.spec.ts`、`clustersApi.spec.ts`、`app*` 导航 spec；确认三态 / Empty vs Not Found / F014 删除入口 / F009 入口不变。
8. **工程门禁**：`typecheck` + 前端测试全绿 + `build` 成功；`docs/api/**`、`backend/**`、`App.vue`、`api/clusters.ts` 未被改动。

## 需要 Tester 独立验证的关键点（自写探针证伪）

1. **前端确实未实现业务校验**：自写探针，向 `ClusterFormDialog.vue` 注入 `includes('/')` / `trim()` / `toLowerCase()` / `normalize('NFC')` / `listClusters` 预检中的任意一种，确认静态 guard 与组件探针**会失败**；再恢复。仅「测试通过」不构成证据。
2. **错误分支确实按 `error.code` 而非 `message`**：注入顶层 `message` 与 `details[].message` 与分支语义**矛盾**的响应，断言渲染的是按 code 的固定文案且顶层 message 未出现。
3. **既有三态 / Empty vs Not Found / 删除入口未被破坏**：独立重跑既有三件套 spec，并**自写**额外探针（如：列表页在登记对话框存在时仍能呈现 loading / empty / error 三态并正确计数分页请求；详情页 404 仍为 `not-found` 且无删除入口）。
4. **`401` 只触发全局处理器**：spy `setUnauthenticatedHandler`，断言被调用且页面不渲染本地 `[data-error-code]`。
5. **零后端 / 零契约改动**：检查 diff 范围仅限上表文件；`docs/api/f001-cluster.md`、`backend/**`、`api/clusters.ts`、`App.vue` 逐字节未变。
6. **空名提交不被前端拦截**：断言提交按钮未 disabled 且请求体为 `{"name":""}`。

---

`READY FOR IMPLEMENTATION`

**放行依据**：Product Handoff 为 `READY FOR ARCHITECT` 且无 Blocking 问题；API Contract Status = `READY`（复用已冻结的 `docs/api/f001-cluster.md`，无需新契约文档）；`database: false` / `backend: false` / `frontend: true`，唯一实现分支（Frontend）拥有全部开工依据；AC-01 ~ AC-17 均可由前端测试与静态 guard 判定；无阻塞性产品 / 架构 / 数据完整性问题。
