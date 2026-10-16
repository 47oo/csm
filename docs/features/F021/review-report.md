# F021 Resources 列表页行内删除 — REVIEW 报告

- **Task**：F021（FEATURE，P1，M12）— Reviewer，独立正式 Review
- **结论**：`APPROVED WITH FOLLOW-UP`（无 BLOCKER / HIGH / 必须修复 MEDIUM）
- **日期**：2026-10-15 / 2026-10-16

## 审查范围

| 项 | 值 |
| --- | --- |
| Feature 分支 | `feature/F021-resource-list-delete` |
| Base 分支 | `codex/v3.1`（SHA `156a5df`） |
| Base SHA / start_commit / merge-base | `156a5dfdc73673e8acd395c299b2a1745128d8ff` |
| 最终批准 HEAD | `28622e2` |
| 合并提交 | `224fe0f`（父：`156a5df`、`28622e2`；集成树与批准 HEAD 一致） |
| 完整范围 | `git diff codex/v3.1...28622e2`，12 文件（生产源 3 + smoke 1 + docs 8） |

## 分层结论
- **需求符合性（PASS）**：AC1–AC9、T59–T63 满足。入口门控 `DELETE_OBJECT && deleted_at===null`；ConfirmDialog 模态含 hostname/软删与引用提示/危险样式/取消；确认恰一次 `DELETE ?version=<行 version>`；204 关闭并保留 query 重载；reference_exists（references 列表）/VERSION_CONFLICT（current_version + 刷新）在对话框内呈现且对象未删；VIEWER 无入口且服务端 403。无范围扩张。
- **架构符合性（PASS）**：严格复用 `ConfirmDialog` 与 `deleteResource`/`describeResourceActionError`；无新端点/参数/契约/Schema（`frontend/src/api`、`backend`、`docs/api` 零 diff）；`layers{database:false,backend:false,frontend:true}`、`api_required=false` 与实现一致。
- **共享模块（PASS）**：`resourceActionMessages.ts` 零 import、无 JSX/React/antd/api；`referenceItemText`/`conflictItemText` 与详情页原函数体逐字一致；详情页改 import 且不再本地定义。
- **功能正确性（PASS）**：失败保持对话框打开、`.finally` 清 busy、不重试；query 不被重置；请求语义与 Base 等价。
- **可维护性（PASS）**：遵循 `ui/` 适配层与代码风格；无死代码；未借机重构。
- **测试充分性（PASS）**：S1–S10 全 PASS；`typecheck`/`smoke:client` 独立复跑 299 passed（含 M5/M6）；后端 664 passed,2 skipped 回归无破坏；浏览器 DOM 项（T01b/T02b/T03c/T04d/T05b/T06d/T07d/T08d）诚实标注 NOT TESTED 且不降低验收。

## Findings
无 BLOCKER / HIGH / 必须修复 MEDIUM。未发现实现、设计或测试缺陷。

NOTE（非阻塞）：无 DOM/E2E 工具时组件层派发次数与弹层/焦点/键盘/loading 仅能由机制级守卫 + 静态断言替代（仓库既有能力边界，与 F020 相同）。

## Follow-ups
- **F021-FU-1（非阻塞，合并前人工）**：按 TD-1 §5 / architecture §6.5 由人工以 ADMIN/VIEWER 各执行九项浏览器清单，确认 T01b/T02b/T03c/T04d/T05b/T06d/T07d/T08d。Owner：协调器 / Frontend。

## 未审查项
真实浏览器交互未在 Review 执行（无工具，与 F021-FU-1 同）；后端真 PG 全量回归未在本轮重跑（无后端/API/数据改动）。

## 裁定
**`APPROVED WITH FOLLOW-UP`**，对 HEAD `28622e2`（Base `codex/v3.1`=`156a5df`）有效。Merge/DONE 由协调器按 `docs/project/git-workflow.md` 执行。