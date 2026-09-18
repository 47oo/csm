# Review Report — F017 应用外壳侧边栏导航

> Verdict: **`APPROVED WITH FOLLOW-UP`**
> Author Role: reviewer
> Date: 2026-09-18
> 已被批准的证据：Feature HEAD `8c6586e99eba70571f351a8262502507f31de9d9`，Base `f74ee2ba18e0e2d3e890fed82ae7d0ad753f3bd2`（= develop），merge-base 同上。
> 后续代码 / 契约 / Base 变化须重新测试与 Review。

## Scope Reviewed

| 项 | 值 |
|---|---|
| Feature Branch | `feature/F017-sidebar-navigation` |
| start_commit / Base | `f74ee2ba18e0e2d3e890fed82ae7d0ad753f3bd2`（= develop，未漂移） |
| 已审查 HEAD | `8c6586e99eba70571f351a8262502507f31de9d9` |
| 范围 | `f74ee2ba...HEAD` 完整差异（13 文件，+1081 / −153） |
| 工作区 | clean（审查前、变异还原后复跑后均为空） |
| 门禁（Reviewer 复跑） | `typecheck` 退出 0；`npm run test` ×2 = **40 files / 618 tests passed**；`build` ✓ |
| 未审查 | 生产实例人工核验、真实浏览器视觉、真实后端数据加载 |

## Product Compliance

AC-01 ~ AC-08 全部满足且未越界：侧边栏 `<aside>` + `<main>`（`App.vue:751-752` flex）；侧边栏内 `<button>` 恰为 7 个 `nav-*` + 登出；活跃态由既有 `navSection` 单源派生、唯一且随切换更新；`bootstrap` / `login` / `:data-view` / 登出语义未改；`<script>` 零语义改动；15 处逐字改写；门禁通过；`pages/**`、`components/**`、`api/**`、`package.json`、`backend/**`、`docs/api/**` 逐字节未改。

**未新增、未修改任何产品规则**：范围 diff 不含 `requirements.md` / `domain-model.md`。**未发现静默改规则。**

## Architecture Compliance

REQUIRED 全部满足：活跃态单源（无 `el-menu`、无 `index`、无第二 `ref`）；侧边栏在内容区之前（`compareDocumentPosition` 探针证实）；7 个 `nav-*` 保留在可点击 `<button>`；`.el-button + .el-button { margin-left: 0 }` 已加（`App.vue:785`）；未引入被 guard 扫描的 token；`bootstrap` / `login` / `:data-view` 与 `<script>` 语义不动。

**`el-menu` 拒绝理由经独立核实成立**：安装版 `element-plus/es/components/menu/src/menu-item.*.mjs` 中 `createElementBlock("li", …)` —— `el-menu-item` 确实渲染 `<li>`，会令 7 个 spec 的 `findAll('button')` 定位失效。选型合理。

API Contract `NOT_REQUIRED` 成立。

## Database / Backend Review

不涉及（均为 false）。范围 diff 无相关文件。

## Frontend Review

唯一实现文件 `frontend/src/App.vue`：**`<script>` 零语义改动（代码级比对，剥离注释后仅 7 处 JSDoc 措辞差异）**；模板把 14 条页面 `v-if` 链包入 `<main>`、会话区搬入 `<aside>`；移除死规则 `.app-shell__header` / `.app-shell__brand-nav`；新增均为布局 / 活跃态，`.app-shell__content` 无 padding（不改变内容区内部视觉）。无第二真相源、无新依赖、无无关格式化。

## Test Review

- **AC-06 改写真实性**：`--numstat` = 5 文件各 `3 3`（插入 15 / 删除 15）；仅 class 字符串逐字替换；无 `it(` 增删；无 `.skip` / `.only` / `it.todo` / `xtest`；`el-button--primary` 在 tests 下零残留；用例总数 **618** 不变；三段结构（进入即活跃 / 切走不活跃 / 目标区活跃）均保留。
- **非空转（三种变异互补，由三方各自执行）**：
  1. 协调器：`:class` 集群项恒 `false` → 5 files 各 1 用例红（`to include`）。
  2. Tester：`navSection` 的 cluster 分支改为返回 `service` → 5 files 各 1 用例红。
  3. **Reviewer 本人两种**：7 处 `:class` 恒 **`true`** → 5 files 各 1 用例红（`to not include`，证明**第二条**断言非恒真）；7 处 `:class` 恒 **`false`** → 5 files 各 1 用例红（`to include`，证明**第一条**非恒真）。
  → 结合三方证据，**三条断言各自均已被独立证明可失败**。测试可信。
- **独立 DOM 探针**（临时，2 passed，已删除）：`aria-current` 契约（活跃 `"true"`，非活跃**不渲染属性**）、sidebar 早于 main、侧边栏按钮集合恰为 7 导航 + 登出、逐项点击唯一活跃。
- **guard 未绕过**：`f009ClusterResourceView.spec.ts` diff 为空、5 passed；`App.vue` 的 `恢复` 全部落在既有 scrub 短语内。
- **测试未被放宽**：回归 spec diff 为空。

## Findings

### LOW-1 — Test Report 证据行号失准（Owner: Tester）

- `docs/test-reports/f017-sidebar-navigation.md:33` 写「`App.vue:610` `display:flex` + `<aside>` + `<main>`」，但 `610` 是「虚拟机」导航按钮；实际 flex 在 `751-752`，`<aside>` / `<main>` 在 `586` / `653`。
- **影响**：证据引用不精确，不影响结论（结论由代码与探针独立成立）。**已在最终状态提交中更正。**

### LOW-2 — 裸金属活跃态在持久套件中缺覆盖（Owner: Frontend / Tester，follow-up）

- AC-02 要求高亮覆盖 7 区，但 15 处已提交改写覆盖 cluster / container / service / ip / nic / vm 六区；**裸金属区活跃态无持久断言**（架构已声明此空缺、不在 AC-06 范围；三方临时探针均覆盖并通过）。
- **影响**：实现为 7 项同构绑定，风险低；但第 7 区无持久回归保护。

### NOTE-1 — Product Handoff 引用行号部分不支撑结论（Owner: Product）

- `docs/product/handoffs/f017-sidebar-navigation.md:53` 引用 `App.vue:23 / 31 / 93`；行 23 实为「仍不引入 vue-router」，不含「导航形式不构成产品规则」（该结论由行 31、93 支撑）。**已在最终状态提交中更正。**

### NOTE-2 — F018 计划提交落在 F017 分支范围内（Owner: Coordinator）

- `bbe59c3` / `0e8455f` / `246266a` 仅改 `docs/project/*` 的 F018 计划，属 F017 主题之外；随 F017 进入 develop。**merge 说明中已确认携带。**

### NOTE-3 — 计划 `head_commit` 与 Test Report 的候选 HEAD 差异（Owner: Coordinator）

- 计划 `git.head_commit` 在 merge 前为 null；Test Report 记录测试环境 HEAD `3a4a13e`，交付 HEAD 为 `8c6586e`。二者之差仅测试报告文档本身，无代码差异，测试证据仍对交付 HEAD 有效。**merge 时已回填 `head_commit`。**

### NOTE-4 — 5 个 spec 的 describe 文案仍为「App 头部导航」（Owner: Tester）

- 架构允许一并更新但未强制；仅命名陈旧，无功能影响。

## Non-blocking Follow-ups

1. ~~LOW-1 / NOTE-1 文档行号与引用修正~~ → **已在 F017 最终状态提交中关闭**。
2. **LOW-2**：为裸金属活跃态补一条持久断言（可与 F018 一并）。
3. ~~NOTE-2 / NOTE-3~~ → merge 说明与 `head_commit` 回填均已处理。
4. **NOTE-4**：describe 文案陈旧。
5. 生产实例人工核验（AC-01 / 03 / 04 视觉与可达性）——属部署验收，非本 Feature 阻塞项。**已由部署后人工核验补上**（见文末）。

## Unreviewed Areas

1. 生产实例 `http://192.168.10.221/` 人工核验：Review 阶段本地未执行（Tester 已如实标注 `NOT TESTED`）。
2. 真实浏览器端视觉 / 交互（侧边栏观感、按钮 margin 复位实际效果、点击命中）。
3. 真实后端数据下的列表加载（组件测试为 fetch 桩）。
4. 真实前后端集成（本 Feature 无 API 面）。

## Verdict

```text
APPROVED WITH FOLLOW-UP
```

无 BLOCKER / HIGH / 必须修复的 MEDIUM；核心验收标准满足；测试可信（三种互补变异证明三条断言各自可失败）；实现未超范围；零后端 / 零契约 / 零 Schema 改动经只读 git 逐字节确认。

**只读 git 命令清单**：`git status --short`、`git rev-parse HEAD|develop`、`git merge-base develop HEAD`、`git merge-base --is-ancestor`、`git log --oneline`、`git diff --stat|--name-status|--name-only|--numstat f74ee2ba...HEAD`（含限定路径）、`git diff --cached --stat`、`git ls-files --others --exclude-standard`、`git show`。未执行 add / commit / branch / merge / stash / reset / checkout / switch。

## 协调器 Merge Gate（2026-09-18）

| # | 条件 | 结果 |
|---|---|---|
| 1 | 必需测试通过、真实集成已验证 | typecheck + 618 ×2 + build 全绿；本 Feature 无 API 面，无集成项 |
| 2 | 无 BLOCKER / HIGH / 必须修复的 MEDIUM | 成立（LOW-1/LOW-2 + NOTE-1~4，均非阻塞） |
| 3 | Subagent 全部结束、工作区 clean | 成立 |
| 4 | HEAD 与批准候选一致、develop 与审查 base 一致 | 成立（`8c6586e` / `f74ee2b`） |

**Merge**：`git switch develop` → `git merge --no-ff --no-commit feature/F017-sidebar-navigation` → `git commit -F`。
结果：**merge_commit = `8fc88324c53a7b8707d71c0964d276594036fc1e`**；父提交 = `f74ee2b`（Base）+ `8c6586e`（批准 HEAD）；**集成树与已审阅候选树逐字节一致**。

### 部署后人工核验（补 Review 的 Unreviewed Areas #1）

F017 已重建并滚动替换生产前端。人工核验结论见部署记录：侧边栏在真实实例上呈现为**左侧纵向**、含且仅含 7 个入口，用户名与登出可用，导航切换不改地址栏。**AC-01 / AC-03 / AC-04 的人工核验由此闭合。**
