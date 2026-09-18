# Test Report — F017 应用外壳侧边栏导航

> Author Role: tester
> Feature Branch: `feature/F017-sidebar-navigation`
> start_commit: `f74ee2ba18e0e2d3e890fed82ae7d0ad753f3bd2`（= develop）
> 候选 HEAD: `3a4a13eca825806933b8a1b64f43212d1450c1ba`
> 实现提交: `8236faa`（feat）、`3a4a13e`（计划检查点）
> 测试环境 HEAD: `3a4a13e`（工作树 clean，测试前后 `git status --short` 均为空）

## Feature

F017 — 应用外壳侧边栏导航（纯呈现层；`{database:false, backend:false, frontend:true}`；Contract `NOT_REQUIRED`）。

## Test Basis

- Product：`docs/product/handoffs/f017-sidebar-navigation.md`（AC-01 ~ AC-08、Confirmed Requirements）
- Architecture：`docs/architecture/f017-sidebar-navigation-handoff.md`（DOM Contract、5 条独立证伪声明、Risks、Verification Strategy）
- Domain：`AGENTS.md`、`docs/product/domain-model.md`（本 Feature 不涉及领域规则）
- 实现：`frontend/src/App.vue`；改写文件：5 个导航 spec；guard：`frontend/tests/f009ClusterResourceView.spec.ts`

## Environment

- Node `v24.14.0`、npm `11.9.0`；已有 `node_modules`。
- 前端：Vue 3 + Element Plus 2.14.5，Vitest 5.0.1（`happy-dom`），无 vue-router。
- 后端 / 数据库：本 Feature 不涉及，未启动。
- 全新性：测试在候选 HEAD 工作树上直接执行，工作树 clean；未复用任何开发 Agent 的测试会话。
- 临时探针文件均以 `zzF017*.spec.ts` 命名，运行后即删除；最终 `git status --short` 为空，全部基线文件 `sha256` 校验通过。

## Acceptance Criteria Mapping

| AC | Test | Result | Evidence |
| --- | --- | --- | --- |
| AC-01（侧边栏呈现 + 7 区可达） | 自写探针：7 个 `nav-*` 齐全且逐一可点击进入对应列表；侧边栏 DOM 在内容区之前；按钮恰为 7 导航 + 登出 | PASS（组件级） | 探针 7 passed；`App.vue:610` `display:flex` + `<aside>` + `<main>`；会话区在 `<aside>` 内 |
| AC-02（高亮唯一且正确） | 自写探针：逐一 7 区点击后恰好一个含活跃 class 且为目标项；详情页归属其资源区探针 | PASS | 探针 7 passed + 详情探针 2 passed |
| AC-03（用户名与登出可用） | 自写探针：用户名 = `admin`，登出按钮存在；登出 204 与 401 均回登录页；既有 `appAuth.spec.ts` 复跑 | PASS | 探针 7 passed；`appAuth.spec.ts` 通过 |
| AC-04（登录页 / bootstrap 不受影响） | 自写探针：bootstrap 未决态显示「正在加载…」且无侧边栏；401 → login 且无侧边栏 | PASS | 探针 7 passed；`appAuth.spec.ts` 通过 |
| AC-05（视图切换与返回链路） | 复跑 `appBareMetalNavigation` / `appBareMetalRelatedNavigation` / `app.spec.ts` / `appAuth.spec.ts` | PASS | 4 files / 17 tests passed |
| AC-06（改写而非删除 15 处 + guard） | `git diff` 核对 + skip/only 扫描 + 自写变异 + `f009` guard 复跑 | PASS | 5 文件各 3/3 行，无 skip/only；变异 → 5 个高亮用例变红；guard 5 passed |
| AC-07（工程门禁） | `typecheck` + `test`×2 + `build` | PASS | 见下 |
| AC-08（范围边界） | `git diff --stat` / `--name-only` / 依赖 diff / grep 无路由·响应式·主题 | PASS | 见下 |

> 说明：AC-01 / AC-03 / AC-04 的**已部署生产实例人工核验**（`http://192.168.10.221/`）本地无法执行，见「Unverified Areas」，不据此判定 PASS。

## Database / Migration

不涉及（`database:false`）。`git diff --name-only start..HEAD` 中无任何数据库 / migration 文件。

## Backend / API

不涉及（`backend:false`，Contract `NOT_REQUIRED`）。无后端文件改动，`docs/api/**` 零改动。

## Frontend

- 唯一实现文件 `frontend/src/App.vue`：
  - `<script>` **仅注释措辞**从「头部导航」改为「侧边栏导航」，无函数 / 类型 / `navSection` 语义改动（以变异证明 `navSection` 仍是活跃态唯一真相源）。
  - 模板：顶部 `<header>` → `.app-shell__layout`（`<aside class="app-shell__sidebar">` + `<main class="app-shell__content">`）；7 个导航项保留 `<el-button data-testid="nav-*">`，`:type="…'primary'"` → `:class="{ 'app-shell__nav-item--active': navSection === '…' }"` + `:aria-current="… ? 'true' : undefined"`；会话区搬入 `<aside>`；既有 14 条 `v-if` 页面链原样包进 `<main>`。
  - `bootstrap` / `login` 分支与根 `:data-view` 未动。
- 5 个导航 spec：每文件 3 处字符串替换 `'el-button--primary'` → `'app-shell__nav-item--active'`。

## Integration

**NOT TESTED（真实前端 ↔ 真实后端）**：本 Feature 为纯前端呈现层，无 Backend / API 契约变更，组件测试以 fetch 桩驱动（非真实后端）。生产实例人工核验未执行（见下）。由于无 API 面，本项不构成对 AC 的阻塞，但如实标注未做真实部署集成。

## Defects

None.

## Unverified Areas

1. **生产实例人工核验（`http://192.168.10.221/`）**：未认证 → 登录页；登录后侧边栏实际渲染、7 区逐个可达、当前区高亮随切换更新、用户名 / 登出可见可用、登出（含 401）均回登录页、导航切换地址栏 URL 不变。**本地环境无法访问该实例，无法替代**，标记 `NOT TESTED`。
2. **真实浏览器视觉 / 交互**（侧边栏视觉、点击命中、Element Plus 相邻按钮 margin 复位的实际观感）：组件级与构建级已验证，未做浏览器端人工核验。
3. **真实后端数据下的列表加载**：组件测试用 fetch 桩，未接真实后端数据验证。

## Test Status

`READY FOR REVIEW`

---

## 附：自写探针清单（临时，已删除）

文件 `frontend/tests/zzF017TesterProbe.spec.ts`（7 passed）与 `frontend/tests/zzF017DetailProbe.spec.ts`（2 passed）：

| # | 探针 | 目的 |
| --- | --- | --- |
| P1 | 7 个 `nav-*` 存在；点击每项后恰好一个活跃且为目标项；其余 6 项不活跃 | AC-01 / AC-02 |
| P2 | 活跃项 `aria-current="true"`；非活跃项 `aria-current` 属性不存在（`undefined`） | DOM Contract |
| P3 | `<aside data-testid="app-sidebar">` 在 `<main>` 之前（`compareDocumentPosition`）；侧边栏按钮恰为 7 导航 + 登出 | Risks #1 / findButton DOM 顺序 |
| P4 | 逐一导航点击前后 `window.location.href` 不变；无 `.el-menu`；无 `<a href>` | AC-08 无路由 |
| P5 | `bootstrap` 未决时显示「正在加载…」且 `data-view=bootstrap`、无侧边栏 | AC-04 |
| P6 | 会话 401 → `data-view=login` 且无侧边栏 | AC-04 |
| P7 | `app` 视图用户名 = `admin`；登出 204 与 401 均回到 `login` 且侧边栏消失 | AC-03 |
| P8 | 集群列表 → 集群详情后 `nav-clusters` 仍唯一活跃 | AC-02（详情归属） |
| P9 | 裸金属列表 → 裸金属详情后 `nav-bare-metals` 仍唯一活跃 | AC-02（详情归属） |

> P4 锚点：无 router，切换前后 `location.href` 相等。

## 附：自写变异记录

- **变异内容**：在 `frontend/src/App.vue` 将 `navSection` 的 `if (kind.startsWith('cluster')) return 'cluster'` 改为 `... return 'service'`（与协调器「集群项恒 false」不同的变异：改 computed 返回值的行为源）。
- **锚点是否命中**：命中（`sed` 后第 536 行为 `if (kind.startsWith('cluster')) return 'service'`）。
- **观察到的失败**：运行 5 个导航 spec → **5 failed | 12 passed (17)**，且失败恰为 5 个文件各自的「导航高亮随资源区域切换」用例（`appContainerNavigation` / `appServiceNavigation` / `appIpAddressNavigation` / `appNetworkInterfaceNavigation` / `appVirtualMachineNavigation` 各 1 个）。证明改写后的活跃态断言**绑定真实 `navSection` 行为**，非恒真 / 非空转。
- **还原 sha256**：变异前 `App.vue` = `ffb5475454bb6f53c3add850901e45bf1d59a6058c5615b36145508a1cee037c`；`cp` 还原后 `sha256sum -c` 再次校验为**成功（逐字节一致）**，第 536 行恢复为 `return 'cluster'`。全部 7 个基线文件 `sha256` 校验通过。

## 附：5 条独立证伪声明核验

1. **15 处为改写**：`git diff --numstat start..HEAD -- frontend/tests/` = 5 个文件各 `3 3`（插入=删除）；无删除的 `it`；`grep -nE "\.skip|\.only|it\.todo|xtest"` → NONE；`grep "el-button--primary"` 在 tests 下 → NONE remaining；全量用例总数仍 **618**（见门禁）。
2. **断言能失败（非恒真）**：见「自写变异记录」。
3. **返回链路未破坏**：`appBareMetalNavigation` / `appBareMetalRelatedNavigation` / `app.spec.ts` / `appAuth.spec.ts` 4 files / 17 tests passed，且这些文件 diff 为空（未被改写放宽）。
4. **无路由 / 无新依赖**：`git diff -- package.json package-lock.json` 为空；`grep -rn "vue-router" frontend/src` 仅命中注释「仍不引入 vue-router」；`src/App.vue` 无 `createRouter` / `createWebHistory` / `createWebHashHistory`；P4 证明导航不改 URL。
5. **源码 guard 未被绕过**：`git diff -- frontend/tests/f009ClusterResourceView.spec.ts` 为空；独立复跑 `f009ClusterResourceView.spec.ts` → 5 passed；手工按该文件同一 scrub 规则扫描 4 个源文件（`不可恢复` / `恢复该上下文` / `返回时恢复` 已剔除）→ `restore` / `undelete` / `include_deleted` / `回收站` / `恢复` 均无命中。

## 附：重点核查

6. **`findButton` DOM 顺序**：P3 证实 `<aside>` 在 `<main>` 之前，且侧边栏按钮文本恰为「集群/裸金属/虚拟机/网络接口/IP 地址/容器/服务/登出」——不含其它含这些子串的按钮。故 `findAll('button').find(text.includes(...))` 对 7 个标签均命中侧边栏导航项，与改版前一致（裸金属导航按钮在内容区「查看裸金属」之前）。**未发现静默错选**。
7. **AC-01~04 行为级**：P1/P2/P5/P6/P7 + AC-02 详情探针 P8/P9 均为自写探针，不依赖既有改写断言。
8. **AC-08 边界**：`git diff --stat start..HEAD -- frontend/src/pages frontend/src/components frontend/src/api backend docs/api database` 为空；`git diff --name-only` 无 `docs/`、`frontend/` 之外文件；`data-testid="nav-` 在 `App.vue` 计数 = 7；`grep -nE "@media|prefers-color-scheme|dark|theme"` 于 `App.vue` 无命中。
9. **`aria-current` 契约**：P2 通过（活跃 = `"true"`，非活跃属性不存在）。

## 附：工程门禁真实输出

```text
$ cd frontend && npm run typecheck
> vue-tsc --noEmit
（无输出，退出码 0）

$ npm run test        # 第 1 次
 Test Files  40 passed (40)
      Tests  618 passed (618)

$ npm run test        # 第 2 次
 Test Files  40 passed (40)
      Tests  618 passed (618)

$ npm run build
> vue-tsc --noEmit && vite build
✓ 1694 modules transformed.
dist/assets/index--CIELtAj.js   1,125.94 kB │ gzip: 350.04 kB
✓ built in 7.00s
```

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-01 ~ AC-08 全部在组件 / 构建 / 源码层取得 PASS 证据（除生产实例人工核验，见下）。
- 15 处断言为等价改写（3/3 每文件、无 skip/only、用例数 618），并以自写变异证明其可失败。
- 全部工程门禁真实通过（typecheck / test×2 / build）。
- 无路由 / 无新依赖 / 无受限目录改动 / guard 未被绕过。

### Not Verified

- 生产实例 `http://192.168.10.221/` 人工核验（本地无法访问）。
- 真实后端数据与真实浏览器端交互。
- 真实前后端集成（本 Feature 无 API 面，组件测试为 fetch 桩）。

### Blocking Issues

None.

### Defect Owner

None（未发现 Defect）。

GIT: NONE
