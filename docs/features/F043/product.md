# F043 前端交互回归可重复入口与 smoke 拆分（R08）— PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1（2026-10-29）；ENABLER / P2 / M30；分支 `feature/F043-test-entry`（交付线 `v3.4`，start_commit `8eec63b9af897167fc448dce222a175b6852188f`）；plan revision 25 / requirements revision 16
- **角色产物**：product-manager 只读产出，协调器持久化
- **Basis**：requirements rev16 §31（测试）；plan rev25 F043 `scope`/`acceptance`/`not_required`（`layers` 全 false、`api_required=false`、`depends_on: []`）；用户 2026-10-29 裁定 **AQ-4 = B**；`/tmp/csm-review-2026-10-29.md` §R08；`docs/features/F041/review-report.md` FU-4；测试基础设施先例 F016

## 1. 性质：测试基础设施，不是产品能力

交付**可重复的交互回归入口与 smoke 拆分**，不新增业务规则、不改产品页面/组件语义（`layers.frontend=false`，先例 F016）。T01–T129 用例集不变；本 Feature 只让若干交互回归**可重复执行、可断言、不依赖环境浏览器**。**不新增运行时或测试依赖**（AQ-4=B）；环境专用 Playwright 脚本（F033/F035/F041 的 `/tmp` 脚本）**不是仓库保证**，不得作为验收依据。「`frontend-ui` SKILL 验证命令去重」按 plan **不属本 Feature**。

## 2. 现状事实（只读核对）

- `frontend/scripts/smoke-client.mjs`：单文件 **9,718 行**，`await test(` 共 **352** 处（F041 test-report 实测 352 passed / 0 failed；R08 记录时为 9,210 行 / 340 项，其后已增长）。结构 = 替换 `globalThis.fetch` 为受控响应 + `calls[]` 计数 + `test()` 自增 + 末行 `${passed} passed, ${failed} failed` + 失败时 exit 1。
- 能力边界：可 `import` `src/api/*.ts` 与**无 JSX 的纯逻辑 `.ts`**（`candidateSelectModel.ts`、`importCarrier.ts` 等，Node ≥22.18 type stripping），**不能加载 `.tsx`**（F041 architecture §1.9）。
- `package.json` scripts 仅 `dev`/`build`/`preview`/`typecheck`/`smoke:client`；**无 DOM/E2E 入口**；dependencies 4、devDependencies 7。
- F033 浏览器巡检使用**环境全局 Python Playwright 1.58.0**（不在仓库依赖），脚本在仓库外、非门禁。

## 3. 交付定义：`npm run <name>` 可重复入口 + 5 类交互

入口使用仓库内既有能力（node + 既有 devDeps），可重复执行、exit 0 且**打印通过数**；覆盖下列 5 类交互，每类须有**可观察**正/负例（请求次数、payload/URL、状态机输出、文案谓词）：

| # | 交互 | 正例断言 | 负例断言 |
| --- | --- | --- | --- |
| ① | 候选检索选中第 101 条（F041） | 单次交互 `calls.length === 1`；URL 含 `q`/`cluster_id`/`type=BARE_METAL`/`page=1`/`page_size=100`；`total=154` 时截断标记为 true 且文案含总数与分页边界；选中第 101 位对象后候选集中该 id **恰一次**、label 不退化（FU-4） | 不出现 `page_size>100`、无循环翻页、无 `include`/`only`/`deleted=` |
| ② | 401 | 用户显式「重试」再发 1 次并成功（累计 2 次）；抛出 `ApiError(status=401)` 不被吞并 | 单次 401：`calls.length === 1`（无自动重试）、全局处理器 `handlerCalls === 1`（登录态只清一次） |
| ③ | 409 版本冲突 → 刷新 | 错误标记为版本冲突且携带 `current_version`；「刷新最新数据」重取后新 version 被采用，再次提交 payload 携带新 version | 冲突与刷新前后 `calls.length` 不出现自动增长；旧 version 再提交仍 409、不静默覆盖 |
| ④ | CSV 文件/文本载体切换（F034/F036） | 切 text 强制 `format="csv"`；切回 file 不回填 xlsx；两载体目标键不相等 | 切换后既有预校验/写入结果失效；未显式「校验/确认」前请求数不增长 |
| ⑤ | 危险操作取消（F020） | 取消/Esc/遮罩关闭 → 请求数 **0**；确认路径恰 1 次请求 | 提交态取消入口不可用；点击取消不产生请求 |

**覆盖声明边界**：① 的真实 ≥101 对象落库与提交被服务端接受属 F041 I 层与 F045 整体验收；本 Feature 只覆盖**逻辑/请求级**，不声明已证 T127/T128。

## 4. 验收标准

| ID | 断言 |
| --- | --- |
| A1 | `npm run <name>` 仓库内可重复执行、exit 0、打印通过项数；连续两次运行结果一致（无环境/时序依赖） |
| A2 | §3 五类交互均有对应用例，映射表逐条列出用例名 ↔ 交互编号 |
| A3 | 每类交互**至少 1 正例 + 1 负例**，断言可观察量（请求次数 / URL 或 payload / 状态机输出），不以「正常」「正确」代替 |
| A4 | smoke 拆分后**总用例数不减**：汇总 ≥ **352** 且可复算，无静默删除、无 skip/注释停用、无放宽既有断言 |
| A5 | `frontend/src/**` 产品语义**零 diff**；新增/调整仅限测试相关路径（`frontend/scripts/**` 等），逐条列出且不改可见文案与交互行为 |
| A6 | `npm run typecheck` 与 `npm run build` 通过；既有 `npm run smoke:client` 仍 `352 passed, 0 failed` |
| A7 | 不依赖浏览器二进制或网络：无 Playwright/Chromium 调用，离线可跑（不拉包、不启服务） |
| A8 | 证据入库 `docs/features/F043/**`（入口日志、映射表、diff 清单），未执行项如实标注 |
| A9 | 不新增依赖：`package.json` 与 `package-lock.json` **零 diff** |
| A10 | 不等同 F045：不替代变更集整体回归与部署等价验收，不改已 DONE Feature 的证据 |

## 5. 明确不做

N1 不降低既有断言覆盖。N2 不静默删除/skip/注释停用既有用例。N3 不新增运行时或测试依赖（含 Playwright、jsdom、测试框架、断言库）。N4 不改产品页面/组件语义、文案、交互与请求行为。N5 不把环境专用脚本或浏览器巡检当作仓库保证。N6 不改 API 契约、后端、Schema、权限与错误码。N7 不动 §20/§23.2 口径，不重写已 DONE 证据。N8 不把未执行项写成 PASS，不以本入口替代 F045。

## 6. Blocking Questions

**无。** AQ-4=B 已裁定，plan scope/acceptance 已定；残留歧义均为技术设计（§7）。

## 7. Non-blocking 观察（交 Architect）

| ID | 观察 |
| --- | --- |
| ON-1 | 入口形态：新建纯 node ESM harness（`frontend/scripts/interaction-*.mjs` + runner）vs 复用 `smoke-client.mjs` 的 fetch 替换与计数模式；均不得新增依赖 |
| ON-2 | 拆分粒度：按领域（api / 纯逻辑 / 候选 / 导入 / 确认）vs 按 Feature 区块；须给「汇总计数 = 352 + N」可复算机制 |
| ON-3 | 防静默删除的机器判据：逐文件 `await test(` 计数白名单、用例名摘要比对，择一或组合 |
| ON-4 | ⑤ 与部分 ③ 的断言点在 `.tsx`（`ConfirmDialog`、页面刷新逻辑）：能否仅用既有 `react-dom/server` 静态渲染，或需抽取纯逻辑谓词模块（后者须逐条列入 A5 放行清单） |
| ON-5 | ② 「刷新」措辞：本次定义为「全局未授权处理器恰一次 + 用户显式重试」；若需覆盖启动恢复失败路径请明确 |
| ON-6 | 入口命名与执行顺序（与 typecheck/build/smoke:client 的关系） |
| ON-7 | 证据目录与日志留存（`docs/features/F043/artifacts/**`） |

## 8. 后续文档更新

需求、`docs/product/**`、`docs/api/**`、`docs/database/**`、`backend/**`、`frontend/package{,-lock}.json` 均零 diff；`docs/features/F043/architecture.md` 由 Architect 新建；Test Report 记录 A1–A10 真实执行证据（未执行不得写 PASS）。
