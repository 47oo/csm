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
---

# Test Execution

- **版本**：TEST-1（2026-10-15）
- **Task**：F021 Resources 列表页行内删除 — TEST 模式（独立验证）
- **Status**：`READY FOR REVIEW`
- **Basis**：`docs/features/F021/test-report.md` TD-1；`docs/features/F021/product.md` v1（AC1–AC9）；`docs/features/F021/architecture.md` v1（DR-365–DR-381，§10 签核）；`docs/features/F021/implementation.md` v1；`docs/product/requirements-v3.md` revision 7 §21/§23/§28（T59–T63）；实现提交 `e956eb3`（`feat(F021): resource list inline delete`）。
- 本报告独立复跑，未复制开发者执行的通过结论。

## 1. Environment

| 项 | 值 |
| --- | --- |
| 工作区 | `/home/hanhao/github/47oo/csm`，HEAD `e956eb3`，工作区干净（`git status --porcelain` 无输出） |
| 前端 | Node（typecheck/build/smoke:client）；无 vitest/jsdom/testing-library；无浏览器/E2E 自动化工具（Playwright/Cypress 均未安装） |
| 后端 | 镜像 `csm-backend-f019test:latest`（`55d6ae45c201`）；真 PG `csmtest-db-1`（postgres:16，network `csmtest_default`，host `db`），库 `csm_test` |

## 2. 静态断言 S1–S10（独立执行）

| 断言 | 证据 | 结果 |
| --- | --- | --- |
| S1 | `ResourcesPage.tsx` ConfirmDialog：`title="删除资源"`、`okText="确认删除"`、`danger`、`confirmLoading={actionBusy}`、`onConfirm={confirmDelete}`、`onCancel={…setAction(null)+setActionError(null)}` | PASS |
| S2 | import `deleteResource`（L9）；`confirmDelete` 调 `deleteResource(resource.id, resource.version)`（L161） | PASS |
| S3 | 删除按钮条件 `canDelete && resource.deleted_at === null`（L402）；`danger` + `className="link-button"`；位于「查看」按钮之后 | PASS |
| S4 | `canDelete = user.permissions.includes("DELETE_OBJECT")`（L90）；未用 `WRITE` 替代（`canWrite` 仅用于「新建资源」） | PASS |
| S5 | 成功分支 `setAction(null)` + `setReloadToken((token) => token + 1)`（L164–165）；`query` 未被改写；列表 useEffect 依赖 `[query, reloadToken]` | PASS |
| S6 | `grep -rn "inline-confirm" frontend/src frontend/scripts frontend/index.html` 命中数 = **0** | PASS |
| S7 | 错误块 `references` 经共享 `referenceItemText`/`conflictItemText`；`versionConflict` 渲染「刷新最新数据」且 `disabled={actionBusy}`；失败分支仅 `setActionError(...)`，不 `setAction(null)`（对话框保持打开）；`.catch` 后无重试 | PASS |
| S8 | `ResourceDetailPage.tsx` 改为 `import { conflictItemText, referenceItemText } from "../components/resourceActionMessages.ts"`（L31）；无本地 `function referenceItemText`/`function conflictItemText` 定义 | PASS |
| S9 | `resourceActionMessages.ts` 零 `import`（grep `^import|require(|from |<[A-Z]` 无命中）；仅 `export function referenceItemText` / `conflictItemText` 两个纯函数 | PASS |
| S10 | 提交 `e956eb3` 的生产源文件变更恰为：`ResourceDetailPage.tsx`(M)、`ResourcesPage.tsx`(M)、`resourceActionMessages.ts`(A)；另含 `scripts/smoke-client.mjs`(M，测试代码) 与 `docs/features/F021/implementation.md`、`docs/project/project-plan.yaml`（非生产源）。`deleteResource` 仅出现于 `api/resources.ts`（定义）+ 上述两个页面文件 | PASS |

## 3. 前端三命令（独立复跑，提交 `e956eb3`）

| 命令 | 结果 |
| --- | --- |
| `cd frontend && npm run typecheck` | PASS（`tsc --noEmit` 无输出） |
| `cd frontend && npm run build` | PASS（1602 modules transformed，`✓ built in 16.82s`；dist 生成） |
| `cd frontend && npm run smoke:client` | **299 passed, 0 failed**（与实现报告一致） |

> `typecheck`/`build`/`smoke` 通过仅证明静态与机制级契约，不构成浏览器交互正确性的证据。

### 3.1 smoke M1–M8 核对

| 用例 | 结果 |
| --- | --- |
| M1 F004 `deleteResource`：DELETE + version Query、204→undefined（`PASS: F004 deleteResource…`） | PASS |
| M2 F006 `reference_exists` 解析 references（含 label）（`PASS: F006 409 CONFLICT reference_exists…`） | PASS |
| M3 F004 `VERSION_CONFLICT` 携带 `current_version`、不重试 | PASS |
| M4 `403 FORBIDDEN`（details.reason=csrf）明确呈现、不重试 | PASS |
| M5 新增 `referenceItemText`：resource→「虚拟机（VM）：<label>」/无 label→「虚拟机（VM）」/未知原样 | PASS |
| M6 新增 `conflictItemText`：cluster/resource 已知文案、未知通用 | PASS |
| M7 F020 守卫 T06a–T06d（once-only / reset / settle / 实例隔离） | PASS |
| M8 导出面（`typeof === "function"`） | PASS |

## 4. 后端真 PG 全量回归

- 命令（只读容器）：
  `docker run --rm --network csmtest_default -e TEST_DATABASE_URL='postgresql+psycopg://csm:csmtestpw@db:5432/csm_test' -e DATABASE_URL='postgresql+psycopg://csm:csmtestpw@db:5432/csm' -e PYTHONDONTWRITEBYTECODE=1 csm-backend-f019test pytest tests/ -q -p no:cacheprovider`
- 结果：**664 passed, 2 skipped**（用时 664.89s）。
- 跳过项（与 F021 无关）：
  - `tests/integration/test_f016_acceptance.py:50` — F016 acceptance module disabled（`F016_ACCEPTANCE=1` 才启用）。
  - `tests/integration/test_migrations.py:105` — 连接角色 `csm` 为 superuser，V3b 需非 superuser DB owner。
- F021 无后端/数据/契约变更；本次为**回归无破坏**结论。相关域断言抽查通过：
  - 软删持久化 / 不级联 / 同 hostname 可复用：`test_soft_delete_then_recreate`；软删可见性与 VIEWER/EDITOR `include|only` 403：`test_soft_delete_visibility_and_permissions`。
  - 权限矩阵（VIEWER delete → 403；EDITOR delete → 403）：`test_permission_matrix`。
  - 引用保护（Host 被未删 VM 引用 → 409 `reference_exists` + references，且对象未删；软删 VM 后可删）：`test_host_delete_protection`。
  - 乐观锁：`test_patch_stale_version_returns_409`（`VERSION_CONFLICT`/`current_version` 信封）；`delete_resource` 服务在 version 不匹配时 `raise VersionConflict`（代码核对 `backend/app/services/resource.py:1093`）。
  - 缺 version 删除 → 422：`test_delete_and_restore_missing_version_is_422`。

## 5. 验收映射（AC1–AC9 / T59–T63）

| 验收 | 验证项（层次） | 结果 |
| --- | --- | --- |
| AC1 门控显示 | T01a 静态（S3/S4）；T01b 浏览器 | T01a PASS；T01b **NOT TESTED**（见 §6） |
| AC2 模态内容 / 无内联 | T02a 静态（S1/S6、DR-373 文案）；T02b 浏览器 | T02a PASS；T02b **NOT TESTED** |
| AC3 取消/Esc/遮罩零请求 | T03a/b 静态+机制（`ConfirmDialog` `maskClosable/keyboard=!confirmLoading`；`onCancel` 仅本地清态，无 delete 调用）；T03c 浏览器 | T03a/b PASS；T03c **NOT TESTED** |
| AC4 恰一次 DELETE | T04a–c 机制（S2；`ConfirmDialog` 守卫 + F020 T06a–d smoke PASS）；T04d 浏览器 | T04a–c PASS；T04d **NOT TESTED** |
| AC5 204 关闭重载保留 query | T05a 静态（S5）；T05b 浏览器；集成（软删 204 / 列表可见性） | T05a+集成 PASS；T05b **NOT TESTED** |
| AC6 reference_exists 呈现 + 对象未删 | T06a 机制（S7、smoke M2）；T06b 集成（`test_host_delete_protection`）；T06c 静态；T06d 浏览器 | T06a–c PASS；T06d **NOT TESTED** |
| AC7 VERSION_CONFLICT 呈现 + 刷新不重试 | T07a 机制（S7、smoke M3）；T07b/c 静态+集成（乐观锁服务/信封）；T07d 浏览器 | T07a–c PASS；T07d **NOT TESTED** |
| AC8 无权限无入口 + 直连 403 | T08a 静态（S4）；T08b 机制；T08c 集成（`test_permission_matrix` VIEWER/EDITOR delete 403）；T08d 浏览器 | T08a–c PASS；T08d **NOT TESTED** |
| AC9 仅 ResourcesPage 新入口、无回归 | T09a 静态（S10 提交范围，其它列表页零改动）；T09b 集成（后端 664 passed 全量回归） | PASS |
| T59 模态二次确认、无内联 | S1/S6 + 机制 | PASS |
| T60 确认文案与危险样式 | S1（`okText="确认删除"`、`danger`）；释放/恢复不改（F020） | PASS |
| T61 提交中 loading / 不可重复 / Esc·遮罩关闭 | `ConfirmDialog` + F020 T06a–d smoke | PASS（浏览器视觉 NOT TESTED） |
| T62 对象标识 / 软删提示 / 引用检查；错误在对话框内且对象不变 | DR-373 文案（S7）+ `test_host_delete_protection` | PASS |
| T63 不改操作集合/权限/引用检查/Audit/载荷/端点，无回归 | S10 + 后端全量回归 | PASS |

## 6. NOT TESTED（浏览器 DOM 项）与替代证据

无 DOM/E2E 框架（无 vitest/jsdom/testing-library/Playwright/Cypress），以下浏览器级项目 **NOT TESTED**，不以 `build`/`typecheck` 通过冒充通过：

| 项 | 替代证据（静态 / 机制 / 集成） |
| --- | --- |
| T01b 入口按权限与 `deleted_at` 实际渲染 | S3/S4 静态门控；`test_soft_delete_visibility_and_permissions`（列表默认排除已删） |
| T02b 模态实际渲染 / 危险样式 / 焦点 | S1、`ConfirmDialog` 原型（`okButtonProps.danger`、width 520）；无渲染快照 |
| T03c 取消/Esc/遮罩真实零请求 | `ConfirmDialog` `maskClosable/keyboard=!confirmLoading`；`onCancel` 仅 `setAction(null)+setActionError(null)`，路径无 `deleteResource` |
| T04d 双击/回车真实不重复 | F020 守卫 smoke T06a–d；`confirmLoading` 置 loading 并禁用取消键 |
| T05b 204 真实关闭与列表重载 | S5（`reloadToken+1`、query 未改）；后端软删 204 集成 |
| T06d 引用列表实际 DOM 渲染 | S7（`referenceItemText` 渲染）；smoke M2/M5；`test_host_delete_protection` |
| T07d 冲突实际 DOM 与刷新交互 | S7（`current_version` 刷新按钮、`disabled={actionBusy}`）；smoke M3；乐观锁集成 |
| T08d VIEWER 界面无入口 + 直连 403 | S4 静态；`test_permission_matrix`（VIEWER/EDITOR delete 403） |

> 上述替代证据为机制级/静态/集成，**不替代** TD-1 §5 的人工浏览器清单；正式 Review 前应按 TD-1 §5 由人工在真实前后端执行 ADMIN/VIEWER 各九项。

## 7. Defects

无。未发现实现缺陷。

| ID | Severity | Layer | Location | 期望/实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — | — | — |

## 8. 未验证项 / Issues

- 浏览器 DOM / 视觉 / 键盘 / 焦点交互（§6）：NOT TESTED，缺工具与环境，替代证据如上。
- DELETE 请求使用「行 `resource.version`」的实际取值：由静态（S2 `resource.version`）与 F004 Contract 保证；无浏览器实测。
- 后端全量回归中 2 项 skip 与 F021 无关（F016 acceptance 未启用；migration V3b 需非 superuser DB owner）。
- 无 Blocking 项，无需 Database/Backend/Contract 验证。

## 9. 结论

`READY FOR REVIEW`：S1–S10 全部 PASS；前端三命令独立复跑通过（smoke **299 passed, 0 failed**）；后端真 PG 全量回归 **664 passed, 2 skipped**（F021 无后端/数据变更，回归无破坏）；AC1–AC9 / T59–T63 的静态、机制级与集成证据均 PASS。全部浏览器 DOM 项如实标记 **NOT TESTED**，替代证据已列，未以构建通过冒充交互正确。无必须修复缺陷。

GIT: git rev-parse --short HEAD
GIT: git status --porcelain
GIT: git diff --stat
GIT: git log --oneline -15
GIT: git show --stat --oneline e956eb3
GIT: git diff-tree --no-commit-id --name-status -r e956eb3
（以上均为只读命令，未改变 Git 状态。）
