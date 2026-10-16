# F021 Resources 列表页行内删除 — ARCHITECTURE 阶段报告

- **Task**：F021（FEATURE，P1，M12）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-15）
- **Basis**：`docs/product/requirements-v3.md` revision 7 §23/§21/§28（T59–T63）；`docs/features/F021/product.md` v1（AC1–AC9）；`docs/api/F004.md` v3 §6.5/§1.2/§1.3；`docs/features/F020/architecture.md`（DR-346–DR-364）；`docs/project/project-plan.yaml` revision 9（`layers{database:false,backend:false,frontend:true}`、`api_required:false`）；现状 `ResourcesPage.tsx`、`NetworksPage.tsx`、`ResourceDetailPage.tsx`、`ui/ConfirmDialog.tsx`、`api/resources.ts`。

## 1. 方案摘要、边界与明确不做

F021 是**纯前端入口扩展**：在 `ResourcesPage.tsx` 行内「操作」列新增单行删除按钮，复用 F020 `ConfirmDialog` 与 F004 `DELETE /api/v1/resources/{id}?version=N`。

1. 镜像 `NetworksPage` 范式：新增 `action`/`actionBusy`/`actionError` 与 `requestDelete`/`confirmDelete`，仅替换渲染为 `ConfirmDialog`；请求语义不变。
2. 门控：`canDelete = DELETE_OBJECT && resource.deleted_at === null`。
3. 成功 204 → 关闭对话框 + `reloadToken+1`（保留过滤/排序/分页）。
4. 失败按 `describeResourceActionError` 在对话框内呈现 `references` / `versionConflict`+`currentVersion` 与「刷新最新数据」；对象不删、不静默重试。
5. 重复提交防护由 `ConfirmDialog` 内置守卫承担。
6. 抽取 `ResourceDetailPage` 的 `referenceItemText`/`conflictItemText` 为共享纯函数模块。
7. 端点/参数/载荷/权限/引用检查/Audit/错误码一律不变。

明确不做：批量/多选删除、列表内恢复、其它列表页删除、改删除语义/权限/Audit/端点/载荷、内联二次确认；无后端/API/Schema/Migration；不新引入 DOM 框架；不借机重写页面。

```yaml
layers: {database: false, backend: false, frontend: true}
api_required: false
```

## 2. Design Requirements（DR-365–DR-381）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-365 | `ResourcesPage` 新增 `action:{kind:"delete";resource}|null`、`actionBusy`、`actionError`；`canDelete=DELETE_OBJECT`。 | CONFIRMED |
| DR-366 | 删除按钮仅 `canDelete && deleted_at===null` 渲染；已删行/无权限不显示；`danger`+`link-button`，置于「查看」旁。 | CONFIRMED |
| DR-367 | `requestDelete`：清 `actionError`，`setAction({kind:"delete",resource})`；打开不发请求。 | CONFIRMED |
| DR-368 | `confirmDelete`：`deleteResource(resource.id, resource.version)`（F004 §6.5），`actionBusy` 管控。 | CONFIRMED |
| DR-369 | 成功 204：`setAction(null)` + `reloadToken+1`；`query` 全保留。 | CONFIRMED |
| DR-370 | 失败：`setActionError(describeResourceActionError(error))`；保持对话框打开；`.finally` 清 busy；不重试。 | CONFIRMED |
| DR-371 | 抽取共享纯函数模块 `frontend/src/components/resourceActionMessages.ts`，导出 `referenceItemText`/`conflictItemText`；`ResourceDetailPage` 改 import，`ResourcesPage` 复用。 | PROPOSED（协调器采纳） |
| DR-372 | `ConfirmDialog` 复用：`open/title="删除资源"/okText="确认删除"/danger/confirmLoading/onConfirm`；`onCancel=setAction(null)+setActionError(null)`。 | CONFIRMED |
| DR-373 | 正文（`WarningState`）含 `hostname` 与软删/不级联/同集群 hostname 可复用提示；BARE_METAL 追加 VM 引用拒绝说明。 | CONFIRMED |
| DR-374 | 错误块移入 `children`：`ErrorState` + `references` 列表（共享 `referenceItemText`）+ `conflicts`（防御性，共享 `conflictItemText`）+ `versionConflict` 的「刷新最新数据」（清错误+清 action+重载，`disabled={actionBusy}`）。 | CONFIRMED |
| DR-375 | `VERSION_CONFLICT` 呈现 `current_version` 并可刷新；`reference_exists` 呈现引用 VM；均不静默重试。 | CONFIRMED |
| DR-376 | 重复提交防护完全依赖 `ConfirmDialog` 守卫，F021 不新增第二个守卫。 | CONFIRMED |
| DR-377 | 删除语义/服务端鉴权（VIEWER 403）/引用检查/软删/Audit/错误码不变。 | CONFIRMED |
| DR-378 | 仅 `ResourcesPage.tsx`、`ResourceDetailPage.tsx`（改 import）、新增共享模块三处变更；其它列表页零改动。 | CONFIRMED |
| DR-379 | 零后端/契约/数据/Schema；`api_required=false`→Contract NOT_REQUIRED。 | CONFIRMED |
| DR-380 | 共享模块命名/导出冻结：`resourceActionMessages.ts`；`referenceItemText({object_type,label})`、`conflictItemText({object_type,object_id})`；函数体逐字保留详情页语义。 | PROPOSED（协调器采纳） |
| DR-381 | 静态断言：`ResourcesPage` 含 `ConfirmDialog`/`deleteResource`/`deleted_at===null` 门控；`ResourceDetailPage` 改为 import 且不再本地定义；无 `.inline-confirm`。 | CONFIRMED |

## 3. Domain / Data Impact

无新增实体/关系/状态/唯一性/生命周期/审计/Schema/迁移。删除仍走既有软删与「未删 VM 引用」反向检查（F006 DR-62）；Audit/权限不变。无需 Database 角色核对。

## 4. Frontend / Backend Work

### Backend — NOT_REQUIRED
无服务端改动；复用 F004 §6.5。

### Frontend — REQUIRED
**新增**：`frontend/src/components/resourceActionMessages.ts`（纯函数，无 JSX/React）。
**修改**：
1. `frontend/src/pages/ResourcesPage.tsx`：新增状态与函数、行内删除按钮、`ConfirmDialog`、对话框内 `WarningState` + `ErrorState` 错误块（含刷新按钮）。
2. `frontend/src/pages/ResourceDetailPage.tsx`：删除本地 `referenceItemText`/`conflictItemText`，改为 import 共享模块（纯重构，行为不变）。

复用（不改）：`ui/ConfirmDialog.tsx`、`confirmDialogState.ts`、`ui/feedback.tsx`、`api/resources.ts`、NetworksPage 范式。

## 5. Contract 引用与状态

**NOT_REQUIRED**（`api_required=false`）。无 `docs/api/F021.md`；不修订契约。复用既有 **F004 v3** §6.5（`DELETE /api/v1/resources/{id}?version=N`，DELETE_OBJECT，204）与 §1.2/§1.3/§5/§8。

## 6. Test Work

### 6.1 验收映射（AC1–AC9）
| 验收 | 覆盖 |
| --- | --- |
| AC1 | 静态断言（门控）+ 人工浏览器（含 VIEWER） |
| AC2 | 人工浏览器 + 静态断言（ConfirmDialog/danger/无 .inline-confirm） |
| AC3 | 人工浏览器（零请求） |
| AC4 | smoke（deleteResource 语义 + F020 守卫 T06a–d）+ 人工浏览器 |
| AC5 | 人工浏览器 + 代码检查（reloadToken 不清 query） |
| AC6 | smoke（F006 reference_exists，describeResourceActionError 未改）+ 人工浏览器 |
| AC7 | smoke（VERSION_CONFLICT）+ 人工浏览器 |
| AC8 | 静态断言 + 既有权限集成回归 + 人工浏览器 |
| AC9 | grep（其它页无改动）+ 既有 F003–F012 集成回归 |

### 6.2 静态断言
`ResourcesPage` 含 `ConfirmDialog`/`deleteResource`/`okText="确认删除"`/`danger`/`deleted_at===null`/`reloadToken`，无 `.inline-confirm`；`ResourceDetailPage` 改为 import 共享模块、不再本地定义；共享模块无 JSX/React；其它列表页无新增删除入口。

### 6.3 smoke:client
既有 F004/F006/VERSION_CONFLICT/FORBIDDEN 回归；新增共享模块纯函数断言（`referenceItemText` resource→「虚拟机（VM）：<label>」、未知原样；`conflictItemText` 已知/未知文案）；`ConfirmDialog` 守卫 T06a–d 覆盖 AC4 重复提交。

### 6.4 真 PG / 集成回归
删除持久化、软删、VM 引用拒绝、Audit、权限、版本冲突沿用既有 F003–F012/F015；无新数据行为，不新增真 PG 用例。

### 6.5 人工浏览器清单（必须）
ADMIN/VIEWER 各执行：①未删行显示/已删行与无权限不显示；②弹模态（hostname/提示/危险确认/取消/无内联）；③取消/Esc/遮罩不发请求；④确认恰一次 DELETE?id&version，提交中 loading/双击不重复；⑤204 关闭重载且保留查询；⑥reference_exists 对话框内引用列表且对象未删；⑦VERSION_CONFLICT 提示当前版本 + 刷新；⑧VIEWER 无入口、直连端点 403；⑨其它列表页/详情页行为不变。

### 6.6 前端三命令
typecheck / build / smoke:client 全绿。

## 7. 决策、风险与 Implementation Layers

决策：DR-365–370、372–379、381 CONFIRMED；DR-371/380（共享模块）PROPOSED→协调器采纳。无重大未决，无需 ADR。

风险：抽取共享模块回归详情页文案（低–中，逐字保留 + 回归）；双击重复（低，守卫）；失败清 action 致错误不可见（低）；include/only 视图下已删行误显示（低，门控）；无 DOM 框架（中，静态 + smoke + 人工并如实标记）；误改其它页（低，限定三文件）。

```yaml
layers: {database: false, backend: false, frontend: true}
```
实现顺序：共享模块 → `ResourceDetailPage` 改 import（先回归）→ `ResourcesPage` → typecheck/build/smoke + grep + 人工浏览器。

## 8. 验证策略与不可验证项

可验证：静态断言；smoke:client（既有语义 + 共享模块纯函数 + F020 守卫）；真浏览器人工清单；既有集成回归。
不可验证（如实标记）：无 DOM 框架时组件层派发次数不可机测（守卫机制级 + 真浏览器替代）；无浏览器时弹层/焦点/键盘/双击标记未验证；构建通过不等于交互正确。

## 9. 待核对项（非阻塞）
共享模块名/导出（默认采纳）；`conflicts` 防御性渲染（默认保留）；模块路径 `components/`（默认认可）。

**结论**：无 Blocking Questions；Database/Backend/Contract `NOT_REQUIRED`；`READY FOR DESIGN`。

GIT: NONE