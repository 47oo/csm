# F017 前端 UI 体系改造（Ant Design + Tailwind CSS）— ARCHITECTURE 阶段报告

- **Task**：F017（FEATURE，P0，M8 前端 UI 改造，deps F016）— Architect，Feature 设计模式
- **阶段**：CONTRACT；**结论**：`READY FOR IMPLEMENTATION`（2026-10-15）
- **Basis**：
  - `docs/product/requirements-v3.md` **revision 4** CONFIRMED：§28（前端交互基线）、§29（Ant Design + Tailwind CSS 已 CONFIRMED；主版本/集成/主题/优先级交 Architect 签核）、§31/§32（测试与上线验收判据不变）、§35.3 D04、§36 revision 4。
  - `docs/features/F017/product.md`（`READY FOR ARCHITECT`；F-UI-1..7、§2.2 不改变业务规则、N-1..N-5）。
  - `docs/project/project-plan.yaml` **plan_revision 5**（用户 2026-10-12 批准并同次授权实施；F017 `layers={database:false,backend:false,frontend:true}`、`api_required=false`）。
  - `docs/architecture/d04-frontend-ui-stack.md` v1（PROPOSED，本次定稿为 v2 FINAL）。
  - `docs/project/change-control.md` §1/§2/§4；`AGENTS.md` §2.9、§4、§6、§9；`docs/project/implementation-rules.md`。
  - 现状（只读盘点）：`frontend/src/pages/` 14 页、`frontend/src/components/*.tsx` 19 个、纯逻辑 `*.ts` 11 个、`frontend/src/api/*.ts` 16 个、`frontend/src/index.css` 758 行；`package.json`（react 18.3 / ts 5.6 / vite 5.4，`build=tsc --noEmit && vite build`）、`vite.config.ts`（仅 `@vitejs/plugin-react`）、`main.tsx`、`App.tsx`、`tsconfig.json`、`scripts/smoke-client.mjs`。

> 本文件为 F017 的权威 Feature 设计，记录 D04 定稿与设计签核；D04 正文由协调器同步为 v2 FINAL（见 §7.3 的应持久化清单）。**API Contract 状态：NOT_REQUIRED**（§4）。本报告只读产出，未执行任何 Git 命令。

---

## 1. 方案摘要：D04 定稿（v1 PROPOSED → v2 FINAL / CONFIRMED）

在**不改业务规则、API 契约、后端、数据库、部署拓扑**的前提下，仅替换前端展示层：引入 `antd` 5.x 与 `tailwindcss` 4.x（`@tailwindcss/vite`），以**显式 cascade layer 顺序**让 Tailwind base(preflight) < 旧样式过渡层 < AntD 组件样式 < Tailwind utilities 形成确定性优先序；以 `ConfigProvider`（seed token）为 AntD 主题唯一权威、`@theme` 为 Tailwind 令牌；`index.css` 收敛为最小全局层。

### 1.1 定稿决策表（D04-1..D04-10）

| ID | 决策（v2 FINAL） | 相对 v1 的变化 / 说明 |
| --- | --- | --- |
| D04-1 | UI 库 **Ant Design 5.x**（`antd`，补丁版本由 `package-lock.json` 固定）；不引 `babel-plugin-import`（v5 ESM 自动 tree-shake）。拒绝 antd 6。 | 同 v1；补丁版本改为「锁文件固定、实施时以可安装组合为准」。 |
| D04-2 | 样式库 **Tailwind CSS 4.x**（`tailwindcss` + `@tailwindcss/vite`，CSS-first，原生 cascade layer）。拒绝 v3（须关 preflight 规避与 AntD reset 冲突）。 | 同 v1。 |
| D04-3 | 维持 **React 18.3.x / TypeScript 5.6.x / Vite 5.4.x**；不升级 React 19 / Vite 6 / antd 6 / Tailwind 5。 | 同 v1。 |
| D04-4 | **Vite 插件路线**：`vite.config.ts` 在 `react()` 旁增加 `tailwindcss()`；不引入 PostCSS 配置、不引入 `cssinjs` 构建插件。 | 同 v1。 |
| D04-5 | **入口 CSS**：保留 `src/index.css`，显式声明 layer 顺序并分片导入 Tailwind；**AntD 根装配经 `StyleProvider layer="antd"`**（`@ant-design/cssinjs` 提为直接依赖），再 `ConfigProvider` + `App`（antd）。不 `import "antd/dist/reset.css"`，preflight 为唯一 base reset。 | **修订**：明确 `@ant-design/cssinjs` 须为直接依赖（`StyleProvider` 不由 `antd` 顶层导出；避免依赖传递依赖的隐式版本漂移）。 |
| D04-6 | **主题分工**：AntD 主题唯一权威 `ConfigProvider.theme`（seed token：`colorPrimary`/`borderRadius`/`fontFamily`）；Tailwind 令牌 `@theme {}`；仅维护最小共享集（品牌色 / 圆角 / 字体栈），**不做运行时双向同步**。 | 同 v1；补共享集具体取值（§1.4）。 |
| D04-7 | **`index.css` 分两态收敛**：迁移期 = layer 声明 + Tailwind 分片 + `@theme` + 最小全局层 + **`@layer legacy` 过渡层（包裹全部旧页面/组件规则）**；定稿 = 删除 `@layer legacy`，仅保留最小全局层。 | **修订（关键）**：v1 只说「迁移未完成前保留旧层」。实测风险：`index.css` 旧规则若保持**未分层（unlayered）**，将因「未分层样式恒胜过任何 `@layer`」而覆盖 AntD 与 Tailwind utilities。故旧规则必须包进 **`@layer legacy`**，并置于 `base` 之后、`antd` 之前（旧样式能被 AntD/utilities 覆盖，同时未迁移页面仍获得样式，无缺口）。 |
| D04-8 | **不新增 DOM 测试框架**；`smoke:client` 脚本与断言零改动、须原样全绿；UI 正确性由 F018 在真实/等价 Compose 手动复验。 | 同 v1。 |
| D04-9 | **locale = `antd/locale/zh_CN`**，仅影响 AntD 内置文案（分页/空态/日期等），不改任何业务语义与自定义中文文案。 | 新增：AntD 组件承担主要交互后，内置文案需与中文界面一致；属展示层，不新增交互能力。 |
| D04-10 | **无 API / 无 Schema / 无部署变更**；`layers={database:false,backend:false,frontend:true}`、`api_required=false`。 | 同 v1；见 §4。 |

### 1.2 layer 顺序与入口 CSS（D04-5/D04-7）

定稿（迁移完成后）`frontend/src/index.css`：

```css
/* F017 定稿最小全局层：只保留真正跨页的规则 */
@layer theme, base, antd, components, utilities;

@import "tailwindcss/theme.css" layer(theme);
@import "tailwindcss/preflight.css" layer(base);
@import "tailwindcss/utilities.css" layer(utilities);

/* 共享最小令牌（与 ConfigProvider seed token 取值对齐；不做运行时同步） */
@theme {
  --color-brand: #2563eb;
  --font-sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue",
    Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --radius-card: 0.375rem;
}

:root {
  font-family: var(--font-sans);
  color: #1f2937;
  background-color: #f9fafb;
}
html,
body,
#root {
  min-height: 100%;
}
body {
  margin: 0;
}
```

- `@layer ... ;` 顺序语句置于所有 `@import` 之前，先建立层序。
- 迁移期优先序：**preflight(base) → legacy(迁移期旧样式) → antd(AntD CSS-in-JS) → utilities(Tailwind 原子类)**；定稿（删除 `legacy` 后）：**preflight(base) → antd → utilities（`components` 为预留空层）**。
- 迁移期在 `@layer legacy { ... }` 中承载旧 `index.css` 全部现有规则（含 `.panel`、`.data-table`、`.badge-*`、`.form-field`、`.detail-grid` 等）；`@theme`/@layer 语句不放进任何层。

### 1.3 ConfigProvider / StyleProvider 装配（D04-5/D04-6/D04-9）

`frontend/src/main.tsx`（示意，签名不变）：

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider, App as AntApp } from "antd";
import { StyleProvider } from "@ant-design/cssinjs";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import "./index.css";

const themeConfig = {
  token: {
    colorPrimary: "#2563eb", // 与 --color-brand 对齐
    borderRadius: 6,
    fontFamily:
      'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, ' +
      '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
  },
};

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StyleProvider layer="antd">
      <ConfigProvider locale={zhCN} theme={themeConfig}>
        <AntApp>
          <App />
        </AntApp>
      </ConfigProvider>
    </StyleProvider>
  </StrictMode>
);
```

- `StyleProvider layer="antd"` 是 D04-5 的核心：只有把 AntD 运行时注入的样式放进 `@layer antd`，Tailwind utilities（更后层）才能确定性覆盖 AntD；否则未分层的 AntD `<style>` 会反向压过 utilities。
- `App`（antd）为 `message/notification/Modal` 提供 context；应用自身组件仍名 `App`，`import { App as AntApp }` 避免命名冲突。
- `#root` 存在性校验保留（现 `main.tsx` 的显式报错不删除）。

### 1.4 主题 token 分工（D04-6）

| 维度 | AntD（`ConfigProvider.theme.token`） | Tailwind（`@theme`） | 共享 |
| --- | --- | --- | --- |
| 品牌色 | `colorPrimary: #2563eb` | `--color-brand: #2563eb` | 取值一致，**人工维护，不运行时同步** |
| 圆角 | `borderRadius: 6` | `--radius-card: 0.375rem` | 同上 |
| 字体栈 | `fontFamily: <当前系统栈>` | `--font-sans: <同一栈>` | 同上 |

- 仅维护上述最小共享集；组件级 token、语义色、间距等各自由 AntD / Tailwind 默认体系承担，不做映射层。
- 现有语义色（`.badge-*` 的绿/蓝/红/灰）在迁移时改为 AntD `Tag`/`Badge` 状态色或 Tailwind 原子类，不并入共享 token。

### 1.5 `index.css` 处置（D04-7）

1. 迁移开始：保留 758 行既有内容，但整体包进 `@layer legacy { ... }`，文件头部加入 §1.2 的 layer 声明、Tailwind 分片、`@theme`、最小全局层。
2. 每迁移完一个页面/组件：删除该页面/组件在 `@layer legacy` 中的专用规则段（保留仍被其它未迁移页面复用的规则）。
3. 全部迁移完成：`@layer legacy` 变为空 → 删除该层与层声明中的 `legacy`，得到 §1.2 定稿内容。
4. 判据（F-UI-6）：无可被 AntD/utilities 覆盖需求仍留在 legacy；无重复/冲突声明；定稿 `index.css` 仅含字体栈、`html/body/#root` 高度与背景、极少数真正跨页规则。

### 1.6 preflight 冲突策略（D04-2 / R2）

- 以 **Tailwind preflight 作为唯一 base reset**，不引入 AntD reset，避免双重 reset。
- AntD 组件样式处于 `@layer antd`（后于 `base`），跨层优先级天然胜出，`preflight` 的 `button{background:transparent}`、`*{border-width:0}` 等不会压垮 AntD 组件。
- 迁移期：preflight 会使未迁移页面依赖浏览器默认的少量样式（列表符、标题边距等）发生变化；凡旧 CSS 已显式重声明的规则由 `@layer legacy` 兜底，其余在 V6 手动抽查中发现缺口时补入 `@layer legacy`（不提前删除旧规则）。
- 校验点：V6 手动确认 preflight 未破坏布局、utilities 可覆盖 AntD。

### 1.7 重大性判定

- §29 已由用户 CONFIRMED 采用 AntD + Tailwind；主版本/集成/主题/优先级属 §2.9 与 §35.3 D04 授权的**专业设计签核**范围，不构成新业务限制或重大架构变化，**无需再次请求用户批准，亦无需新建 ADR**；D04 由 PROPOSED 升为 CONFIRMED 并记录签核（§7）。
- 越界项（React/Vite 升级、antd 6、Tailwind 5、引入 PostCSS/路由库/状态库）一律返回 `change-control.md`。

---

## 2. 目录 / 文件影响清单

### 2.1 需要修改 / 新增

| 文件 | 动作 | 内容 |
| --- | --- | --- |
| `frontend/package.json` | 修改 | `dependencies` 增 `antd`、`@ant-design/cssinjs`；`devDependencies` 增 `tailwindcss`、`@tailwindcss/vite`。脚本不变（`typecheck`/`build`/`smoke:client` 保持原义）。 |
| `frontend/package-lock.json` | 重新生成并提交 | 与声明一致、可复现（F-UI-1）。 |
| `frontend/vite.config.ts` | 修改 | `import tailwindcss from "@tailwindcss/vite"`；`plugins: [react(), tailwindcss()]`；注释更新，不配置代理/硬编码地址。 |
| `frontend/src/index.css` | 重写 | §1.2 layer 骨架 + `@theme` + 最小全局层；迁移期含 `@layer legacy { ... }`。 |
| `frontend/src/main.tsx` | 修改 | §1.3 `StyleProvider`/`ConfigProvider`/`AntApp` 装配；保留 `#root` 校验与 `./index.css` 引入。 |
| `frontend/src/App.tsx` | 修改 | 应用壳（boot-loading / boot-error / login / authenticated 四态）改用 AntD `Spin`/`Result`/`Alert`/`Button` 与 Tailwind 原子类；401 全局处理与重试逻辑语义不变。 |
| `frontend/src/pages/`（14 个） | 迁移 | `LoginPage`、`HomePage`、`ClustersPage`、`ClusterCreatePage`、`ClusterDetailPage`、`ResourcesPage`、`ResourceCreatePage`、`ResourceDetailPage`、`NetworksPage`、`IpPoolsPage`、`IpAddressesPage`、`ServicesPage`、`AuditPage`、`SystemPage`。 |
| `frontend/src/components/`（19 个 `.tsx`） | 迁移 | `AccountManagementPanel`、`AuditQueryPanel`、`ClusterForm`、`DashboardPanel`、`DeletedObjectsPanel`、`GlobalSearch`、`HealthPanel`、`InterfaceForm`、`InterfacesPanel`、`IpAddressForm`、`IpPoolForm`、`NetworkForm`、`ResourceForm`、`ResourceImportPanel`、`ServiceEndpointForm`、`ServiceEndpointsPanel`、`ServiceForm`、`ServicesPanel`、`VirtualMachineFields`。 |

主要交互控件映射（非强制一一对应，供实现与 Review 对齐 F-UI-2）：导航 → `Layout`/`Menu` 或 `Tabs`；列表 → `Table`（`pagination`/`sorter`/受控 `filters` 或外部过滤表单）；表单 → `Form`/`Input`/`Select`/`InputNumber`/`Checkbox`/`Switch`；弹窗确认 → `Modal`/`Popconfirm`；按钮 → `Button`；状态/类型/角色标识 → `Tag`/`Badge`；四态 → `Spin`/`Alert`/`Empty`/`Result`；消息 → `App.useApp()` 的 `message`/`notification`。

### 2.2 明确不改动的边界（硬约束）

| 边界 | 文件 | 约束 |
| --- | --- | --- |
| API 层 | `frontend/src/api/*.ts`（16 个：`client`、`auth`、`clusters`、`resources`、`interfaces`、`networks`、`ipPools`、`ipAddresses`、`services`、`serviceEndpoints`、`search`、`dashboard`、`imports`、`audit`、`deleted`、`users`） | **零改动**：URL/method/body/错误语义/权限语义/`requestUpload` 均不变（F-UI-4d）。不引入 `antd`/CSS/React 依赖。 |
| 纯逻辑 | `frontend/src/components/*.ts`（11 个：`hardware`、`virtualMachine`、`interfaceForm`、`networkForm`、`ipPoolForm`、`ipAddressForm`、`serviceForm`、`serviceEndpointForm`、`globalSearchForm`、`auditQueryForm`、`importForm`） | **零改动、不迁移**（无 JSX）。不得新增 JSX/CSS/`antd` import，否则破坏 `smoke:client`（Node 类型剥离加载）与 F-UI-4d。 |
| 测试入口 | `frontend/scripts/smoke-client.mjs` | **零改动**、断言不得删减（F-UI-5）。 |
| 构建/静态 | `frontend/index.html`、`frontend/tsconfig.json` | 预期不改（如确需类型项，须回归 V1–V3 并在实现报告说明）。 |
| 部署 | `frontend/Dockerfile`、`frontend/nginx.conf`、`compose.yaml` | 不改（§30）；放行 `dist` 体积变化。 |
| 后端 | `backend/**`、`docs/database/**`、各 `docs/api/**` | 不改。 |

---

## 3. 迁移策略与顺序

原则：**先立骨架，再迁壳，后迁页，最后清样式**；每步保持 `typecheck`/`build`/`smoke:client` 可运行，避免大爆炸式改动；`api/` 与纯逻辑 `*.ts` 全程冻结。

| 阶段 | 范围 | 动作与出口 |
| --- | --- | --- |
| P0 依赖与骨架 | `package.json`、`package-lock.json`、`vite.config.ts`、`main.tsx`、`index.css` | 接入 `antd`/`tailwindcss`/`@tailwindcss/vite`/`@ant-design/cssinjs`；`main.tsx` 装配 Provider；`index.css` 建 layer 骨架并把旧规则整体包进 `@layer legacy`。出口：`typecheck`/`build` 通过、`dist` 有非空 CSS、`smoke:client` 全绿（V1–V3），真实渲染无 preflight 破版（V6 首抽）。 |
| P1 共享壳 | `App.tsx`、`LoginPage.tsx`、`HomePage.tsx`（header/nav/权限门控/登出） | 用 `Layout`/`Menu`/`Button`/`Spin`/`Result` 等替换壳与登录表单；保留 boot 四态、401 全局处理、`permissions` 门控（Audit 需 `AUDIT_READ`，System 需 `USER_ADMIN` 或 `VIEW_DELETED`）。同步删除 `.app-header`/`.app-nav`/`.login-main`/`.form-field` 等仅此范围用的 legacy 段。出口：导航与登录行为不回归（V5）。 |
| P2 页面 | 14 页按域分批：Clusters(+Detail/Create) → Resources(+Detail/Create) → Networks → IP Pools/IP Addresses → Services → Audit/System → HomeOverview(Search+Dashboard) | 每批：页面 + 其专属 `components/*.tsx` 一起迁移；列表页对齐 §28 分页/排序/过滤/模糊搜索，触发参数与迁移前**逐一致**（过滤名 `type`、排序字段 `resource_type` 不可互换，F-UI-3）；保留 Loading/Success/Empty/Error 与 401/403/409/422 呈现（F-UI-4b/c）。出口：每批 `typecheck`/`build`/`smoke:client` 通过。 |
| P3 清样式 | `index.css` | 随各批删除已迁移页面的 legacy 段；`@layer legacy` 清空后移除该层与声明，得 §1.2 定稿。出口：F-UI-6（最小全局层，无重复/冲突）。 |
| P4 收口 | 全量 | 全量回归 V1–V5；为 F018 留 V6/V7 手动复验清单（不写 PASS）。 |

**半迁移期间样式缺口处理**：
- 未迁移页面继续由 `@layer legacy` 提供样式；已迁移页面由 AntD/utilities 提供，legacy 因层序靠前而不会覆盖新样式。
- **不提前删除仍在使用的 legacy 段**（对应 R5）。若发现 preflight 造成未迁移页面缺口，把所需规则补进 `@layer legacy`，而非回退 layer 结构。
- 禁止把旧规则改回未分层，否则会反向覆盖 AntD/utilities（R8）。

---

## 4. Layers 与 API Contract

```yaml
layers:
  database: false   # 纯展示层改造：无新表/列/约束/索引/迁移
  backend: false    # 无后端路由/服务/模型变更；frontend/src/api 冻结
  frontend: true
api_required: false
```

- **Contract 状态：`NOT_REQUIRED`**。理由：无新增/变更 Endpoint、字段、类型、nullable、错误码/错误语义、分页/排序/过滤/权限/并发语义；前端仅消费 F001–F015 的既有 READY Contract（`api_required=false`，plan_revision 5）。
- **无 API 的最终设计签核**：本文件即 F017 的 CONTRACT 定稿载体，记录 Architect 对 `api_required=false` 的最终设计签核（§7）；不新建 `docs/api/F017.md`。
- `database` 预期 **NOT_REQUIRED**（由 Database 正式裁定），见 §7.2。

---

## 5. 验证策略（V1–V7，对应 F-UI-1..7 与 D04 V1–V6）

| # | 判据 | 方法 | 自动化边界 | 映射 |
| --- | --- | --- | --- | --- |
| V1 | 依赖与锁文件一致、可复现 | 核对 `package.json` 声明版本与 D04 定稿一致；提交 `package-lock.json`；依赖源可达时干净环境 `npm ci` 成功 | **自动**（`npm ci` 需依赖源可达，否则如实标注未验证，不得伪造 PASS，N-2/R1） | F-UI-1 / D04 V1,V3 |
| V2 | 类型与构建 | `npm run typecheck`、`npm run build`；断言 `dist` 含非空 CSS | **自动** | F-UI-5 / D04 V1 |
| V3 | 纯逻辑机制回归 | `npm run smoke:client`（脚本与断言零改动，全绿） | **自动**（守门 `api/` 与纯逻辑 `*.ts` 未被污染） | F-UI-4d、F-UI-5 / D04 V2 |
| V4 | 迁移完整性与样式收敛（静态） | 代码审查 + 检索：14 页与 19 组件是否均由 AntD/utilities 承担主要交互、无遗留原生控件承担主要交互（语义元素/非交互容器可保留，N-3）；`index.css` 是否仅剩最小全局层、旧专用样式已删、无重复/冲突 | **半自动**（检索 + 人工判定） | F-UI-2、F-UI-6 / D04 V4 |
| V5 | 行为无回归（可见行为 + 机制） | 机制由 V3 覆盖；界面侧在真实/等价环境抽查：权限门控（Audit/System 显隐）、列表四态、401/403/409/422 呈现、Audit 无修改/删除/清空入口、查询参数不变 | **必须手动**（真实渲染）；机制部分自动 | F-UI-3、F-UI-4a/b/c/e / D04 V6 |
| V6 | layer 优先序与 AntD 真实渲染 | 真实浏览器抽查：Tailwind utility 覆盖 AntD、preflight 未破坏布局、AntD 组件样式正确（`StyleProvider layer="antd"` 生效） | **必须手动**（AntD v5 运行时注入样式不在构建产物，构建通过≠UI 正确，D04-8） | F-UI-2、F-UI-6 / D04 V4 |
| V7 | Nginx 入口可达性与 SPA fallback | 真实/等价 Compose：经 Nginx 入口访问前端、直接访问子路径返回应用入口 | **必须手动**（归 F018；F017 仅保证 `Dockerfile`/`nginx.conf`/产物不被破坏，不写部署 PASS） | F-UI-7 / D04 V5 |

- **可自动验证**：V1–V3 与 V4 的静态检索部分。
- **必须手动验证**：V5/V6/V7 的真实渲染与部署可达性（F018 承接）；未实际执行项**不得写 PASS**。
- D04 的 V5（真实部署回归）与 V6（业务验收复验）在本表拆为 V6/V7 与 V5/V7，语义一致；D04 v1 表述的「V1–V6」在 v2 中显式扩展到含部署可达的 V7。

---

## 6. 技术决策记录、风险与 Rollback

### 6.1 技术决策记录

| ID | 决策 | 状态 | 依据 |
| --- | --- | --- | --- |
| TD-F017-1 | antd 5.x + tailwindcss 4.x + `@tailwindcss/vite`；`@ant-design/cssinjs` 直接依赖 | CONFIRMED | §29 rev4；§2.9；D04-1/2/5 |
| TD-F017-2 | 层序 `theme, base, legacy, antd, components, utilities`，`StyleProvider layer="antd"` | CONFIRMED | D04-5/7；未分层样式覆盖风险 R8 |
| TD-F017-3 | `ConfigProvider` seed token 为 AntD 主题唯一权威；`@theme` 为 Tailwind 令牌；最小共享集、无运行时同步 | CONFIRMED | D04-6 |
| TD-F017-4 | `index.css` 分两态收敛（过渡 `@layer legacy` → 最小全局层） | CONFIRMED | D04-7；F-UI-6 |
| TD-F017-5 | 不引 DOM 测试框架；构建通过不等于 UI 正确；UI 复验归 F018 | CONFIRMED | D04-8；§31/§32 |
| TD-F017-6 | locale zh_CN 仅影响 AntD 内置文案 | CONFIRMED | D04-9 |

### 6.2 风险与缓解

| ID | 风险 | 等级 | 缓解 |
| --- | --- | --- | --- |
| R1 | 依赖源不可达 / 无 npm 镜像，`npm ci` 不可复现 | MEDIUM | 提交 `package-lock.json`；配置镜像；不可执行时如实标注未验证（N-2），不得局部结果声称 F-UI-1 通过 |
| R2 | preflight 与 AntD 冲突 | MEDIUM | 层序 + `StyleProvider layer="antd"`；不引 AntD reset；V6 抽查 |
| R3 | 包体积/首屏增长 | LOW–MEDIUM | antd v5 ESM tree-shake；§32 无性能验收项，仅记录不阻塞 |
| R4 | 版本漂移 | LOW | 锁文件固定；升级走变更控制（D04-3） |
| R5 | `index.css` 收缩与页面迁移不同步 | MEDIUM | 分两态收敛；未迁移前保留 `@layer legacy`；不提前删旧段；F018 复验 |
| R6 | 纯逻辑 `*.ts` 误引入 React/CSS/antd | MEDIUM | 明确边界（§2.2）；V3 守门回归 |
| R7 | 夹带框架升级 | LOW | D04-3 明确不升级；越界返回变更控制 |
| **R8** | **旧 `index.css` 保持未分层，覆盖 AntD/utilities** | **MEDIUM** | **必须包进 `@layer legacy`（D04-7 修订）；V4/V6 检查未分层旧规则** |
| R9 | `@ant-design/cssinjs` 与 `antd` 内部版本不匹配 | LOW–MEDIUM | 作为直接依赖并随 antd 同批锁定；`npm ci` + V6 渲染抽查 |
| R10 | 以构建通过声称 UI 正确 | MEDIUM | D04-8/§5：运行时样式须真实渲染验证，未执行不写 PASS |
| R11 | preflight 使未迁移页面出现样式缺口 | LOW–MEDIUM | `@layer legacy` 兜底；V6 抽查发现即补 legacy，不回退层结构 |

### 6.3 Rollback

无 DB Migration、无数据/API/部署拓扑变化。回滚仅需撤销 F017 提交（或还原分支/镜像）并重新部署上一 `dist`；不涉及数据恢复。F018 复验在回滚前不置 PASS。

---

## 7. 设计签核、待核对项与结论

### 7.1 设计签核（Architect）

- 签核对象：F017 设计（本文档 v1）+ `docs/architecture/d04-frontend-ui-stack.md` 定稿 **v2 FINAL / CONFIRMED**。
- 签核者：Architect（本角色）。
- 签核日期：2026-10-15（本会话日期，协调器可核）。
- 上游批准依据：`docs/product/requirements-v3.md` revision 4（§29 rev4 用户 CONFIRMED，§35.3 D04 授权专业签核）；`docs/project/project-plan.yaml` plan_revision 5（用户 2026-10-12 批准）。
- 覆盖范围：F017 及 F018 复验所需的前端 UI 集成设计。
- 结论依据：`docs/features/F017/product.md`（READY FOR ARCHITECT，F-UI-1..7）。
- API Contract：`NOT_REQUIRED`（§4），本文件记录最终设计签核，不新建 `docs/api/F017.md`。

### 7.2 待 Database / Tester 核对事项

- **Database（预期 `NOT_REQUIRED`）**：确认 F017 无 Schema/迁移/约束/索引变更（纯展示层），与 plan_revision 5 `layers.database=false` 一致，并记录 `database: NOT_REQUIRED`。
- **Tester（TEST_DESIGN）**：
  1. 依 F-UI-1..7 与 §5 V1–V7 细化可执行步骤与断言；V1–V3/V4 静态部分给自动化命令与期望，V5–V7 给手动复验清单（真实/等价 Compose）。
  2. **不得**把未执行的 V5–V7 写成 PASS；明确区分 F017 与 F018 的执行归属。
  3. 依赖源不可达时按 N-2 声明限制，不作为 F-UI-1 通过证据。
  4. `smoke:client` 断言不得删减；如执行方式需变更（Node 版本等）须先返回 Architect 评估。

### 7.3 需协调器持久化的 D04 v2 差异（Architect 只读产出，未写文件）

在 `docs/architecture/d04-frontend-ui-stack.md` 上：状态 `PROPOSED` → `CONFIRMED`、版本 `v1` → `v2 FINAL`、补「Architect 签核 2026-10-15，依据 requirements revision 4 / plan_revision 5」、并把 D04-5 补 `@ant-design/cssinjs` 直接依赖、D04-7 拆为「过渡 `@layer legacy` → 最小全局层」、layer 顺序加入 `legacy`、新增 D04-9（locale zh_CN）。其余正文与 R1–R7 保持不变，另补 R8–R11。

### 7.4 结论

无 Blocking Questions，无新增业务规则，无 API/Schema/部署语义变更。**Status：`READY FOR IMPLEMENTATION`。**

CONTRACT 阶段已核对 Database `NOT_REQUIRED`（`docs/database/f017-frontend-ui.md` v1）、Test Design `TEST DESIGN READY`（`docs/features/F017/test-report.md#test-design` TD-1）与 D04 v2 FINAL，并裁定 TD-1（见 §7.5）；`api_required=false`，不新建 `docs/api/F017.md`。

### 7.5 CONTRACT 最终设计签核（Architect）

- 签核对象：F017 最终设计（本文档 + `docs/architecture/d04-frontend-ui-stack.md` v2 FINAL / CONFIRMED）。
- 签核者：Architect。
- 签核日期：2026-10-15。
- 覆盖 Feature：F017（含 F018 复验所依赖的前端 UI 集成设计）。
- 版本：本文件 CONTRACT 定稿；D04 v2 FINAL（含 TD-1 编辑性更正）。
- 上游依据：`docs/product/requirements-v3.md` revision 4（§28 / §29 rev4 CONFIRMED、§35.3 D04）；`docs/project/project-plan.yaml` plan_revision 5（用户 2026-10-12 批准）。
- 核对输入：product.md（PRODUCT COMPLETE）；database/f017-frontend-ui.md（Database NOT_REQUIRED）；test-report.md#test-design（TD-1 TEST DESIGN READY）。
- Contract 状态：`NOT_REQUIRED`（api_required=false；无 Endpoint / 字段 / 错误语义 / 分页 / 排序 / 过滤 / 权限 / 并发变更）。
- TD-1 裁定：定稿 `@layer` 行为 `@layer theme, base, antd, components, utilities;`（删除 `legacy`）；§1.2 与 D04 §2.1 按此订正（编辑性更正，不改 D04-7 规范文本、不改行为或范围）。
- 结论：`READY FOR IMPLEMENTATION`（无阻塞、无新增业务规则、无 API / Schema / 部署语义变化）。