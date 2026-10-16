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