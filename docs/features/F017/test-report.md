# F017 前端 UI 体系改造（Ant Design + Tailwind CSS）— Test Report

本文件承载 TEST_DESIGN 与后续 TEST。TEST_DESIGN 只描述方案与可验证性，**不填充任何执行 PASS**；执行结果全部标 `待执行（TE-1）`。V5–V7 的真实渲染/部署复验由 F018 承接，本 Feature 不写部署或界面 PASS。

---

## Test Design（TD-1）

- **Task**：F017（FEATURE，P0，M8 前端 UI 改造，deps F016）— Tester，TEST_DESIGN 模式。
- **Status**：`TEST DESIGN READY`。
- **Basis**：
  - `docs/features/F017/product.md`（`READY FOR ARCHITECT`；F-UI-1..7、§2.2 不改变业务规则、§3.1 验收边界、N-1..N-5）。
  - `docs/features/F017/architecture.md`（`READY FOR DESIGN`，2026-10-15；D04-1..D04-10 定稿、§2.2 硬边界、§3 迁移策略、§5 V1–V7、§6.2 R1–R11、§7.2 Tester 核对项）。
  - `docs/architecture/d04-frontend-ui-stack.md` v2 FINAL / CONFIRMED（Architect 签核 2026-10-15）。
  - `docs/product/requirements-v3.md` **revision 4** CONFIRMED §28 / §29 / §31 / §32 / §33；`docs/project/project-plan.yaml` **plan_revision 5**（用户 2026-10-12 批准；F017 `layers={database:false,backend:false,frontend:true}`、`api_required=false`）。
  - `docs/project/implementation-rules.md`；`docs/project/handoff.md`；`.pi/skills/data-integrity/SKILL.md`。
- **角色边界**：Tester 只设计/执行验证，不改生产实现、Schema、产品规则与 `docs/features/F017/` 之外的权威文档；Git 由协调器统一管理。
- **只读探测（设计输入，非执行结果）**：分支 `feature/F017-frontend-ui-antd-tailwind`，HEAD `25198e0`；`frontend/scripts/smoke-client.mjs` 基线 `await test(` 计数 **265**；环境 `node v22.23.2` / `npm 12.0.2`（沿用 F016 记录）。

### 版本记录

| 版本 | 日期 | 依据 | 结论 | 说明 |
| --- | --- | --- | --- | --- |
| TD-1 | 2026-10-15 | F017 product.md / architecture.md / D04 v2 FINAL / requirements revision 4 / plan_revision 5 | `TEST DESIGN READY` | 首次设计检查；不含执行结果。若上游设计或需求修订，须重新核对并保留本版本。 |

### 0. 数据完整性对应表（F017 范围）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| F017 product.md §1.4 / §2.2；plan_revision 5 `layers.database=false` | 无（纯展示层，无新增/变更写入入口） | 无 Schema / Migration / 约束 / 索引变更 | 无业务规则变更；沿用各权威 Feature | 不适用 | `database: NOT_REQUIRED`（architecture §7.2、plan）；不在本 Feature 重验 PG 约束 |

> F017 不涉及唯一性、跨对象关系、生命周期、并发分配、导入或 Migration，数据完整性方法（`.pi/skills/data-integrity/SKILL.md`）对本 Feature 判为不适用；不新建业务约束清单。

---

## 1. 验收映射（F-UI-1..7 → V1–V7 可执行步骤与断言）

> 执行归属列：**F017** 表示本 Feature 自动/静态可完成；**F018** 表示真实渲染或真实/等价部署复验，F017 记为 `待执行（F018）`，不得写 PASS。所有页面/组件数量依据 architecture §2.1：14 页 + 19 个 `.tsx` + 11 个纯逻辑 `*.ts` + 16 个 `api/*.ts`。

### V1 — 依赖与锁文件一致、可复现（F-UI-1 / D04 V1,V3）

- **执行归属**：F017（自动）。
- **步骤**
  1. 读取 `frontend/package.json`，核对声明（与 D04-1/2/5 定稿一致）：
     - `dependencies.antd` 主版本 = 5；`dependencies["@ant-design/cssinjs"]` **存在且为直接依赖**（D04-5 修订点）。
     - `devDependencies.tailwindcss` 主版本 = 4；`devDependencies["@tailwindcss/vite"]` 主版本 = 4。
     - `react` 仍 18.3.x、`typescript` 仍 5.6.x、`vite` 仍 5.4.x（D04-3，不得夹带升级）。
  2. 确认 `package-lock.json` 已纳入版本控制：`git ls-files frontend/package-lock.json` 非空。
  3. 干净环境执行 `npm ci`（`frontend/`）：退出码 0。
  4. `npm ls antd @ant-design/cssinjs tailwindcss @tailwindcss/vite`：退出码 0；每个包仅一个已解析版本；无 `invalid` / `missing` / `UNMET`（含 R9 的 cssinjs↔antd 内部匹配）。
- **断言**：以上全部满足 → PASS；依赖源不可达导致 `npm ci` 无法执行 → 记 `BLOCKED` 并注明原因（N-2 / R1），**不得**以局部结果声称 F-UI-1 通过。
- **不适用**：§32 无性能项；`dist` 体积增长仅记录（R3），不作验收判据。

### V2 — 类型与构建（F-UI-5 / D04 V1）

- **执行归属**：F017（自动）。
- **步骤与断言**
  1. `npm run typecheck`（`tsc --noEmit`）→ 退出码 0，无错误输出。
  2. `npm run build`（`tsc --noEmit && vite build`）→ 退出码 0。
  3. 构建产物含非空 CSS：`find dist -name '*.css' -size +0c` 至少命中一个文件（对应 F-UI-5「`dist` 含非空 CSS」）。
  4. 该 CSS 为 Tailwind 产物而非空壳：文件内可检索到 layer 声明/`@theme` 令牌（如 `--color-brand`）与至少一条 utility。
  5. `dist/index.html` 引用带哈希的 JS/CSS 资源且 `#root` 入口存在。
- **负向**：若 `dist` 无 CSS 文件或全部为 0 字节，V2 FAIL（Tailwind 未接入/未生效的典型表现）。
- **边界**：AntD v5 运行时 CSS-in-JS 不在 `dist` 中（D04-8）；V2 通过≠UI 正确，不得据此声称 F-UI-2 / F-UI-6 通过。

### V3 — 纯逻辑机制回归与污染守门（F-UI-4d、F-UI-5 / D04 V2）

- **执行归属**：F017（自动）。
- **步骤与断言**
  1. `frontend/scripts/smoke-client.mjs` **零改动**：`git diff --exit-code <base> -- frontend/scripts/smoke-client.mjs` 为空。
  2. 用例覆盖未删减：脚本内 `await test(` 计数 ≥ 基线 **265**（只增不减）。
  3. `npm run smoke:client` → 退出码 0，输出 `N passed, 0 failed` 且 `N ≥ 265`。
  4. **污染守门**（architecture §2.2 硬边界）：
     - `git diff --name-only <base> -- frontend/src/api frontend/src/components/*.ts` 为空（`api/*.ts` 与纯逻辑 `*.ts` 零改动）。
     - 静态检索：`src/api/*.ts` 与 `src/components/*.ts` 中不存在 `from "antd"` / `from "react"` / `import "*.css"`（防止破坏 Node 类型剥离加载）。
- **断言**：smoke 覆盖 F-UI-4c 的机制级（401 全局处理器、403/409/422 错误信封与 code/details 语义、不自动重试）与 F-UI-3 的请求参数构造（过滤名 `type`、排序字段名 `resource_type` 不可互换，F-UI-3 边界）。任何 FAIL 为 HIGH，Owner=Frontend。

### V4 — 迁移完整性与样式收敛（F-UI-2、F-UI-6 / D04 V4）

- **执行归属**：F017（半自动：静态检索 + 人工判定）；真实渲染确认归 V6/F018。
- **步骤与断言**
  1. **迁移覆盖（F-UI-2 静态部分）**：对 `src/pages/`（14）与 `src/components/*.tsx`（19）逐文件确认主要交互（登录表单、列表、表单、弹窗、按钮、导航）由 AntD 组件与/或 Tailwind utility 承担。
     - 辅助检索：`grep -rlE "from ['\"]antd['\"]" frontend/src/pages frontend/src/components --include=*.tsx` 计数；未命中 AntD 的 `.tsx` 必须由人工确认其仅含静态展示/语义容器且已用 Tailwind utility，否则 FAIL。
     - 语义化原生元素（`main`/标题/`role="alert"`）与非交互容器为合理保留（N-3），不判「遗留控件」。
  2. **入口装配**：`src/main.tsx` 含 `StyleProvider layer="antd"`（`@ant-design/cssinjs`）、`ConfigProvider`（`locale={zhCN}` + `theme.token`：`colorPrimary`/`borderRadius`/`fontFamily`）、`App as AntApp`；**无** `import "antd/dist/reset.css"`；保留 `#root` 存在性校验。
  3. **`index.css` 收敛（F-UI-6）**
     - 定稿态：`@layer` 层序列不含 `legacy`（D04-7 定稿），旧专用类（`.panel`、`.data-table`、`.badge-*`、`.form-field`、`.detail-grid` 等）已删除；仅保留字体栈、`html/body/#root` 高度与背景、极少数跨页规则。
     - 迁移中间态（若尚未完成迁移）：全部旧规则必须包在 `@layer legacy { ... }` 内，且层声明将 `legacy` 置于 `base` 之后、`antd` 之前；**不得**存在未分层旧规则（R8）。
     - 无重复/冲突声明；无同时定义于 legacy 与新样式的互斥规则。
  4. **插件接入**：`vite.config.ts` `plugins` 含 `react()` 与 `tailwindcss()`；无 PostCSS 配置、无 cssinjs 构建插件（D04-4）。
- **断言**：静态项全部满足且人工判定无遗留主要交互原生控件 → PASS；发现未分层旧规则、遗留 legacy 专用类或未迁移页面 → FAIL（F-UI-6 / R8）。真实渲染样式需 V6 确认，本项不得替代。

> **TD-1 设计一致性 NOTE（交 Architect 核对）**：architecture §1.2 的 `index.css` 代码块标注为「定稿」，但 `@layer` 行仍含 `legacy`，与 §3 P3、D04-7「定稿删除 `legacy`」及 §1.5 步骤 3 相冲突。TD-1 以 D04-7 文字为准断言「定稿态层序列不含 `legacy`」，请 Architect 核对后统一 §1.2 示例，或确认 `components` / `legacy` 在定稿中的预期形态。

### V5 — 行为无回归（F-UI-3、F-UI-4a/b/c/e / D04 V6）

- **执行归属**：机制部分 F017（由 V3 自动覆盖）；可见界面部分 **F018**（真实/等价渲染，手动）。
- **F017 可自动覆盖（引用 V3）**：401/403/409（`CONFLICT`/`VERSION_CONFLICT`）/422 的 API 层语义、无自动重试、请求参数名不变。
- **F018 手动复验清单（F017 记 `待执行（F018）`，不得写 PASS）**
  1. **权限门控（F-UI-4a）**：Audit 入口仅 `AUDIT_READ` 可见；System 入口仅 `USER_ADMIN` 或 `VIEW_DELETED` 可见；VIEWER/EDITOR/ADMIN 可见能力与迁移前一致（§23/§25；前端门控不替代服务端）。
  2. **四态（F-UI-4b）**：各页面 Loading / Success / Empty / Error 仍可观察；错误不伪装为空列表（implementation-rules「查询与界面」）。
  3. **错误呈现（F-UI-4c）**：401 回登录、403 禁止、409 冲突（含版本冲突提示刷新后重改）、422 字段级错误，语义与迁移前一致。
  4. **Audit 无变更入口（F-UI-4e）**：Audit 页无任何修改/删除/清空入口（§22 / T36）。
  5. **列表交互（F-UI-3）**：每个列表页实际可**分页/排序/过滤/模糊搜索**，且触发请求参数与迁移前逐一致（不可互换 `type` / `resource_type`）。
- **F017 静态辅助断言**：`src/pages` 与 `src/components/*.tsx` 中保留 `AUDIT_READ` / `USER_ADMIN` / `VIEW_DELETED` 门控条件；`AuditPage.tsx` / 审计相关组件中不存在删除/编辑/清空处理函数（人工确认）。静态通过仅记为辅助证据，不构成 F-UI-4a/e 的 PASS。

### V6 — layer 优先序与 AntD 真实渲染（F-UI-2、F-UI-6 / D04 V4）

- **执行归属**：**F018**（真实浏览器，手动）。**F017 记 `待执行（F018）`，不写 PASS。**
- **F017 仅做的静态断言**
  1. 入口 CSS 层序列字符串正确（迁移期含 `legacy`，顺序 `theme, base, legacy, antd, components, utilities`；定稿去 `legacy`）。
  2. `main.tsx` `StyleProvider layer="antd"` 存在（未分层的 AntD `<style>` 会反向压过 utilities——R8/R2 静态校验点）。
  3. 未引入 AntD reset（唯一 base reset 为 preflight）。
- **F018 手动复验清单**：Tailwind utility 能确定性覆盖 AntD 组件样式；preflight 未破坏未迁移/已迁移页面布局；AntD 组件样式正确呈现（`StyleProvider layer="antd"` 生效）；迁移期 legacy 页面无样式缺口（R11）。
- **理由**：AntD v5 运行时注入样式不在构建产物，构建通过≠UI 正确（D04-8 / R10）。

### V7 — Nginx 入口可达性与 SPA fallback（F-UI-7 / D04 V5）

- **执行归属**：静态不破坏检查 F017（自动）；真实部署可达性 **F018**（手动）。
- **F017 静态断言**
  1. 部署配置零改动：`git diff --name-only <base> -- frontend/Dockerfile frontend/nginx.conf compose.yaml` 为空（§30）。
  2. `dist` 构建成功且 `index.html` + 哈希资源齐备（复用 V2 证据）。
- **F018 手动复验清单（F017 记 `待执行（F018）`）**：经 Nginx 入口访问前端可达；直接访问子路径返回应用入口而非 404（SPA fallback 正常）。
- **边界**：F017 不写部署 PASS；F-UI-7 完整判定归 F018。

---

## 2. 可自动验证命令与期望（F017 执行清单）

> 以下命令为 TE-1 的实际执行模板；本轮未执行，不给结果。`<base>` = plan_revision 5 F017 `git.start_commit`（`67770639067bd7fe11bf633de4ff7b9c31e42c5e`）或协调器指定的合并基线，执行时以实际核对的 base 为准。

| # | 命令（`cd frontend`） | 期望 | 映射 |
| --- | --- | --- | --- |
| A1 | `npm ci` | 退出码 0；依赖源不可达则 `BLOCKED` | F-UI-1 / V1 |
| A2 | `npm ls antd @ant-design/cssinjs tailwindcss @tailwindcss/vite` | 退出码 0；单版本、无 invalid/missing | F-UI-1 / V1 |
| A3 | `git ls-files frontend/package-lock.json` | 输出非空 | F-UI-1 / V1 |
| A4 | `npm run typecheck` | 退出码 0 | F-UI-5 / V2 |
| A5 | `npm run build` | 退出码 0 | F-UI-5 / V2 |
| A6 | `find dist -name '*.css' -size +0c` | 至少 1 个非空 CSS | F-UI-5 / V2 |
| A7 | `grep -R "color-brand" dist/assets/*.css`（或按实际产物名） | 命中（Tailwind `@theme` + layer 生效证据） | F-UI-5 / V2 |
| A8 | `npm run smoke:client` | `N passed, 0 failed`，`N ≥ 265`，退出码 0 | F-UI-4d/5 / V3 |
| A9 | `git diff --exit-code <base> -- scripts/smoke-client.mjs` | 无输出（零改动） | F-UI-5 / V3 |
| A10 | `grep -c "await test(" scripts/smoke-client.mjs` | `≥ 265` | F-UI-5 / V3 |
| A11 | `git diff --name-only <base> -- src/api src/components/*.ts` | 无输出 | F-UI-4d / V3 |
| A12 | `grep -rnE "from ['\"]antd['\"]\|from ['\"]react['\"]\|\.css['\"]" src/api src/components/*.ts` | 无命中（纯逻辑无 antd/react/css） | F-UI-4d / V3 |
| A13 | `grep -n "StyleProvider\|layer=\"antd\"\|antd/locale/zh_CN\|antd/dist/reset.css" src/main.tsx` | 命中 StyleProvider/locale；**无** reset.css | F-UI-6 / V4,V6 |
| A14 | `grep -n "@layer" src/index.css` | 层序列符合定稿/迁移期约定 | F-UI-6 / V4 |
| A15 | `git diff --name-only <base> -- Dockerfile nginx.conf ../compose.yaml` | 无输出 | F-UI-7 / V7 |
| A16 | `grep -n "tailwindcss" vite.config.ts` | 命中 `@tailwindcss/vite` 插件 | F-UI-2 / V4 |

**不自动断言（须真实渲染/真实部署，归 F018）**：AntD 运行时 CSS-in-JS 的实际样式、layer 优先序的真实生效、preflight 对布局的实际影响、权限门控与四态的真实可见性、Nginx 入口可达性与 SPA fallback。

---

## 3. 边界 / 负向场景

| ID | 场景 | 期望（设计判据） | 归属 |
| --- | --- | --- | --- |
| NEG-1 | `src/api/*.ts` 或 `components/*.ts` 被引入 React/CSS/AntD | A11/A12 命中即 FAIL（HIGH，破坏 smoke 加载与 F-UI-4d） | F017 / V3 |
| NEG-2 | 旧 `index.css` 规则保持未分层（R8） | 层次检查命中未分层旧规则 → FAIL（F-UI-6 / 可能连带 F-UI-2） | F017 / V4 |
| NEG-3 | 层序列错误或 `StyleProvider layer` 缺失 | A13/A14 不满足 → FAIL（AntD 反压 utilities） | F017 静态 / F018 渲染 |
| NEG-4 | `dist` 无 CSS 或 0 字节 | A6 未命中 → FAIL（Tailwind 未生效） | F017 / V2 |
| NEG-5 | lockfile 与 `package.json` 不一致 | A1/A2 失败 → 版本漂移，返回变更控制（R4） | F017 / V1 |
| NEG-6 | 夹带 React 19 / Vite 6 / antd 6 / Tailwind 5 | `package.json` 主版本越界 → FAIL，返回 `change-control.md`（D04-3/R7） | F017 / V1 |
| NEG-7 | smoke 用例被删减或断言弱化 | A9/A10 不满足 → FAIL（HIGH） | F017 / V3 |
| NEG-8 | 401/403/409/422 呈现语义变化 | smoke 机制级断言失败（自动）；界面呈现不符由 F018 判定 | F017(V3) / F018(V5) |
| NEG-9 | 权限门控（Audit/System）被改动或缺失 | 静态条件缺失 → FAIL；真实可见性由 F018 判定 | F017 静态 / F018(V5) |
| NEG-10 | 新增 Audit 修改/删除/清空入口 | 静态发现处理入口 → FAIL（§22/T36）；真实入口由 F018 判定 | F017 静态 / F018(V5) |
| NEG-11 | 查询参数名改动（`type` ↔ `resource_type` 互换） | smoke 机制级断言失败（自动） | F017 / V3 |
| NEG-12 | `Dockerfile`/`nginx.conf`/`compose.yaml` 被改动 | A15 非空 → FAIL（§30 边界） | F017 / V7 |

**只读无副作用**：F017 为展示层改造，前端无业务写副作用；A1–A16 均为构建/静态/机制命令，不对真实数据库或生产环境执行任何写入。无 DB 变更，故无 Migration/约束验证项。

---

## 4. 环境与可验证性说明

- **执行环境**：`frontend/` 目录，Node `v22.23.2` / npm `12.0.2`（沿用 F016 基线）。若执行需变更 Node 版本或 `smoke:client` 运行方式，须先返回 Architect 评估（architecture §7.2-4）。
- **依赖源可达性（OPEN，环境依赖）**：`npm ci` 依赖 npm registry/镜像可达。当前未探测网络；不可达时 A1/A2 记 `BLOCKED`，按 N-2 / R1 如实标注，**不得**伪造 PASS 或用 `node_modules` 现状替代干净安装证据。
- **无数据库/无后端**：`database: NOT_REQUIRED`、`backend: NOT_REQUIRED`、`api_required=false`（architecture §4/§7.2；plan_revision 5）。本 Feature 不连接 PG、不执行 Migration、不做真实 HTTP 集成；`api/` 仅由 smoke 机制级守门。
- **可自动断言**：V1–V3、V4 静态部分、V7 配置零改动（A1–A16 中除需人工判定项外）。
- **不可自动断言 / 未执行不得写 PASS**：
  - AntD 运行时样式、layer 优先序、preflight 实际影响（V6，F018）。
  - 权限门控与四态的真实可见性、错误呈现界面、Audit 入口真实缺失、列表交互实际触发（V5，F018）。
  - Nginx 入口可达性与 SPA fallback（V7，F018）。
  - `npm ci` 依赖源不可达时的可复现性（V1）。
- **判定纪律**：构建通过 ≠ UI 正确（D04-8 / R10）；半自动项（V4）须人工判定并记录理由；未实际执行的项一律标 `待执行`，不得以「设计应通过」代替执行结果。

---

## 5. 执行归属汇总（F017 vs F018）

| 验证项 | F017（本次） | F018（承接） |
| --- | --- | --- |
| V1 依赖/锁文件/`npm ci` | 自动执行 | — |
| V2 typecheck/build/dist CSS | 自动执行 | 重跑确认（plan F018） |
| V3 smoke + 污染守门 | 自动执行 | 重跑确认 |
| V4 迁移完整性/index.css 收敛 | 静态 + 人工 | 真实渲染抽查 |
| V5 行为无回归（机制） | 自动（V3） | — |
| V5 行为无回归（真实界面） | 不执行 | 手动复验（权限/四态/错误/Audit/列表交互） |
| V6 layer 优先序与 AntD 渲染 | 静态断言 | 真实浏览器手动复验 |
| V7 Nginx/SPA fallback | 配置零改动静态断言 | 真实/等价 Compose 手动复验 |

---

## 6. 缺陷路由

| 类型 | Owner |
| --- | --- |
| 实现缺陷（迁移遗漏、样式/行为回归、smoke 失败） | Frontend |
| 设计不一致（如 §1.2 定稿示例含 `legacy`） | Architect |
| 依赖/构建/测试基础设施 | 协调器 |
| 需求或业务规则歧义 | Product Manager / 用户 |

Severity 与是否必须修复按 `docs/project/handoff.md` 公共规范。

---

## 7. Issues / Next

- **OPEN TD-1（Architect，NOTE）**：architecture §1.2 定稿 `index.css` 示例的 `@layer` 行包含 `legacy`，与 D04-7 / §3 P3 / §1.5 冲突；请 Architect 在 CONTRACT 定稿时统一，TD-1 暂以 D04-7 文字为准。
- **OPEN TD-2（协调器，环境依赖）**：`npm ci` 依赖源可达性未探测；TE-1 执行前确认 registry/镜像，否则 V1 记 `BLOCKED`。
- **Next**：Database 已 `NOT_REQUIRED`；待 CONTRACT 定稿并得到实现报告后进入 TEST（TE-1），按 §2 执行 A1–A16、按 §3 复核负向场景，并按 §1 完成 F017 可自动项；V5–V7 真实项交 F018，F017 不写其 PASS。

---

## 8. 结论

`TEST DESIGN READY`（TD-1）——F-UI-1..7 已逐条映射到 V1–V7 的具体可执行步骤与断言，并明确 F017 自动/静态可验证项与 F018 承接的真实渲染/部署项；自动化命令与期望（typecheck / build 非空 CSS / smoke 零改动全绿 / `npm ci`）已固定；边界与负向场景（纯逻辑与 `api/` 污染、`index.css` 收敛、preflight 与 AntD layer 优先序、401/403/409/422 呈现、权限门控、Audit 无变更入口）已覆盖；环境与不可自动断言项已声明。**READY 仅表示方案可验证，不代表测试已运行、不填充 PASS、不批准实现或合并。**