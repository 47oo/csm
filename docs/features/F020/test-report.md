# F020 二次确认统一为模态对话框 — TEST REPORT

- **版本**：TD-1（TEST DESIGN）；执行结果见后续 `# Test Execution` 小节
- **日期**：2026-10-15

## TEST DESIGN

- **结论**：`TEST DESIGN READY`
- **依据**：`docs/product/requirements-v3.md` revision 7 §28/§21/§22/§23/§31（T59–T63）；`docs/features/F020/product.md` v1（AC1–AC7）；`docs/features/F020/architecture.md`（DR-346–DR-364，`layers{database:false,backend:false,frontend:true}`，api_required=false，Contract NOT_REQUIRED）；`frontend/package.json`、`frontend/scripts/smoke-client.mjs`、9 个受影响文件。
- READY 仅表示方案可验证，不代表测试通过、不批准实现或合并。
- 环境：无 vitest/jsdom/testing-library；可用 `npm run typecheck`、`npm run build`、`npm run smoke:client`（Node type-stripping + 受控 fetch）。真 PG 集成沿用 `compose.test.yaml`（`-p csmtest`）+ `TEST_DATABASE_URL`。

### 0. 数据完整性（无 Schema/后端变更，复用既有保证）
软删/恢复、Audit、权限、版本冲突均由既有 `confirm*` 请求与既有约束承担，本 Feature 未改，回归复用 F003–F012/F015。

### 1. 验收映射（AC1–AC7 / T59–T63）
| 验收 | 测试项 | 层次 | 预期 |
| --- | --- | --- | --- |
| AC1/T59 | F020-T01 | 静态 | `src` 内 `.inline-confirm` 引用=0；`index.css` 规则删除；11 处内联消失 |
| AC1/T59 | F020-T07 | 浏览器 | 9 文件各点击出现带遮罩模态，操作区无内联确认 |
| AC2/T60 | F020-T02 | 静态 | title/正文/okText/danger 正确（删/释 danger，恢复非 danger） |
| AC2/T60 | F020-T07 | 浏览器 | 文案与危险样式对应 |
| AC3/T62/T63 | F020-T05 | 机制级 | `smoke:client`：delete/release/restore 的 URL/method/body 不变，失败恰 1 次不重试 |
| AC3/T62/T63 | F020-T04 | 静态 | 无新增/改动 API client 调用；`confirm*` 未改 |
| AC3 | F020-T08 | 浏览器 | 确认发恰 1 次请求、成功后刷新 |
| AC4/T59/T61 | F020-T09 | 浏览器 | 取消/Esc/遮罩（非提交态）不发请求、状态不变 |
| AC4 | F020-T06 | 机制级 | 守卫模块：取消/关闭后不派发 |
| AC5/T61 | F020-T10 | 浏览器 | 提交中 loading、双击/回车/遮罩/Esc 不重复提交 |
| AC5/T61 | F020-T06 | 机制级 | 守卫 once-only |
| AC6/T62 | F020-T11 | 浏览器+真 PG | 引用/版本冲突错误在对话框内、对象未删、刷新按钮可用 |
| AC7/T63/T60 | F020-T12 | 真 PG 集成 | 权限/引用/Audit/载荷/端点无回归；释放/恢复同等 |
| AC7/T63 | F020-T03 | 浏览器 | VIEWER/EDITOR 无入口、ADMIN 可见 |

### 2. 静态断言
- F020-S1：`frontend/src` 内 `.inline-confirm` 命中=0（排除 `dist/`）。
- F020-S2：`index.css` 不含 `.inline-confirm` 块。
- F020-S3：`ConfirmDialog` 使用点=11（若迁移 ApiKey 则 12）。
- F020-S4：`onCancel` 调用 `setAction(null)`（并清 `actionError`），不发请求。
- F020-S5：`onConfirm` 指向既有 `confirmDelete/confirmRelease/confirmRestore`。
- F020-S6：`WarningState` 仍导出且被非本 Feature 引用。
- F020-S7：无新增 client 调用/请求构造改动；`confirm*` 逐字未改。
- F020-S8：`ConfirmDialog` 不 import `../api/*`、不持业务状态、不构造请求。
- NOTE：`frontend/dist/assets/*` 旧 CSS 不作为源引用；断言范围限 `src`。

### 3. 请求语义回归（AC3/T62/T63）
- `npm run smoke:client` 覆盖各域 client 的 URL/method/body 与「失败恰 1 次、不重试」；`confirm*` 未改即等价覆盖确认触发的请求语义。
- 静态 diff（S7）确认仅渲染层替换。
- 组件层「确认=1/取消=0」派发次数无 DOM 框架不可断言；由守卫模块（§4）部分覆盖 + 真浏览器覆盖，**不得以 build 通过冒充**。

### 4. 纯逻辑守卫模块（DR-363，采纳）
新增 `frontend/src/components/confirmDialogState.ts`（无 JSX）+ smoke 断言：
- F020-T06a：`beginCommit` 同会话二次返回 false（once-only）。
- F020-T06b：取消/关闭后守卫重置，重开可再提交。
- F020-T06c：提交失败后释放守卫，允许用户再次触发（不自动重试）。
- F020-T06d：守卫按对话框实例隔离。

### 5. 人工浏览器清单（必须）
每类对象：①点击→模态、无内联；②取消→无请求；③非提交态 Esc/遮罩→同②；④确认→恰 1 次请求、成功刷新；⑤引用/版本冲突→对话框内错误、对象未删、刷新可用；⑥提交中→loading、取消禁用、Esc/遮罩失效、双击不重复；⑦VIEWER/EDITOR 无入口、ADMIN 可见；⑧键盘 Tab/Esc 与焦点归还。
真 PG/集成回归：F003–F012/F015 删除/释放/恢复持久化、软删/恢复、引用拒绝、Audit、权限 403、版本冲突 409。

### 6. 不可验证项
| 项 | 理由 |
| --- | --- |
| 组件层派发次数、遮罩/Esc/双击事件接线 | 无 vitest/jsdom/testing-library，不新引入框架 |
| 弹层渲染/遮罩层级/焦点捕获与归还/键盘可达性 | 同上；仅人工浏览器，未执行时标 NOT TESTED |
| loading 视觉与禁用交互 | 同上 |

### 7. 结论
`TEST DESIGN READY`（TD-1）。无 Database Gate、Contract NOT_REQUIRED、无 Blocking 项。

---

# Test Execution（TEST）

- **版本**：TE-1（2026-10-15）
- **结论**：**`READY FOR REVIEW`**（残留 NOT TESTED 见 §E；本报告不批准合并，Merge Gate 由协调器执行）
- **执行对象**：F020 前端实现提交 `ef28edf`（`feature/F020-confirm-modal`），工作区干净
- **环境**：Node v24.14.0；后端 test 镜像 `csm-backend-f019test`；真 PG 容器 `csmtest-db-1`（库 `csm_test`，网络 `csmtest_default`）
- **Basis**：Test Design TD-1；`docs/features/F020/product.md` v1（AC1–AC7）；`architecture.md` DR-346–DR-364 + §10 签核；`implementation.md` v1；需求 revision 7 §28/§31（T59–T63）。Contract/Database/Backend `NOT_REQUIRED`。

## A. 静态断言（S1–S8）

| ID | 判据 | 实际 | 结果 |
| --- | --- | --- | --- |
| F020-S1 | `frontend/src` 内 `.inline-confirm` 命中=0（排除 `dist/`） | `grep -rn "inline-confirm" frontend/src` → 0；含 `scripts/` 亦 0 | **PASS** |
| F020-S2 | `index.css` 不含 `.inline-confirm` 块 | `grep -c` → 0，且 diff 显示该 CSS 块被删除 | **PASS** |
| F020-S3 | `<ConfirmDialog` 使用点=12（11 + ApiKey 1） | `grep -rn "<ConfirmDialog" src` → 12（10 文件） | **PASS** |
| F020-S4 | `onCancel` → `setAction(null)`（并清 `actionError`），不发请求 | 12 处 `onCancel` 均为 `setAction(null)`+`setActionError(null)`（ApiKey 为 `closeRevoke`），无请求调用 | **PASS** |
| F020-S5 | `onConfirm` 指向既有 `confirmDelete/confirmRelease/confirmRestore/confirmRevoke` | 逐处核对通过；`await`/API 调用行在 diff 中零变更 | **PASS** |
| F020-S6 | `WarningState` 仍导出且被非本 Feature 引用 | `ui/feedback.tsx` 导出；`InterfaceIpBindingPanel.tsx`（非 F020）仍引用 | **PASS** |
| F020-S7 | 无新增 client 调用/请求构造改动；`confirm*` 逐字未改 | F020 提交对 `frontend/src/api` 零改动；`git diff` 中页面/组件无新增/删除 `await`、无域名 client 调用；`confirm*` 仅行号位移 | **PASS** |
| F020-S8 | `ConfirmDialog` 不 import `../api/*`、不持业务状态、不构造请求 | 仅 import `antd`、`react`、`../confirmDialogState.ts` | **PASS** |

附加静态核对：删除/释放 `danger=true`、恢复 `danger=false`（`DeletedObjectsPanel`/`ResourceDetailPage` 恢复、`ClusterDetailPage` 恢复均无 `danger`）；`okText`=`确认删除/确认释放/确认恢复/确认吊销`（AC2/T60）。

## B. 前端命令（独立复跑）

| 命令 | 结果 |
| --- | --- |
| `npm run typecheck` | PASS（`tsc --noEmit` 无输出） |
| `npm run build` | PASS（1601 modules，`built in 16.59s`；仅 chunk>500kB 既有告警） |
| `npm run smoke:client` | **297 passed, 0 failed** |
| `F020 T06a` tryBegin once-only | PASS |
| `F020 T06b` reset 后重开可再提交 | PASS |
| `F020 T06c` settle 后释放、不自动重试 | PASS |
| `F020 T06d` 实例隔离 | PASS |

## C. 后端真 PG 回归（F020-T12）

- 全量：`pytest tests/ -q` → **664 passed, 2 skipped**（skip：F016 验收模块未启用、`test_migrations.py:105` 非超级用户前置，均与 F020 无关）。
- 聚焦（删除/释放/恢复/已删对象/审计/API Key 验收/权限/版本冲突/引用检查）12 模块 → **247 passed**。
- F020 无后端/数据改动（提交对 `backend/` 零改动），无新增用例；调用/载荷/端点由 S7 + 既有集成回归覆盖，确认 AC3/AC7/T62/T63 无回归。

## D. 验收映射（AC1–AC7 / T59–T63）

| 验收 / 条款 | 验证项 | 结果 | 说明 |
| --- | --- | --- | --- |
| AC1 / T59 | F020-T01/S1–S3 | **PASS** | 内联确认 0 残留、CSS 规则删除、12 处对话框；build 通过 |
| AC2 / T60 | F020-T02/S5 | **PASS** | 文案与 danger 静态核对逐项一致 |
| AC3 / T62 / T63 | F020-T04/T05/S7 + smoke | **PASS** | client/api 零改动；`confirm*` 未改；297 smoke 覆盖 URL/method/body 与不重试 |
| AC4 / T59 / T61 | F020-T06/T06b + S4 | **PASS（机制级）** | 取消映射 `setAction(null)` 不发请求；守卫 reset 可重开。Esc/遮罩浏览器触发 **NOT TESTED** |
| AC5 / T61 | F020-T06/T06a/T06c + S8 | **PASS（机制级）** | once-only 守卫 + `confirmLoading`/`cancelButtonProps.disabled`/`keyboard`/`maskClosable` 派生。双击/loading 浏览器渲染 **NOT TESTED** |
| AC6 / T62 | F020-T11 + 后端集成 | **PASS（机制级/后端）** | 错误块（references/conflicts/rangeConflicts/dependencyConflicts/occupancy/versionConflict + 刷新按钮）已移入对话框正文；失败保持对话框打开；对象未删由后端引用/版本冲突用例覆盖。对话框内渲染 **NOT TESTED** |
| AC7 / T63 / T60 | F020-T03/T12 + 247 集成 | **PASS（后端）+ NOT TESTED（浏览器权限 UI）** | 后端权限 403/引用/Audit/版本冲突回归通过；VIEWER/EDITOR 入口隐藏与 ADMIN 可见为静态条件渲染，浏览器表现 **NOT TESTED** |

## E. 未验证项（NOT TESTED）与替代证据

| 项 | 状态 | 替代证据 |
| --- | --- | --- |
| F020-T07 弹层/遮罩渲染、操作区无内联 | **NOT TESTED** | S1/S2/S3 静态 + build |
| F020-T08 确认发恰 1 次请求、成功刷新 | **NOT TESTED** | smoke 287→297 回归 + S5/S7 |
| F020-T09 取消/Esc/遮罩不发请求 | **NOT TESTED（浏览器）** | S4 + T06b 守卫机制级 |
| F020-T10 loading 视觉、双击/回车/遮罩/Esc 不重复 | **NOT TESTED（浏览器）** | T06a/T06c 守卫 + ConfirmDialog 派生 props 静态 |
| F020-T11 对话框内错误呈现与「刷新最新数据」可用 | **NOT TESTED（浏览器）** | 错误块移入静态核对 + 后端 409/引用集成 |
| 焦点捕获/归还、Tab 可达性 | **NOT TESTED** | AntD Modal 默认（DR-358） |
| 浏览器→真实 API 端到端 | **NOT TESTED** | `smoke:client` 为受控 fetch 机制级；服务端语义由真 PG 集成覆盖 |

**未验证项不影响机器可执行结论**：以上均为本仓库无 DOM/E2E 工具、已由 TD-1 §6 预先列为不可机测项，且已用静态/机制级/后端集成替代，符合 TD-1 的验证策略（不以 build 通过冒充交互验证）。合并前建议由人工浏览器清单（architecture §6.3）确认。

## F. Defects

None。未发现 BLOCKER/HIGH/MEDIUM/LOW 缺陷；无必须修复项。

## G. Issues / Next

| ID | 内容 | Owner |
| --- | --- | --- |
| F020-ISSUE-1 | 人工浏览器清单（弹层/遮罩/Esc/双击/焦点/loading/权限 UI）合并前应在真实浏览器上执行确认（TD-1 §5 / architecture §6.3） | 协调器 / Frontend |

## H. 结论（TE-1）

**`READY FOR REVIEW`**：全部机器可执行验收项（S1–S8、前端三命令、真 PG 回归）通过，无必须修复缺陷；浏览器 DOM 交互按 TD-1 声明为不可机测项并如实标 **NOT TESTED** 及替代证据。本报告不批准合并。

> 后续：Review 阶段判定 CHANGES REQUIRED（REV-F020-1/2/3），本 TE-1 结论已被下方「Repair round 1」复测取代；TE-1 记录与证据保留不改。

GIT: git status --short
GIT: git rev-parse --short HEAD
GIT: git branch --show-current
GIT: git show --stat --oneline ef28edf
GIT: git diff --stat ef28edf^ ef28edf -- frontend/src/api
GIT: git diff ef28edf^ ef28edf -- frontend/src/index.css
GIT: git diff ef28edf^ ef28edf -- frontend/src/pages frontend/src/components
GIT: git diff --name-only ef28edf^ ef28edf -- backend/tests
GIT: git status --porcelain --ignored frontend/dist

---

# Test Execution — Repair round 1（TE-2）

- **版本**：TE-2（repair round 1，2026-10-15）
- **结论**：**`READY FOR REVIEW`**（残留浏览器 DOM 项仍标 NOT TESTED；本报告不批准合并，Merge Gate 由协调器执行）
- **执行对象**：F020 修复提交 `483102c`（`feature/F020-confirm-modal`），工作区干净
- **Base**：`codex/v3.1` = `0bd9e24`；前次候选 `ef28edf` / 前次测试 `33a9a33`
- **复测范围**：Review 缺陷 REV-F020-1（MEDIUM，4 处对话框缺对象标识，已修复）与 REV-F020-2（F020-T02 判据缺口，本轮扩展）；REV-F020-3（LOW，刷新按钮未关闭对话框，已同轮统一）一并核对。
- **Basis**：Test Design TD-1；`product.md` v1（AC1–AC7）；`architecture.md` DR-346–DR-364（DR-361：`title`「<操作> <对象类型>」，正文保留对象标识/软删/引用提示）；需求 revision 7 §28/§31（T59–T63，T60/T62 要求对话框含**对象标识**）。Contract/Database/Backend `NOT_REQUIRED`。

## R1. REV-F020-1 独立核对（修复：对话框正文含当前对象标识）

修复提交 `483102c` 仅改动 `frontend/src/pages/ResourceDetailPage.tsx` 与 `ClusterDetailPage.tsx`（`git diff --name-only 33a9a33 483102c -- frontend`，无其他前端源文件）。逐处核对：

| 位置 | 操作 | title | 正文对象标识 | 结果 |
| --- | --- | --- | --- | --- |
| `ResourceDetailPage.tsx:757` | 删除资源 | 删除资源 | `确认软删除资源 {state.resource.hostname}？…`（保留软删/引用提示；BARE_METAL 追加 VM 引用说明） | **PASS** |
| `ResourceDetailPage.tsx:824` | 恢复资源 | 恢复资源 | `确认恢复资源 {state.resource.hostname}？…`（保留重检说明） | **PASS** |
| `ClusterDetailPage.tsx:321` | 删除集群 | 删除集群 | `确认软删除集群 {state.cluster.code}？…`（保留不级联/code 不可复用说明） | **PASS** |
| `ClusterDetailPage.tsx:374` | 恢复集群 | 恢复集群 | `确认恢复集群 {state.cluster.code}？…`（保留不级联/version 递增说明） | **PASS** |

REV-F020-1 的 4 处缺标识已全部补齐，文案与危险样式（删除 `danger`、恢复非 `danger`）及既有软删/引用提示无删减。

## R2. REV-F020-3 核对（刷新按钮关闭对话框）

全部 11 处「刷新最新数据」按钮点击回调均含 `setActionError(null)` + `setAction(null)` + `setReloadToken(…)`（`setAction(null)` 关闭对话框）；ApiKey 的「刷新列表」对应 `setRevokeTarget(null)` 关闭对话框。与其余 7 处一致。

位置：`NetworksPage:723`、`IpPoolsPage:679`、`ResourceDetailPage:813/875`、`IpAddressesPage:904`、`ServicesPage:739`、`ClusterDetailPage:363/413`、`DeletedObjectsPanel:315`、`InterfacesPanel:709`、`ServiceEndpointsPanel:594`（11 处）；`ApiKeyManagementPanel:695`（刷新列表）。**PASS**

## R3. F020-T02 判据扩展（REV-F020-2：逐一核对全部 ConfirmDialog 使用点）

对全部 12 个 `<ConfirmDialog` 使用点逐一核对 `title`/正文是否含对象标识或可接受的操作对象描述：

| # | 位置 | 操作 | title | 正文对象标识 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | `NetworksPage:660` | 删除/恢复网络 | 删除网络 / 恢复网络 | `action.network.name` | **PASS** |
| 2 | `IpPoolsPage:603` | 删除/恢复地址池 | 删除地址池 / 恢复地址池 | `action.ipPool.name` | **PASS** |
| 3 | `ResourceDetailPage:757` | 删除资源 | 删除资源 | `state.resource.hostname` | **PASS** |
| 4 | `ResourceDetailPage:824` | 恢复资源 | 恢复资源 | `state.resource.hostname` | **PASS** |
| 5 | `IpAddressesPage:840` | 释放/恢复 IP | 释放 IP 地址 / 恢复 IP 地址 | `action.ipAddress.address` | **PASS** |
| 6 | `ServicesPage:674` | 删除/恢复服务 | 删除服务 / 恢复服务 | `action.service.name` | **PASS** |
| 7 | `ClusterDetailPage:321` | 删除集群 | 删除集群 | `state.cluster.code` | **PASS** |
| 8 | `ClusterDetailPage:374` | 恢复集群 | 恢复集群 | `state.cluster.code` | **PASS** |
| 9 | `DeletedObjectsPanel:284` | 恢复已删对象 | `恢复 <对象类型>` | `「{action.item.label}」`（+ 对象类型） | **PASS** |
| 10 | `ApiKeyManagementPanel:663` | 吊销 API Key | 吊销 API Key | `「{revokeTarget.label}」`（+ 绑定账号 `username`、状态） | **PASS** |
| 11 | `InterfacesPanel:653` | 删除/恢复接口 | 删除接口 / 恢复接口 | `action.iface.name` | **PASS** |
| 12 | `ServiceEndpointsPanel:524` | 删除/恢复监听端点 | 删除监听端点 / 恢复监听端点 | `endpointLabel(action.endpoint)` | **PASS** |

12/12 均含对象标识或可接受的操作对象描述（第 9/10 处为名称+类型/名称+账号+状态，符合 DR-361）。**未发现遗漏，无新增缺陷放行阻塞。** 前次 TE-1 因未逐一核对对象标识而将 AC2 判为 PASS 的判据缺口（REV-F020-2）已在本轮闭合。

## R4. 静态断言 S1–S8 复跑

| ID | 判据 | 实际 | 结果 |
| --- | --- | --- | --- |
| S1 | `frontend/src` 内 `.inline-confirm` 命中=0 | 0（`grep` 退出码 1，无匹配） | **PASS** |
| S2 | `index.css` 不含 `.inline-confirm` | `grep -c` → 0 | **PASS** |
| S3 | `<ConfirmDialog` 使用点=12 | 12 | **PASS** |
| S4 | `onCancel` → `setAction(null)`+清 `actionError`，不发请求 | 11 处 `setAction(null)`+`setActionError(null)`，ApiKey 为 `closeRevoke`；无请求调用 | **PASS** |
| S5 | `onConfirm` 指向既有 `confirmDelete/confirmRelease/confirmRestore/confirmRevoke` | 12 处逐项核对通过 | **PASS** |
| S6 | `WarningState` 仍导出且被非本 Feature 引用 | `ui/feedback.tsx` 导出；11 文件引用 | **PASS** |
| S7 | 无新增 client 调用/请求构造改动；`confirm*` 未改 | `git diff --name-only 0bd9e24 483102c -- frontend/src/api backend docs/api` 为空 | **PASS** |
| S8 | `ConfirmDialog` 不 import `../api/*`、不持业务状态、不构造请求 | 仅 import `antd`、`react`、`../confirmDialogState.ts` | **PASS** |

## R5. 前端三命令（独立复跑，对象 `483102c`）

| 命令 | 结果 |
| --- | --- |
| `npm run typecheck` | PASS（`tsc --noEmit` 无输出） |
| `npm run build` | PASS（1601 modules，`built in 16.41s`；仅 chunk>500kB 既有告警） |
| `npm run smoke:client` | **297 passed, 0 failed**（含 F020 T06a–T06d） |

## R6. 后端回归

`git diff --name-only 0bd9e24 483102c -- backend docs/api frontend/src/api` 输出为空；`git log --oneline 0bd9e24..483102c -- frontend/src/api` 为空。本次修复无后端 / API / Contract 改动，删除/释放/恢复端点与载荷逐字复用，无需重复全量真 PG 回归（TE-1 全量 664 passed,2 skipped 仍有效，未被本修复触及）。

## R7. 验收映射更新（AC2）

| 验收 / 条款 | 前次（TE-1） | 本轮（TE-2） | 说明 |
| --- | --- | --- | --- |
| AC2 / T60 / T62 | PASS（判据缺口，未逐一核对对象标识） | **PASS（判据已闭合）** | 12/12 ConfirmDialog 均含对象标识/可接受描述；4 处新增标识；danger/okText 与操作对应 |
| AC1 / T59 / S1–S3 | PASS | **PASS** | 内联 0 残留、CSS 删除、12 处对话框 |
| AC3 / T62 / T63 / S7 + smoke | PASS | **PASS** | client/api 零改动；`confirm*` 未改；297 smoke |
| AC4–AC7 | PASS（机制级/后端）或 NOT TESTED（浏览器） | 维持不变 | 本轮未触及交互接线；浏览器项见下 |

## R8. 未验证项（NOT TESTED，维持）

弹层/遮罩渲染、取消/Esc/遮罩/双击/loading 事件接线、焦点捕获与归还、真浏览器→真实 API 端到端、浏览器权限 UI 均仍为 **NOT TESTED**（本仓库无 DOM/E2E 工具，TD-1 §6 预先列为不可机测项；替代证据同 TE-1 §E）。本轮新增标识/关闭行为仅为静态文案与回调核对，未在真实浏览器触发。

## R9. Defects

None。REV-F020-1（MEDIUM）与 REV-F020-3（LOW）经独立核对确认已修复；REV-F020-2 判据缺口已闭合，未发现新缺陷。

## R10. 结论

**`READY FOR REVIEW`**：REV-F020-1/2/3 已独立验证关闭；S1–S8、前端三命令（297 passed）通过；无后端改动；无必须修复缺陷。浏览器 DOM 项如实标 NOT TESTED 并保留替代证据。本报告不批准合并。

GIT: git log --oneline -8
GIT: git status --short
GIT: git rev-parse --short HEAD
GIT: git branch --show-current
GIT: git show --stat --oneline 483102c
GIT: git diff 33a9a33 483102c
GIT: git diff --stat 0bd9e24 483102c -- frontend/src/api backend/ docs/api
GIT: git log --oneline 0bd9e24..483102c -- frontend/src/api
GIT: git diff --name-only 33a9a33 483102c -- frontend
GIT: git diff --name-only 0bd9e24 483102c -- backend docs/api frontend/src/api
GIT: git status --porcelain
