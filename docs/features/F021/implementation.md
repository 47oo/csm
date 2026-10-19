# F021 Resources 列表页行内删除 — IMPLEMENTATION 报告

- **版本**：v1（2026-10-15）
- **结论**：`FRONTEND COMPLETE`；Backend / Database / Contract `NOT_REQUIRED`

## Backend
`NOT_REQUIRED`：无服务端改动；复用 `DELETE /api/v1/resources/{id}?version=N`（F004 §6.5）。

## Database
`NOT_REQUIRED`：无 Schema/索引/迁移。

## Frontend

### 改动文件
| 文件 | 变更 |
| --- | --- |
| `frontend/src/components/resourceActionMessages.ts` | 新增：`referenceItemText`/`conflictItemText` 自 `ResourceDetailPage` 逐字抽取为纯函数（零 import、无 JSX/React/antd/api） |
| `frontend/src/pages/ResourceDetailPage.tsx` | 删除本地两函数，改为 import 共享模块；调用点不变（纯重构） |
| `frontend/src/pages/ResourcesPage.tsx` | 新增 `action/actionBusy/actionError`、`requestDelete/confirmDelete`、行内删除按钮（`canDelete && deleted_at===null`，danger+link-button）、`ConfirmDialog`（title=删除资源/okText=确认删除/danger/confirmLoading）与 `WarningState`/`ErrorState` 错误块（references/conflicts/versionConflict 刷新按钮） |
| `frontend/scripts/smoke-client.mjs` | 追加 F021 M5/M6 机制级用例 |

### 交互
点击行内删除 → F020 模态确认（hostname + 软删/引用提示）→ 确认恰一次 `DELETE ?version=<行 version>`（提交中加载/不可重复）→ 204 关闭并按当前 query 重载；失败（reference_exists / VERSION_CONFLICT）在对话框内呈现且对象未删；取消/Esc/遮罩零请求。

### Contract 符合性
`NOT_REQUIRED`；复用 F004 v3 §6.5 与 §1.2/§1.3/§5/§7，经既有 `deleteResource`/`describeResourceActionError` 原样调用；`frontend/src/api` 零改动。

### 验证
| 命令/断言 | 结果 |
| --- | --- |
| `npm run typecheck` | 通过 |
| `npm run build` | 通过 |
| `npm run smoke:client` | 299 passed, 0 failed（含 M5/M6） |
| S6 `.inline-confirm`=0 | 通过 |
| S8 详情页不再本地定义两函数 | 通过 |
| S9 共享模块零 import | 通过 |
| S10 `deleteResource` 仅出现于 api 定义 + ResourcesPage + ResourceDetailPage | 通过 |

### 未验证项
- 浏览器 DOM 交互（模态渲染/焦点/键盘/双击/loading、AC1–AC8 人工清单）：无 DOM/E2E 框架 → NOT TESTED；由 F020 守卫机制级 + 静态断言替代。
- 真实后端集成回归（F003–F012/F015）：无新数据行为，沿用既有回归。