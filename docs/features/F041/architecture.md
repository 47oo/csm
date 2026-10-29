# F041 对象选择控件候选完整性（R04）— ARCHITECTURE 设计记录 + CONTRACT 最终签核

- **状态**：§1 ARCHITECTURE = `READY FOR DESIGN`；§2 CONTRACT = `NOT_REQUIRED`；§6 最终签核 = `READY FOR IMPLEMENTATION`（2026-10-29）
- **版本**：v1（2026-10-29）；FEATURE / P1 / M30；分支 `feature/F041-candidate-completeness`（交付线 `v3.4`，start_commit `d5c0a4c9aa5bd1036dd9acf087d210a22f43571d`）；plan revision 25；requirements revision 16
- **Basis**：requirements revision 16 §28.1（六段 CONFIRMED）+ §31 T127–T129 + §32 + §35.1 留痕；用户 AQ-1 = A 并「批准并执行」；plan 25 F041（`layers={database:false,backend:false,frontend:true}`、`api_required=false`、`depends_on=[F003,F004,F006]`、`blocking_decisions=[]`、三条硬约束）；`docs/features/F041/product.md` v1（A1–A16、N1–N11、ON-1..ON-11）；`docs/features/F041/test-report.md` §1 TD-F041-1（I/F/S 38 用例 + §1.10 AQ-4=B + §1.14 R1–R9）；契约基线 F003 §4/§6.1、F004 §4、F013 §1.4/§6；`docs/architecture/frontend-ui-stack.md`；`.pi/skills/frontend-ui/SKILL.md`
- **文件基线（`d5c0a4c` 只读核对）**：`VirtualMachineFields.tsx:99` 一次性 `listResources({cluster_id,type,page_size:100,sort})` 无 `q`/无分页；`ResourceCreatePage.tsx:63` 一次性 `listClusters({page_size:100,sort})` 且**整页门控**；`ResourceForm.tsx:281` 为 create 模式 Cluster `<Select>` 实际渲染点（`clusters` prop 仅 ResourceCreatePage 传入）；`ui/controls.tsx:114` 的 `Select` 用 `showSearch`+`optionFilterProp="label"`（仅过滤已加载），`<Select` 调用点 **60 处 / 23 文件**；`api/{resources,clusters}.ts` 客户端类型**已含** `q`/`page`/`page_size`/`cluster_id`/`type`/`sort`/`order`；`frontend/src` 无 debounce 工具

## 1. 设计

### 1.1 组件形态（ON-1）：新增独立候选组件，`ui/controls.tsx` 零 diff

采纳**方案 A**：新增 2 文件（纯逻辑模块 + 组件）。理由：① plan 硬约束② 与 §28.1「新行为由承载服务端检索的候选组件提供」；② A13 的可机械验证形态是「`controls.tsx` diff 为空」，opt-in props 必然改共享文件、证据强度更低；③ 事件契约不同（`controls.tsx` 适配 DOM `change` + `children=<option>`，候选需要 `showSearch`/`onSearch`/`filterOption={false}`/`notFoundContent`）。

新文件：

1. `frontend/src/components/candidateSelectModel.ts`（纯逻辑，无 JSX/React/antd，可被 node type stripping 加载）
2. `frontend/src/components/CandidateSelect.tsx`（唯一候选控件；内部使用 Ant Design `Select` 与既有 `ui/feedback`）

`CandidateSelectProps`：`domain: "host"|"cluster"`、`clusterId?`（host 域必填，空串=空闲态）、`id`、`name`、`value`、`onChange`、`pinned?`、`disabled?`、`placeholder`、`onContextChange?`、`aria-describedby?`。行为：`showSearch` + 受控 `searchValue` + `onSearch` + **`filterOption={false}`**（服务端检索，禁 Ant 客户端二次过滤）+ `options` 来自 `candidateOptions` + `notFoundContent`/状态提示来自 `candidateView` + 超限提示来自 `candidateTruncation`；`disabled` **仅**由 `submitting` 决定（不因 loading/error 禁用检索，否则第 101 位之后重新不可达）。

### 1.2 逻辑与视图分离（R2 硬约束，必须满足）

**状态机/文案/请求参数构造/epoch 门控/选项合成全部落在 `candidateSelectModel.ts`**。若逻辑内嵌 `.tsx`，AQ-4=B（无浏览器）下 A4/A7/A9/A16 没有可执行证据 → TEST 必须判 `TEST BLOCKED`（红线保留）。

导出面（要点）：

```ts
export const CANDIDATE_PAGE_SIZE = 100;            // 既有上限，不提高（N4/A2）
export const CANDIDATE_SEARCH_DEBOUNCE_MS = 300;
export type CandidateDomain = "host" | "cluster";
export interface CandidateItem { id: string; label: string }
export type CandidateSelectState =
  | { kind: "idle" } | { kind: "loading" }
  | { kind: "success"; items: CandidateItem[]; total: number; pageSize: number }
  | { kind: "error"; message: string };
export function buildCandidateQuery(domain: CandidateDomain, input: { clusterId: string; search: string }): CandidateQuery;
export function idleCandidateState(): CandidateSelectState;
export function loadingCandidateState(): CandidateSelectState;
export function isStaleCandidateResponse(requestEpoch: number, latestEpoch: number): boolean;
export function applyCandidateResponse(current, requestEpoch, latestEpoch, outcome): CandidateSelectState; // stale → 原样返回
export type CandidateViewKind = "idle" | "loading" | "error" | "empty" | "ready";
export interface CandidateView { kind: CandidateViewKind; role: "note"|"status"|"alert"|"log"|"none"; text: string; canRetry: boolean }
export function candidateView(state: CandidateSelectState, domain: CandidateDomain): CandidateView;
export function candidateTruncation(state, domain): { truncated: boolean; text: string | null };
export function candidateOptions(state, pinned?): { value: string; label: string }[]; // pinned 恰一次
```

**请求参数（既有参数，禁 `include`/`only`，不改 `q` 语义，`page_size ≤ 100`）**

| 域 | 端点（既有） | 参数（顺序即序列化顺序） |
| --- | --- | --- |
| host | `GET /api/v1/resources` | `q`（trim 非空才带）· `cluster_id=<clusterId>` · `type="BARE_METAL"` · `page=1` · `page_size=100` · `sort="hostname"` · `order="asc"` |
| cluster | `GET /api/v1/clusters` | `q` · `page=1` · `page_size=100` · `sort="code"` · `order="asc"` |

不设置 `deleted`（默认 exclude）、不设置 `role`/`status`/`code`（N10）；`page` 恒 1，无「加载更多」、无循环翻页（A3）。

**状态 → 视图**（`noun` = host→`宿主机`、cluster→`集群`）

| state | view.kind | role | 文案要点 |
| --- | --- | --- | --- |
| idle（host 且 `clusterId===""`） | idle | note | `请先选择所属集群，再选择宿主机候选。` |
| loading | loading | status | `正在加载${noun}候选…` |
| error | error | alert | `加载${noun}候选失败：${message}。可重试；失败态不代表${noun}候选为空。` |
| success 且 items 空 | empty | log | host：`该集群内未检索到未删除的 BARE_METAL；…` / cluster：`未检索到可选择的集群；…` |
| success 且 items 非空 | ready | none | `""` |

四态 `kind` 互异、文案两两不等且非空；`error` 含「可重试」且**不含**「无匹配」「暂无数据」；`canRetry` 仅 error 为 true。cluster 域 idle 不可达。

### 1.3 数据流与竞态

输入 → 内联 `setTimeout(300ms)`（不新增依赖、不建 hook，DR-F041-03）→ `committedSearch`；`clusterId`/域变更与 `committedSearch` 变化触发**唯一**的 `epoch = ++epochRef.current` + `loading` + 1 次请求 → `applyCandidateResponse(cur, epoch, latest, outcome)`：stale 返回原状态、否则**整体替换**（不 merge、不追加）。打开下拉**不发请求**；重试是第三且最后一个触发源（`retryToken`）。

集群切换（ON-4）：host 域 `clusterId` 变化时 `setSearch("")` + `onContextChange()`（调用方清空 `host_resource_id`）+ 重新 loading；首次挂载 `""→实际值` 不清空（`prevClusterIdRef` 区分）。编辑态 `clusterId` 固定，永不触发。

### 1.4 两处控件改造点

**① VM Host —— `VirtualMachineFields.tsx`**：删除本地 `HostOptionsState` 与一次性请求，改渲染 `<CandidateSelect domain="host" clusterId=… />`；四态/重试/超限提示改由模型派生；**`disabled` 仅 `submitting`**；`pinned = currentHost ? {id, label: `${hostname}（当前宿主）`} : null`，且在 loading/error 态同样保留为唯一选项（DR-F041-06，保证 A16 在候选失败时也能原值提交）；`onContextChange` 清空已选 Host（DR-F041-07）；props 契约与 `ResourceForm.tsx:497` 调用点**零改动**；字段错误呈现不变。

**② Resource 创建页 Cluster —— `ResourceCreatePage.tsx` + `ResourceForm.tsx`**：删除集群预加载与**整页门控**（DR-F041-04：四态从页面级下沉到字段级，`§28.1` 要求四态显式区分且失败可重试；权限门控/提交/错误呈现不变）；create 分支改用 `<CandidateSelect domain="cluster" … />`；删除 `ResourceFormProps.clusters` 与 `Cluster` 类型导入（死参数）；编辑态 Cluster 只读**不改**。

**其余控件零改动**：Interface / Network / IP Pool / IP Address / Service / Endpoint、`interfaceIpSelection.ts`（§13.4）、列表筛选、`GlobalSearch`（N6/N8）。

### 1.5 超限提示与 `total` 语义（ON-11）

`truncated = success && total > items.length`；文案：`按 ${sortLabel} 排序共 ${total} 个${noun}，当前仅显示前 ${pageSize} 个（列表分页上限 ${pageSize} 条）；更靠后的对象请用检索词查找。`（host `sortLabel="hostname"`、cluster `="code"`）。`total` **只取响应值**，前端不请求全库、不二次统计 ⇒ §23.2 非 ADMIN 的 `total` 天然只计授权集群对象（全库 120/授权 3 → 提示 3）。`total == items.length`（含 0）不提示。

### 1.6 layers / api_required / Contract 复核

`layers.frontend=true`（2 新建 + 3 改造 + smoke 追加）、`backend=false`（无服务端改动）、`database=false`（无 DDL）、`api_required=false`、Contract `NOT_REQUIRED`。

### 1.7 技术决策（本角色签核）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-F041-01 | 组件形态 = 新增 `CandidateSelect`（方案 A），`ui/controls.tsx` 零 diff | CONFIRMED |
| DR-F041-02 | 运行态 4 值（idle/loading/success/error）+ 视图投影 5 值（idle/loading/error/empty/ready） | CONFIRMED |
| DR-F041-03 | debounce 用内联 `setTimeout`（300ms 常量在纯模块），不新增依赖/hook | CONFIRMED |
| DR-F041-04 | Cluster 候选四态由页面级门控下沉至字段级；创建表单常渲染；权限与提交语义不变 | CONFIRMED |
| DR-F041-05 | `disabled` 仅在 `submitting`；失败/空态用文案表达而非禁用 | CONFIRMED |
| DR-F041-06 | `pinned` 在 loading/error/empty 态也保留为唯一选项 | CONFIRMED |
| DR-F041-07 | 切换集群清空已选 Host（首次挂载不清空） | CONFIRMED |
| DR-F041-08 | `q` 仅首尾 trim，非空才携带；不改大小写/折叠（A12） | CONFIRMED |
| DR-F041-09 | N9「不改 `backend/**`」= 不改**后端生产代码/配置**；`backend/tests/**` 新增测试文件属测试资产（Tester 在 TEST 阶段新增） | CONFIRMED（需 Product 编辑性追认，不影响实现） |

### 1.8 实施层与文件所有权

| 层 | 文件 | 内容 |
| --- | --- | --- |
| L1 | `frontend/src/components/candidateSelectModel.ts`（新建） | §1.2 全部纯函数与常量 |
| L2 | `frontend/src/components/CandidateSelect.tsx`（新建） | props + 数据流 + 三视图投影渲染 |
| L3 | `VirtualMachineFields.tsx` / `ResourceForm.tsx` / `ResourceCreatePage.tsx`（改） | §1.4 两处改造 |
| L4 | `frontend/scripts/smoke-client.mjs`（改） | 追加 F-01..F-12 共 **12** 条用例（基线 340 → **352**） |
| L5 | `docs/features/F041/implementation.md`（Frontend）、`test-report.md` §2（Tester） | 实现记录与证据 |

### 1.9 测试入口（ON-8）

不新增 `package.json` script、不新增依赖：`smoke:client` 已是唯一前端入口。smoke 只导入 `candidateSelectModel.ts` 与既有 `api/{resources,clusters}.ts`（`.tsx` 不能被 type stripping 加载）。断言：请求参数集合精确匹配（含 `q`/`page_size=100`/`cluster_id`/`type`，负向断言无 `include`/`only`/`deleted=`）；状态机与文案纯值断言（四态互异、`canRetry`、`truncated`、pinned 去重）；epoch 竞态（陈旧响应丢弃）；重试 `calls.length` 增量。基线要求 `352 passed, 0 failed` 且 `await test(` 增量 = 12；只允许追加、不得删/放宽既有 340 条。

## 2. CONTRACT：`NOT_REQUIRED`

`docs/api/**` 零 diff，不新建 `docs/api/F041.md`。12 维逐项无变化：端点/方法/路径（复用既有两个列表端点，**不新增专用选项端点**）、查询参数（`q`/`cluster_id`/`type`/`page`/`page_size`/`sort`/`order` 均既有）、`q` 语义（仍 ILIKE，未引 pg_trgm）、`page_size` 上限 100、请求/响应 Schema、错误语义（401/403/404/409/422 不变）、认证与权限（候选为 READ；不发送 `deleted`）、分页排序过滤、软删默认 exclude、§23.2 范围、标识寻址（不扩字符集）、版本冲突与审计（候选无 Audit；换 Host 仍 T19）。若后续有人提出专用 options 端点或提高 `page_size`，属新变更须走 change-control。

## 3. 与 TD-F041-1 一致性

A1–A16 与 38 用例（I-01..I-18 / F-01..F-12 / S-01..S-08）逐条对齐，无 UNMAPPED。TD 判定式的定稿更正（仅导入名/形态，不削弱验收）：T1 模块名 `candidateSelectModel.ts`；T2 `state.kind==="success"` 与 `candidateView().kind==="ready"` 并存；T3 走方案 A（`controls.tsx` 零 diff、`<Select` 仍 60/23）；T4 **`backend` 判定收窄为「生产代码零 diff」**（`git diff d5c0a4c -- backend` 空 + `git status` 仅允许新增 `f041_*.py`）；T5 新组件引用集合白名单（定义 + `VirtualMachineFields` + `ResourceForm`，禁出现在 IP 页/列表/全局搜索等）；T7 基线 352；T10 cluster 域 idle 不可达。

**R2 裁定**：本设计以纯逻辑模块承载状态机/文案/参数/epoch/选项，满足 AQ-4=B 可断言要求；红线保留——若实现把逻辑写进 `.tsx`，TEST 必须 `TEST BLOCKED`。**F016 真实栈不可达**（`127.0.0.1:18080` = 000）不影响 F/I 层：A1「提交被服务端接受」由 I-05/I-06/I-07（真实 PG + DB 行核对）承载，F-11 只证载荷。

## 4. Database：`NOT_REQUIRED`

无 DDL/索引/约束/Migration；`docs/database/**` 零 diff。测试夹具的 `INSERT ... SELECT generate_series`（TD §1.5，实测 150+151 行 0.075s）属测试代码，只在专用测试库 `csm_f037_test` 的 `public` schema 内由既有 `committed_engine` teardown 清理，不改 Schema、不入生产路径。data-integrity 无设计对象；被触及但不得改变的既有保证（§9/T01/T02、T08/T09、§21、§23.2、§22）以 I-05..I-17 验证。

## 5. 风险

| ID | 风险 | 级别 | 检测 |
| --- | --- | --- | --- |
| FR-1 | 共享组件语义漂移（改 `controls.tsx` 或 `optionFilterProp`，60 处静默变化） | HIGH | S-03（`controls.tsx` diff 空 + `<Select` 仍 60/23）、S-04 白名单、Review 逐处核对 |
| FR-2 | 跨集群候选残留（旧 Host 仍可选 → 提交必 422） | HIGH | F-04/F-05（replace + 陈旧丢弃）、`onContextChange` 清空、I-14、F-12 |
| FR-3 | 编辑态回填丢失（A16） | HIGH | F-10（pinned 恰一次、含/不含两分支）、I-07（T19 审计）、审读 `currentHost → pinned` |
| FR-4 | `q`+分页+范围组合导致「空结果误导」或泄露全库规模 | HIGH | F-06（empty/error 文案与 role 互异）、F-08/F-09（含响应 total、不含 120）、I-16 |
| FR-5 | A3 被实现成「加载更多」或循环翻页 | HIGH | F-03（`calls.length===1`、`page` 恒 1）、S-02、审读无累积页请求 |
| FR-6 | smoke 基线漂移（删/改既有 340 条） | MEDIUM | 352 passed + `await test(` 增量 12 + 既有块无删除行 |
| FR-7 | 误用新组件到 §13.4/列表筛选/其它表单 | MEDIUM | S-04 引用集合白名单、diff 文件清单 ⊆ §6 放行集 |
| FR-8 | 移除整页门控引发创建页回归 | MEDIUM | S-07 `npm run build`；审读 diff 仅删预加载与门控；`canWrite` 分支保留；I-12/I-13 |

## 6. 最终设计签核

```text
签核：Architect；日期 2026-10-29；对象：architecture.md v1（§1 READY FOR DESIGN、§2 NOT_REQUIRED、§6 最终签核）。
上游依据：requirements revision 16 §28.1 + §31 T127–T129 + §32 + §35.1；AQ-1=A；plan 25 F041；F041 product.md v1（A1–A16/N1–N11/ON-1..ON-11）；F041 test-report.md §1 TD-F041-1（38 用例 + R1–R9）。
定稿核对：TD 38 用例逐条覆盖 A1–A16 无 UNMAPPED；R2 已满足（纯逻辑模块导出面见 §1.2），红线保留；F016 不可达不影响 F/I 层（U3=NOT_TESTED，A1 由 I-05/I-06/I-07 承载）；ON-1..ON-11 全部落定；TD 判定式更正 T1–T11 记录在案（仅形态，不削弱验收）；Database NOT_REQUIRED；Contract NOT_REQUIRED（12 维无变化）。
覆盖：F041 仅此一项。
放行写入：frontend/src/components/candidateSelectModel.ts（新建）、frontend/src/components/CandidateSelect.tsx（新建）、VirtualMachineFields.tsx、ResourceForm.tsx、ResourceCreatePage.tsx、frontend/scripts/smoke-client.mjs、docs/features/F041/**（implementation.md、test-report.md §2、artifacts/**）；backend/tests/integration/f041_*.py 仅 TEST 阶段由 Tester 新增（DR-F041-09）；docs/project/** 由协调器维护。
零 diff 禁止：docs/api/**、docs/product/**、docs/database/**、docs/architecture/**、backend/**（生产代码与配置）、frontend/src/components/ui/controls.tsx 及其 60 处 <Select 调用点、frontend/src/api/**、frontend/package.json（依赖区与 scripts 区）、frontend/package-lock.json、frontend/vite.config.ts、frontend/src/index.css、F001–F040 历史证据。
结论：READY FOR IMPLEMENTATION。
```

**硬边界**：① 只写放行清单内文件；② **不得改 `backend/**` 生产代码**（若必须改 → 停止并走 change-control）；③ 不得提高 `page_size`、不得循环抓全量、不得前端全量缓存；④ 不得新增依赖或浏览器测试框架；⑤ TEST 阶段 `smoke:client` 须 `352 passed, 0 failed` 且 exit 0。
