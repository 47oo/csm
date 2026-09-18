# Review Report — F016「Cluster 登记与改名 UI」

> Verdict: **`APPROVED WITH FOLLOW-UP`**
> Author Role: reviewer
> Date: 2026-09-18
> 已被批准的证据：Feature HEAD `ddf49dbc15943153753f6f2a7b2a35dcf6704e9c`，Base `67a498fab950f130330189e92756870623222a3d`（= develop），merge-base 同上。
> 后续代码 / 契约 / Base 变化须重新测试与 Review。

## Feature

F016「Cluster 登记与改名 UI」（post-V1 缺口闭合；纯前端）

## Scope Reviewed

| 项 | 值 |
|---|---|
| Feature Branch | `feature/F016-cluster-registration-ui` |
| start_commit | `67a498fab950f130330189e92756870623222a3d`（= develop） |
| Base Branch / SHA | `develop` / `67a498fab950f130330189e92756870623222a3d` |
| merge-base | `67a498fab950f130330189e92756870623222a3d`（= start_commit，未漂移） |
| 已审查 HEAD | `ddf49dbc15943153753f6f2a7b2a35dcf6704e9c` |
| 分支提交序列 | `02829b4 → 80fc12c → 6388134 → 83aa448 → ddf49db`（5 commits，祖先关系确认） |
| 工作区 | `git status --short` 空；无 staged、无 untracked |
| 完整差异 | 12 文件 / +2434 / −7（`git diff --stat start_commit..HEAD`，逐一按文件审查） |
| 工程门禁 | `typecheck` 通过；`test` **40 files / 604 tests passed**（基线 562，+42）；`build` ✓ 1694 modules |
| 独立注入 | 2 组（见「对抗注入记录」），工作区已逐字节还原 |
| 未审查内容 | 见「Unreviewed Areas」 |

审查文件（逐文件）：`ClusterFormDialog.vue`（新）、`ClusterListPage.vue`、`ClusterDetailPage.vue`、`clusterFormDialog.spec.ts`（新）、`clusterFormNoClientValidation.spec.ts`（新）、`clusterListPage.spec.ts`、`clusterDetailPage.spec.ts`、以及 5 个 docs 交付；对照物：`http.ts`、`clusters.ts`（未变）、`App.vue`（未变）、`f009ClusterResourceView.spec.ts`。

## Product Compliance

逐条核对 AC-01 ~ AC-17，**全部满足**：

- **AC-01/02/03**：列表页 `[data-testid=open-create-dialog]`「登记集群」、详情页内容态 `[data-testid=open-edit-dialog]`「改名」；两页挂载的是**同一个** `ClusterFormDialog`（`mode=create|edit`），`frontend/src/components/` 无第二套 Cluster 表单。edit 预填当前 `name`。
- **AC-04**：`el-form` 恰 1 个 `el-form-item`，仅 `name` 一个 `el-input`；无 select/number/date、无 状态/DataCenter/机柜/上级/计数/关系/`deleted_at`（源码 + 测试双重确认）。
- **AC-05**：实现不含任何业务校验/变换（`name` 原样提交，提交按钮禁用条件仅 `submitting`）。可失败性见 Finding REV-1。
- **AC-06/08/09/11**：`POST /api/clusters {name}`、`PATCH /api/clusters/{id} {name}`；201 关闭并 `emit openDetail(id)`（App.vue 既有 `@open-detail="openClusterDetail"` 接线确认）；失败不关闭、不 emit、不刷新；改为自身名 → 按 200 成功不误报冲突。
- **AC-07/10**：错误严格按 `error.code` 分支。404 仅 edit 渲染「该集群不存在或已被删除」，create 为防御性兜底。
- **AC-12**：前端不维护「旧名被占用」本地状态，改后旧名可直接 POST。
- **AC-13/14/15**：提交中 Loading + 连点不产生第二个写请求；取消仅关闭不发写请求；失败 alert 可关闭后再提交成功。
- **AC-16/17**：既有三态/Empty/Not Found、F014 删除、F002「查看裸金属」入口均未改（新增 describe，既有断言零删除）。

范围控制：**未实现任何未经确认的能力**（无列表行内改名、无批量、无备注；PROPOSED-2/3 未实现）。无 Scope Creep。

## Architecture Compliance

符合 Architecture Handoff 全部 REQUIRED #1~#10：同一组件、单字段、零业务守卫、禁引用读/预检 API（`import` 集合恰为 `{createCluster, updateCluster, ClusterRead}`，无 `listClusters`/`getCluster*`/直接 `fetch`）、打开不请求、按 code 分支、401 交全局、只做加法、冻结面未动。PROPOSED #1（成功跳转详情）已落地且 `App.vue` 零改动。`database: false` / `backend: false` / `frontend: true` 与实现一致。

## Database Review

不适用（`database: false`）。无 schema / 索引 / 约束 / migration 变更。`clusters` 表与 `ck_clusters_name_no_slash`、`ux_clusters_name_active` 未触碰。

## Backend Review

不适用（`backend: false`）。静态核对：`clusters.ts` 的 `createCluster`/`updateCluster` 与契约 §3.1/§3.5 一致，未重定义类型、未新建请求层。无真实 HTTP 联调（见 Unreviewed Areas；**协调器已在 Merge Gate 阶段另行完成真实集成核验，见文末**）。

## Frontend Review

- `ClusterFormDialog.vue` 职责清晰：`<script setup>` 内 props/model/emits 与既有 6 个 FormDialog 同构；`failureView` 内联（未抽 composable，符合「避免无关大范围重构」）。
- **错误分支只依据 `error.code`**：`failureView` switch 仅读 `error.code`、`details[].field`、`details[].code`；`message` 与 `details[].message` 仅作**展示文本**，从不参与分支（`default` 用 `${error.code}`）。401 → 返回 `null` 不渲染本地提示；catch 中 `code === 'UNAUTHENTICATED'` 跳过 `failure`。测试注入「矛盾 message」证伪按 message 分支。
- 无 loading/empty/error 混淆；无新依赖；`useAsyncQuery` 复用正确。
- `ClusterDetailPage` 改名成功 `run()` 重读（展示新 `name`+`updated_at`）；`ClusterListPage` 成功 `emit openDetail(created.id)`（解决 page_size 50 下新集群不可观察，R6）。

## Test Review

- 永久测试**真实覆盖** AC-01~AC-17 主路径，非迎合实现的空转断言：断言了请求 method/path/**body 逐字节**、请求次数（区分 GET/POST/PATCH）、不关闭/不清空、无 `openDetail`、无 `[data-error-code]`、Loading `is-loading`。
- 既有测试文件**纯插入**（`+428 / −0`），未改写既有断言。
- 静态 guard（形式 A）覆盖 3 个触点文件 + import 集合 + `:disabled` 不依赖 `form.name`；组件探针（形式 B）覆盖空名、` a/b `、零预检、错误码矩阵。
- 独立注入证实 guard/探针**可失败且非空转**（对 Coordinator/Tester 测过的类），但**非穷尽**（REV-1）。

## Findings

### REV-1

```text
Severity: MEDIUM（可 follow-up，不阻塞 Merge）
Layer:    Frontend / Test
Location: frontend/tests/clusterFormNoClientValidation.spec.ts（BANNED_TOKENS）、
          frontend/tests/clusterFormDialog.spec.ts（AC-05 探针取值）
Problem:  AC-05 的可失败保障覆盖不完整。静态 guard 的 token 白名单与组件探针的取值
          （仅 ''、' a/b '、'a/b'）无法捕获若干**等价实现**的业务校验，例如：
          startsWith('/') / endsWith('/') / match(/^\//) / search(/\//) / charAt(0)
          === '/' / replace('/', '')，以及模板层 maxlength / minlength / el-form
          :rules（rules 不进 <script>，不会被 token 扫描命中）。
Evidence: 在 clean 工作树上独立注入两组，运行两个 F016 spec：
          R-A：handleSubmit 内 `if (form.name.startsWith('/')) return`
               → guard + 组件探针 **27 passed（未捕获）**。
          R-B：el-input 上添加 `maxlength="5"`
               → guard + 组件探针 **27 passed（未捕获）**。
          （Coordinator 的 4 组 / Tester 的 3 组用的是 includes('/')/trim/toLowerCase/
           normalize/listClusters/:disabled，均被 guard 捕获——故保障**非空转**，
           只是不穷尽。）
Impact:   当前实现正确（已 grep + 通读确认源码无上述任一等价写法），故**不构成
          当前缺陷**。风险在**未来回归**：若后续有人用 startsWith('/') 或 maxlength
          悄悄引入前端拦截，永久测试会全绿通过，AC-05 会静默退化。
Expected: 加固 guard token（加入 startsWith/endsWith/match(/search/charAt/replace、
          以及模板属性 maxlength|minlength|:rules|rules= 的断言），并在组件探针增加
          以 '/' 开头与超长名称的提交用例，使「任意一种等价拦截」都会失败。
Suggested Owner: Frontend
```

### REV-2

```text
Severity: LOW
Layer:    Docs / Project Plan
Location: docs/project/project-plan.yaml（features[F016].git.head_commit）
Problem:  head_commit 记录为 "6388134…"（实现提交），但当前 Feature HEAD 为 ddf49db
          （其后的 test-report 提交）。即该字段落后 2 个提交，未反映 Review 的实际候选 HEAD。
Impact:    审查范围证据与计划元数据不一致；Review 批准针对的是 ddf49db，而 plan 记为
          6388134。不影响实现正确性（6388134 的文件集与内容全部包含于 ddf49db）。
Expected: 协调器在落盘本 Review 时把 head_commit 更新为候选 HEAD，并在 merge 后填
          merge_commit。
Suggested Owner: Coordinator
```

### REV-3

```text
Severity: NOTE
Layer:    Docs
Location: docs/project/project-plan.yaml（F016.last_result）
Problem:  「最高风险 R1：R2 拷贝 BareMetalFormDialog 的 listClusters 做「重名预检」」
          存在笔误（R1/R2 混用）。事实对应 Arch Handoff 的 R1。
Impact:    仅文档可读性。Expected: 修正为 R1。Owner: Coordinator
```

### REV-4

```text
Severity: NOTE
Layer:    Frontend / Test
Location: frontend/tests/clusterFormNoClientValidation.spec.ts
Problem:  guard 只扫描 3 个文件并按固定 token 列表匹配；若把校验封装为**其他模块**的
          helper（如 import validateName from '../utils/...'）再在三个文件中调用，
          guard 因不扫描该模块且 token 未列举而绕过。另：注释剥离正则
          /\/\/[^\n]*/g 理论上可吞掉含 `//` 的行内容（当前三个文件无此字面量，未触发）。
Impact:    理论性；当前实现干净。属 guard 设计边界的诚实记录（其 docstring 已自述
          「静态最佳努力」）。
Expected: 可考虑改为「断言被扫描文件集合 = Cluster 写入路径的全部触达文件」的清单守卫，
          或对 helper 引入做白名单。Owner: Frontend（可选）
```

## Existing Defects

Tester 记录的 **F016-T-01（LOW，Frontend）** — 4 个「细节不匹配」错误分支（409 field=name 但 code≠DUPLICATE；409 code=DUPLICATE 但 field≠name；未知错误码 default；400 缺 field 回退）缺永久回归保护。**独立重评：LOW 恰当，不阻塞 Merge。** 理由：契约 §3.1/§3.5 保证真实 409 恒为 `field==name && code==DUPLICATE`、400 恒带 `field`，故这些分支为防御性/不可达；当前实现经 Tester 临时探针实测正确；缺的仅是未来回归保护。**不改判为必须修复**。

Tester 观察项「VALIDATION_ERROR 透传 details[].message 作为展示文本」：与既有 6 个 FormDialog 形态及 Arch Handoff「details 仅展示、不参与分支」一致，**非违规**。

## Non-blocking Follow-ups

1. **REV-1**（MEDIUM 可 follow-up）：加固 AC-05 guard token 与探针取值。
2. **REV-2**（LOW）：更新 plan `head_commit`（协调器）。
3. **REV-3 / REV-4**（NOTE）。
4. 维持 F016-T-01 为 LOW。

## Unreviewed Areas

1. **真实前后端 HTTP / 浏览器级 E2E 集成**：本 Review **未执行**（无浏览器自动化环境）。所有前端验证基于 `fetch` 桩。
2. **视觉 / 可访问性 / 响应式布局 / 真实浏览器 el-dialog 行为**：未验证。
3. `undefined_constraints`（空串 / trim / 长度 / NFC）的**业务**合法性：按契约本就不予承诺，未验证。
4. 未运行后端测试（`backend: false`）。

## 对抗注入记录（Reviewer 独立）

| 项 | 内容 |
|---|---|
| 基线 `ClusterFormDialog.vue` sha256 | `7f3cecd9ee69c140c8f7f048d5da9a2749375225ec82192aa47cb76249a3cccd`（与 Tester/Coordinator 记录一致） |
| 注入 R-A | `handleSubmit` 内 `if (form.name.startsWith('/')) return`（唯一锚点命中）→ 两 F016 spec **27 passed（未被捕获）** |
| 注入 R-B | `el-input` 加 `maxlength="5"`（唯一锚点命中）→ 同两 spec **27 passed（未被捕获）** |
| 还原 | 两次均 `cp` pristine 副本还原；sha256 复原为 `7f3cecd9…cccd`；`git diff` 空；`git status --short` 空；`frontend/tests/` 无残留文件 |
| 还原后复跑 | 全量 `npm run test` = **40 files / 604 tests passed** |
| 结论 | 保障**可失败、非空转**（对 Coordinator/Tester 测过的类），但**不穷尽**（REV-1）。**未被说服**其覆盖完备——R-A/R-B 即为反例。 |

## Verdict

```text
APPROVED WITH FOLLOW-UP
```

依据：无 BLOCKER、无 HIGH、无必须在当前 Feature 修复的 MEDIUM；AC-01~AC-17 核心验收标准满足；测试可信（可失败性经独立注入确认，且既有断言未被削弱）；实现未超范围；零后端 / 零契约 / 零 Schema 改动经只读 git 逐字节确认。剩余为不阻塞 Merge 的 REV-1（MEDIUM 可 follow-up）+ LOW/NOTE。

---

**只读 git 命令清单（无任何改变 Git 状态的命令）**：`git status --short`、`git rev-parse HEAD`、`git rev-parse develop`、`git merge-base develop HEAD`、`git log --oneline develop..HEAD`、`git log --oneline -1 6388134`、`git show --stat --oneline 6388134`、`git diff --stat/--name-status/--numstat 67a498f..ddf49db`（含对 `docs/api`、`backend`、`frontend/src/api`、`frontend/src/App.vue`、`frontend/package.json`、`frontend/src/pages/`、`docs/architecture/f001-cluster-handoff.md`、`docs/project/project-plan.yaml`、两个测试文件的限定路径 diff）、`git diff --cached --stat`、`git ls-files --others --exclude-standard`、`git grep ... 67a498f -- frontend/src`、`git diff --stat -- frontend/src/components/ClusterFormDialog.vue`。未执行 add / commit / branch / merge / stash / reset / checkout / switch。

---

## 协调器 Merge Gate 与真实集成核验（2026-09-18）

### Merge Gate 逐项核对（§9）

| # | 条件 | 结果 |
|---|---|---|
| 1 | 必需测试通过、真实集成已验证 | typecheck / 604 测试 ×2 / build 全绿；**真实集成**：见下（评审声明未做，协调器在 Merge Gate 阶段补做） |
| 2 | 无 BLOCKER / HIGH / 必须修复的 MEDIUM / PRODUCT DECISION REQUIRED | 成立（REV-1 = MEDIUM **可 follow-up**，评审明确「不阻塞 Merge」） |
| 3 | 所有 Subagent 已结束、工作区 clean | 成立（`git status --porcelain` 空；4 个 Agent 均已返回） |
| 4 | HEAD 与批准候选一致、develop 与审查 base 一致 | 成立（HEAD `ddf49d` = 批准 HEAD；develop `67a498f` = 审查 base） |

**Merge**：`git switch develop` → `git merge --no-ff --no-commit feature/F016-cluster-registration-ui` → `git commit -F`。
结果：**merge_commit = `937291914ce7c6eeb1b1898fe72849a3165d544c`**；父提交 = `67a498f`（Base）+ `ddf49d`（批准 HEAD）；**集成树与已审阅候选树逐字节一致**（`HEAD^{tree} == ddf49db^{tree}` → YES）。

### 真实前后端集成核验（协调器，对已部署实例 `http://192.168.10.221/`）

评审把「真实 HTTP 集成」列为 Unreviewed。协调器在 Merge Gate 阶段补做，以**已部署的真实后端 + 真实 PostgreSQL**核验 UI 实际依赖的每一个响应形状：

| UI 依赖 | 实测结果 |
|---|---|
| 未认证 → `401`（交全局会话失效） | `401 UNAUTHENTICATED` ✓ |
| 登记请求体 `{name}` → `201` | `201`，返回 `{id,name,created_at,updated_at}` ✓ |
| 含 `/` → `400` 且 `details[].field == "name"` | `400 VALIDATION_ERROR`，`details:[{field:"name",code:"INVALID_CHARACTER"}]` ✓ |
| 缺 `name` → `400` 且 `field == "name"` | `400`，`details:[{field:"name",code:"INVALID"}]` ✓ |
| 活跃同名 → `409` 且 `field=="name" && code=="DUPLICATE"` | `409 CONFLICT`，`details:[{field:"name",code:"DUPLICATE"}]` ✓（**正是 UI 冲突分支所判定的两个条件**） |
| 改名 `PATCH {name}` → `200` | `200`，`name` 与 `updated_at` 更新，`id`/`created_at` 不变 ✓ |
| **改为自身当前名** → `200`（AC-11 不误报冲突） | `200` ✓ |
| `PATCH` 不存在 id → `404` | `404 NOT_FOUND`「资源不存在或已被逻辑删除」 ✓ |

**额外发现（非缺陷，值得记录）**：`POST {"name":""}`（空串）**实测返回 `201` 并落库**。这是 `undefined_constraints` 所描述的后果在**真实服务端**被实证——不是缺陷，也**不得**被解读为「空名称已确认合法」。该行为与产品 Handoff、架构 Handoff、契约 §7 的声明完全一致；UI 按 AC-05 不拦截是**正确**的。已作为事实记录，供未来 PROPOSED-3 裁定参考。

核验数据均已清理（4 行均为软删历史，活跃 Cluster = 0）。

---

## 追加复核：REV-1 / REV-4 修复（2026-09-18）

> Verdict: **`APPROVED WITH FOLLOW-UP`**
> 修复分支 `fix/F016-rev1-guard-hardening`；start_commit `8e35bee`（= 当时的 develop）；候选 HEAD `2497167`；范围**恰 2 个测试文件**（+256 / −16）；merge_commit **`38c9260`**。
> 本小节由协调器在 **merge 之后**追加，故不影响上述已批准的 HEAD。

### REV-1 / REV-4 闭合判定（Reviewer）

| finding | 判定 | 依据 |
|---|---|---|
| **REV-1 前半**（脚本层等价写法：`startsWith` / `endsWith` / `charAt` / `match` / `search` / `replace` / 正则 / 与 `'/'` 比较） | **已闭合（对可枚举写法）** | 全部进入 `BANNED_TOKENS`；当前源码零命中（无误报）。注入 `startsWith('/')` → 此前 **0 失败**，现 **5 failed** |
| **REV-1 后半**（模板层 `maxlength` / `minlength` / `rules` / `:rules` / `:model` / `pattern`） | **已闭合** | 新增模板静态断言。注入 `maxlength="5"` → 此前 **0 失败**，现 **1 failed**（且 Reviewer 独立复证：行为探针 30 条全绿、**只有**模板断言失败） |
| **REV-4 前半**（helper 绕过） | **在限定作用域内闭合** | `ClusterFormDialog` 的 import 模块集合被钉死为 `{vue, ../types/api, ../api/http, ../api/clusters}`；注入新 helper import → 失败。**但不覆盖**「逻辑塞进已白名单模块内部」或「新组件自建表单」 |
| **REV-4 后半**（注释剥离吞代码） | **已闭合** | 行注释只剥整行，并由「注释剥离前提」用例把该假设固化为**可失败**不变量；注入行内 `//` → 失败。Reviewer 另行核验：`frontend/src` 现有 **0 处**行内 `//` / `/*` / `<!--`，该不变量与既有代码风格一致、非为本用例新造 |

### 复核独立尝试的绕过（均非实现者 / 协调器所用写法）

| # | 注入 | 结果 |
|---|---|---|
| A | `includes(String.fromCharCode(47))`（未知语法，绕开 token） | **被检出**——token 未命中，但**行为探针** 9 条失败（写请求数 0）。证明分层设计有效：静态管家可枚举写法，行为兜未知语法 |
| B | `v-bind="{ ['max' + 'length']: 5 }"`（拼接键） | **未检出** → 新增 **REV-5**（NOTE） |
| C | `maxlength="5"` | 被检出（模板断言）——复证 REV-1 后半 |
| D | 新增 `import { validateName } from '../utils/…'` | 被检出（import 白名单）——复证 REV-4 前半 |
| E | 行内 `aria-description="a//b"` | 被检出（注释剥离前提）——复证 REV-4 后半 |

五组注入**全部逐字节还原**（`ClusterFormDialog.vue` sha256 恒为 `7f3cecd9…cccd`），结束时全量复跑 **618 passed**。

### 新 Finding

- **REV-5**（NOTE，Frontend，可选）：模板层静态断言按**字面 token** 匹配，可被拼接键规避；而行为探针因 `setValue` 绕过属性截断而失明——**两层同时漏**。当前实现干净，属 token 扫描固有边界。更强做法：模板属性改**白名单枚举**而非黑名单 token。
- **REV-6**（NOTE，Frontend / Coordinator）：加宽后的 token 对若干**合法**未来写法会误报（`:model-value`、`aria-pattern`、展示用 `.replace(`）。**判断为可接受的取舍**（写路径单一、失败 fail-closed 且指名 token、误报成本可逆），但建议在 token 注释中标明已知误报面；并把「helper 封堵」的作用域限定为「仅新增 import」。

### 「脆弱 guard」判断（Reviewer 第 2 项）

**未改判为缺陷。** 理由：三个文件是单一职责写路径，出现上述写法的概率低；失败是 fail-closed 且**指名 token**，不会静默；相对「AC-05 未来静默退化」的代价，误报成本可逆且局部。唯一建议是**把已知误报面写进注释**，避免后人误以为 guard 坏了而直接删 token（→ REV-6）。

### `maxlength` 认知核对

**论断成立、注释未夸大。** Reviewer 独立实证：`maxlength="5"` 在场时，VTU `setValue` 写入 300 字符**不被截断**、请求体逐字节原样、探针全绿；**只有**模板静态断言能失败。组件探针中「超长名称」用例的注释明确写着「只能证明**脚本层**没有长度校验、**不能**证明模板层没有 `maxlength`」——边界表述准确。

### 仍未覆盖的绕过路径（**本条为正式产物**，此前仅存在于提交信息中）

Reviewer 指出「6 条未覆盖清单」未落盘，无法逐字核对。现正式记录（经 Reviewer 补充后为 7 条，逐条独立，不宜合并计数）：

1. **已白名单模块内部**：校验逻辑若藏进 `../api/clusters.ts` / `../api/http.ts` / `vue` 内部，静态层不扫描（前者属冻结面、禁改）。行为兜底：探针的 body 逐字节比对会捕获任何**实际**变换。
2. **新建文件 / 第二个组件自建表单**：静态 guard 只扫 3 个固定文件。既有页面级测试（入口打开的是 `ClusterFormDialog`）提供部分行为兜底。
3. **脚本层长度阈值高于探针取值**（如 `if (name.length > 1000) return`）：300 字符探针不触发；`name.length` 形式的 token 因潜在误报未列入。
4. **拼接 / 动态构造的模板属性**（REV-5，如 `v-bind="{ ['max' + 'length']: 5 }"`）：静态字面 token 与行为探针**两层同时漏**。
5. **多行模板字符串行首含注释定界符**：静态不可区分（当前文件无多行模板字符串，且「注释剥离前提」用例已封堵单行情形）。
6. **仅真实浏览器生效且不改变请求体的机制**（如纯 CSS / 视觉限制）：不在 AC-05 范围内。
7. **真实浏览器人工输入路径**（`maxlength` 截断的实际体验）：无自动化覆盖，与本文「Unreviewed Areas」一致。

### 协调器独立验证（不采信 Frontend 与 Reviewer 的声明）

| 复核项 | 结果 |
|---|---|
| 改动范围 | 恰 2 个测试文件；`git diff -- frontend/src/` **空** |
| 实现是否被动过 | `ClusterFormDialog.vue` sha256 `7f3cecd9…cccd`、两页 `cd9ba7ce…` / `b8d67b24…` —— 与合并前**逐字节一致** |
| 独立注入（协调器自做 3 组） | A `startsWith('/')` → **5 failed**（此前 0）；B `maxlength="5"` → **1 failed**（此前 0）；C 未白名单 helper import → **1 failed**。全部先确认锚点命中，再逐字节还原（sha 前后一致） |
| 工程门禁 | typecheck 零输出；`test` **40 files / 618 passed 连续 2 次**（基线 604，+14）；build ✓ |
| 既有测试是否被削弱 | dialog spec **+84 / −0**（纯追加）；guard spec 原 4 用例保留、token 只增不减 |

**结论**：REV-1 两半、REV-4 两半均**已闭合**（REV-4 前半限于「新增 import」作用域）。残余 7 条已作为正式产物记录。新增 REV-5 / REV-6 为 NOTE，不阻塞。**「任意一种等价拦截都会被捕获」在任何记录中均未被声称**——被声称的是更窄且更真的一句：**已枚举的写法，加上行为测试能观察到的一切**。
