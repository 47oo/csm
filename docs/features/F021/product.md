# F021 Resources 列表页行内删除 — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1
- **上游依据**：`docs/product/requirements-v3.md` revision 7 §23（权限矩阵，删除=DELETE_OBJECT）、§21（软删、不级联、引用检查、恢复）、§28（revision 7 删除/释放/恢复二次确认统一为模态，T59–T63）、§31；`docs/api/F004.md` v3 §6.5/§1.2/§1.3；`docs/features/F020/architecture.md`（ConfirmDialog）；用户 2026-10-15 输入。
- **复用说明**：复用 product-manager 2026-10-15 的 F021 澄清报告（结论 `READY FOR ARCHITECT`，无 Blocking Questions）。协调器核验：确认证据覆盖范围与验收；Architect 评估 database/backend/contract 无变更；无未决业务问题。

---

## 1. 目标与范围

在 Resource 列表页（`frontend/src/pages/ResourcesPage.tsx`，即「resource 首页」）行内「操作」列新增**单行删除**按钮，改善删除入口可达性（当前删除仅能在 Resource 详情页执行）。

范围内（复用既有规则）：
- 行内「删除」按钮：仅未删除行（`deleted_at = null`）且用户具备 `DELETE_OBJECT` 时显示。
- 点击复用 F020 `ConfirmDialog` 模态确认：含 hostname 对象标识、软删/不级联/引用检查提示、确认「确认删除」危险样式、取消；提交中不可重复提交。
- 确认调用既有 `DELETE /api/v1/resources/{id}?version=<行 version>`；成功 204 后关闭对话框并重载当前列表查询（保留过滤/排序/分页）。
- 失败在对话框内按 `describeResourceActionError` 呈现：409 `CONFLICT{reference_exists,references}` 引用列表、409 `VERSION_CONFLICT{current_version}`；对象状态不变。

## 2. 明确不做

- 不做批量 / 多选删除。
- 不做列表内「恢复」入口（仍在详情页）。
- 不为其它列表页（Cluster/Network/Interface/IP/Service 等）新增删除入口。
- 不改删除语义、权限门禁、引用检查、Audit、端点、请求载荷、错误码。
- 不使用内联二次确认（§28 已确认为模态）。

## 3. 验收标准（映射 §28 T59–T63、§23、F004 §6.5）

| # | 用户可观察行为 |
| --- | --- |
| AC1 | 行内「删除」仅对未删除行（`deleted_at=null`）且用户具备 `DELETE_OBJECT` 显示；无权限或已删行不显示；排序/过滤/翻页后规则不变 |
| AC2 | 点击弹出模态对话框：含 hostname、软删/不级联/引用检查提示；确认「确认删除」危险样式；有「取消」；页面无内联二次确认 |
| AC3 | 非提交态取消 / Esc / 遮罩关闭，不发送任何 DELETE 请求 |
| AC4 | 确认后仅发送一次 `DELETE /api/v1/resources/{id}?version=<行 version>`；提交中 loading，重复点击/回车/遮罩不产生第二次请求 |
| AC5 | 204 后关闭对话框并重载当前查询；`deleted=exclude` 下该行消失；过滤/排序/分页状态保持 |
| AC6 | 409 `reference_exists` 时对话框内呈现引用对象列表（如 VM hostname）且对象未删除 |
| AC7 | 409 `VERSION_CONFLICT` 时对话框内提示已被他人修改 + 服务器当前版本，可刷新；不静默重试/覆盖 |
| AC8 | 无 `DELETE_OBJECT` 用户无入口；直接调用端点仍被服务端 403 |
| AC9 | 本次仅 ResourcesPage 出现新删除入口；其它列表页与删除语义/权限/Audit 无回归 |

> 验收标准未执行；本报告仅定义可验证行为。

## 4. 领域与数据影响

无新对象/关系/状态/唯一性/生命周期；删除仍受「未删除 Interface / VM 引用」反向检查、软删 `deleted_at`、`version+1`、不级联、可恢复、Audit 约束，均不变。

## 5. Blocking Questions

无。非阻塞推荐项（单行删除、仅 Resource 列表）已获用户确认。

## 6. 受影响 Feature 与承接

F004（Resource 核心，DONE）、F020（ConfirmDialog，DONE）为复用对象，不改写其交付历史；本变更由新 Feature **F021** 承接。