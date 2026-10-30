# F041 对象选择控件候选完整性（R04）— IMPLEMENTATION（Frontend）

- **状态**：**`FRONTEND COMPLETE`**
- **版本**：v1（2026-10-29）；角色 frontend；Feature F041（FEATURE / P1 / M30，`layers={database:false,backend:false,frontend:true}`、`api_required=false`、`depends_on=[F003,F004,F006]`、`blocking_decisions=[]`）；plan revision 25；requirements revision 16
- **分支 / 基线**：`feature/F041-candidate-completeness`；`start_commit=d5c0a4c9aa5bd1036dd9acf087d210a22f43571d`；本轮实现基于工作树 HEAD（前后端 / 契约 / Schema 零 diff，见 §5）
- **Basis**：`docs/features/F041/architecture.md` v1（§1.1–§1.5、§1.8、§1.9、§6 最终签核 READY FOR IMPLEMENTATION）；`docs/features/F041/product.md` v1（A1–A16、N1–N11、ON-1..ON-11）；`docs/product/requirements-v3.md` revision 16 §28.1 + §31 T127–T129；`docs/project/implementation-rules.md`；`docs/architecture/frontend-ui-stack.md`（§1–§5）；`.pi/skills/frontend-ui/SKILL.md`；`.agents/skills/ui-ux-pro-max/SKILL.md`
- **写权限**：仅 architecture §6 放行清单内的 6 个代码文件 + 本文件（清单见 §1）；**未**修改 `backend/**`、`docs/api/**`、`docs/product/**`、`docs/database/**`、`docs/architecture/**`、`ui/controls.tsx`、`frontend/src/api/**`、`package.json`、`package-lock.json`、`vite.config.ts`、`index.css`；未执行任何 Git 写操作

---

## 1. 变更清单（文件级）

| 类型 | 文件 | 内容 | 行数 |
| --- | --- | --- | --- |
| 新建 | `frontend/src/components/candidateSelectModel.ts` | 候选纯逻辑（无 JSX / React / antd，**仅 `import type`**）：常量、4 值状态机、5 值视图投影、请求参数构造、epoch 门控、超限提示、选项合成、响应项 → 候选项映射 | 294 行（新建） |
| 新建 | `frontend/src/components/CandidateSelect.tsx` | 唯一候选控件（Ant `Select` + 既有 `ui/feedback`）：受控检索词 + 内联 debounce + epoch 竞态 + 四态/超限渲染 + pinned 保留 | 231 行（新建） |
| 改 | `frontend/src/components/VirtualMachineFields.tsx` | 改造点 ①：删除本地 `HostOptionsState` / `useEffect` 一次性加载 / 三态手写 / 本地截断提示，改 `<CandidateSelect domain="host">`；`pinned=currentHost`；`onContextChange` 清空 `host_resource_id`；**props 契约与 `ResourceForm` 调用点零改动** | −129/+62 |
| 改 | `frontend/src/components/ResourceForm.tsx` | 改造点 ②：create 分支集群控件换 `<CandidateSelect domain="cluster">`；删除 `ResourceFormProps.clusters` 与 `Cluster` 类型导入（死参数）；`canWrite`/本地校验/提交载荷逻辑不变 | +10/−15 |
| 改 | `frontend/src/pages/ResourceCreatePage.tsx` | 删除集群预加载（`listClusters`）与**整页门控**（`ClusterOptionsState` / `LoadingState` / `ErrorState` 重试 / `EmptyState` / 截断 `InfoState` / `reloadToken`）；表单常渲染；`canWrite` 拦截与提交逻辑不变 | +18/−84 |
| 改 | `frontend/scripts/smoke-client.mjs` | 追加 **F-01..F-12 共 12 条**用例（纯追加，既有 340 条零删改）+ 新增 1 个 import 块 + 文件头 F041 段落 | +507/−0 |
| 新建 | `docs/features/F041/implementation.md` | 本文件 | 278 行（新建） |

`git diff --stat -- frontend/src frontend/scripts`：`4 files changed, 563 insertions(+), 200 deletions(-)`（另 2 个新建文件为未跟踪状态）。

---

## 2. DR / §1.x 落实情况

### 2.1 决策落实

| ID | 决策 | 落实证据 |
| --- | --- | --- |
| DR-F041-01 | 方案 A：新增 `CandidateSelect`，`ui/controls.tsx` 零 diff | `git diff -- frontend/src/components/ui/controls.tsx` 空；本文件 §5 |
| DR-F041-02 | 运行态 4 值 + 视图投影 5 值 | `candidateSelectModel.ts`：`CandidateSelectState`（idle/loading/success/error）、`CandidateViewKind`（idle/loading/error/empty/ready）；smoke F-06 |
| DR-F041-03 | debounce = 内联 `setTimeout`（300ms 常量） | `CANDIDATE_SEARCH_DEBOUNCE_MS = 300` 在纯模块；`CandidateSelect.tsx` 唯一 `setTimeout`；无新依赖（`package.json` 零 diff） |
| DR-F041-04 | 集群四态由页面级门控下沉到字段级 | `ResourceCreatePage.tsx` 删除 `ClusterOptionsState` 与整页 loading/error/empty/truncation；`ResourceForm.tsx` create 分支渲染候选控件 |
| DR-F041-05 | `disabled` 仅 `submitting` | `CandidateSelect` 的 `disabled` prop 由两处调用点传入 `submitting`；loading/error 不禁用（浏览器验证：失败态下仍可继续输入并重试） |
| DR-F041-06 | `pinned` 在 loading/error/empty 也保留为唯一选项 | `candidateOptions()`；smoke F-10（4 种非 success 态均返回 `["pinned-1"]`）；浏览器 §4 步骤 9 |
| DR-F041-07 | 切换集群清空已选 Host，首次挂载不清 | `prevClusterIdRef` 区分首次挂载；`onContextChange()` → `onChange({host_resource_id: ""})`；`ResourceForm` 原清空逻辑保留（幂等） |
| DR-F041-08 | `q` 仅首尾 trim，非空才携带，不改大小写/折叠 | `buildCandidateQuery` 内 `search.trim()`；smoke F-01（`" f41n-0110 "` → `q=f41n-0110`）、F-02（`F41C-0110` 原样） |
| DR-F041-09 | 不改 `backend/**` 生产代码 | `git diff -- backend` 空（`backend/tests/**` 由 Tester 在 TEST 阶段新增，本轮未触碰） |

### 2.2 §1.1 组件形态与 props

`CandidateSelectProps` 全部实现：`domain` / `clusterId` / `id` / `name` / `value` / `onChange` / `pinned` / `disabled` / `placeholder` / `onContextChange` / `aria-describedby`。

* `showSearch` + 受控检索词 + `onSearch` + **`filterOption={false}`** + `notFoundContent` 全部启用。**实现形态说明**：antd 6.6.6 已将顶层 `searchValue` / `onSearch` / `filterOption` 标记 deprecated，改由 `showSearch` 对象承载（`@rc-component/select` 的 `useSearchConfig` 把对象展开进搜索配置，语义等价）。因此写作
  `showSearch={{ searchValue: search, onSearch, filterOption: false, autoClearSearchValue: false }}`，语义与 §1.1 完全一致（服务端检索、禁客户端二次过滤、受控检索词）。
* `name` 说明：Ant Design `Select` 无原生 `name` 属性（表单不走原生提交），故 `name` 落到包裹容器的 `data-field-name`，保留调用方字段语义标识；两处调用点仍传原值（`virtual_machine.host_resource_id` / `cluster`）。
* `notFoundContent` 与字段下方状态块复用同一 `CandidateView` 投影节点，四态在“下拉打开/关闭”两种情形都可见；`ui/feedback` 组件映射为 `idle→InfoState(note)`、`loading→LoadingState(status)`、`error→ErrorState(alert + 重试)`、`empty→EmptyState(log)`、`ready→无`。

### 2.3 §1.2 纯逻辑模块导出面（R2）

全部实现（`candidateSelectModel.ts`，零 JSX/React/antd，仅 `import type { Cluster, ListClustersQuery }`、`import type { ListResourcesQuery, Resource }`）：

`CANDIDATE_PAGE_SIZE`(100)、`CANDIDATE_SEARCH_DEBOUNCE_MS`(300)、`CandidateDomain`、`CandidateItem`、`CandidateSelectState`、`buildCandidateQuery(domain, { clusterId, search })`（**参数顺序与 §1.2 参数表一致**）、`idleCandidateState()`、`loadingCandidateState()`、`isStaleCandidateResponse()`、`applyCandidateResponse()`（stale → **原样返回当前对象引用**）、`CandidateViewKind`、`CandidateView`、`candidateView()`、`candidateTruncation()`（文案含 `total` 与 `pageSize`）、`candidateOptions()`（pinned **恰一次**）。

为满足 R2（状态机不得内嵌 `.tsx`）与组件最小化额外导出 3 个纯函数 + 1 个类型（不改任何判定式）：`initialCandidateState(domain, clusterId)`（idle 仅 host 未选集群可达 → 可断言 T10）、`CandidateOutcome`、`resourceCandidateItems()`、`clusterCandidateItems()`（响应项 → 候选项映射，label 保持原展示：host=`hostname`、cluster=`code — name`）。

请求参数（§1.2 表，顺序即序列化顺序）经既有 api 函数实际产生（浏览器实测 URL 参数集）：
host → `q?`·`cluster_id`·`type=BARE_METAL`·`page=1`·`page_size=100`·`sort=hostname`·`order=asc`；cluster → `q?`·`page=1`·`page_size=100`·`sort=code`·`order=asc`。无 `deleted` / `include` / `only` / `role` / `status` / `code`（N10）。

### 2.4 §1.3 数据流与竞态

* 输入 → 内联 `setTimeout(300ms)` → `committedSearch`（检索词按 `domain:clusterId` 上下文归属，集群切换即自然归零，**避免切换时先用旧检索词打一次请求**）。
* **唯一请求触发点**：`useEffect([domain, clusterId, committedSearch, retryToken])` → `epoch = ++epochRef.current` → `loadingCandidateState()` → 1 次请求 → `applyCandidateResponse(cur, epoch, epochRef.current, outcome)`；陈旧响应原样丢弃、否则整体替换（不 merge / 不追加）。
* 打开下拉**不发请求**（未接 `onOpenChange`）；`retryToken` 是第三且最后一个触发源（重试按钮）。
* host 域 `clusterId === ""` → idle：epoch 递增使在飞响应失效，且**不发请求**。
* 集群切换：`onContextChange()` 触发调用方清空已选 Host；首次挂载 `""→实际值` 不清空（`prevClusterIdRef` 初值 = 当前 `clusterId`）。
* 编辑态 `clusterId` 固定（`resource.cluster.id`），永不触发清空。

### 2.5 §1.4 两处改造点

| 改造点 | 落实 |
| --- | --- |
| ① VM Host（`VirtualMachineFields.tsx`） | 本地 `HostOptionsState` / `useEffect` / `listResources` 调用 / `Button` 重试 / `LoadingState`·`ErrorState`·`EmptyState` 手写分支 / 本地截断 `InfoState` 全部删除；`<CandidateSelect domain="host" clusterId=… disabled={submitting} pinned={currentHost ? {id, label: `${hostname}（当前宿主）`} : null} onContextChange={…} />`；**组件 props 契约零改动**（`ResourceForm.tsx` 第 492 行起的调用点参数逐项不变）；字段错误呈现与 `serverFields["virtual_machine.host_resource_id"]` 映射不变 |
| ② Resource 创建页 Cluster（`ResourceCreatePage.tsx` + `ResourceForm.tsx`） | 删除集群预加载与整页门控；create 分支改 `<CandidateSelect domain="cluster" …>`；删除 `ResourceFormProps.clusters` 与 `Cluster` 导入（`ResourceCreatePage` 为唯一外部传入方，`ResourceDetailPage` 编辑态从未传 `clusters`，零波及）；编辑态 Cluster 只读展示不变；`canWrite` 门控、409/422/403 错误呈现、提交逻辑不变 |

**其余控件零改动**：Interface / Network / IP Pool / IP Address / Service / Endpoint、`interfaceIpSelection.ts`（§13.4）、列表筛选、`GlobalSearch`。`CandidateSelect` 引用集合（`grep -rn "CandidateSelect" src --include=*.tsx`）：定义文件 + `VirtualMachineFields.tsx`（import + 渲染）+ `ResourceForm.tsx`（import + 渲染）+ `ResourceCreatePage.tsx`（**仅文档注释提及**），与 §1.9 T5 白名单一致。

### 2.6 §1.5 超限提示

`truncated = success && total > items.length`；文案：
`按 ${sortLabel} 排序共 ${total} 个${noun}，当前仅显示前 ${pageSize} 个（列表分页上限 ${pageSize} 条）；更靠后的对象请用检索词查找。`（host `hostname`/`宿主机`，cluster `code`/`集群`）。`total` 只取响应值，前端不请求全库、不二次统计。

---

## 3. 验证（实际命令与真实输出）

工作目录 `frontend/`（除特别标注）。

### 3.1 类型 / 构建 / 客户端 smoke

```console
$ npx tsc --noEmit 2>&1 | tail -5
（无输出，exit 0）

$ npm run build 2>&1 | tail -5
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 23.93s

$ npm run smoke:client 2>&1 | tail -3
PASS: F041 F-12 提交拒绝语义不变（A10）：候选态不被错误吞并，错误经既有描述器呈现、不重试

352 passed, 0 failed

$ grep -c "await test(" scripts/smoke-client.mjs
352
```

* **smoke 通过数：352 passed / 0 failed**（基线 340 + 新增 12 = 352，exit 0）。`await test(` 增量 = 12，既有 340 条断言零删改（diff 仅追加）。
* chunk 体积警告为 F040 已结论的既有现象，不计缺陷（S-07）。

### 3.2 静态 / 零 diff

```console
$ grep -rn "CandidateSelect" src --include=*.tsx | grep -v "components/CandidateSelect.tsx"
src/pages/ResourceCreatePage.tsx:33: *   必 422）。F041 起由 `<CandidateSelect domain="cluster">` 在字段内完成服务端
src/components/ResourceForm.tsx:3:import CandidateSelect from "./CandidateSelect";
src/components/ResourceForm.tsx:281:          <CandidateSelect
src/components/VirtualMachineFields.tsx:3:import CandidateSelect from "./CandidateSelect";
src/components/VirtualMachineFields.tsx:57: * - Host 选择器改用 `CandidateSelect domain="host"`（F041）：候选由
src/components/VirtualMachineFields.tsx:96:        <CandidateSelect

$ grep -rn "<Select" src --include=*.tsx | wc -l
58
$ grep -rln "<Select" src --include=*.tsx | wc -l
22

（仓库根）
$ git diff --stat -- frontend/src/components/ui/controls.tsx frontend/src/api frontend/package.json frontend/package-lock.json backend docs/api docs/product
（空输出，exit 0）

$ git status --porcelain
 M frontend/scripts/smoke-client.mjs
 M frontend/src/components/ResourceForm.tsx
 M frontend/src/components/VirtualMachineFields.tsx
 M frontend/src/pages/ResourceCreatePage.tsx
?? frontend/src/components/CandidateSelect.tsx
?? frontend/src/components/candidateSelectModel.ts
```

**`<Select` 计数为 58 处 / 22 文件（非架构文字中的 60/23）——偏差已核准说明，见 §7.1**。逐文件对照（`git grep -c "<Select" HEAD -- 'src/**/*.tsx'` vs 当前）：仅 `VirtualMachineFields.tsx` 1→0、`ResourceForm.tsx` 4→3（即两个 F041 候选载体由 `<Select` 改为 `<CandidateSelect`），其余 21 个文件计数逐个不动 → **共享 `Select` 的既有调用点逐处未变**（FR-1 的实质要求成立）。

---

## 4. 浏览器验证（真实渲染 + 交互 + 可访问性）

环境限制说明：仓库无 Playwright/jsdom/Vitest 依赖（N11 保证零新增，`package.json` 零 diff），F016 真实栈入口本环境不可达。为满足「组件/交互变更需实际操作并检查焦点与提交反馈」，本轮使用**环境已有的 Node/浏览器能力 + 仓库外临时脚本**（`/tmp/f041_browser.py`、`/tmp/f041_layout.py`，**不入库**）：`npm run dev`（vite 5199）+ Playwright（Python，系统已装）+ `page.route("**/api/v1/**")` 受控 mock，**不新增仓库依赖、不改仓库配置**。Mock 说明见 §6。

真实输出（23 项交互/可访问性断言全通过）：

```text
PASS  cluster 请求参数正确且无 deleted/include/only → {'q': 'F41C-0110', 'page': '1', 'page_size': '100', 'sort': 'code', 'order': 'asc'}
PASS  服务端检索后下拉仅 1 条候选（客户端过滤关闭）→ 1
PASS  a11y 镜像列表 aria-label 与 label 一致
PASS  键盘选中后 Select 展示集群 label
PASS  host 请求参数正确且无 deleted → {'cluster_id': 'c-0110', 'type': 'BARE_METAL', 'page': '1', 'page_size': '100', 'sort': 'hostname', 'order': 'asc'}
PASS  超限提示含总数 154 与分页边界 100
PASS  候选首页第一项 = f41n-0001（既有排序）→ f41n-0001
PASS  host 检索请求带 q=f41n-0110 → {'q': 'f41n-0110', 'cluster_id': 'c-0110', 'type': 'BARE_METAL', 'page': '1', 'page_size': '100', 'sort': 'hostname', 'order': 'asc'}
PASS  第 110 位宿主机被检索命中 → 1 条
PASS  选中名次 ≥101 的宿主机后表单展示 hostname
PASS  失败态显示 alert 且提供重试
PASS  失败态不伪装为空结果
PASS  失败后未自动重试（7 → 7）
PASS  显式重试恰 +1 次请求（1）且恢复候选
PASS  空结果态文案独立
PASS  375px 无横向溢出（0px）
PASS  768px 无横向溢出（0px）
PASS  idle 态提示先选集群
PASS  idle 态不发候选请求
PASS  label[for]=1 / role=combobox / focus=rgba(5, 122, 255, 0.06) 0px 0px 0px 1.93883px|none
PASS  编辑态当前宿主以「（当前宿主）」保留为选项（候选首页不含 h-0140）
PASS  下拉首项为 pinned（恰一次）→ ['f41n-0140（当前宿主）', 'f41n-0001', 'f41n-0002']
PASS  编辑态候选请求仍走既有参数 → {'cluster_id': 'c-0110', 'type': 'BARE_METAL', 'page': '1', 'page_size': '100', 'sort': 'hostname', 'order': 'asc'}

23 passed, 0 failed
```

布局度量（DOM 断言，非人眼视觉；四断点）：

```text
1440 {'w': 539, 'h': 36, 'hitInsideSelect': True, 'hitTag': 'ant-select-input|INPUT', 'alertVisible': True, 'labelAbove': True}
1024 {'w': 331, 'h': 36, 'hitInsideSelect': True, ...}
768  {'w': 327, 'h': 36, 'hitInsideSelect': True, ...}
375  {'w': 317, 'h': 36, 'hitInsideSelect': True, ...}

PASS  1440px 控件可点（无遮挡）/ 超限提示完整可见 / label 在上方
PASS  1024px / PASS 768px / PASS 375px（同上）
4 passed, 0 failed
```

**截图**（13 张，视口见文件名；临时目录，未入库）：`/tmp/f041_shots/01-create-cluster-1440.png`、`02-cluster-search-1440.png`、`03-host-truncated-1440.png`、`04-host-search-1440.png`、`05-host-selected-1440.png`、`06-host-error-1440.png`、`07-host-retry-1440.png`、`08-host-empty-1440.png`、`09-mobile-375.png`、`10-tablet-768.png`、`11-idle-1024.png`、`12-focus-1024.png`、`13-edit-pinned-1024.png`。覆盖场景：idle / loading→success / 检索命中第 110 位 / 超限提示 / 失败可重试 / 空结果 / 编辑态 pinned；断点 1440·1024·768·375。

**采用 ui-ux-pro-max 的建议与项目适配**：`--domain ux`（searchable select / loading-error-empty form field）返回 Error Placement（错误内联在字段下方 + `role=alert`）、Empty States（空态要有可操作指引）、Form Labels（保留 `<label for>` 而非仅 placeholder）、Error Messages（`role=alert`）——全部与项目既有 `ui/feedback` + `field-error` 约定一致，未引入新视觉规范；`--stack react` 返回「Debounce rapid input changes」与「Handle async errors」——对应 `CANDIDATE_SEARCH_DEBOUNCE_MS` 与 `request.then(onFulfilled, onRejected)`（无未处理 rejection）。技能未覆盖本项目已确认选型（`uiDeferredValue` 等替代方案未被采用，遵循 DR-F041-03 与 N11）。

---

## 5. 硬边界（§6）符合情况

| 硬边界 | 结果 |
| --- | --- |
| ① 只写放行清单内文件 | 是：`git status --porcelain` 仅 4 修改 + 2 新建（+ 本文件） |
| ② 不得改 `backend/**` 生产代码 | 是：`git diff -- backend` 空；未新增 `backend/tests/**` |
| ③ 不得提高 `page_size`、不得循环抓全量、不得前端全量缓存 | 是：`CANDIDATE_PAGE_SIZE=100` 单页、单次交互 1 请求、`applyCandidateResponse` 整体替换（smoke F-03/F-04） |
| ④ 不得新增依赖或浏览器测试框架 | 是：`package.json` / `package-lock.json` 零 diff；浏览器验证脚本在 `/tmp`，未入库、未加脚本入口 |
| ⑤ TEST 阶段 `smoke:client` 须 352 passed / 0 failed 且 exit 0 | 当前已满足（§3.1），TEST 阶段复跑即为门禁 |

Contract 符合性：**零契约变更**（`docs/api/**` 零 diff）。仅复用 F003 §4/§6.1（`q`/`page`/`page_size`/`sort=code`/`order`）、F004 §4/§2.5（`q`/`cluster_id`/`type`/`sort=hostname`/`order`）；未新增端点/参数/权限项/错误码；未发送 `deleted`（默认 exclude，§21）；401/403/404/409/422 呈现沿用既有 `describe*ActionError`。

共享组件影响：`ui/controls.tsx`、`ui/feedback.tsx`、`src/api/**` **全部零 diff**；新增组件为 opt-in 独立文件，不改任何既有控件默认语义。

---

## 6. Mock 位置与替换真实 API 的方式

| 项 | 位置 | 说明 |
| --- | --- | --- |
| 客户端 smoke（入库） | `frontend/scripts/smoke-client.mjs` | 以受控 `globalThis.fetch` 替换既有模式（`respond` + `calls[]`）；F-01..F-12 只导入 `src/components/candidateSelectModel.ts` 与既有 `src/api/{resources,clusters,client}.ts`、`src/components/virtualMachine.ts`，**不引入新依赖**；响应形状严格按 Contract（`{items,page,page_size,total}`、统一错误信封 `{error:{code,message,details}}`）。**替换真实 API**：删除 F041 段不影响生产代码，真实集成由 TEST 的 I 层（真实 PG + 生产 app）承载 |
| 浏览器验证（临时，不入库） | `/tmp/f041_browser.py`、`/tmp/f041_layout.py` | `page.route` 受控响应：150 clusters（`F41C-0001..0150`）、154 BARE_METAL（`f41n-0001..0154`，属 `c-0110`）、1 个 VM（宿主 `h-0140`）、`/auth/me`、`/dashboard`、`/health`。**替换方式**：删掉脚本即可（不触碰仓库）；真实栈联调需可用的 backend + PG（本环境 F016 入口 `000` 不可达） |

Mock 通过 ≠ 集成通过：A1「提交被服务端接受」仍须 TEST 阶段 I-05/I-06/I-07（真实 PG + 生产 app + DB 行核对）证明。

---

## 7. 偏差、观察与未验证项

### 7.1 `<Select` 计数偏差（需要 Review/Tester 注意）

架构 §1.9 S-03 / §3 T3 的文字是「方案 A：`controls.tsx` 零 diff、`<Select` 仍 60/23」。实测为 **58 处 / 22 文件**：`grep "<Select"` 不匹配 `<CandidateSelect`，而两个 F041 载体（`VirtualMachineFields.tsx` 的 host 选择、`ResourceForm.tsx` 的 create 集群选择）按 §1.1/§1.4 必须改用新组件，因此必然少 2 处（60−2=58、23−1=22）。「仍 60/23」只在方案 B（给共享 `Select` 加 opt-in props、保留 `<Select` 调用点）下成立，与方案 A 的（T5 白名单 + `controls.tsx` 零 diff）互斥，属架构文字内的算术不自洽，不影响任何验收判定。**实质要求成立**：其余 21 个文件 `<Select` 计数逐个不变、`controls.tsx` 零 diff（§3.2 逐文件对照）。建议 Tester 在 §2 按 58/22 记录基线并注明原因；本角色未修改 `docs/architecture/**`（不在写权限内）。

### 7.2 antd 6 检索 prop 形态

antd 6.6.6 已把顶层 `searchValue` / `onSearch` / `filterOption` 标记 deprecated，改用 `showSearch` 对象（§2.2）。语义与 §1.1 一致；若 Review 要求字面使用顶层 props，会引入 deprecation 警告。

### 7.3 下拉关闭时组件库回灌空检索词 → 一次基准查询

`@rc-component/select` 在「下拉关闭且单选非 combobox」时调用 `onSearch("")`（`BaseSelect` 的 `rawOpen` effect，「Clean up search value when the dropdown is closed」），且不向业务层透传 `source`。因此：**输入检索词 → 关闭下拉**会额外产生 1 次不带 `q` 的基准候选请求（把列表恢复为首页）。实测（§4）：失败态下关闭下拉 → 仍 1 次请求；隔离该行为后，显式重试恰 +1。这符合 §1.3「`committedSearch` 变化即 1 次请求」，请求次数始终与候选总量无关（A3）；但 Review 若观察到「一次点击 2 次请求」，原因是本项而非重试重复。可接受（下拉关闭后输入框已清空，展示首页候选与用户所见一致）。

### 7.4 未验证项

| # | 未验证 | 原因 / 影响 |
| --- | --- | --- |
| U1 | **真实后端 + 真实 PG 的端到端**（真实栈入口 `127.0.0.1:18080` 不可达，`/api/v1/health` → `000`） | 本角色不做 I 层；A1「服务端接受」、A6 范围 `total`、A10 拒绝语义由 TEST 的 I-05..I-17 承载 |
| U2 | **人眼视觉复核** | 截图已生成（`/tmp/f041_shots/`，13 张，临时目录）；本 Agent 无法读图，视觉结论由 DOM 度量（无遮挡 / 无横向溢出 / label 在上方 / 提示完整可见 / 焦点环）承载；建议 Review 人工过一遍截图后转存 `docs/features/F041/artifacts/**`（本轮未写入以避免越权） |
| U3 | **屏幕阅读器真实播报** | 仅验证 `role=combobox`、`label[for]` 关联、Ant a11y 镜像列表 `aria-label`、`role=alert` 提示存在；未做 NVDA/VoiceOver 播报验证 |
| U4 | 大列表虚拟滚动在真实数据量下的性能 | product §3 明确不在验收范围（性能指标） |
| U5 | 编辑态「改选 Host 后服务端记 UPDATE 审计」 | 由 I-07 承载（前端只保证载荷携带新 id，smoke F-10/F-11） |

### 7.5 风险 FR-1..FR-8 实际观察

| ID | 观察 | 结论 |
| --- | --- | --- |
| FR-1 | 共享组件语义漂移 | `controls.tsx` 零 diff；`<Select` 仅两个 F041 载体减少（§7.1）；其余 21 文件计数不变 → 未漂移 |
| FR-2 | 跨集群候选残留 | 集群切换清空检索词（上下文归属）+ `onContextChange` 清空已选 Host + epoch 丢弃陈旧响应；单测 F-05、浏览器步骤 2（切类型后 host 请求自动带新 `cluster_id`）→ 未发现残留 |
| FR-3 | 编辑态回填丢失 | `pinned` 在 loading/error/empty 保留且恰一次；浏览器步骤 9（候选首页 100 条不含 `h-0140`，仍显示「f41n-0140（当前宿主）」并置于首项）→ 通过 |
| FR-4 | `q`+分页+范围导致「空结果误导」或泄露全库规模 | 四态 kind/role/文案互异（F-06）；error 含「可重试」、不含「无匹配/暂无数据」（F-06/浏览器）；超限文案只取响应 `total`（F-09 断言不含 120） |
| FR-5 | A3 被实现成「加载更多」或循环翻页 | 单触发点、`page` 恒 1、无累积请求（F-03：154 与 1540 均 1 次；浏览器实测每次交互 1 请求） |
| FR-6 | smoke 基线漂移 | 340 → 352，既有用例零删改，`await test(` 增量恰 12 |
| FR-7 | 新组件误用到其它控件 | 引用集合 = 定义 + `VirtualMachineFields` + `ResourceForm`（+ 一处文档注释）→ 未越界 |
| FR-8 | 移除整页门控引发创建页回归 | `npm run build` exit 0；`ResourceCreatePage` diff 仅删预加载与门控、保留 `canWrite` 拦截与提交构造；浏览器在 4 断点创建页可用、字段级四态正常 |

### 7.6 其它观察（不改动，供 Review）

* 浏览器控制台出现 antd 6 deprecation 警告（`Alert.message` → `title`、`Modal.maskClosable` → `mask.closable`），来自既有共享 `ui/feedback` / 确认弹窗组件（**零 diff**），非 F041 引入。
* `CandidateSelect` 的可见状态块与 `notFoundContent` 使用同一节点：四态在“下拉开/关”都可见（A7 不依赖打开下拉），代价是下拉打开时同一提示出现两处（属可接受的信息重复，无功能影响）。

---

## 8. 结论

`FRONTEND COMPLETE`：architecture §1.1–§1.5、§1.9、§6 全部落实；类型检查、生产构建、客户端 smoke（352/0）与真实浏览器交互/可访问性/四断点度量均通过；契约、Schema、后端、共享控件与依赖零 diff。本结论不替代独立 TEST（I 层真实 PG + 生产 app）、Review 或 Feature DONE；未验证项见 §7.4。

GIT: NONE
