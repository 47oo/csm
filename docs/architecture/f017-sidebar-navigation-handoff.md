# Architecture Handoff — F017 应用外壳侧边栏导航

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-18
> Feature Branch: `feature/F017-sidebar-navigation` ｜ start_commit `f74ee2b`

## Feature

**F017 — 应用外壳侧边栏导航**（App Shell Sidebar Navigation）

## Product Source

- `docs/product/handoffs/f017-sidebar-navigation.md`（`READY FOR ARCHITECT`，无 Blocking Open Questions，AC-01 ~ AC-08）
- `docs/project/v1/project-plan.yaml` `features[F017]` / `M7` / `DEC-020`

## Architecture Summary

**纯呈现层改造**，唯一实现文件 `frontend/src/App.vue`（模板布局 + 活跃态呈现 + scoped 样式），另有 5 个既有导航测试文件中的 15 处活跃态断言**改写**。

现有系统状态（已核实）：

- Vue 3 + Element Plus 2.14.5；**无 `vue-router`**；**无独立导航组件 / 路由模块**——应用外壳、视图状态机（`ResourceView` + `open*` / `back*`）、登录 / bootstrap / 登出全部集中在 `App.vue`。
- Backend / Database / API 契约与本 Feature 无关。
- 测试基线 40 files / **618 tests**；7 个 `app*.spec.ts` 通过 `App.vue` 驱动导航。

方案要点：

1. **布局**：`app` 分支内把顶部 `<header>` 改为纯 CSS flex 纵向布局——左侧 `<aside class="app-shell__sidebar">`（品牌 + `<nav>` + 会话区），右侧 `<main class="app-shell__content">` 承载既有 14 条 `v-if` 页面链。
2. **不引入新依赖、不使用 `el-menu`**：保留每个导航项为既有 `<el-button data-testid="nav-*">`，只改排布方向与活跃态表达（见「布局方案对比与选型」）。
3. **活跃态**：保留既有与布局无关的 computed `navSection`（**语义不改**），活跃态由 `:type="primary"`（`el-button--primary`）改为自定义 class `app-shell__nav-item--active` + `aria-current="true"`。15 处断言即改为断言该 class。
4. **`data-testid` 稳定**：7 个 `nav-*` testid 原样保留在 `<button>` 上。
5. **`<script>` 逻辑零语义改动**；不改 `bootstrap` / `login` 分支、`:data-view`、登出逻辑。

## 布局方案对比与选型

| 维度 | (a) `el-container` / `el-aside` / `el-menu` / `el-menu-item` | **(b) 纯 CSS flex + 保留既有 `el-button`** ✅ 选定 |
| --- | --- | --- |
| 依赖 | 组件已在 element-plus 内，不算新依赖 | 同左（仅用 CSS） |
| **测试可定位性** | **`el-menu-item` 渲染为 `<li role="menuitem">`，不是 `<button>`**。7 个 `app*.spec.ts` 的 `findButton(wrapper, '容器'\|'集群'\|…)` 靠 `findAll('button')` 定位并点击——**全线失效**，被迫重写远超 AC-06 所限的断言（跨 7+ 文件） | **保留 `<button>`**，既有 `findButton` 点击链路零改动；只需改 15 处活跃态断言（正是产品限定的范围） |
| 与既有样式关系 | 需引入 `el-menu` 次级样式并将配色重新对齐 | 复用现有 `app-shell__*` scoped 样式与配色，改动最小 |
| 语义适配风险 | `el-menu` 默认与 `index` / 路由耦合；无 vue-router 时需受控 `:default-active` + `@select` + 手写 `index↔navSection` 映射，**引入「选中态」第二真相源** | 无：活跃态直接由既有 `navSection` 单源派生 |
| 可访问性 | `<li role="menuitem">` 在无路由场景语义含糊 | `<aside><nav>` + 原生 `<button>` + `aria-current` 语义直接正确 |
| 复杂度 | 引入折叠、子菜单、index 等当前不需要的概念 | 最小 |

**结论：选 (b)。** ① 不扩大测试回归面；② 无 vue-router 时 (a) 会制造 `index` 与 `view` 的双真相；③ 复用既有样式与既有 `<el-button>`，符合「简单、可读、易验证」。**产品 AC 明确不要求任何实现机制**（未要求 `el-menu`）。

## Domain Impact

**无。** 不新增 / 修改任何资源类型、分类、关系、状态、唯一性、生命周期；不新增导航目标（保持既有 7 个）。导航形态不构成产品规则（`f002-bare-metal-handoff.md:230`、`App.vue` 既有注释）。

## Data Layer Impact

**无**（`database: false`）：无新表 / 字段 / 关系 / 索引 / 唯一约束 / migration。

## Backend Work

`None`（`backend: false`）。

## Frontend Work

1. **`App.vue` 模板布局改造**（`app` 分支内）：

```html
<div class="app-shell__layout">
  <aside class="app-shell__sidebar">
    <div class="app-shell__brand">CSM</div>
    <nav class="app-shell__nav"> …7 个 nav 按钮（原样，见 2）… </nav>
    <div class="app-shell__session"> …用户名 + 登出（原样搬移）… </div>
  </aside>
  <main class="app-shell__content"> …既有 14 条 v-if / v-else-if / v-else 页面链（原样搬移）… </main>
</div>
```

`bootstrap` / `login` 两个分支与根 `<div class="app-shell" :data-view="view">` **保持不动**。

2. **7 个导航项**：保留 `<el-button>` 与 `data-testid="nav-*"`，`@click` 目标不变；**去掉** `:type="navSection === '…' ? 'primary' : 'default'"`，改为：

```html
<el-button
  data-testid="nav-clusters"
  :class="{ 'app-shell__nav-item--active': navSection === 'cluster' }"
  :aria-current="navSection === 'cluster' ? 'true' : undefined"
  @click="openClusterList"
>集群</el-button>
```

（其余 6 项同构，仅切换 `navSection` 值与 click 目标。）

3. **scoped 样式**（全部在 `App.vue`）：
   - `.app-shell__layout { display: flex; align-items: stretch; min-height: 100vh; }`
   - `.app-shell__sidebar { flex: 0 0 200px; width: 200px; display: flex; flex-direction: column; gap: 8px; padding: 16px; background:#fff; border-right:1px solid #e4e7ed; }`
   - `.app-shell__nav { display: flex; flex-direction: column; gap: 4px; }`
   - `.app-shell__nav .el-button { width: 100%; justify-content: flex-start; }`
   - **必需**：`.app-shell__nav .el-button + .el-button { margin-left: 0; }`——Element Plus 默认 `.el-button + .el-button { margin-left: 12px }`，纵向堆叠时会变成「后续按钮缩进 12px」的视觉缺陷。
   - `.app-shell__nav-item--active { /* 活跃态视觉，例如实心背景 / 左侧色条；仅样式 */ }`
   - `.app-shell__session { margin-top: auto; display:flex; align-items:center; gap:12px; }`
   - `.app-shell__content { flex: 1; min-width: 0; }`（**不加内边距**，避免改变既有页面内部视觉）
   - 删除不再使用的 `.app-shell__header` / `.app-shell__brand-nav` 规则。
   - 说明：`<el-button>` 作为子组件根元素会带上父 scope id，故 `.app-shell__nav .el-button` 这类 scoped 选择器可命中；如不命中再用 `:deep(.el-button)`（不改变任何语义）。

4. **注释更新（低风险）**：`navSection` 上方「头部导航高亮」改为「侧边栏导航高亮」；测试注释里的「头部导航」措辞可一并更新。**不得**引入 `恢复` / `回收站` / `restore` / `undelete` / `include_deleted` token（见 Constraints）。

5. **5 个测试文件的 15 处断言改写**（见「Test Work」），**不改**其余用例、**不新增 / 不删除**用例（保持 618 计数）、不 skip。

**明确不写代码到**：`pages/**`、`components/**`、`api/**`、`docs/api/**`、后端、数据库。

## API Contract

```text
NOT_REQUIRED
```

**理由**：呈现层改造，不改 `ResourceView` / `open*` / `back*` / 任何资源页面的数据请求，故**不新增、不修改任何 HTTP 端点、请求 / 响应 schema、错误语义**。既有契约保持冻结，`docs/api/` 无需新增文件。Backend 与 Frontend 之间**不存在需要冻结的新协议**。

## Test Work

### AC-06：15 处断言改写方案（DOM Contract，Architecture 冻结）

侧边栏中**当前所在资源区**的导航按钮，其根 `<button>` 同时满足：class 列表含 `app-shell__nav-item--active`；`aria-current="true"`。非当前区不含该 class，`aria-current` 为 `undefined`（不渲染该属性）。

**改写规则**：5 个文件、每文件 3 处，把字符串 `'el-button--primary'` **逐字替换**为 `'app-shell__nav-item--active'`（其余断言结构、testid、waitFor 全部不动）：

| 文件 | 现有 3 处（行） |
| --- | --- |
| `appContainerNavigation.spec.ts` | 153 / 160–162 / 163 |
| `appServiceNavigation.spec.ts` | 162 / 169–171 / 172 |
| `appIpAddressNavigation.spec.ts` | 330 / 337–339 / 340 |
| `appNetworkInterfaceNavigation.spec.ts` | 277 / 284–286 / 287 |
| `appVirtualMachineNavigation.spec.ts` | 277 / 284–286 / 287 |

**为什么等价、不削弱**：改写后每条用例仍保持原有三段结构——① 进入目标区后该区**活跃**；② 切走后该区**不再活跃**；③ 切换目标区（集群）**变为活跃**。这恰好验证「当前所在资源区高亮正确、且非当前区不高亮」。原断言绑定 Element Plus 的 `el-button--primary`，新断言绑定本 Feature 定义的活跃态 class，二者在「唯一活跃、随切换更新」上语义一一对应。**禁止**改成恒真、删除任一断言、或 `.skip`。

**（PROPOSED，非必需）**：如需更强冻结「唯一性」，可在同一用例内加「7 个 `nav-*` 中恰好一个含活跃 class」。

### AC-01 ~ AC-05 回归

- AC-01 / 02：既有 7 个 `app*.spec.ts` 已覆盖各资源区进入（`findButton(...)`），改写后仍执行全部点击与请求断言；活跃态由改写后的三段断言覆盖 cluster / container / service / ip / nic / vm（**裸金属区活跃态为既有覆盖空缺**，不在 AC-06 范围，不强制新增）。
- AC-03 / 04：`appAuth.spec.ts` 覆盖登录、bootstrap、全局 401、登出 204/401 归一；`findButton('登出')` 在侧边栏会话区仍命中；`[data-view]` 保留。
- AC-05：`app*Navigation.spec.ts` + `appBareMetalRelatedNavigation.spec.ts` 覆盖列表↔详情与 F010 返回链路 / 集群·宿主上下文；本次无逻辑改动，应全绿。
- **AC-06 guard**：`f009ClusterResourceView.spec.ts` 源码 token 扫描**保持原样、不删除**。

### Testing Agent 必须独立证伪的声明

1. **15 处是「改写」而非删除 / 恒真 / skip**：`git diff` 应显示 5 个文件各 3 处**仅字符串替换**，无删除的 `it`、无 `skip`、无恒真断言；`npm run test` 用例总数应仍为 **618**。
2. **改写后的断言确实能失败（非恒真）**：用**临时、不提交**的变异——把 `App.vue` 的活跃 `:class` 绑定去掉（或恒置 `false`），对应 5 个文件的活跃态断言必须**变红**；随后逐字节还原。这证明断言绑定真实行为。
3. **返回链路与上下文确实未破坏**：全量跑既有 `app*` / `appBareMetalRelatedNavigation` 用例（不得因改写而放宽）。
4. **无路由 / 无新依赖**：`package.json` 依赖段无 diff；`grep -R "vue-router" frontend/src frontend/package.json` 无命中。
5. **源码 guard 未被绕过**：`f009ClusterResourceView.spec.ts` diff 为空，且 token 扫描实际通过。

## Technical Decisions

### CONFIRMED

纯呈现层 `{database:false, backend:false, frontend:true}`；Contract `NOT_REQUIRED`；不引入 vue-router / 不新增依赖 / 不改路由 URL / 不改资源页面内容与业务 / 不做响应式主题；不新增或修改产品规则；AC-06 改写而非删除；`f009` guard 不得删除；**导航形式不构成产品规则**（`f002:230`、`App.vue` 注释）。

### REQUIRED

- 活跃态必须**由既有单一真相源 `navSection` 派生**，不得新增第二真相源（如菜单 index）。
- 侧边栏在 DOM 中位于资源内容**之前**，保持既有 `findButton()`（取首个文本匹配按钮）定位语义不变。
- 7 个 `data-testid="nav-*"` 必须保留在可点击的 `<button>` 上。
- `.app-shell__nav .el-button + .el-button { margin-left: 0; }`——否则纵向堆叠出现缩进缺陷。
- 新代码 / 样式 / 注释不得引入 `恢复` / `回收站` / `restore` / `undelete` / `include_deleted` token（`f009` guard 会扫 `App.vue`；既有已被 scrub 的「不可恢复 / 恢复该上下文 / 返回时恢复」除外）。
- `bootstrap` / `login` 分支与 `:data-view` 保持不动；侧边栏只在 `app` 视图出现。
- 不修改 `<script>` 中任何函数 / 类型 / `navSection` 的语义。

### PROPOSED

- 采用 (b) 纯 CSS flex 侧边栏 + 保留 `<el-button>`。
- 活跃态 class 名 `app-shell__nav-item--active` + `aria-current="true"`。
- 可选：给 `<aside>` 加 `data-testid="app-sidebar"`。
- 同步更新失效的「头部导航」注释措辞。
- 侧边栏固定宽度 200px、无折叠、无图标、无持久化（对应 NQ-1 ~ NQ-5 不纳入本次范围）。

### OPEN（非阻塞，均不在本次范围）

折叠 / 图标 / 折叠状态持久化 / 宽度可拖拽 / 按分类分组 / 键盘无障碍增强 / 视觉回归截图。

## Risks

1. **`findButton()` 的「首个子串匹配」依赖 DOM 顺序**：侧边栏必须排在内容区之前，且侧边栏内不得新增含 `集群` / `服务` 等子串的额外 `<button>`。违反时 `findButton(wrapper, '集群')` 可能选中内容区按钮（如「返回集群列表」）。
2. **回归面**：5 个导航 spec 的 15 处活跃态断言（必改）；另 2 个 spec（`appBareMetalNavigation` / `appBareMetalRelatedNavigation`）与 `app.spec.ts` / `appAuth.spec.ts` 不含 `el-button--primary` 断言但依赖 `<button>` 定位与 `[data-view]`——保留 `<el-button>` 与结构顺序即可全绿。`f009` 源码 guard 对所有 `App.vue` 文本改动敏感。
3. **与 F018 的文件所有权冲突**：F018（全局搜索）也改 `App.vue`。本次不改 `<script>` 逻辑可显著降低未来冲突；仍按协调器要求 **F017 先 merge 再启动 F018**。
4. **Element Plus 相邻按钮 margin**：不做 REQUIRED 的 margin 复位会导致纵向排列视觉不一致（非功能缺陷）。
5. **`el-menu` 若被误选**：将导致 7+ 文件导航定位失效——本 Handoff 已明确拒绝。

## Constraints

- 只改 `frontend/src/App.vue` + 5 个导航测试文件；不得触碰 `pages/**`、`components/**`、`api/**`、后端、`docs/api/**`、数据库 / migration。
- 不新增依赖、不引入 `vue-router`、不改 URL、不做响应式 / 主题。
- 不改 `ResourceView`、`open*` / `back*`、`returnView` / `returnClusterId` / `clusterId` 逻辑与 `bootstrap` / `login` / 登出语义。
- 7 个 `nav-*` testid 与中文标签不变。
- 15 处断言改写，不得删除 / skip / 恒真；用例总数不得低于 618。
- 不删除 `f009ClusterResourceView.spec.ts` 的 guard 及其 token 语义。

## Implementation Layers

```yaml
database: false
backend: false
frontend: true
```

## Implementation Order

```text
Architecture + API Contract (NOT_REQUIRED)
  └─ Frontend（App.vue 布局 + 活跃态 + 15 处断言改写，同一变更内完成）
                 ↓
              Tester → Reviewer
```

Frontend 必须先落 `App.vue` 的 DOM Contract（class + `aria-current`），再改断言。

## Verification Strategy

**门禁**：`npm run typecheck` 通过；`npm run test` **连续 2 次**全绿，基线 40 files / **618 tests**（改写不改变用例数、不得低于）；`npm run build` 通过。并逐条核验上述「Testing Agent 必须独立证伪的声明」1–5；其中断言非恒真须用**临时变异 → 变红 → 还原**证明。

**生产实例 `http://192.168.10.221/`（有真实数据，人工核验 AC-01 / 03 / 04）**：未认证 → 登录页；登录后侧边栏为左侧纵向、含且仅含 7 个入口、逐个可进入对应列表并正常加载、当前区高亮唯一且随切换更新（含详情页归属其资源区）；用户名与登出可见可用，登出（含 401）均回登录页；导航切换时**地址栏 URL 不变**；无移动端抽屉 / 主题入口。

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

API Contract Status：`NOT_REQUIRED`。
