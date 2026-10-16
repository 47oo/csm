# F020 二次确认统一为模态对话框 — IMPLEMENTATION 报告

- **版本**：v1（2026-10-15）
- **结论**：`FRONTEND COMPLETE`；Backend / Database / Contract `NOT_REQUIRED`

## Backend
`NOT_REQUIRED`：无服务端改动；删除/释放/恢复端点、参数、载荷逐字复用（F003/F004/F007–F012/F015）。

## Database
`NOT_REQUIRED`：无 Schema/索引/迁移。

## Frontend

### 新增
- `frontend/src/components/ui/ConfirmDialog.tsx`：纯展示组件（props：`open/title/children/okText/cancelText/danger/confirmLoading/onConfirm/onCancel`）；基于 AntD `Modal`，内部派生 `maskClosable/keyboard={!confirmLoading}`、`cancelButtonProps={{disabled}}`、`okButtonProps={{danger}}`、`width=520`；不 import `../api/*`、不持业务状态、不构造请求；内部一次性提交守卫忽略 `confirmLoading` 回落前的重复 onConfirm。
- `frontend/src/components/confirmDialogState.ts`：无 JSX 纯逻辑，`createConfirmCommitGuard()` → `{tryBegin/settle/reset/isInFlight}`；once-only、settle 不重试、reset 重开可再提交、实例隔离；import 带 `.ts` 供 Node 加载。

### 改造（仅替换渲染；`action`/`actionBusy`/`actionError` 与 `request*`/`confirm*` 逐字未改）
| 文件 | 内容 |
| --- | --- |
| `pages/NetworksPage.tsx` | Network 删/恢 → ConfirmDialog；错误块移入 |
| `pages/IpPoolsPage.tsx` | IP Pool 删/恢 |
| `pages/ResourceDetailPage.tsx` | Resource 删、恢（两处） |
| `pages/IpAddressesPage.tsx` | IP 释放（danger）/恢复 |
| `pages/ServicesPage.tsx` | Service 删/恢 |
| `pages/ClusterDetailPage.tsx` | Cluster 删、恢（两处） |
| `components/DeletedObjectsPanel.tsx` | 恢复 |
| `components/InterfacesPanel.tsx` | Interface 删/恢 |
| `components/ServiceEndpointsPanel.tsx` | Endpoint 删/恢 |
| `components/ApiKeyManagementPanel.tsx` | 吊销确认迁移为 `ConfirmDialog`（明文弹窗不动） |
| `index.css` | 删除 `.inline-confirm`（零引用后） |
| `scripts/smoke-client.mjs` | 追加 F020 T06a–T06d 机制级断言 |

- `okText`：确认删除/确认释放/确认恢复/确认吊销；删除与释放 `danger=true`，恢复 `danger=false`。
- 错误块（`ErrorState`，含 references/conflicts/rangeConflicts/dependencyConflicts/occupancy/versionConflict 与「刷新最新数据」）移入对话框正文；失败保持对话框打开。
- `WarningState` 保留（ApiKey 创建/明文、InterfaceIpBindingPanel、对话框正文）。

### Contract 符合性
`NOT_REQUIRED`；`frontend/src/api/` 零改动，无新增 client import；`onCancel`→`setAction(null)`+清 `actionError` 不发请求；`onConfirm` 指向既有 `confirmDelete/confirmRelease/confirmRestore/confirmRevoke`。

### 验证
| 命令 | 结果 |
| --- | --- |
| `npm run typecheck` | 通过 |
| `npm run build` | 通过 |
| `npm run smoke:client` | 297 passed, 0 failed（含 F020 T06a–T06d） |
| `grep -rn "inline-confirm" frontend/src` | 0 命中 |
| `grep -c "inline-confirm" frontend/src/index.css` | 0 |
| `<ConfirmDialog` 使用点 | 12（11 + ApiKey 1） |
| `frontend/src/api` diff | 0 |

### 未验证项
- 真实浏览器 DOM 交互（弹层/遮罩/Esc/双击/焦点/loading，F020-T07–T11）：无 DOM 工具 → NOT TESTED；由守卫模块 T06 作机制级替代，交互由人工浏览器清单覆盖。
- 真浏览器权限表现（T03）与真 PG 集成回归（T12）：复用既有 F003–F012/F015；本 Feature 无后端/数据变更。