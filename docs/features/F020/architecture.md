# F020 二次确认统一为模态对话框 — ARCHITECTURE 阶段报告

- **Task**：F020（FEATURE，P1，M11）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-15）
- **Basis**：`docs/product/requirements-v3.md` revision 7 §28（revision 7 二次确认模态条款）、§21、§22、§23、§31（T59–T63）；`docs/features/F020/product.md` v1（AC1–AC7）；`docs/project/project-plan.yaml` revision 8（F020：`layers{database:false,backend:false,frontend:true}`、`api_required:false`）；规划轻量评估结论；现有实现 `index.css`（`.inline-confirm`）、`ui/{feedback,surfaces}.tsx`、`ApiKeyManagementPanel.tsx`（吊销 Modal 基准）与 9 个受影响文件；既有契约 F003/F004/F007–F010/F011/F012/F015。

## 1. 方案摘要、边界与明确不做

F020 是**纯前端呈现层重构**：把 9 个文件共 11 处「内联二次确认」（`WarningState` + `div.inline-confirm`，位于操作区下方、易被忽略）改由**模态对话框**呈现，以既有「吊销 API Key」Modal 为一致样式基准。

1. 新增薄展示组件 `frontend/src/components/ui/ConfirmDialog.tsx`，封装 Ant Design `Modal`；只接收受控 props，**不持业务状态、不发请求**。
2. 各页面**保留 `action`/`actionBusy`/`actionError` 与 `request*`/`confirm*` 函数**（请求语义完全不变），仅把内联渲染替换为 `<ConfirmDialog>`。
3. 提交失败错误块（`ErrorState`，含 `references`/`conflicts`/`rangeConflicts`/`dependencyConflicts`/`occupancy`/`versionConflict`/「刷新最新数据」按钮）**移入对话框正文**。
4. 删除 `index.css` 的 `.inline-confirm`；`WarningState` 继续作为共享反馈原语保留。
5. 端点、参数、载荷、权限门禁、引用检查、Audit、错误码**一律不变**。

明确不做：不改语义/权限/引用检查/Audit/错误码/操作集合；不改 `AccountManagementPanel`（无删除端点）；无后端/API/Schema/契约/Migration；不新引入 DOM 测试框架；不借机全量重写；`ApiKeyManagementPanel` 一次性明文弹窗保持原样。

```yaml
layers: {database: false, backend: false, frontend: true}
api_required: false
```

## 2. Design Requirements（DR-346–DR-364）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-346 | 新增 `ui/ConfirmDialog.tsx`，基于 AntD `Modal`；纯展示原语，禁止持业务状态/构造请求/调用 API。 | CONFIRMED |
| DR-347 | Props 唯一清单：`open/title/children/okText?/cancelText?/danger?/confirmLoading?/onConfirm/onCancel`。 | CONFIRMED |
| DR-348 | `maskClosable={!confirmLoading}`、`keyboard={!confirmLoading}` 内部派生，不外露；`width` 固定默认（520）。 | PROPOSED |
| DR-349 | 不持业务状态、不发请求；`onConfirm`/`onCancel` 透传既有函数。 | CONFIRMED |
| DR-350 | 各页保留 `action/actionBusy/actionError` 与 `request*`/`confirm*`；仅替换渲染。 | CONFIRMED |
| DR-351 | 错误块移入对话框 `children`（含引用/冲突/版本冲突/刷新按钮）；删除对话框外 `actionError` 渲染。 | CONFIRMED |
| DR-352 | 失败时保持对话框打开（不清 `action`）；仅取消/关闭/「刷新最新数据」时关闭。 | CONFIRMED |
| DR-353 | `onCancel`=关闭且不发请求；非提交态取消/Esc/遮罩触发；提交态取消禁用、Esc/遮罩失效。 | CONFIRMED |
| DR-354 | 重复提交防护：`danger`+`confirmLoading` + `useRef` 一次性提交守卫，覆盖双击/回车连发。 | CONFIRMED |
| DR-355 | `WarningState` 保留；仅移除本 Feature 11 处内联用法。 | CONFIRMED |
| DR-356 | 零引用后删除 `index.css` 的 `.inline-confirm`，grep 断言无残留。 | CONFIRMED |
| DR-357 | （PROPOSED）`ApiKeyManagementPanel` 吊销 Modal 迁移为 `ConfirmDialog`；明文弹窗不变；非验收必需。 | PROPOSED |
| DR-358 | 可访问性沿用 AntD Modal（`title` 命名、焦点捕获、Esc、焦点归还）；不新增自定义 ARIA。 | CONFIRMED |
| DR-359 | 删除/释放 `danger=true`；恢复 `danger=false`；`okText`=`确认删除/确认释放/确认恢复`。 | CONFIRMED |
| DR-360 | 零后端/契约/数据变更；`api_required=false`→Contract NOT_REQUIRED。 | CONFIRMED |
| DR-361 | `title` 建议「<操作> <对象类型>」；正文保留原对象标识/软删/引用提示。 | PROPOSED |
| DR-362 | 11 处使用面（9 文件）：Networks/IpPools/ResourceDetail×2/IpAddresses/Services/ClusterDetail×2/DeletedObjects/Interfaces/ServiceEndpoints。 | CONFIRMED |
| DR-363 | （PROPOSED）可选纯逻辑守卫模块 `confirmDialogState.ts` 供 smoke 机制级断言重复/取消。 | PROPOSED |
| DR-364 | `confirm*` 函数体不动，保证 URL/method/body 与错误映射无回归。 | CONFIRMED |

## 3. Domain / Data Impact

无新增实体/关系/状态/生命周期/审计/Schema。软删/恢复、Audit、权限均复用既有保证且未改；无 Migration；无需 Database 角色核对。

| 规则依据 | 入口（未变） | 保证（未变） | 验证 |
| --- | --- | --- | --- |
| §21 软删/恢复 | 各域 delete/restore | 既有 FK/唯一/触发器 | 既有 F003–F012 回归 |
| §22 Audit | 成功操作 | 业务同事务写 audit_logs | 既有测试回归 |
| §23 权限 | 各端点鉴权 | 服务端权威 | 既有测试回归 |

## 4. Frontend / Backend Work

### Backend — NOT_REQUIRED
无服务端改动；复用既有 DELETE 与 `POST /api/v1/{object}/{id}/restore?version=`；不改契约。

### Frontend — REQUIRED
**新增**
1. `frontend/src/components/ui/ConfirmDialog.tsx`：薄展示组件（props 见 DR-347；内部派生 `maskClosable/keyboard`；一次性提交守卫；固定 `width`）。
2. （可选 PROPOSED）`frontend/src/components/confirmDialogState.ts`：无 JSX 提交守卫/状态转换纯模块，供 smoke。

**逐文件改造清单**

| # | 文件 | 内联处 | 改造 |
| --- | --- | --- | --- |
| 1 | `pages/NetworksPage.tsx` | 1 | → `ConfirmDialog`（title/okText/danger 随 kind）；错误块移入 |
| 2 | `pages/IpPoolsPage.tsx` | 1 | 同上 |
| 3 | `pages/ResourceDetailPage.tsx` | 2 | 两个 `ConfirmDialog`；错误块移入 |
| 4 | `pages/IpAddressesPage.tsx` | 1 | `okText`=确认释放/确认恢复，释放 danger；错误块移入 |
| 5 | `pages/ServicesPage.tsx` | 1 | 同上（删/恢） |
| 6 | `pages/ClusterDetailPage.tsx` | 2 | 两个 `ConfirmDialog`；错误块移入 |
| 7 | `components/DeletedObjectsPanel.tsx` | 1 | 恢复（无 danger）；错误块移入 |
| 8 | `components/InterfacesPanel.tsx` | 1 | 删/恢；错误块移入 |
| 9 | `components/ServiceEndpointsPanel.tsx` | 1 | 删/恢；错误块移入 |
| 10 | `components/ApiKeyManagementPanel.tsx` | 吊销 Modal（PROPOSED） | 改用 `ConfirmDialog`；明文弹窗不动 |
| 11 | `index.css` | `.inline-confirm` | 零引用后删除 |

复用：AntD `Modal`（经 ConfirmDialog）、`ui/feedback.tsx` 的 `ErrorState`/`WarningState`；各域 client 与 `describe*ActionError` 不动。

## 5. Contract 引用与状态

**NOT_REQUIRED**（`api_required=false`）。无 `docs/api/F020.md`；不修订任何契约。复用 F003（Cluster）、F004–F006（Resource）、F007（Interface）、F008（Network）、F009（IP Pool）、F010（IP Address 释放/恢复）、F011（Service）、F012（Endpoint）、F015（已删对象恢复）——端点/载荷/错误一律不变。

## 6. Test Work

### 6.1 验收映射
| 验收 | 判据 | 覆盖 |
| --- | --- | --- |
| AC1/T59 | 弹出带遮罩模态、操作区无内联确认 | grep + 真浏览器 |
| AC2/T60 | 对象标识/软删/引用提示；文案对应；删/释危险样式 | 浏览器 + 代码检查 |
| AC3/T62/T63 | 发出与改版前相同请求并执行原操作 | smoke:client 回归 + 集成 |
| AC4/T59/T61 | 取消/非提交态关闭不发请求不改状态 | 浏览器 +（可选）纯逻辑 |
| AC5/T61 | 提交中加载且不可重复提交 | 浏览器 +（可选）纯逻辑 |
| AC6/T62 | 错误在对话框内呈现、对象未删 | 浏览器 + 集成 |
| AC7/T63/T60 | 权限门禁不变；释放/恢复同等行为 | 既有权限集成回归 |

### 6.2 无 DOM 框架下的机制级替代
- grep 断言：`src` 内 `.inline-confirm` 引用=0 且 `index.css` 不含该规则；`ConfirmDialog` 使用=11（+可选 1）；`onCancel` 映射 `setAction(null)`；`WarningState` 仍存在且有非本 Feature 引用。
- 请求语义回归：既有 `npm run smoke:client`（各域 client URL/method/body 与「失败恰一次、不重试」）覆盖 AC3/T62/T63（`confirm*` 未改）。
- 「确认=1/取消=0」组件层派发次数：无 DOM 框架不可组件级断言；若采纳 DR-363 可部分机制级，否则仅真浏览器覆盖，不得以构建通过冒充交互验证。
- 不新增 DOM 框架（除非协调器裁定）。

### 6.3 人工浏览器清单（必须）
每类对象各执行：①点击→模态出现且无内联；②取消→无请求无状态变化；③Esc/遮罩（非提交态）→同②；④确认→请求与改版前一致、成功后刷新；⑤引用/版本冲突→错误在对话框内且对象未删、「刷新最新数据」可用；⑥提交中→loading、取消禁用、Esc/遮罩无效、双击不重复；⑦VIEWER 无入口、ADMIN 可见；⑧键盘 Tab/Esc 与关闭后焦点归还。

### 6.4 真 PG / 集成
删除/释放/恢复持久化、软删/恢复、Audit、权限、版本冲突沿用既有 F003–F012/F015 用例回归；本 Feature 无新数据行为，不新增真 PG 用例。

## 7. 决策、风险与 Implementation Layers

决策：见 §2（1–9、11–12、14 CONFIRMED；3、10、13 及标题文案 PROPOSED）。

风险：双击重复派发（中，DR-354）；错误移入后流程清 `action` 致错误不可见（中，DR-352）；漏改引用致死样式（低，DR-356）；ApiKey 迁移回归（低）；无 DOM 框架致交互不可机测（中，§6.2 + 真浏览器并如实标记）。

```yaml
layers: {database: false, backend: false, frontend: true}
```
实现顺序：`ConfirmDialog.tsx`（+ 可选 `confirmDialogState.ts`）→ 逐文件替换 11 处并移入错误块 → 删除 `.inline-confirm` →（可选）ApiKey 迁移 → typecheck/build/smoke:client + grep + 真浏览器清单。

## 8. 验证策略与不可验证项

可验证：前端三命令；grep 静态断言；浏览器人工清单；既有删除/释放/恢复/权限/审计集成回归。
不可验证：组件层派发次数（无 DOM 框架）；无浏览器时的弹层/焦点/键盘/双击交互须如实标记未验证。无数据库/后端/Schema 变更，无相应验证项。

## 9. 待核对项（非阻塞）
`maskClosable/keyboard/width` 是否外露、是否迁移 ApiKey 吊销 Modal、是否新增纯逻辑守卫模块、标题文案、默认 `width`。

**结论**：无 Blocking Questions；Contract/Database/Backend `NOT_REQUIRED`；`READY FOR DESIGN`。

GIT: NONE
---

## 10. 最终设计签核（CONTRACT Gate）

- **签核者**：Architect；**结果**：`READY FOR IMPLEMENTATION`
- **签核版本**：F020 Design v1（本文件）；Contract `NOT_REQUIRED`
- **核对的 Database / Backend**：均 `NOT_REQUIRED`（无 Schema/迁移/服务端改动）
- **核对的 Test Design**：`docs/features/F020/test-report.md` TD-1
- **上游依据**：requirements-v3.md revision 7 §28（T59–T63）；F020 product v1（AC1–AC7）；project-plan.yaml revision 8（用户 2026-10-15 批准）
- **覆盖 Feature**：F020
- **PROPOSED 项裁定**：采纳 DR-363（`confirmDialogState.ts` 纯守卫模块）；采纳 DR-357（`ApiKeyManagementPanel` 吊销确认迁移为 `ConfirmDialog`，与已批准 scope 文本「同步迁移该处」一致）；DR-348/DR-361 按默认实现。
- **一致性**：AC1–AC7 ↔ T59–T63 ↔ DR-346–DR-364 ↔ F020-T01–T12 无缺口/矛盾；Contract/Database/Backend NOT_REQUIRED 成立。
