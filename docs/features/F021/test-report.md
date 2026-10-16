# F021 Resources 列表页行内删除 — TEST REPORT

- **版本**：TD-1（TEST DESIGN）；执行结果见后续 `# Test Execution` 小节
- **日期**：2026-10-15

## TEST DESIGN

- **结论**：`TEST DESIGN READY`
- **依据**：`docs/features/F021/product.md`（AC1–AC9）；`docs/features/F021/architecture.md`（DR-365–DR-381；layers{database:false,backend:false,frontend:true}；api_required=false；Contract NOT_REQUIRED）；`docs/product/requirements-v3.md` revision 7 §21/§23/§28（T59–T63）；`docs/api/F004.md` v3 §6.5/§1.2/§1.3；现状前端。
- READY 仅表示方案可验证，不代表测试通过、不批准实现或合并。

### 0. 环境与既有保证
- 前端：`typecheck`/`build`/`smoke:client`；无 vitest/jsdom/testing-library（不新引入）。
- 真 PG：`compose.test.yaml`（`-p csmtest`）+ `TEST_DATABASE_URL`；复用既有 F003–F012/F015。
- 本 Feature 无数据/后端/契约变更，集成回归「确认未回归」，不新增真 PG 用例。

### 1. 验收映射（AC1–AC9）
| 验收 | 测试项 | 层次 | 预期 |
| --- | --- | --- | --- |
| AC1 | T01a/T01b | 静态 + 浏览器 | 仅「未删行 + DELETE_OBJECT」显示；VIEWER/已删行不显示；排序过滤翻页规则不变 |
| AC2 | T02a/T02b | 静态 + 浏览器 | 模态含 hostname/软删/引用提示；确认删除危险样式；无内联 |
| AC3 | T03a/T03b/T03c | 静态 + 机制级 + 浏览器 | onCancel 仅 setAction(null)+清错误；取消/Esc/遮罩零请求 |
| AC4 | T04a–d | 机制级 + 静态 + 浏览器 | 确认恰一次 `DELETE ?version=<行version>`；提交中 loading、双击/回车/遮罩不重复 |
| AC5 | T05a/T05b | 静态 + 浏览器 | 204 关闭并 reloadToken 重载、query 不变（保留过滤/排序/分页） |
| AC6 | T06a–d | 机制级 + 集成 + 浏览器 | reference_exists 呈现 references；对象未删 |
| AC7 | T07a–d | 机制级 + 静态 + 集成 + 浏览器 | VERSION_CONFLICT 呈现 current_version + 刷新按钮；不重试 |
| AC8 | T08a–d | 静态 + 机制级 + 集成 + 浏览器 | 无 DELETE_OBJECT 无入口；直连端点 403 |
| AC9 | T09a/T09b | 静态 + 集成 | 仅 ResourcesPage 新增入口；其它列表页/详情页行为无回归 |

必须真实浏览器：T01b、T02b、T03c、T04d、T05b、T06d、T07d、T08d。

### 2. 静态断言（F021-S1–S10）
- S1：`ResourcesPage` 含 ConfirmDialog（title=删除资源/okText=确认删除/danger/confirmLoading/onConfirm/onCancel）。
- S2：import `deleteResource`；`confirmDelete` 调 `deleteResource(resource.id, resource.version)`。
- S3：删除按钮条件含 `canDelete` 与 `resource.deleted_at === null`；danger+link-button，位于「查看」旁。
- S4：门控为 `permissions.includes("DELETE_OBJECT")`，不得用 WRITE 替代。
- S5：成功分支 `setAction(null)` + `setReloadToken(+1)`；query 未改写；列表 useEffect 依赖含 reloadToken。
- S6：`.inline-confirm` 命中=0。
- S7：错误块 references 经共享 `referenceItemText`；versionConflict 渲染「刷新最新数据」且 `disabled={actionBusy}`；失败保持对话框打开。
- S8：`ResourceDetailPage` 改为 import `resourceActionMessages`，不再本地定义两函数。
- S9：共享模块无 JSX/React/antd/api import，仅导出纯函数。
- S10：变更文件恰为 `ResourcesPage.tsx`、`ResourceDetailPage.tsx`、新增 `resourceActionMessages.ts`；`deleteResource` 仅出现在这两文件。

### 3. smoke:client（F021-M1–M8）
- M1 F004 `deleteResource` 回归；M2 `reference_exists` 回归；M3 `VERSION_CONFLICT` 回归；M4 `FORBIDDEN` 回归。
- **M5 新增** `referenceItemText`（resource→「虚拟机（VM）：<label>」、无 label→「虚拟机（VM）」、未知原样）。
- **M6 新增** `conflictItemText`（cluster/resource 已知文案、未知通用）。
- M7 F020 守卫 T06a–d 回归（覆盖 AC4 重复提交）；M8 导出面。

### 4. 真 PG / 集成回归（复用，不新增）
F004 删除软删持久化；F006 未删 VM 反向引用 409 reference_exists；恢复不级联；VIEWER 403；VERSION_CONFLICT；F015 Audit；F003/F005–F012 其它域回归。

### 5. 人工浏览器清单（必须）
ADMIN/VIEWER 各执行：①入口显示规则；②模态文案/危险样式/无内联；③取消/Esc/遮罩零请求；④确认恰一次、提交中不可重复；⑤204 关闭重载且保留查询；⑥reference_exists 对话框内引用列表且对象未删；⑦VERSION_CONFLICT 当前版本 + 刷新；⑧VIEWER 无入口、直连 403；⑨其它列表页/详情页无回归。

### 6. 不可验证项
组件层派发次数与事件接线、模态渲染/焦点/键盘、loading 视觉：无 DOM 框架 → NOT TESTED（由 M7 守卫机制级 + 人工清单替代）；`typecheck`/`build` 通过不证明交互正确。

### 7. 结论
`TEST DESIGN READY`（TD-1）。无 Database Gate、Backend/Contract NOT_REQUIRED、无 Blocking 项。