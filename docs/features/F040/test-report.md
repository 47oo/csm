# F040 前端依赖版本范围与架构升级策略对齐（R07）— TEST REPORT

- **状态**：**TEST DESIGN READY（TD-F040-1）**；本文件当前只含 §1 TEST DESIGN，**不含 TEST 执行结果**（执行留待 TEST 阶段写 §2，届时补执行版本与证据）
- **版本**：TD-F040-1 v1（2026-10-29）；角色 tester；Feature F040（ENABLER / P1 / M30，`layers={database:false,backend:false,frontend:true}`、`api_required=false`）
- **分支 / 基线**：`feature/F040-dependency-ranges`；`start_commit=adef87a43d9c73465c815fe85b2577d5dd17a1f2`；设计时实测 `HEAD=109b61d`（`chore(F040): preflight` + `docs(F040): PRODUCT READY FOR ARCHITECT`）；plan revision 25；requirements revision 16
- **Basis**：`docs/features/F040/product.md` v1（A1–A10、ON-1..ON-6）；`docs/architecture/frontend-ui-stack.md` §1（Ant Design 6.6.x / Tailwind CSS 4.3.x）与 §4（仅次版本内升级）；`docs/project/project-plan.yaml` F040 `acceptance`（plan revision 25）；`frontend/package.json`、`frontend/package-lock.json`；`.pi/skills/frontend-ui/SKILL.md`（验证命令口径）；`docs/project/implementation-rules.md`；`docs/project/handoff.md`（交接与缺陷格式）；`docs/project/project-state.md` §3（TEST_DESIGN Gate）；`/tmp/csm-review-2026-10-29.md` §R07（340 passed 基线来源）
- **写权限说明**：本次仅写本文件 §1；`docs/project/**` 由协调器维护；未修改任何生产实现、Schema、契约或产品规则

---

## 1. TEST DESIGN

### 1.1 范围、分层与不适用项

| 项 | 判定 | 依据 |
| --- | --- | --- |
| 数据库 / Migration | `NOT_REQUIRED` | plan F040 `layers.database=false`、`not_required.database`；本 Feature 不触碰 Schema |
| 后端 / API 契约 | `NOT_REQUIRED` | `layers.backend=false`、`api_required=false`、`not_required.contract`；无请求/响应/权限/错误语义变化 |
| 真实前后端集成 | `NOT_REQUIRED` | 无 API 调用面变化；集成证据由 F045（变更集整体回归）承接 |
| 浏览器专项 / 全页巡检 | `NOT_REQUIRED` | product N8 + ON-6：无交互、视觉、文案改动；仓库无 DOM/E2E 依赖，浏览器检查属环境侧且未入库；可重复交互入口归 F043 |
| 性能 / chunk 体积 | `NOT_REQUIRED`（不计缺陷） | product A5 后半 + ON-5：本 Feature 不改包体，`build` 的 chunk 体积警告不记为 F040 缺陷 |
| 可验证层 | S 静态 / E 环境执行 / D 依赖解析 | 三者全部在仓库内可重复执行，无外部环境依赖（除 registry 可达性，见 §1.7） |

验证深度依据 `.pi/skills/frontend-ui/SKILL.md`「按影响选择验证命令」；此处**例外地全跑** `typecheck` + `build` + `smoke:client`，因为 product A5 明确要求三者全通过（A5 即验收条件，不是重复保证）。

### 1.2 环境探测（TEST_DESIGN 阶段实测，只读）

探测日期 2026-10-29；工作目录 `/home/hanhao/github/47oo/csm`，分支 `feature/F040-dependency-ranges`，`HEAD=109b61d`。以下为真实输出摘录。

| # | 探测 | 命令 | 实测结果 |
| --- | --- | --- | --- |
| P1 | Node / npm 版本 | `node --version` / `npm --version` | `v22.23.3` / `10.9.9`（与 F033 报告记录一致；`smoke:client` 依赖原生 type stripping，无需额外 flag） |
| P2 | 三项当前安装版本 | `cd frontend && npm ls antd tailwindcss @tailwindcss/vite 2>&1 \| head -20` | 输出仅两行：`csm-frontend@0.1.0 /home/.../frontend` 与 `└── (empty)`；**该输出不能作为 A4 证据**（原因见 P7 / D-F040-TD-03） |
| P3 | `package.json` 依赖计数与声明 | `node -e "…Object.keys(p.dependencies).length, Object.keys(p.devDependencies).length, p.dependencies.antd, p.dependencies.tailwindcss, p.devDependencies['@tailwindcss/vite']"` | `4 7 ^6.6.6 undefined ^4.3.3` → `dependencies` **4** 项、`devDependencies` **7** 项；`antd=^6.6.6`；**`tailwindcss` 不在 `dependencies`**（在 `devDependencies`，值 `^4.3.3`）；`@tailwindcss/vite=^4.3.3` |
| P4 | A8 源码零 diff（设计时） | `git diff --stat adef87a -- frontend/src frontend/vite.config.ts frontend/index.css frontend/scripts` | **空输出，exit 0**（A8 前置成立；TEST 阶段需重跑） |
| P5 | 相对 start_commit 的全部改动（设计时） | `git diff --stat adef87a` | 仅 `docs/features/F038/review-report.md`(+98)、`docs/features/F040/product.md`(+75)、`docs/project/backlog.md`、`docs/project/milestones.md`、`docs/project/project-plan.yaml`；`frontend/package.json`、`frontend/package-lock.json` **零 diff**（实现尚未开始，符合预期） |
| P6 | lockfile 规模 | `grep -c '"resolved"' package-lock.json`；`node -e` 统计 | `resolved` 行 **215**；`packages` 条目 **222**（其中 215 带 `resolved`+`integrity`）；`lockfileVersion=3`；`sha256(package-lock.json)=9eedc6f4…3775`；`sha256(package.json)=e94baa98…7390` |
| P7 | `node_modules` 现状 | `test -d frontend/node_modules`；`ls node_modules \| wc -l`；`npm ls --depth=0` | **存在**（64 个顶层条目）；但 `npm ls --depth=0` 以 `ELSPROBLEMS` 报 **11 个 `UNMET DEPENDENCY`** + `node_modules@ extraneous -> ./node_modules`（自引用符号链接，创建于 10-22）；同时 `node_modules/.package-lock.json` 只有 **150** 条目（vs lockfile 222），磁盘上包文件真实存在（见 P8）。**结论：当前 `node_modules` 不是可信安装树** |
| P8 | 磁盘实际版本（绕过 npm ls） | `node -e "require('./node_modules/<pkg>/package.json').version"` | `antd 6.6.6`、`tailwindcss 4.3.3`、`@tailwindcss/vite 4.3.3`、`@ant-design/icons 6.3.4`、`react 18.3.1`、`react-dom 18.3.1`、`typescript 5.9.3`、`vite 5.4.21`、`@vitejs/plugin-react 4.7.0`、`@types/react 18.3.31` |
| P9 | registry | `npm config get registry`；`npm ping` | `https://registry.npmmirror.com/`；`PONG 133ms`（**可达**） |
| P10 | 离线可行性（间接） | `du -sh ~/.npm/_cacache`；`df -h /home` | npm 缓存 **3.3G**；可用磁盘 595G。推断 `npm ci` 可走缓存，预计 30–90s；**未实测耗时**（`npm ci` 属写操作，本阶段禁止执行） |
| P11 | `smoke:client` 只读性 | `grep -n "writeFile\|mkdir\|rmSync\|createWriteStream\|appendFile\|process.exit" frontend/scripts/smoke-client.mjs` | 仅命中 `process.exit(failed>0?1:0)`；脚本无文件写入 → 可安全作为探测/复测命令 |
| P12 | semver 可用性（D 层判定工具） | `node -e "require('semver')"` | `semver 6.3.1` 可用（`node_modules` 传递依赖）；`satisfies('6.6.6','~6.6.6')=true`、`satisfies('6.7.0','~6.6.6')=false`。**限制**：传递依赖可能随安装树变化（见 §1.7 降级项） |

**基线 smoke 复测（只读，落基线值）**：`cd frontend && npm run smoke:client` → **`340 passed, 0 failed`，exit 0**（2026-10-29，HEAD `109b61d`，当前未改动的工作树）。该计数与 `/tmp/csm-review-2026-10-29.md`（`340 passed, 0 failed`）及 `docs/features/F036/evidence-notes.md`（F036 起基线 340）一致；`docs/features/F033` 的 322/328 为历史值，不作为本 Feature 基线。

### 1.3 A → 用例映射总表

| 验收 | 用例 ID | 类型 | 一句话判定 |
| --- | --- | --- | --- |
| A1 | S-01, S-02, D-01, D-02 | S/D | 三项声明 ∈ {`~x.y.z`, `x.y.z`}、形式一致、无 `^`；lockfile 根同步；`~` 语义拒绝次版本越界 |
| A2 | S-09, S-11, D-05 | S/D | `frontend-ui-stack.md` §1/§4 与三项逐项一致，且核对记录 + `npm ls` 原始输出入 F040 `architecture.md` |
| A3 | E-01, E-02, S-02 | E/S | 干净树 `npm ci` 成功：无 `ERESOLVE`、无 `EUSAGE`（lockfile 不同步） |
| A4 | E-03, E-04, E-09, E-10, D-03 | E/D | `npm ls` 显示 6.6.6 / 4.3.3 / 4.3.3，无 `UNMET`/`invalid`/`extraneous`；无跨次版本 |
| A5 | E-05, E-06, E-07 | E | `typecheck` / `build` / `smoke:client` 全通过，smoke `0 failed` 且 N ≥ 340 |
| A6 | S-03, S-04, D-06 | S/D | 除三项范围外 `package.json` 零 diff；依赖名集合不变（`dependencies` 4 / `devDependencies` **7**）；`scripts` 与元数据逐字不变 |
| A7 | S-05, S-06, D-04 | S/D | 无新增/删除包；其它包 `version`/`resolved`/`integrity` 不变 |
| A8 | S-07 | S | `frontend/src`、`vite.config.ts`、`index.css`、`scripts` 零 diff |
| A9 | S-08 | S | `frontend-ui-stack.md`、`docs/product/**`、`docs/api/**`、`docs/database/**`、`backend/**` 零 diff |
| A10 | S-10 | S | 变更文件 ⊆ 白名单 |
| ON-1 分支 | S-12 | S | 若选精确版本，`architecture.md` 记录理由且 plan 措辞同步（`~` 或精确） |
| ON-6 / N8 | §1.1 | — | 浏览器专项 `NOT_REQUIRED` + 理由 |

### 1.4 用例明细

通用约定：所有命令以仓库根 `/home/hanhao/github/47oo/csm` 为基准目录；`BASE=adef87a`；证据落点相对仓库根；`<A>` 表示"该用例映射的验收条目"。

#### S 层（静态检查，无需安装/构建）

---

**S-01 — 三项范围已收敛且形式一致（A1）**

- 前置：`frontend/package.json` 存在；实现已完成（`frontend` gate COMPLETE）。
- 命令：
  ```bash
  cd frontend && node -e '
    const p=require("./package.json");
    const t={antd:p.dependencies.antd,
             tailwindcss:p.devDependencies.tailwindcss,
             "@tailwindcss/vite":p.devDependencies["@tailwindcss/vite"]};
    console.log(JSON.stringify(t));'
  ```
- 判定表达式：令 `ALLOW={antd:["~6.6.6","6.6.6"], tailwindcss:["~4.3.3","4.3.3"], "@tailwindcss/vite":["~4.3.3","4.3.3"]}`，则
  `∀k: t[k] ∈ ALLOW[k]` ∧ `|{shapeish(t[k])}| = 1`（三项同为 `~` 或同为精确版本）∧ `∀k: !t[k].startsWith("^")` ∧ `t` 中无 `undefined`。
  **补充**：若三项形式不一致 → FAIL（A1 明确要求"三项形式一致"）。
- 证据落点：`docs/features/F040/test-report.md#2-test`（S-01 行）+ `docs/features/F040/artifacts/static.json`
- 对应：A1

---

**S-02 — lockfile 根声明与 `package.json` 同步（A1/A3）**

- 前置：同 S-01。
- 背景：`package-lock.json` 的 `packages[""]` 同时记录 `dependencies`/`devDependencies` 范围（实测当前为 `^` 形式）。若实现只改 `package.json` 而不改该处，`npm ci` 会以 `EUSAGE`（out of sync）失败 → A3 必失败。这是 A3 与 A7 之间的真实耦合点。
- 命令：
  ```bash
  cd frontend && node -e '
    const p=require("./package.json"), l=require("./package-lock.json");
    const root=l.packages[""]; const bad=[];
    for (const s of ["dependencies","devDependencies"])
      for (const [k,v] of Object.entries(p[s]||{}))
        if ((root[s]||{})[k]!==v) bad.push([s,k,root[s]&&root[s][k],v]);
    console.log("mismatch:",JSON.stringify(bad));
    console.log("extra-in-lock:",JSON.stringify([
      ...Object.keys(root.dependencies||{}).filter(k=>!(p.dependencies||{})[k]),
      ...Object.keys(root.devDependencies||{}).filter(k=>!(p.devDependencies||{})[k])]));'
  ```
- 判定表达式：`mismatch === []` ∧ `extra-in-lock === []`（全部 11 项双向一致）。
- 证据落点：同上 + `artifacts/static.json`
- 对应：A1、A3

---

**S-03 — `package.json` 除三项范围外零 diff（A6）**

- 前置：同 S-01。
- 命令：
  ```bash
  cd frontend && git show adef87a:frontend/package.json > /tmp/f040-pkg-base.json && node -e '
    const a=require("/tmp/f040-pkg-base.json"), b=require("./package.json");
    const ALLOW=new Set(["antd","tailwindcss","@tailwindcss/vite"]);
    const diffs=[]; const walk=(x,y,path)=>{
      const keys=new Set([...Object.keys(x||{}),...Object.keys(y||{})]);
      for (const k of keys){
        const px=path?path+"."+k:k, xv=x&&x[k], yv=y&&y[k];
        if (xv&&yv&&typeof xv==="object"&&typeof yv==="object") walk(xv,yv,px);
        else if (xv!==yv) diffs.push([px,xv,yv]);
      }};
    walk(a,b,"");
    const ok=diffs.filter(d=>ALLOW.has(d[0].split(".").pop()));
    const bad=diffs.filter(d=>!ALLOW.has(d[0].split(".").pop()));
    console.log("allowed-diff:",JSON.stringify(ok));
    console.log("forbidden-diff:",JSON.stringify(bad));
    console.log("counts:",Object.keys(b.dependencies).length,Object.keys(b.devDependencies).length);'
  ```
- 判定表达式：`bad === []` ∧ `allowed-diff` 恰好 3 条且路径分别为
  `dependencies.antd` / `devDependencies.tailwindcss` / `devDependencies["@tailwindcss/vite"]` ∧
  `Object.keys(dependencies).length === 4` ∧ `Object.keys(devDependencies).length === 7`（**实测基线 7，见 D-F040-TD-01**）。
  `scripts` / `name` / `version` / `private` / `type` 由 `bad===[]` 覆盖（逐字不变）。
- 证据落点：`artifacts/static.json` + 报告 §2 S-03 行
- 对应：A6

---

**S-04 — 非授权依赖零变更（A6/A7 前置）**

- 前置：同 S-01。
- 命令：`git diff adef87a -- frontend/package.json | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)'`
- 判定表达式：diff 行集合 ⊆ 6 行（3 个 `-` 旧值与 3 个 `+` 新值）；且这些行的 key ⊆ `{antd, tailwindcss, @tailwindcss/vite}`；
  `_protected = {react, react-dom, vite, typescript, @ant-design/icons, @types/react, @types/react-dom, @vitejs/plugin-react}` 在 diff 中**零出现**。
- 证据落点：`artifacts/package-json.diff`
- 对应：A6

---

**S-05 — lockfile 结构 diff 仅限三项范围（A7）**

- 前置：同 S-01。
- 命令：
  ```bash
  cd frontend && git show adef87a:frontend/package-lock.json > /tmp/f040-lock-base.json && node -e '
    const a=require("/tmp/f040-lock-base.json"), b=require("./package-lock.json");
    console.log("lockfileVersion:",a.lockfileVersion,b.lockfileVersion);
    const ka=Object.keys(a.packages), kb=Object.keys(b.packages);
    const added=kb.filter(k=>!ka.includes(k)), removed=ka.filter(k=>!kb.includes(k));
    console.log("added:",JSON.stringify(added),"removed:",JSON.stringify(removed));
    const changed=[];
    for (const k of ka.filter(k=>kb.includes(k)&&k!=="")){
      if (JSON.stringify(a.packages[k])!==JSON.stringify(b.packages[k])) changed.push(k);}
    console.log("non-root-entry-diffs:",JSON.stringify(changed));
    const T=["antd","tailwindcss","@tailwindcss/vite"];
    const rd=[]; 
    for (const s of ["dependencies","devDependencies"]){
      const ra=a.packages[""][s]||{}, rb=b.packages[""][s]||{};
      for (const k of new Set([...Object.keys(ra),...Object.keys(rb)]))
        if (ra[k]!==rb[k]) rd.push([s,k,ra[k],rb[k]]);}
    console.log("root-range-diffs:",JSON.stringify(rd));
    const T2=new Set(T); console.log("root-diff-scope-ok:",rd.every(d=>T2.has(d[1])));'
  ```
- 判定表达式：`lockfileVersion` 均为 3 ∧ `added===[]` ∧ `removed===[]` ∧ `non-root-entry-diffs===[]`（222 个非根条目逐字节等价 → 覆盖其它包 `version`/`resolved`/`integrity`）∧ `root-range-diffs` 恰好 3 条且 `root-diff-scope-ok===true`。
- 证据落点：`artifacts/static.json`、`artifacts/package-lock.diff`
- 对应：A7

---

**S-06 — 无新增/删除依赖、包计数不变（A7）**

- 前置：同 S-01。
- 命令：`cd frontend && node -e 'const l=require("./package-lock.json");const k=Object.keys(l.packages);console.log(k.length, k.filter(x=>l.packages[x].resolved).length, k.filter(x=>l.packages[x].integrity).length)'`
- 判定表达式：`222 215 215`（与基线 P6 完全一致）；`git diff adef87a --numstat -- frontend/package-lock.json` 增删行数 ≤ 6（仅 3 行替换）。
- 证据落点：`artifacts/static.json`
- 对应：A7

---

**S-07 — 前端源码零 diff（A8）**

- 前置：无（TEST 阶段在任何实现提交后重跑）。
- 命令：
  ```bash
  git diff --stat adef87a -- frontend/src frontend/vite.config.ts frontend/index.css frontend/scripts; echo "exit=$?"
  git diff --stat adef87a -- frontend/src frontend/vite.config.ts frontend/index.css frontend/scripts | wc -l
  ```
- 判定表达式：输出为空 ∧ exit 0 ∧ 行数 0。（设计时实测已为空，见 P4。）
- 证据落点：`artifacts/git-scope.txt`
- 对应：A8

---

**S-08 — 文档与后端零 diff（A9）**

- 前置：无。
- 命令：
  ```bash
  git diff --stat adef87a -- docs/architecture/frontend-ui-stack.md docs/product docs/api docs/database backend | wc -l
  git diff --stat adef87a -- docs/architecture/frontend-ui-stack.md docs/product docs/api docs/database backend; echo "exit=$?"
  ```
- 判定表达式：行数 0 ∧ 输出为空 ∧ exit 0。
- 证据落点：`artifacts/git-scope.txt`
- 对应：A9

---

**S-09 — A2 符合性核对记录与原始 `npm ls` 输出已入架构文档（A2）**

- 前置：`docs/features/F040/architecture.md` 存在（当前仅 `product.md`，故本用例在 ARCHITECTURE/早 TEST 阶段为 `BLOCKED`，不是 FAIL）。
- 命令：
  ```bash
  test -f docs/features/F040/architecture.md && echo present
  grep -nE '6\.6\.x|4\.3\.x|npm ls|antd@6\.6|tailwindcss@4\.3|@tailwindcss/vite@4\.3' docs/features/F040/architecture.md | head -20
  grep -nE '^#+.*(§1|§4|选型|升级策略|符合性)' docs/features/F040/architecture.md | head
  ```
- 判定表达式：文件存在 ∧ 命中 §1（6.6.x）与 §4（仅次版本内升级）各至少 1 处 §"逐项一致"记录 ∧ 命中 `antd@6.6.x`、`tailwindcss@4.3.x`、`@tailwindcss/vite@4.3.x` 三条原始 `npm ls` 行 ∧ 该 `npm ls` 输出与 E-03 实测输出一致（版本号逐字相同）。
- 证据落点：`artifacts/architecture-crosscheck.txt`（本次 `grep` 输出）
- 对应：A2（人工判定项：核对记录是否真的逐项，而非仅贴输出）

---

**S-10 — 变更文件范围受控（A10）**

- 前置：无。
- 命令：
  ```bash
  git diff --name-only adef87a -- . | sed 's/^/CHANGED: /'
  ```
- 判定表达式：`CHANGED` 集合 ⊆ 白名单正则
  `^frontend/(package\.json|package-lock\.json)$` ∨ `^docs/features/F040/` ∨ `^docs/project/`；
  且必须包含 `frontend/package.json` 与 `frontend/package-lock.json`。
- 证据落点：`artifacts/git-scope.txt`
- 对应：A10

---

**S-11 — 架构策略文档仍为 6.6.x / 4.3.x 且未被弱化（A2/A9）**

- 前置：无。
- 命令：`grep -nE '6\.6\.x|4\.3\.x|跨次版本升级' docs/architecture/frontend-ui-stack.md`
- 判定表达式：命中 §1「Ant Design 6.6.x … Tailwind CSS 4.3.x」与 §4「Ant Design 仅在 6.6.x 兼容范围内升级，Tailwind CSS 仅在 4.3.x 兼容范围内升级」两条原文；配合 S-08（零 diff）证明未被改写。
- 证据落点：`artifacts/policy-grep.txt`
- 对应：A2、A9

---

**S-12 — ON-1 分支：精确版本选择时须留理由并同步 plan 措辞（A1）**

- 前置：S-01 判定为"精确版本"形式时启用；`~` 形式时本用例自动 `NOT_APPLICABLE`。
- 命令：
  ```bash
  grep -nE '精确|exact|ON-1' docs/features/F040/architecture.md | head
  python3 -c "import yaml;p=yaml.safe_load(open('docs/project/project-plan.yaml'));f=[x for x in p['features'] if x['id']=='F040'][0];print(f['acceptance'])" | grep -oE '~|精确版本'
  ```
- 判定表达式：`architecture.md` 含选择精确版本的理由 ∧ plan `acceptance` 措辞与实际形式一致（plan 现文为「收敛为 `~`」，见 D-F040-TD-02）。
- 证据落点：`artifacts/on1-decision.txt`
- 对应：A1（ON-1 条件分支）

#### E 层（环境执行，需安装与构建）

---

**E-01 — 隔离干净目录 `npm ci`（A3，零风险主证据）**

- 前置：S-02 通过（根范围同步）；registry 可达（P9）或缓存可用（P10）。
- 命令：
  ```bash
  rm -rf /tmp/f040-ci-clean && mkdir -p /tmp/f040-ci-clean
  cp frontend/package.json frontend/package-lock.json /tmp/f040-ci-clean/
  cd /tmp/f040-ci-clean && /usr/bin/time -f 'elapsed=%es' npm ci --no-audit --no-fund 2>&1 | tee /tmp/f040-ci-clean.log; echo "exit=${PIPESTATUS[0]}"
  ```
- 判定表达式：`exit=0` ∧ 日志无 `ERESOLVE` ∧ 日志无 `npm error code EUSAGE`（lockfile 不同步）∧ 出现 `added \d+ packages` ∧ `test -f /tmp/f040-ci-clean/node_modules/antd/package.json` 为真。耗时只作记录，不作判定。
- 证据落点：`docs/features/F040/artifacts/npm-ci-clean.log`
- 对应：A3

---

**E-02 — 工作区原地 `npm ci`（A3/A4 前置，按 §1.5 协议）**

- 前置：E-01 通过（否则先查 S-02 / lockfile 同步，不进入工作区写操作）；已按 §1.5 Step 0 记录 pre-state（`git status`、两份 sha256、`ls node_modules | wc -l`）。
- 命令（严格按 §1.5 顺序执行；`mv` 备份在仓库外，避免污染工作区）：
  ```bash
  mv frontend/node_modules /tmp/f040-node_modules-backup-$(date +%Y%m%d%H%M)
  cd frontend && /usr/bin/time -f 'elapsed=%es' npm ci --no-audit --no-fund 2>&1 | tee ../docs/features/F040/artifacts/npm-ci-inplace.log; echo "exit=${PIPESTATUS[0]}"
  ```
- 判定表达式：`exit=0` ∧ 无 `ERESOLVE` ∧ 无 `EUSAGE` ∧ `frontend/node_modules/antd/package.json` 存在。
- 失败回退：见 §1.5 Step 5（`rm -rf frontend/node_modules && mv /tmp/backup frontend/node_modules`），并置本用例 `BLOCKED`（不得以 E-01 结果顶替 E-02 的 A4/A5 前置）。
- 证据落点：`artifacts/npm-ci-inplace.log`、`artifacts/env-prestate.txt`
- 对应：A3

---

**E-03 — `npm ls` 三项版本与树健康（A4）**

- 前置：E-02（或 E-01 的干净树 + 在同树执行）完成；**禁止**在 P7 所述的可疑旧树上执行本用例。
- 命令：
  ```bash
  cd frontend && npm ls antd tailwindcss @tailwindcss/vite 2>&1 | tee ../docs/features/F040/artifacts/npm-ls.txt; echo "exit=${PIPESTATUS[0]}"
  ```
- 判定表达式：`exit=0` ∧ 输出匹配 `antd@6\.6\.6` ∧ `tailwindcss@4\.3\.3` ∧ `@tailwindcss/vite@4\.3\.3` ∧ 输出不含 `UNMET`、`invalid`、`extraneous`、`(empty)`。
- 证据落点：`artifacts/npm-ls.txt`（原始输出，同时供 S-09 比对）
- 对应：A4

---

**E-04 — 全树 `npm ls --depth=0` 无异常项（A4）**

- 前置：E-02。
- 命令：`cd frontend && npm ls --depth=0 2>&1 | tee ../docs/features/F040/artifacts/npm-ls-depth0.txt; echo "exit=${PIPESTATUS[0]}"`
- 判定表达式：`exit=0` ∧ 输出现 11 个直接依赖且全部无 `UNMET`/`invalid`/`extraneous`。
- 说明：设计时旧树此处为 `ELSPROBLEMS` + 11 `UNMET`（P7）。干净 `npm ci` 后出现的改善**不算 F040 交付物**，仅记录为环境正常化；若干净树仍报 `UNMET`/`extraneous` → FAIL（A4）并作为实现/环境缺陷处理。
- 证据落点：`artifacts/npm-ls-depth0.txt`
- 对应：A4

---

**E-05 — `npm run typecheck`（A5）**

- 前置：E-02。
- 命令：`cd frontend && npm run typecheck 2>&1 | tee ../docs/features/F040/artifacts/typecheck.log; echo "exit=${PIPESTATUS[0]}"`
- 判定表达式：`exit=0` ∧ 日志无 `error TS`。
- 证据落点：`artifacts/typecheck.log`
- 对应：A5

---

**E-06 — `npm run build`（A5）**

- 前置：E-02。
- 命令：`cd frontend && npm run build 2>&1 | tee ../docs/features/F040/artifacts/build.log; echo "exit=${PIPESTATUS[0]}"; test -f dist/index.html && echo dist-ok`
- 判定表达式：`exit=0` ∧ `dist-ok` 出现 ∧ 日志无 `error TS`／`Error:`（构建失败）。
- 允许项：chunk 体积警告（`> 500 kB` 等）**不计缺陷**（product A5 后半、ON-5），只在报告注明。
- 副作用：`frontend/dist/` 被 `frontend/.gitignore:2` 忽略，不产生 Git 变更（S-10 不受影响）。
- 证据落点：`artifacts/build.log`
- 对应：A5

---

**E-07 — `npm run smoke:client` 回归（A5 + 基线）**

- 前置：E-02。
- 命令：
  ```bash
  cd frontend && npm run smoke:client 2>&1 | tee ../docs/features/F040/artifacts/smoke-client.log; echo "exit=${PIPESTATUS[0]}"
  grep -E '^[0-9]+ passed, [0-9]+ failed$' ../docs/features/F040/artifacts/smoke-client.log
  ```
- 判定表达式：`exit=0` ∧ 末行匹配 `^(\d+) passed, 0 failed$` ∧ `N ≥ 340`（基线见 §1.6）。
- 证据落点：`artifacts/smoke-client.log`
- 对应：A5

---

**E-08 — `npm ci` 未修改 lockfile / `package.json`（A3/A7）**

- 前置：E-02 完成（本用例为 E-02 的伴随断言）。
- 命令：
  ```bash
  sha256sum frontend/package.json frontend/package-lock.json | tee docs/features/F040/artifacts/lock-after.sha256
  diff docs/features/F040/artifacts/lock-before.sha256 docs/features/F040/artifacts/lock-after.sha256 && echo LOCK-UNCHANGED
  git status --porcelain frontend/package.json frontend/package-lock.json; echo "status-lines=$(git status --porcelain frontend/package.json frontend/package-lock.json | wc -l)"
  ```
- 判定表达式：`LOCK-UNCHANGED` 出现 ∧ `status-lines=0` ∧ `lock-after.sha256` 中两值等于 §1.5 Step 0 记录值（设计时基线：`package-lock.json=9eedc6f4…3775`、`package.json=e94baa98…7390`；实现后应等于**实现提交内**的值，故以 Step 0 为唯一比对基准）。
- 允许项：`npm ci` 会写 `frontend/node_modules/.package-lock.json`（隐藏 lockfile，位于 gitignored 的 `node_modules/` 内）——不属 lockfile 修改。
- 证据落点：`artifacts/lock-before.sha256` / `artifacts/lock-after.sha256` / `artifacts/env-prestate.txt`
- 对应：A3、A7

---

**E-09 — 实装版本与 lockfile 条目一致（A4）**

- 前置：E-02。
- 命令：
  ```bash
  cd frontend && node -e '
    const l=require("./package-lock.json");
    for (const k of ["antd","tailwindcss","@tailwindcss/vite"]){
      const want=l.packages["node_modules/"+k].version;
      const got=require("./node_modules/"+k+"/package.json").version;
      console.log(k,"lock="+want,"installed="+got,want===got?"OK":"MISMATCH");}'
  ```
- 判定表达式：三行均 `OK`，且 `want` 分别为 `6.6.6` / `4.3.3` / `4.3.3`。
- 证据落点：`artifacts/installed-versions.txt`
- 对应：A4

---

**E-10 — 无跨次版本升级（A4 + product「不覆盖 N1」）**

- 前置：E-02、S-01。
- 命令：
  ```bash
  cd frontend && node -e '
    const s=require("semver"), p=require("./package.json"), l=require("./package-lock.json");
    const M={antd:p.dependencies.antd,tailwindcss:p.devDependencies.tailwindcss,"@tailwindcss/vite":p.devDependencies["@tailwindcss/vite"]};
    for (const k of Object.keys(M)){
      const v=l.packages["node_modules/"+k].version;
      const minor=v.split(".").slice(0,2).join(".");
      const declaredMinor=M[k].replace(/^[~^=v]/,"").split(".").slice(0,2).join(".");
      console.log(k,"declared="+M[k],"locked="+v,"minorMatch="+(minor===declaredMinor),"satisfies="+s.satisfies(v,M[k]));}'
  ```
- 判定表达式：三项均 `minorMatch=true` ∧ `satisfies=true`；且 `antd` 的 minor 为 `6.6`、两个 tailwind 包为 `4.3`。
- 证据落点：`artifacts/installed-versions.txt`
- 对应：A4

#### D 层（依赖解析语义，可在无网络下重复执行）

---

**D-01 — `~` 范围确实阻止次版本越界（A1）**

- 前置：S-01 判定为 `~` 形式（精确版本形式时本用例 `NOT_APPLICABLE`，由 D-01b 覆盖）。
- 命令：
  ```bash
  cd frontend && node -e '
    const s=require("semver");
    const cases=[["6.6.6","~6.6.6",true],["6.6.9","~6.6.6",true],["6.7.0","~6.6.6",false],
                 ["4.3.3","~4.3.3",true],["4.3.9","~4.3.3",true],["4.4.0","~4.3.3",false]];
    for (const [v,r,want] of cases) console.log(v,r,s.satisfies(v,r),want,(s.satisfies(v,r)===want)?"OK":"FAIL");'
  ```
- 判定表达式：全部 6 行 `OK`（`~` 允许同 minor 的补丁、拒绝 `6.7.0` 与 `4.4.0`）。
- D-01b（精确版本形式）：`satisfies('6.6.6','6.6.6')=true` ∧ `satisfies('6.6.7','6.6.6')=false` ∧ 对 `4.3.3` 同理。
- 证据落点：`artifacts/range-semantics.txt`
- 对应：A1

---

**D-02 — 对照：`^` 形式确实允许越界（R07 问题成立性）**

- 前置：无（用基线值即可，可离线）。
- 命令：`cd frontend && node -e 'const s=require("semver");console.log(s.satisfies("6.7.0","^6.6.6"), s.satisfies("4.4.0","^4.3.3"))'`
- 判定表达式：输出 `true true`（记录用；证明收敛为 `~`/精确版本不是形式主义，而是消除 6.7.x / 4.4.x 被静默接受的可能）。本用例不作为 A 条目判定项，仅作 A2 理由证据。
- 证据落点：`artifacts/range-semantics.txt`
- 对应：A2（辅助证据）

---

**D-03 — lockfile 条目版本满足声明范围（A4/A7）**

- 前置：S-02。
- 命令：
  ```bash
  cd frontend && node -e '
    const s=require("semver"), p=require("./package.json"), l=require("./package-lock.json");
    const M={antd:p.dependencies.antd,tailwindcss:p.devDependencies.tailwindcss,"@tailwindcss/vite":p.devDependencies["@tailwindcss/vite"]};
    for (const k of Object.keys(M)) console.log(k,s.satisfies(l.packages["node_modules/"+k].version,M[k]));'
  ```
- 判定表达式：三行均为 `true`。
- 证据落点：`artifacts/range-semantics.txt`
- 对应：A4、A7

---

**D-04 — 三项目标包的 `resolved`/`integrity` 与基线一致（A7）**

- 前置：S-05 已导出 `/tmp/f040-lock-base.json`。
- 命令：
  ```bash
  cd frontend && node -e '
    const a=require("/tmp/f040-lock-base.json"), b=require("./package-lock.json");
    for (const k of ["antd","tailwindcss","@tailwindcss/vite"]){
      const x=a.packages["node_modules/"+k], y=b.packages["node_modules/"+k];
      console.log(k, x.version===y.version, x.resolved===y.resolved, x.integrity===y.integrity);}'
  ```
- 判定表达式：三行均 `true true true`（无重新解析到不同 tarball）。
- 证据落点：`artifacts/static.json`
- 对应：A7

---

**D-05 — 声明范围与架构策略 minor 逐项一致（A2）**

- 前置：S-01、S-11。
- 命令：
  ```bash
  cd frontend && node -e '
    const fs=require("fs"), p=require("./package.json");
    const doc=fs.readFileSync("../docs/architecture/frontend-ui-stack.md","utf8");
    const pol=doc.match(/6\.6\.x/g)||[], polT=doc.match(/4\.3\.x/g)||[];
    const minor=v=>String(v).replace(/^[~^=v]/,"").split(".").slice(0,2).join(".");
    console.log("policy-antd-hits="+pol.length,"policy-tailwind-hits="+polT.length);
    console.log("declared-antd-minor="+minor(p.dependencies.antd));
    console.log("declared-tw-minor="+minor(p.devDependencies.tailwindcss),minor(p.devDependencies["@tailwindcss/vite"]));'
  ```
- 判定表达式：`policy-antd-hits ≥ 2`（§1 + §4）∧ `policy-tailwind-hits ≥ 2` ∧ `declared-antd-minor === "6.6"` ∧ 两个 tailwind minor 均为 `"4.3"`。
- 证据落点：`artifacts/policy-grep.txt`
- 对应：A2

---

**D-06 — 反向护栏：未被授权的依赖仍保持原 `^` 声明（A6）**

- 前置：S-01。
- 命令：
  ```bash
  cd frontend && node -e '
    const p=require("./package.json");
    const P=Object.assign({},p.dependencies,p.devDependencies);
    for (const k of ["react","react-dom","vite","typescript","@ant-design/icons","@types/react","@types/react-dom","@vitejs/plugin-react"])
      console.log(k,P[k],String(P[k]).startsWith("^"));'
  ```
- 判定表达式：8 行全部 `true`（保持 `^`）且值分别等于 `^18.3.1`、`^18.3.1`、`^5.4.9`、`^5.6.3`、`^6.3.4`、`^18.3.11`、`^18.3.1`、`^4.3.2`（与 `adef87a` 逐字相同）。
- 证据落点：`artifacts/static.json`
- 对应：A6

### 1.5 `npm ci` 验证方案（ON-2）

**原则**：先零风险证明 lockfile 自洽（E-01），再在仓库内刷新安装树（E-02）；任何一步都不得破坏工作区、不得产生 Git 变更、不得让 `npm ci` 重写 lockfile。

| Step | 动作 | 判定 / 记录 |
| --- | --- | --- |
| 0 | **记录 pre-state**：`git status --porcelain`、`sha256sum frontend/package{,-lock}.json`、`ls frontend/node_modules \| wc -l`、`git rev-parse --short HEAD`，写入 `artifacts/env-prestate.txt` 与 `artifacts/lock-before.sha256` | 必须 `git status` 干净（除已声明的 F040 文档）；否则先由协调器核对现场 |
| 1 | 静态同步前置：S-02（`packages[""]` 与 `package.json` 全部 11 项一致） | 不同步则**不进入** Step 2/3，直接判 A3 失败并退实现（实现必须同步 lockfile 根范围） |
| 2 | **隔离目录**（主证据，零风险）：`cp package.json package-lock.json /tmp/f040-ci-clean/` → `npm ci --no-audit --no-fund` | E-01；不接触仓库 `node_modules`，也不产生 Git 变更 |
| 3 | **原地刷新**：`mv frontend/node_modules /tmp/f040-node_modules-backup-<ts>`（**备份目标在仓库外**，避免 `node_modules.bak*` 成为未跟踪文件——`frontend/.gitignore` 只忽略 `node_modules/` 与 `dist/`）→ `cd frontend && npm ci --no-audit --no-fund` | E-02；预计 30–90s（缓存 3.3G、registry PONG 133ms，P9/P10） |
| 4 | **证明 lockfile 未被修改**：`sha256sum` 复算与 Step 0 逐字节比对（`diff`）+ `git status --porcelain frontend/package.json frontend/package-lock.json`（必须 0 行）+ `git diff --stat` 对两个文件必须仍只含实现提交内的 3 项范围变更 | E-08。说明：`npm ci` 按设计**不读改写 `package.json`/`package-lock.json`**；它只写 `node_modules/**`（含隐藏 `node_modules/.package-lock.json`），两者均被 `frontend/.gitignore` 忽略。**预期 lockfile 不被重写**；若 Step 4 显示 lockfile 变化 → 判 A3/A7 风险，停止，恢复后 `RETURN TO IMPLEMENTATION` |
| 5 | **回退**：`rm -rf frontend/node_modules && mv /tmp/f040-node_modules-backup-<ts> frontend/node_modules`（可重复、幂等）；确认 `git status --porcelain` 与 Step 0 一致 | 任一步失败即回退；失败用例置 `BLOCKED`，不得用旧树结果充当 A4/A5 证据 |
| 6 | 清理（可选）：删除 `/tmp/f040-ci-clean`、`/tmp/f040-node_modules-backup-*`、`/tmp/f040-lock-base.json` | 仅 `/tmp`，不动仓库 |

**已知环境事实（作为 Step 3 的动机）**：当前 `frontend/node_modules` 不是可信安装树（P7：隐藏 lockfile 150 条 vs 222；`npm ls` 11 × `UNMET`；`node_modules/node_modules -> .` 自引用符号链接，2026-10-22 创建）。原地 `npm ci` 会一次性消除这些既有异常；**该异常不由 F040 引入，也不记为 F040 缺陷**（见 D-F040-TD-03）。

### 1.6 基线值与"不少于基线"判定

| 项 | 值 | 命令 / 日期 | 判定方式 |
| --- | --- | --- | --- |
| `smoke:client` 通过项基线 | **340** | `cd frontend && npm run smoke:client` → `340 passed, 0 failed`（2026-10-29，HEAD `109b61d`，TEST_DESIGN 实测） | TEST 阶段末行 `N ≥ 340` 且 `failed = 0`；取"实测最小值"作为下限，若 TEST 实测更高（例如后续 Feature 增测），仍以 **340** 为不可退化下限并在报告中同时记录两次实测值 |
| 交叉来源 | 340 | `/tmp/csm-review-2026-10-29.md`（`340 passed，0 failed`）；`docs/features/F036/evidence-notes.md`（F036 起基线 340）；`docs/features/F036/implementation.md`（340） | 一致，无冲突 |
| 历史值（不作基线） | 322（F028/F029）、328（F033）、337（F034）、339（F035） | 各 Feature 报告 | 仅作演进记录；不得用历史低值当基线 |
| `smoke` 用例数期望 | 340（±0） | — | 本 Feature 不改 `scripts/smoke-client.mjs`（A8），故期望计数不变；若 `N > 340` 说明改动了 smoke 脚本 → 触发 A8 复核 |
| 全树包数 / `resolved` / `integrity` | `222 / 215 / 215` | 设计实测（P6） | 实现后必须完全相等（S-06） |
| `dependency` 计数 | `dependencies=4`、`devDependencies=7` | 设计实测（P3） | S-03；**product A6 写的"8 项"与实际不符**，见 D-F040-TD-01 |
| lockfile 基线哈希 | `package-lock.json=9eedc6f4b0c19d809d50721becfa12ae810cf1a0f03d40836cc7b19a795d3775`；`package.json=e94baa98328117e2b288828d51e3a326ce75211e9d18af7fab08da0ee8427390`（`adef87a`/设计时同一内容） | `sha256sum` | E-08 比对基准；实现后以 Step 0 新值为准 |

### 1.7 不可验证项与降级规则

| 场景 | 处理 | 禁止做法 |
| --- | --- | --- |
| registry 不可达（`npm ping` 失败）且缓存不足 | E-01/E-02 置 **`NOT TESTED`**（原因：环境不可达），A3/A4/A5 相应判 `NOT TESTED`；整体结论 `TEST BLOCKED`，不得写 READY | **不得**用 `npm ls` / `node_modules` 现有内容"证明 `npm ci` 通过"；不得改写 `/etc/hosts`、registry 或 `package-lock.json` 绕过 |
| 缓存可用但网络不可达 | 允许 `npm ci --offline`（记录 `--offline` 变体与耗时），判定表达式不变；报告中注明离线变体 | 不得把 `--offline` 与在线结果混写为同一条证据 |
| `semver` 包不可用（D 层，依赖传递安装） | D-01/D-02/D-03/D-10 改为等价正则判定：`~X.Y.Z` ⇒ 允许补丁、拒绝 minor 变化；仍必须给出逐条结论 | 不得因工具缺失跳过 D 层而不说明；不得把 `npm ls` 当作 range 语义证据 |
| 架构文档缺失（S-09） | 该用例 `BLOCKED`（输入缺失），A2 判 `BLOCKED`；其余 A 条目仍可判 | 不得用 product.md 的核对代替 `architecture.md` 内的记录 |
| chunk 体积警告 | 记录但不判缺陷（ON-5） | 不得因此判 A5 FAIL |
| 浏览器专项 / 全页巡检（ON-6、N8） | `NOT_REQUIRED`：无交互/视觉改动，仓库无 DOM/E2E 依赖，Playwright 属环境侧未入库；可重复入口归 F043 | 不得写成"DOM 已验证"或"浏览器验收通过" |
| 真实前后端集成 | `NOT_REQUIRED`：`api_required=false`、无请求面变化；整体回归归 F045 | 不得用 Mock/本地结果替代 F045 的整体验收 |
| 需求 §31–33 跨功能整体验收 | 不在 F040 范围（F045 承接）；F040 的局部 PASS 不能拼成整体 PASS | 不得在 F040 报告中宣称变更集整体验收通过 |

### 1.8 设计检查发现（Issues）

| ID | Severity | Layer | Location | 期望 / 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D-F040-TD-01 | MEDIUM | 文档口径（验收标准事实） | `docs/features/F040/product.md` A6「`devDependencies` 8 项」 | 期望与实测一致：实测 `dependencies=4`、`devDependencies=**7**`（`@tailwindcss/vite`、`@types/react`、`@types/react-dom`、`@vitejs/plugin-react`、`tailwindcss`、`typescript`、`vite`）；实际写 8 | 若按 8 判定，A6 会得到**假 FAIL**，或诱导实现"补第 8 项"越界新增依赖 | Product Manager（正文修订）/ Architect（在 `architecture.md` 记正确计数） | 是（口径必须澄清）。**不阻塞 TEST_DESIGN**：TD 已固定以实测 7 为判定基线（S-03） |
| D-F040-TD-02 | LOW | 验收措辞分支 | `docs/project/project-plan.yaml` F040 `acceptance`（「收敛为 `~`」）vs `product.md` A1 / ON-1（允许精确版本） | 期望单一可判口径；实际为 `~` 与 `~`/精确 并存 | 若 Architect 选精确版本，plan 措辞与实现不一致，A1 判定出现歧义 | Architect（ON-1 裁定）+ 协调器（同步 plan 措辞） | 是（仅在选精确版本时；选 `~` 时自愈） |
| D-F040-TD-03 | MEDIUM | 环境 / 测试基础设施 | `frontend/node_modules`（工作区） | 期望可信安装树；实际：`npm ls --depth=0` 报 11 × `UNMET DEPENDENCY` + `node_modules@ extraneous -> ./node_modules`（自引用符号链接，2026-10-22），`node_modules/.package-lock.json` 仅 150 条（lockfile 222），而磁盘包文件存在（antd 6.6.6 等） | 若在旧树上取 A4 证据会得到**假 FAIL**；任何 `npm ls` 单点判定不可信 | 协调器（环境维护）；**不归 F040 实现** | 否（`npm ci` 刷新即消除）；但要求 A4/A5 证据必须在干净 `npm ci` 后的树取得，且不得把该既存异常记成 F040 缺陷 |
| D-F040-TD-04 | NOTE | 文档措辞 | `product.md` §2 变更表 / A6 未区分 `dependencies` 与 `devDependencies`（`tailwindcss`、`@tailwindcss/vite` 实为 devDependencies） | 期望按实际位置表述；实际统一称"依赖" | 无功能影响；S-01/S-03 已按实际位置断言 | Product Manager | 否 |
| N-F040-TD-01 | NOTE | 实现提示 | `frontend/package-lock.json` 的 `packages[""]` 亦记录三项范围 | 期望实现同步该处（A3 蕴含）；product.md 未显式点名 | 漏改会让 `npm ci` 以 `EUSAGE` 失败 → A3 FAIL | Frontend | 否（S-02 已做前置拦截） |
| N-F040-TD-02 | NOTE | 证据卫生 | `npm ci` 会写 `node_modules/.package-lock.json`（gitignored，隐藏 lockfile） | 不属 lockfile 修改，E-08 不得误判 | 仅影响判定口径 | Tester | 否 |

### 1.9 结论

**TEST DESIGN READY（TD-F040-1）**

- A1–A10 全部已展开为可执行、可重复的断言（S-01..S-12 / E-01..E-10 / D-01..D-06，共 **28** 条），每条给出前置、命令、判定表达式、证据落点与 A 映射；判定不依赖"看起来合理"的人工印象（唯一人工判定项 S-09 也给了可机检的最低门槛）。
- 环境与数据来源已核实：Node/npm 版本、registry 可达性、缓存、`node_modules` 真实状态（含既有异常）、lockfile 规模与哈希，均实测记录（§1.2）。
- `npm ci` 验证方案（含隔离目录、仓库外备份、回退、lockfile 不改的证明手段）已固定（§1.5）。
- 基线值已固定为 `smoke:client` **340 passed / 0 failed**（2026-10-29 实测），并写明"不少于基线"的判定方式（§1.6）。
- 不可验证/降级项已逐条声明，并明确禁止用 `npm ls` 顶替 `npm ci`、禁止把浏览器/整体验收写成仓库保证（§1.7）。
- 设计检查发现 2 项 MEDIUM、1 项 LOW、3 项 NOTE；均不阻塞本 Gate：D-F040-TD-01 已由 TD 采用实测基线（7 项）消解，D-F040-TD-03 已由 §1.5 的干净 `npm ci` 协议消解，D-F040-TD-02 仅在选精确版本时生效。

**声明**：`TEST DESIGN READY` 仅表示"方案可验证、验收映射完整、环境与基线明确"。它**不是测试通过**，**不放行实现**，也不批准合并；`frontend` 实现与 TEST 执行均未开始，A1–A10 目前一律为 `NOT TESTED`（设计阶段不作 PASS 填充）。放行实现须由 Architect 在 CONTRACT 阶段核对本 Test Design 与最终设计（含 ON-1 取舍）后给出 `READY FOR IMPLEMENTATION`；执行结果在 §2 TEST 记录。

**Result（本次未执行、未判定任何 A 条目）**：本阶段唯一产物为本文件 §1；未修改生产实现、Schema、契约或产品规则。建议协调器把 `implementation.test_design` 置 COMPLETE 并以 `docs/features/F040/test-report.md#1-test-design` 作为 evidence。

**Next**：Architect 产出 `docs/features/F040/architecture.md`（含 ON-1 取舍、§1/§4 逐项核对记录与原始 `npm ls` 输出）→ 协调器进入 CONTRACT → Frontend 实现三项范围 + lockfile 根同步 → tester 按本设计执行 S/E/D 层并写 §2 TEST。

GIT: git rev-parse --abbrev-ref HEAD
GIT: git rev-parse --short HEAD
GIT: git status --porcelain
GIT: git diff --stat adef87a43d9c73465c815fe85b2577d5dd17a1f2 -- frontend/src frontend/vite.config.ts frontend/index.css frontend/scripts
GIT: git diff --stat adef87a43d9c73465c815fe85b2577d5dd17a1f2 -- frontend/package.json frontend/package-lock.json
GIT: git diff --stat adef87a43d9c73465c815fe85b2577d5dd17a1f2
GIT: git log --oneline adef87a43d9c73465c815fe85b2577d5dd17a1f2..HEAD
GIT: git check-ignore -v frontend/node_modules frontend/dist

（上列为本次实际执行的只读 Git 命令；`git status --porcelain | head -30`、`git log --oneline … | head -20` 带管道截断。§1.4 中 `git show adef87a:frontend/package.json` / `git show adef87a:frontend/package-lock.json` 属 **TEST 阶段待执行**的设计命令，本次未运行。未执行任何 Git 写操作。）
