# Product Handoff

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-18
> Feature: **F016「Cluster 登记与改名 UI」**（post-V1 缺口闭合）
> 上游依据：用户已确认「补做 Cluster 登记 + 改名，共用同一个对话框」；`docs/api/f001-cluster.md` §3.1 (`POST`) / §3.5 (`PATCH`) 为既有且已冻结契约；`docs/product/handoffs/f001-cluster.md` 的 AC-01 / AC-12 为既有后端验收。

> **协调器注记**：本 Feature 于 V1 全部完成（`project.status: DONE`）之后由用户在实际使用已部署生产实例时发现缺口而开启。
> 用户明确裁定「补做」，范围恰为**登记 + 改名**。本 Handoff 不新增、不修改任何产品规则。

---

## Feature

Cluster 登记与改名 UI（F016）— 为已经存在且已冻结的 Cluster 写入能力（`POST /api/clusters`、`PATCH /api/clusters/{id}`）补上唯一缺失的前端入口与表单，闭合 V1 交付中「找不到登记集群的地方」的真实缺口。

## Problem

**谁在什么情况下使用**：HPC / AI 集群运维人员、基础设施管理员（`requirements.md` §3）。他们在「新增了一个集群」「要登记一个新集群」「某个集群名称写错了 / 需要更名」时使用本功能。

**现在怎么做、哪里困难**：V1 已全部交付并已部署到生产实例，但用户在真实使用中反馈「找不到登记集群的地方」。经查证这是**真实的 UI 交付缺口**，而非需求未规划：

- 后端**完全支持**：`POST /api/clusters` → `201`、`PATCH /api/clusters/{id}` → `200`，已在真实实例上实测。
- 前端**没有任何入口**：`ClusterListPage.vue` 只有「刷新 / 详情」（行内另有删除）；`ClusterDetailPage.vue` 只有「返回列表 / 查看裸金属 / 删除集群」。
- `frontend/src/api/clusters.ts` 的 `createCluster` / `updateCluster` **已交付但 0 个调用者**（悬空代码，已验证）。
- `frontend/src/components/` 下 6 个 `*FormDialog.vue`（BareMetal / Container / IpAddress / NetworkInterface / Service / VirtualMachine）中**唯独没有 `ClusterFormDialog.vue`**。

**根因（记录以防重蹈）**：`docs/architecture/f001-cluster-handoff.md` 自身矛盾——Frontend Work §6 写「登记 / 改名 UI（PROPOSED，不构成 AC）」，决策 §7 写「前端 POST / PATCH 表单随本次交付（不构成 AC）」。两处都附加「不构成 AC」，因此没有任何 AC 要求它，Review 无据可查，且从未被记录为遗留项（f001 review / test report 零处提及）。F001 是最早的 Feature，后续 F002+ 各自建立了 FormDialog，Cluster 一直未被回头补上。

**为什么需要这个功能 / 价值**：Cluster 是 CSM 中资源组织与隔离的边界（`requirements.md` §7），BareMetal、IP 唯一性边界、Service 归属推导、查询入口都挂在它上面。没有登记入口，运维人员**只能靠直接调 API 才能让集群这一层事实进入系统**，直接违背「替代分散维护的 Excel」的产品目标。补上 UI 后，「登记一个新集群 / 更正一个集群名称」成为运维人员可直接完成的操作。

**最终希望得到的结果**：集群列表页可发起「登记集群」；已存在集群可发起「改名」；两者共用一个对话框、共用一个 API 客户端、共用一套错误渲染；所有业务校验仍由后端裁决。

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态、唯一性规则，也不修改任何 API 契约。**

---

## Confirmed Requirements

### 上游范围（用户已明确确认，非待裁定项）

1. **补做范围恰为「登记 + 改名」**：对应 `POST /api/clusters` 与 `PATCH /api/clusters/{id}` 两个已交付的 API 客户端函数。
2. **两者共用同一个对话框**（同一组件，create / edit 两种模式），与既有 6 个 `*FormDialog.vue` 的形态一致。

### 既有产品规则（本 Feature 直接消费，不修改）

3. Cluster 必须拥有可被运维人员识别的**名称**；名称是 Cluster 的唯一标识（R-CLUSTER-001；`domain-model.md` §5.1）。
4. Cluster Name 在所有**当前有效** Cluster 中**全局唯一**，比较**区分大小写**（R-CLUSTER-002、§22）。
5. Cluster **不设置运行状态**；不得为填表而增加状态字段（R-CLUSTER-003）。
6. Cluster 名称**不得包含 `/`**；写入路径必须校验并拒绝；**除 `/` 外的字符规则（长度 / 首尾空白 / 空串 / 大小写以外的字符规则）当前未定义，不得假设**（R-CLUSTER-005；`domain-model.yaml > resources[Cluster].fields[name].undefined_constraints`）。
7. 关键冲突必须在**保存前**由 Backend / Database 阻止，**不能只依赖 UI 校验**（§21）。
8. 资源采用逻辑删除；已逻辑删除的 Cluster 默认不出现在常规查询，也不占用名称唯一性（§17、R-DELETE-002、R-DELETE-006）——由既有后端契约保障（AC-07）。
9. 查询结果必须区分 **Resource Not Found** 与 **Empty**（R-QUERY-004）——既有列表 / 详情页已实现，本 Feature 不得改变该语义。

### 既有 API 契约（已冻结，本 Feature 不得改动）

10. `POST /api/clusters`（`docs/api/f001-cluster.md` §3.1）：请求体仅 `{"name"}`；`201` 返回单对象 `{id, name, created_at, updated_at}`；`400 VALIDATION_ERROR`（缺 `name` / `name` 非字符串 / `name` 含 `/`，`details[].field == "name"`）；`409 CONFLICT`（活跃同名，`details[].code == "DUPLICATE"`）；不得 `500`。
11. `PATCH /api/clusters/{id}`（同契约 §3.5）：请求体仅 `{"name"}`，必填；`200` 返回更新后单对象；错误语义与 §3.1 **规则完全相同**（`/` 禁令、活跃唯一性共用同一实现入口）；目标不存在或已逻辑删除 → `404 NOT_FOUND`；改为自身当前名称 → `200`（不得误报 `409`）。
12. 资源表示**字段集合封闭**（契约 §2）：仅 `id` / `name` / `created_at` / `updated_at`；**不存在** `deleted_at`、任何状态字段、任何 DataCenter / 位置 / 机柜 / U 位字段、任何 BareMetal 计数或关系字段。
13. 前端**必须按 `error.code`（必要时结合 `details[].code` 与 `details[].field`）分支渲染固定文案，不解析 `error.message`**（契约 §5）。
14. 现有前端 API 客户端 `frontend/src/api/clusters.ts` 的 `createCluster` / `updateCluster` 签名与语义即契约的 1:1 映射，本 Feature **直接复用**，不新建请求层、不重定义类型。

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。**

---

## Confirmed Domain Rules

| 规则 | 内容 | 来源 |
|---|---|---|
| R-CLUSTER-001 | Cluster 必须拥有可被运维人员识别的名称 | `requirements.md` §7；`domain-model.md` §5.1 |
| R-CLUSTER-002 | 名称在所有当前有效 Cluster 中全局唯一，比较区分大小写 | `requirements.md` §7、§22 |
| R-CLUSTER-003 | Cluster 不设置运行状态 | `requirements.md` §7 |
| R-CLUSTER-005 | 名称不得包含 `/`；写入路径必须校验 | `requirements.md` §7；`domain-model.md` §5.1 |
| `undefined_constraints` | 长度 / 首尾空白 / 空字符串 / 大小写以外的字符规则 / Unicode NFC 规范化**当前未定义，不得自行假设** | `domain-model.yaml > resources[Cluster].fields[name].undefined_constraints`；`requirements.md` R-CLUSTER-005 |
| §21 Data Consistency | 关键冲突（含全局 Cluster Name 重复）必须在保存前由 Backend / Database 阻止，不能只依赖 UI | `requirements.md` §21；`domain-model.yaml > data_consistency` |
| §22 Case Sensitivity | Cluster Name 唯一性比较区分大小写 | `requirements.md` §22 |
| §16 R-QUERY-004 | 查询须区分 Resource Not Found 与 Empty | `requirements.md` §16 |
| §17 R-DELETE-002/006 | 已逻辑删除不出现在常规查询；已删不占名称唯一性 | `requirements.md` §17 |
| §6 / §13 | 不建立 DataCenter 层级；不管理 Rack / U 位 | `requirements.md` §6、§13 |

**本 Feature 不新增、不修改任何领域规则。** 上述规则的**唯一裁决方是后端 + 数据库**（见「前后端职责边界」）。

---

## Scope

### 本次包含

1. **新增前端组件 `ClusterFormDialog.vue`**：同一对话框组件支持 `create` / `edit` 两种模式，仅含 `name` 一个输入字段。
2. **登记入口**：在 Cluster 列表页提供「登记集群」入口，打开对话框 `create` 模式；提交调用 `createCluster({name})`。
3. **改名入口**：对已存在 Cluster 提供「改名」入口（详情页至少一个），打开对话框 `edit` 模式并预填当前 `name`；提交调用 `updateCluster(id, {name})`。
4. **成功后的界面反映**：登记成功后列表 / 界面无需人工刷新即可观察到新集群；改名成功后界面呈现新名称与更新后的 `updated_at`。
5. **失败的界面反映**：按 `error.code`（必要时结合 `details[].code` / `details[].field`）渲染固定文案，覆盖 `400 VALIDATION_ERROR` / `409 CONFLICT` / `404 NOT_FOUND` / `401 UNAUTHENTICATED`（交既有全局会话失效）/ 网络错误 / 其他。
6. **消除悬空代码**：`createCluster` / `updateCluster` 从「0 个调用者」变为被本对话框使用。
7. **提交态与幂等**：提交中 Loading、禁止重复提交；取消 / 关闭不产生写入。

### 本次明确不包含

（用户明确排除，或已由 CONFIRMED 规则 / 已冻结契约排除）

1. **任何后端改动**：不改 `backend/**`，不新增 / 修改 / 删除任何端点，不改 `docs/api/f001-cluster.md` 及其契约语义。
2. **不改 Cluster 的字段集合**：不新增状态、不新增 DataCenter / 位置 / 机柜 / U 位、不新增上级、不新增 BareMetal 计数或关系字段（R-CLUSTER-003、契约 §2、§6、§13）。
3. **不引入批量导入 / 批量创建**：Excel 批量导入已于 2026-09-18 取消，不在 V1 范围内（`requirements.md` §18、§26）。
4. **不重复实现任何业务校验**（R-CLUSTER-002/005、§21、§22）：`/` 禁令、活跃全局唯一、大小写敏感全部由后端裁决。
5. **不实现 `undefined_constraints`**：空串、`trim`、长度上下限、Unicode NFC 规范化一律**不做**（见下文专门章节）。
6. **不做删除**：删除能力已由 F014 交付，本 Feature 不加不改（R-DELETE-*；`docs/api/f014-soft-delete.md`）。
7. **不修改既有列表 / 详情三态与 Empty / Not Found 语义**（R-QUERY-004；f001 AC-14）。
8. **不做导出、高级筛选、历史审计、排序、搜索、备注 / 负责人 / 标签**等无已确认需求的能力（`requirements.md` §23、§25）。

### 本次未涉及

当前需求没有要求，但**不能推断为永远不需要**：

- Cluster 改名的历史记录 / 时间线；
- 列表排序规则、关键字搜索、按名称前缀筛选；
- 批量创建、复制 Cluster；
- Cluster 级别的备注 / 负责人 / 标签等附加字段；
- 名称的展示归一化（统一大小写显示）；
- 登记成功后是否自动跳转到新集群详情（见 Non-blocking NQ-2）。

---

## 前后端职责边界（硬约束）

以下既有规则**由后端 + 数据库裁决**，前端**不得重复实现、不得预判、不得拦截**：

| 规则 | 后端裁决方式（契约） | 前端**必须** | 前端**不得** |
|---|---|---|---|
| Cluster 名称必填（R-CLUSTER-001） | 缺 `name` / `null` / 非字符串 → `400 VALIDATION_ERROR` + `details[].field == "name"` | 提交请求体始终包含 `name` 字段（字符串） | 以「非空」为由在客户端拦截；**尤其不得**把空串当作非法（`undefined_constraints` 未定义空串行为） |
| `/` 禁令（R-CLUSTER-005） | `name` 含 `/` → `400 VALIDATION_ERROR` + `details[].field == "name"`（应用层预检先于 DB CHECK，永不 `500`） | 按 `400` 的 `details[].field` 渲染字段级提示 | 客户端检测 `/` 并阻止提交；不把 `/` 当作前端校验项 |
| 活跃名称全局唯一（R-CLUSTER-002） | 活跃同名 → `409 CONFLICT` + `details[].code == "DUPLICATE"`、`field == "name"`（DB partial unique index 为最终权威） | 按 `409` 渲染「已存在活跃的同名集群」固定文案 | 发请求前查询列表做去重预判；不在客户端维护「名称已被占用」状态 |
| 大小写敏感（§22） | `cluster-a` 与 `Cluster-A` 是不同 Cluster；比较区分大小写 | 原样提交、原样展示 | 做大小写折叠（`toLowerCase`）或据此判断「重名」 |
| 逻辑删除（§17、R-DELETE-002/006） | 已删不参与查询 / 不占唯一性 | 按后端返回值渲染 | 自行判断某名称「是否被已删记录占用」 |
| 并发最后提交生效（契约 §3.5） | 无乐观锁，`updated_at` 非并发控制依据 | 按最后一次成功响应刷新界面 | 用 `updated_at` 做冲突检测 |

**错误渲染规则（契约 §5）**：前端**必须**按 `error.code` 分支（必要时结合 `details[].code` / `details[].field`）渲染固定文案，**不得解析 `error.message`**。

## `undefined_constraints`：明确**不得**当作规则、前端**不得**实现

以下四项当前**未定义且不得假设**（`domain-model.yaml > resources[Cluster].fields[name].undefined_constraints`；`requirements.md` R-CLUSTER-005；`docs/api/f001-cluster.md` §7）：

1. **空字符串是否允许** — 无承诺；
2. **首尾空白是否保留 / 去除（trim）** — 无承诺；
3. **长度上限 / 下限** — 无承诺；
4. **Unicode NFC / NFD 归一化** — 无承诺（大小写也**不做**折叠）。

据此：

- 本 Feature **不得**为之编写任何前端校验或变换；
- 本 Feature **不得**在 AC、文案或契约中承诺这些取值的行为；
- **后果声明（是事实，不是规则）**：在现行已确认规则下，空串 / 含首尾空白的名称在 UI 上**不会被前端拒绝**，会原样提交给后端（后端同样按未定义处理）。这**不得**被解读为「CSM 已确认空名称合法」。该边界沿用 f001 NQ-1。

## 「改名」的产品语义（引用既有 AC-12，不新造）

- 「改名」= 对已存在 Cluster 的 `name` 执行 `PATCH /api/clusters/{id}`；`name` 是 Cluster **当前唯一可变字段**（契约 §3.5）。
- **旧名释放语义直接引用既有 f001 AC-12**（「改后旧名称不再被占用，可作为其他 Cluster 的名称登记成功」），由**后端**保证；**本 Feature 不新造任何改名语义**，前端不自行维护「旧名是否被占用」。
- 改为自身当前名称 → `200`（契约 §3.5）；前端不得把它当作 `409` 处理，也不需要特殊分支。
- 改名成功后 `id`、`created_at` 不变，`name`、`updated_at` 更新（契约 §3.5）。

## 表单最小性（Cluster 只有 `name` 一个字段）

Cluster 的登记字段**仅有名称**（`domain-model.md` §5.1）。因此对话框**恰有一个输入字段 `name`**：

- **不得**出现运行状态 / 状态选择（R-CLUSTER-003，对应 f001 AC-09）；
- **不得**出现 DataCenter / 园区 / 机房 / 机柜 / U 位等上级或位置字段（§6、§13，对应 f001 AC-10）；
- **不得**出现所属上级 Cluster、BareMetal 数量或任何关系字段（R-CLUSTER-004 在登记 / 改名路径不产生用户可观察行为）；
- **不得**出现 `deleted_at` 或任何逻辑删除字段（契约 §2）。

---

## Acceptance Criteria

> 每条均描述**用户可观察到的 UI 行为**，可判定（是 / 否）。本 Feature 的 AC **只约束 UI 新增行为**，**不重复、不替代、不冲突** f001 的 AC-01 / AC-12（后端写入语义仍由 f001 验收）。响应字段名、路由与错误结构以 `docs/api/f001-cluster.md` 为准。

### 入口可达性

- **AC-01（登记入口可达）**：在集群列表页存在一个明确标识为「登记集群」（或等价文案）的入口；点击后打开登记对话框。
- **AC-02（改名入口可达）**：对已存在的集群，界面提供「改名」（或等价文案）入口（集群详情页至少一个）；点击后打开对话框的编辑模式，且名称输入框**预填该集群当前 `name`**。
- **AC-03（同一对话框）**：登记与改名由**同一个对话框组件**承载，仅模式不同；不存在第二套独立的登记 / 改名表单。

### 表单最小性

- **AC-04（仅一个字段）**：对话框的输入项**恰为 `name` 一项**；不存在运行状态、DataCenter / 位置 / 机柜 / U 位、上级、BareMetal 计数 / 关系、逻辑删除等任何其他字段或选择控件（R-CLUSTER-003、契约 §2、§6、§13、f001 AC-09 / AC-10）。
- **AC-05（不做客户端业务校验 / 变换）**：前端不检测 `/`、不比对活跃重名、不做大小写折叠、不做 `trim`、不做 NFC 归一化、不做长度 / 空串校验；`name` 原样提交；提交与否不因名称内容而被阻止。

### 登记

- **AC-06（登记请求与成功反映）**：在登记对话框填写名称并提交 → 前端调用 `POST /api/clusters`（请求体为 `{name}`）；收到 `201` 后对话框关闭，且**无需用户手工刷新**即可在界面上观察到新集群（列表中出现该集群，或界面导航至其详情）。
- **AC-07（登记失败按 `error.code` 渲染）**：
  - `400 VALIDATION_ERROR` → 展示字段级错误提示，指向 `name`；
  - `409 CONFLICT`（活跃同名）→ 展示固定文案「已存在活跃的同名集群」类提示，且**不关闭**对话框、**不**清空用户已填内容；
  - `401 UNAUTHENTICATED` → 交由既有全局会话失效处理（切回登录页），**不**渲染本地错误；
  - 其他错误 → 展示通用失败提示。
  以上分支**不得**依赖 `error.message` 文案。
- **AC-08（登记失败不产生误报成功）**：请求失败时对话框不关闭、不显示成功、不触发列表刷新为「已登记」状态。

### 改名

- **AC-09（改名请求与成功反映）**：在改名对话框修改名称并提交 → 前端调用 `PATCH /api/clusters/{id}`（请求体为 `{name}`）；收到 `200` 后对话框关闭，且界面上该集群显示**更新后的名称**与**更新后的 `updated_at`**。
- **AC-10（改名失败按 `error.code` 渲染）**：
  - `400 VALIDATION_ERROR` → 字段级提示，指向 `name`；
  - `409 CONFLICT` → 固定文案「已存在活跃的同名集群」类提示，对话框保持打开；
  - `404 NOT_FOUND` → 固定文案「该集群不存在或已被删除」类提示（目标不存在或已逻辑删除，两者不区分）；
  - `401 UNAUTHENTICATED` → 交既有全局会话失效处理；
  - 其他错误 → 通用失败提示。
  所有分支**不得**解析 `error.message`。
- **AC-11（改为自身当前名称不误报冲突）**：以当前名称提交改名 → 前端按 `200` 处理为成功，不显示冲突提示（契约 §3.5）。
- **AC-12（旧名释放由后端保证，前端不自行维护）**：改名成功后，前端不保留任何「旧名已被占用」的本地状态；界面不阻止用户以旧名登记其他集群（该行为由后端 AC-12 裁决）。

### 提交态与可恢复性

- **AC-13（提交中保护）**：提交进行中显示 Loading 且禁止重复提交（重复点击不产生第二个写请求）。
- **AC-14（取消不写入）**：取消 / 关闭对话框不发送任何写请求，不改变列表或详情内容。
- **AC-15（错误可关闭 / 表单不锁死）**：失败提示可关闭；关闭后用户可修改内容再次提交。

### 不破坏既有行为

- **AC-16（既有三态与 Empty / Not Found 不变）**：本 Feature 不改变列表页 Loading / Empty / Error 三态的区分，也不改变详情页 404（Not Found）与列表 Empty 的区分（f001 AC-14、R-QUERY-004）。
- **AC-17（既有删除入口不变）**：F014 的行内 / 详情删除入口与其错误渲染不受本 Feature 影响；本 Feature 不新增删除路径。

---

## Assumptions

（不阻塞当前工作、可安全暂时采用；**不得当作 CONFIRMED**）

1. **纯前端 Feature**：本 Feature 只改 `frontend/**`，`database: false`、`backend: false`；不新增 migration、不改契约。
2. **复用既有基座**：复用 `frontend/src/api/clusters.ts`（不新建请求层）、`api/http.ts` 的错误归一（`ApiError`）、既有 `*FormDialog.vue` 的交互与错误渲染形态；不引入新依赖（`App.vue` 现有极简视图状态，暂不引入 `vue-router`）。
3. **登记入口位置**：沿用既有 6 个资源页的先例，登记入口置于**集群列表页**；改名入口置于**集群详情页**（可另在列表行提供）。入口的具体位置与图标 / 文案属 UI 设计，不构成产品规则，只要 AC-01 / AC-02 的「可达性」成立。
4. **登记成功后的导航**：至少保证「无需人工刷新即可观察新集群」。是否自动跳转到新集群详情、还是留在列表并刷新，属 UI 设计（见 NQ-2），**不阻塞**。
5. **F013 已落地**：`/api/clusters*` 已受认证保护；`401` 由既有全局会话失效处理，表单不单独处理。
6. **系统已有真实 Cluster 数据**：`PATCH` 改名路径面向已存在数据可用；本 Feature 不涉及数据迁移。
7. **`page_size` 默认 50 / 上限 200** 等分页约定沿用既有实现，不作为产品规则。

---

## Proposed Rules

- **PROPOSED-1（需用户裁定，非 CONFIRMED）**：登记成功后自动跳转到新集群详情页（与 F007 / F008 的 `*FormDialog` 先例一致）。当前按假设 4 不强制；若确认，属 UI 行为的产品要求。
- **PROPOSED-2（需用户裁定，非 CONFIRMED）**：改名入口同时在集群列表行内提供（当前仅要求详情页可达）。
- **PROPOSED-3（需用户裁定，非 CONFIRMED）**：沿用 f001 PROPOSED-1，是否将 `name` 的空串 / `trim` / 长度上限升级为产品规则（当前属 `undefined_constraints`，本 Feature **不实现**）。

其余无产品建议。本 Feature 不新增任何产品规则，也不修改任何已有规则。

---

## Open Questions

### Blocking

**无。**

逐条对照「真正阻塞」判定标准：

- **不确认就无法确定本次功能范围？** 否。范围已由用户明确确认为「登记 + 改名，共用同一对话框」；后端能力、契约、领域规则均 CONFIRMED。
- **不确认会导致两种明显不同的用户行为？** 否。所有**行为**（提交、成功、失败、错误渲染、提交态）均在上述 AC 中单值确定；仅**入口位置**与**成功导航**属 UI 设计，不改变任何**业务行为**，且不影响可判定性。
- **不确认会改变核心领域关系？** 否。本 Feature 不触碰任何关系或唯一性边界。
- **不确认会导致验收标准无法定义？** 否。AC-01 ~ AC-17 全部可判定，且不依赖任何 `undefined_constraints` 或未确认项。

### Non-blocking

- **NQ-1（`name` 的 `undefined_constraints`）**：长度 / `trim` / 空串 / NFC 当前未定义，本 Feature **不实现、不承诺**（沿用 f001 NQ-1）。后果：空串 / 含首尾空白名称在 UI 不会被前端拒绝。建议在真实数据规模扩大前由用户裁定是否升级为规则（PROPOSED-3）。
- **NQ-2（成功后的导航形式与入口位置）**：登记成功是「留在列表刷新」还是「跳转新集群详情」；改名入口是否进列表行。属 UI 设计 / 架构可裁定项（见 PROPOSED-1 / PROPOSED-2），不改变业务行为。
- **NQ-3（`name` 字段的视觉「必填」标识）**：是否在名称输入框加必填星标属 UI 规范；**不得**因此引入客户端非空拦截（会违反 `undefined_constraints` 边界）。建议仅作视觉提示或不加。
- **NQ-4（文档与计划元数据）**：`docs/project/project-plan.yaml` 尚无 F016（V1 已全部 DONE）；需由协调器新增 F016 条目（`depends_on: [F001, F013, F014]` 均已 DONE，`layers: {frontend: true}`），并把 F001 的 root-cause 缺口登记为已闭合；`docs/architecture/f001-cluster-handoff.md` Frontend Work §6 与决策 §7 的「不构成 AC」矛盾表述建议加一条指向 F016 的更正注记。属流程 / 文档同步，不改产品规则。
- **NQ-5（前端测试形态）**：AC-01 ~ AC-17 的组件级验证方式（挂载对话框断言请求体与错误分支、静态 guard 断言前端不实现业务校验）由 Testing / Frontend 决定。

---

## Architecture Handoff

> 只说明 Architect 接下来需要解决的技术设计问题；不替 Architect 选框架、定 API 或写代码。

1. **确认本 Feature 为纯前端、零后端改动**：`docs/api/f001-cluster.md` §3.1 / §3.5 保持为唯一权威且冻结；不得新增 / 修改 / 删除端点或契约字段；不得新增 migration。
2. **`ClusterFormDialog.vue` 的组件契约**：`mode: 'create' | 'edit'`、`v-model` 可见性、`edit` 模式下传入当前 `ClusterRead`、成功事件的形式；复用 `createCluster` / `updateCluster` 与 `ClusterWriteBody`，不重定义类型、不新建请求层。
3. **入口接线**：在既有视图状态导航（`App.vue`，无 `vue-router`）下确定登记入口（列表页）与改名入口（详情页，可选列表行）的位置，以及成功事件的传播与导航（回应 NQ-2 / PROPOSED-1/2）。
4. **错误渲染的统一路径**：按 `error.code`（+ `details[].code` / `details[].field`）分支的固定文案映射，尽可能与既有 `*FormDialog.vue` 的错误渲染形态共享（可抽公共 composable），**明确禁止**解析 `error.message`（契约 §5）。
5. **「前端不实现业务守卫」的可失败保障**：以组件测试 / 静态 guard 固定 AC-05 与「前后端职责边界」表——前端不存在 `/` 检测、不发起唯一性预检、不做大小写折叠 / `trim` / NFC、不以空串为由拦截。
6. **不改既有三态与删除路径**：确认列表 / 详情页既有 Loading / Empty / Error / Not Found 与 F014 删除入口不受影响（AC-16 / AC-17）。
7. **交付层与计划落盘**：确认 F016 为 `frontend` 层；`docs/project/project-plan.yaml` 新增 F016 条目与依赖（回应 NQ-4）。
8. **与 f001 的 AC 边界对齐**：明确本 Feature 的 AC 只覆盖 UI 新增行为，后端写入语义（AC-01 / AC-12）仍归 f001，避免重复验收或语义漂移。

---

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。上游范围已由用户确认（补做「登记 + 改名」，共用同一对话框）；后端能力、API 契约与全部业务规则均已 CONFIRMED 且冻结；AC-01 ~ AC-17 仅陈述 UI 层新增行为、与既有 AC-01 / AC-12 语义不冲突，且不依赖任何 `undefined_constraints` 或未确认项（NQ-1 ~ NQ-5 均为 Non-blocking）。
