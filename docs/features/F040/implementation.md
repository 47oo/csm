# F040 前端依赖版本范围与架构升级策略对齐（R07）— IMPLEMENTATION 报告

- **结论**：**FRONTEND COMPLETE**
- **版本**：v1（2026-10-29）；角色 frontend；Feature F040（ENABLER / P1 / M30，`layers={database:false,backend:false,frontend:true}`、`api_required=false`）
- **分支 / 基线**：`feature/F040-dependency-ranges`；`start_commit=adef87a43d9c73465c815fe85b2577d5dd17a1f2`；写前 `HEAD=32d05fe`（`docs(F040): ARCHITECTURE READY FOR DESIGN + CONTRACT signed`）、工作区干净；plan revision 25；requirements revision 16
- **上游依据**：`docs/features/F040/architecture.md` §1.3（三处目标字符串）/ §1.4（lockfile 根条目同步 + 三重判定）/ §1.7（硬边界）；`docs/features/F040/test-report.md` §1.5（`npm ci` 协议）/ §1.6（基线 340）；`docs/features/F040/product.md` v1（A1–A10）
- **写权限落实**：仅 `frontend/package.json`、`frontend/package-lock.json`、`docs/features/F040/architecture.md` §7 锚点、本文件、`docs/features/F040/artifacts/**`。`frontend/src/**`、`vite.config.ts`、`index.css`、`scripts/**`、`backend/**`、`docs/api/**`、`docs/product/**`、`docs/architecture/**`、`docs/database/**` **零 diff**（见 §4）。

---

## 1. 变更清单（唯一变更面：3 + 3 处字符串）

| # | 文件 | 段 | 键 | 前 | 后 |
| --- | --- | --- | --- | --- | --- |
| 1 | `frontend/package.json` | `dependencies` | `antd` | `^6.6.6` | `~6.6.6` |
| 2 | `frontend/package.json` | `devDependencies` | `@tailwindcss/vite` | `^4.3.3` | `~4.3.3` |
| 3 | `frontend/package.json` | `devDependencies` | `tailwindcss` | `^4.3.3` | `~4.3.3` |
| 4 | `frontend/package-lock.json` | `packages[""].dependencies` | `antd` | `^6.6.6` | `~6.6.6` |
| 5 | `frontend/package-lock.json` | `packages[""].devDependencies` | `@tailwindcss/vite` | `^4.3.3` | `~4.3.3` |
| 6 | `frontend/package-lock.json` | `packages[""].devDependencies` | `tailwindcss` | `^4.3.3` | `~4.3.3` |
| 7 | `docs/features/F040/architecture.md` | §7 锚点 | — | 占位行 | `npm ls` 原始输出（含 `npm --version` 与执行时间） |
| 8 | `docs/features/F040/implementation.md` | — | — | — | 本报告（新建） |
| 9 | `docs/features/F040/artifacts/**` | — | — | — | 12 个证据文件（新建，未跟踪） |

方法：**纯手工编辑**（`edit` 精确替换，三处在各文件内唯一，已先 `grep -n` 确认唯一性）。**未执行** `npm install` / `npm update` / `npm install --package-lock-only` / `npm pkg set`（architecture §1.7 第 3 条）；唯一安装命令为 `npm ci`。未新增/删除依赖（4 + 7 不变）、未升级、未新增 `overrides` / `resolutions` / `npm-shrinkwrap.json` / `.npmrc`。

---

## 2. 执行命令与真实输出（逐条，含 exit 码）

环境：`node v22.23.3`、`npm 10.9.9`、registry `https://registry.npmmirror.com/`（`npm ping` → `PONG "pong": true`）。

### 2.1 pre-state（`artifacts/pre-sha256.txt`、`pre-git-status.txt`、`exec-time.txt`）

```text
$ sha256sum package.json package-lock.json          # 2026-10-29T20:20:02+08:00
de893314ee9472576ed8a68b5a2e1590fbea06029dac6b54cf733084d53bf687  package.json
471d775c7c242c3dcb5896b60dc8fd0d06efdf592037546373b3a4c03aa5606a  package-lock.json

$ git status --porcelain
 M frontend/package-lock.json
 M frontend/package.json
?? docs/features/F040/artifacts/

$ node -e 'JSON.parse(require("fs").readFileSync("package-lock.json"));console.log("lockfile-json-ok")'
lockfile-json-ok                                    # exit=0
```

说明：`git status` 的 2 个 `M` 即本次实现声明内的两文件；`artifacts/` 为本次证据目录（architecture §1.7 第 6 条要求先 `mkdir -p`）。

### 2.2 `node_modules` 备份（仓库外）与干净 `npm ci`

```text
$ mv node_modules /tmp/f040-node_modules-backup-$TS
backup=/tmp/f040-node_modules-backup-1793276403     # 仓库外；备份前顶层 64 条目

$ npm ci
added 150 packages in 9s
12 packages are looking for funding
exit=0                                              # 20:20:12；无 EUSAGE / ERESOLVE
```

日志：`artifacts/npm-ci.log`。**`npm ci` 未重写 lockfile**（见 §2.5 pre/post sha256 完全一致）。

安装树对账（`artifacts/install-tree-reconciliation.txt`）：

```text
lock-entries(non-root): 221
installed(hidden .package-lock.json entries): 150
not-installed: 71 | all marked optional/os/cpu: true
```

`added 150 packages` 与 `node_modules/.package-lock.json` 的 150 条**不是**污染迹象：lockfile 221 条非根条目中有 71 条为平台专属 optional 依赖（`@esbuild/linux-*` 之外的 aix/android/darwin/freebsd/win32 变体、`@rollup/rollup-*` 他平台、`lightningcss-*` 他平台、`fsevents` 等），本机 linux-x64 不安装。此对账同时响应 D-F040-TD-03 的「隐藏 lockfile 150 vs 222」疑虑：历史 150 与本机平台过滤后的应装集合一致，真正异常是旧的 11 × `UNMET` 与 `node_modules/node_modules -> .` 自引用符号链接，本次 `npm ci` 已消除（§2.3）。

### 2.3 三项实装版本（`artifacts/npm-ls.txt`，原文已同步至 architecture.md §7）

```text
$ npm ls antd tailwindcss @tailwindcss/vite 2>&1 | tee ../docs/features/F040/artifacts/npm-ls.txt; echo "exit=${PIPESTATUS[0]}"
csm-frontend@0.1.0 /home/hanhao/github/47oo/csm/frontend
├─┬ @tailwindcss/vite@4.3.3
│ ├─┬ @tailwindcss/node@4.3.3
│ │ └── tailwindcss@4.3.3 deduped
│ └── tailwindcss@4.3.3 deduped
├── antd@6.6.6
└── tailwindcss@4.3.3

exit=0
```

- **三项实装版本**：`antd@6.6.6`、`tailwindcss@4.3.3`、`@tailwindcss/vite@4.3.3`（与 §1.2 设计基线一致，未升级）。
- `tailwindcss` **单一版本、无嵌套副本**（两处 `deduped` 指向同一顶层实例）→ R-2 检测项通过；`@tailwindcss/vite` 采用 `~4.3.3`，未被 npm 拉入第二份 `tailwindcss`。

顶层安装树健康度（`artifacts/npm-ls-depth0.txt`，A4 辅助证据，**不冒充** `npm ci` 证据）：

```text
$ npm ls --depth=0
├── @ant-design/icons@6.3.4   ├── @tailwindcss/vite@4.3.3  ├── @types/react-dom@18.3.7
├── @types/react@18.3.31      ├── @vitejs/plugin-react@4.7.0 ├── antd@6.6.6
├── react-dom@18.3.1          ├── react@18.3.1             ├── tailwindcss@4.3.3
├── typescript@5.9.3          └── vite@5.4.21
exit=0                          # 11 个顶层包（4 + 7）；无 UNMET / invalid / extraneous
```

### 2.4 A5 三命令（product A5）

| 命令 | 结果 | exit | 日志 |
| --- | --- | --- | --- |
| `npm run typecheck` | `tsc --noEmit` 无输出 | **0** | `artifacts/typecheck.log` |
| `npm run build` | `✓ 3215 modules transformed`；`dist/index.html 0.39 kB`、`dist/assets/index-D6T2dbJW.css 25.89 kB (gzip 6.17 kB)`、`dist/assets/index-yK5gyDbD.js 1,271.59 kB (gzip 388.89 kB)`；`✓ built in 15.72s` | **0** | `artifacts/build.log` |
| `npm run smoke:client` | 末行 `340 passed, 0 failed` | **0** | `artifacts/smoke.log` |

- **smoke 通过数 = 340**，等于 TD §1.6 基线 340（`failed = 0`，用例数未变 → `scripts/**` 零改动，A8 自洽）。
- chunk 体积警告（`> 500 kB`）按 product ON-5 / TD §1.7 **记录不判缺陷**；本 Feature 不改变包体，警告为既有状态。

### 2.5 post-state 与 lockfile 未被重写（E-08 口径）

```text
$ sha256sum package.json package-lock.json        # 20:20:53
de893314ee9472576ed8a68b5a2e1590fbea06029dac6b54cf733084d53bf687  package.json
471d775c7c242c3dcb5896b60dc8fd0d06efdf592037546373b3a4c03aa5606a  package-lock.json
sha256-pre-post-identical: YES (LOCK-UNCHANGED)

$ git status --porcelain
 M docs/features/F040/architecture.md
 M frontend/package-lock.json
 M frontend/package.json
?? docs/features/F040/artifacts/
```

- **pre/post sha256 完全一致**（两文件均一致）→ `npm ci` 只写 `node_modules/**`（含 gitignored 隐藏 lockfile），未重写受版本管理文件。Git 相对 pre-state 仅新增本次声明内的 `architecture.md`（§7）与未跟踪 `artifacts/`，`frontend/package*.json` 的 `M` 仍只是 §1 的 3 + 3 行变更（§3）。`dist/`、`node_modules/` 均被 `frontend/.gitignore` 命中（`git check-ignore -v` 输出 `frontend/.gitignore:2:dist/`、`:1:node_modules/`），未产生未跟踪产物。

---

## 3. 静态自检（`artifacts/static-selfcheck.txt`、`static-selfcheck-2.txt`）

```text
### numstat（期望各 3 3）
3	3	frontend/package-lock.json
3	3	frontend/package.json

### 与 start_commit adef87a 比较（同样各 3 3）
3	3	frontend/package-lock.json
3	3	frontend/package.json

### forbidden-paths-diffstat（必须空）
（空输出）

### 全仓 diff --stat adef87a（仅文档 + 两文件）
 docs/features/F038/review-report.md |  98 ++++++
 docs/features/F040/architecture.md  | 138 +++++++++
 docs/features/F040/product.md       |  75 +++++
 docs/features/F040/test-report.md   | 601 +++++++++++++++++++++
 docs/project/backlog.md             |   6 +-
 docs/project/milestones.md          |   4 +-
 docs/project/project-plan.yaml      |  72 +++--
 frontend/package-lock.json          |   6 +-
 frontend/package.json               |   6 +-
 (docs/ 部分均为本次之前已批准的 READY/签核产物，非本角色写入)
```

### 3.1 lockfile 三重判定（architecture §1.4）

```text
### 非根条目逐字节比对（基线 git show adef87a:frontend/package-lock.json）
non-root-entry-diffs: 0 []
added: [] removed: []
current  packages/resolved/integrity: 222 215 215
baseline packages/resolved/integrity: 222 215 215
root-entry-matches-package.json: true
lockfileVersion: 3 requires: true
three-targets: {"antd":"6.6.6","resolved":"https://registry.npmmirror.com/antd/-/antd-6.6.6.tgz","integrityOk":true,"tw":"4.3.3","twv":"4.3.3"}
```

- 判定 1（非根逐字节）**通过**：`non-root-entry-diffs: 0`、`added/removed = []`（`JSON.stringify` 逐条比较，覆盖 `version`/`resolved`/`integrity`）。
- 判定 2（规模不变）**通过**：`packages`/`resolved`/`integrity` = `222 / 215 / 215`（`packages` 计数含根键 `""`，即 `1 + 221`；见 §5 NOTE-1）。
- 判定 3（行级规模）**通过**：`numstat = 3 3`。
- 补充 **通过**：`resolved`/`integrity` 与基线逐字相同（非根 0 diff）、`lockfileVersion=3`、`requires=true`、根条目与 `package.json` 逐字一致（11 项双向同步，A3/S-02 前提）。
- `node -e 'JSON.parse(package-lock.json)'` → `lockfile-json-ok`（R-5 格式/语义检查）。

### 3.2 architecture.md §7 锚点（S-09 机检）

```text
$ sed -n '/F040-NPMLS-BEGIN/,/F040-NPMLS-END/p' architecture.md | <去围栏> | diff - artifacts/npm-ls.txt
anchor-verbatim-match: YES
```

锚点内容与 `artifacts/npm-ls.txt` **逐字一致**（含首行路径、树形符号、空行与 `exit=0`）；三行必需版本均在：`├── antd@6.6.6`、`└── tailwindcss@4.3.3`、`├─┬ @tailwindcss/vite@4.3.3`。同时记录 `npm --version = 10.9.9`、执行时间 `2026-10-29 20:20:14 +0800`。

---

## 4. 越界自查（零 diff 断言，实测）

`git diff --stat -- frontend/src frontend/vite.config.ts frontend/index.css frontend/scripts backend docs/api docs/product docs/architecture` → **空输出**（exit 0）。`docs/database/**` 同为零 diff（未被修改）。`frontend/.gitignore`、`frontend-ui-stack.md` 未被修改。无 `overrides` / `resolutions` / `npm-shrinkwrap.json` / `.npmrc` 新增。**唯一**由本角色改动的非证据文件为 `frontend/package.json`、`frontend/package-lock.json`、`docs/features/F040/architecture.md`（仅 §7 锚点）。

---

## 5. 观察与偏差记录（不阻塞，如实报告）

| ID | 观察 | 影响与处置 |
| --- | --- | --- |
| **NOTE-1** | architecture §1.4 与任务书述「222 个**非根**键」；实测 `packages` 键总数 222、**非根 221**（加根 `""`） | 纯称谓偏差（`222` 为含根计数，`resolved/integrity = 215/215` 一致）。逐条比对以实际 221 个非根键全覆盖执行，`non-root-entry-diffs: 0`。无需改文件；建议后续文档措辞写「`packages` 222 条（含根条目）」。 |
| **NOTE-2** | `npm ci` 报 `added 150 packages`，隐藏 lockfile 亦 150，而 lockfile 非根条目 221 | 差集 71 条**全部**带 `optional`/`os`/`cpu`（他平台 `@esbuild/*`、`@rollup/rollup-*`、`lightningcss-*`、`fsevents` 等），本机 linux-x64 按设计不安装 → 正常，非污染。已在 `artifacts/install-tree-reconciliation.txt` 留证。 |
| **NOTE-3** | D-F040-TD-03 记录的旧树异常（11 × `UNMET`、`node_modules/node_modules -> .`） | 干净 `npm ci` 后 `npm ls --depth=0` **exit 0**，无 `UNMET`/`invalid`/`extraneous`，顶层 11 包（4 + 7）。旧异常非 F040 引入、未记为缺陷；本 Feature 已顺带消除（仅写 `node_modules/**`，无版本管理影响）。 |
| **NOTE-4** | `build` 输出 chunk 体积警告 | 按 ON-5 / TD §1.7 记录不判缺陷（本 Feature 不改包体）。 |
| **NOTE-5** | `/tmp/f040-node_modules-backup-1793276403` 保留在仓库外 | 按 TD §1.5 Step 6 为可选清理项；保留以便复核，未写入仓库，不影响交付。 |

---

## 6. 风险实际观察（R-1..R-8）

| ID | 风险 | 本次实际观察 | 结论 |
| --- | --- | --- | --- |
| R-1 | lockfile 与声明不同步 → `npm ci` `EUSAGE` | 根条目 11 项与 `package.json` 逐字一致（`root-entry-matches-package.json: true`）；`npm ci` **exit 0**，日志无 `EUSAGE`/`ERESOLVE` | **未发生** |
| R-2 | `~` 允许补丁升级 / 嵌套 `tailwindcss` 副本 | 未执行任何 `npm install` 系命令；`npm ci` 后两文件 sha256 不变；`npm ls` 显示 `tailwindcss@4.3.3` 单一实例（2 × `deduped`），无嵌套目录 | **未发生** |
| R-3 | npmmirror 解析差异 | `npm ping` → `PONG`；`npm ci` 从 npmmirror 成功，`resolved` 全指向 npmmirror 且与基线逐字相同；未改 `resolved`/`.npmrc` | **未发生**（在线安装一次通过，无 `--offline` 变体） |
| R-4 | 旧 `node_modules` 污染造成假证据 | 旧树先 `mv` 到仓库外，再原地 `npm ci`；证据全部取自干净树；旧异常已在 NOTE-3 声明 | **未发生** |
| R-5 | 手工编辑 lockfile 破坏格式/语义 | JSON 解析通过；`non-root-entry-diffs: 0`、`added/removed=[]`、`numstat 3 3`、计数 `222/215/215`、`npm ci` 成功 | **未发生** |
| R-6 | 实现越界 | 变更行集合 = 6 行（3 + 3）；8 个未授权项仍为 `^` 原值（非根 0 diff 即证明）；`frontend/src` 等零 diff；无 `overrides` | **未发生** |
| R-7 | 证据链缺口（§7 未补 `npm ls`） | §7 已填，`diff` 机检 `anchor-verbatim-match: YES` | **未发生**（不判 BLOCKED） |
| R-8 | 把局部 PASS 写成整体验收 | 本报告只声明 F040 局部完成；变更集整体回归归 **F045**，未宣称整体验收通过 | **已规避** |

---

## 7. 验收条目落地情况（A1–A10，供 TEST 复核）

| A | 条目 | 本次落地证据 |
| --- | --- | --- |
| A1 | 三项收敛为 `~`（或精确） | `~6.6.6` / `~4.3.3` / `~4.3.3`（§1 表；`git diff` 6 行） |
| A2 | 与 `frontend-ui-stack.md` §1/§4 一致 | architecture §1.6 表格 + §7 `npm ls` 原文（§3.2） |
| A3 | lockfile 根条目同步、`npm ci` 可用 | `root-entry-matches-package.json: true`；`npm ci` exit 0 |
| A4 | 干净树三项实装版本正确 | `npm ls` → 6.6.6 / 4.3.3 / 4.3.3；`npm ls --depth=0` exit 0 无 UNMET |
| A5 | `typecheck` + `build` + `smoke:client` 全通过 | exit 0 / 0 / 0；smoke `340 passed, 0 failed` |
| A6 | 依赖数 4 / 7 不变（取实测，非「8」） | 顶层 11 包；根条目 `dependencies` 4 项、`devDependencies` 7 项，键集与基线相同 |
| A7 | 非根条目零变更（`version`/`resolved`/`integrity`） | `non-root-entry-diffs: 0`、`added/removed = []`、`222/215/215` |
| A8 | 源码/smoke 脚本零 diff | §4 越界自查空输出；smoke 用例数仍 340 |
| A9 | 无新增依赖清单文件/`overrides`/`.npmrc` | `git status` 仅 2 M + `artifacts/` |
| A10 | 变更面仅两文件 + 文档 | §1 变更清单 |

> 上述为**实现侧自证**，不替代 TEST 阶段 §2 的独立执行与判定（本报告不写「A 条目 PASS」结论，只提供证据位置）。

---

## 8. 技能使用与项目适配

- 读取并遵循 `.pi/skills/frontend-ui/SKILL.md` 的验证命令口径（`typecheck` / `build` / `smoke:client` 全跑的依据为 product A5，非冗余）。
- **未使用** `ui-ux-pro-max` 检索：本次为纯依赖声明范围变更，**零交互、零视觉、零布局、零文案**（product N8 / ON-6），属 addendum「纯 API/配置接线且呈现不变时不必设计检索」的同类情形，故无设计技能建议需要核对。
- 项目适配：遵守 architecture §1.7 硬边界（禁 `npm install` 系、禁改 `resolved`/`.npmrc`、备份在仓库外、证据落 `artifacts/**`）。

## 9. 共享组件 / Contract / Mock

- **共享组件影响**：无（未触碰 `frontend/src/**` 任何组件、主题、样式或 `index.css`）。
- **Contract 符合情况**：F040 CONTRACT = `NOT_REQUIRED`；`docs/api/**` 零 diff，12 维无变化，无 Mock/Fixture 新增或替换需求（`api_required=false`）。
- **Mock 位置**：不适用（无 Mock 引入、无真实 API 替换动作）。
- **待集成项**：无（依赖范围声明不产生集成面）；变更集整体回归与端到端集成证据由 **F045** 承接。

## 10. 未验证项

| 项 | 原因 | 状态 |
| --- | --- | --- |
| 浏览器 / 视觉 / 全页巡检（1440/1024/768/375） | product N8 + ON-6：无交互/视觉改动；仓库无 DOM/E2E 依赖，浏览器检查属环境侧未入库 | **NOT_REQUIRED**（不得写成「DOM 已验证」） |
| 真实前后端集成 | `api_required=false`，无请求面变化 | **NOT_REQUIRED**（整体归 F045） |
| 需求 §31–33 跨功能整体验收 | 不在 F040 范围 | **NOT_REQUIRED**（归 F045） |
| `npm ci --offline` 变体 | 在线安装一次成功（R-3 未发生） | 未执行（无必要） |
| `git commit` / 暂存 / 分支操作 | 按规则由协调器统一管理；本角色禁止 Git 写操作 | 未执行 |

---

## 11. 证据清单（`docs/features/F040/artifacts/`）

| 文件 | 内容 |
| --- | --- |
| `pre-sha256.txt` | 实现后、`npm ci` 前两文件 sha256 |
| `pre-git-status.txt` | `npm ci` 前 `git status --porcelain` |
| `npm-version.txt` / `exec-time.txt` | `npm --version = 10.9.9`；pre-state 时间戳 |
| `node-modules-backup.txt` | 仓库外备份路径 `/tmp/f040-node_modules-backup-1793276403` |
| `npm-ci.log` | `npm ci` 完整日志 + `exit=0` |
| `npm-ls.txt` | A4 主证据（原文，已同步 architecture §7） |
| `npm-ls-depth0.txt` | `npm ls --depth=0` 顶层健康度（辅助，不冒充 `npm ci`） |
| `install-tree-reconciliation.txt` | 221 / 150 / 71（71 全为 optional/平台专属）对账 |
| `typecheck.log` / `build.log` / `smoke.log` | A5 三命令日志，各含 `exit=0`；smoke `340 passed, 0 failed` |
| `post-sha256.txt` | post sha256 + `sha256-pre-post-identical: YES (LOCK-UNCHANGED)` |
| `post-git-status.txt` | `npm ci` 后 `git status --porcelain` |
| `static-selfcheck.txt` / `static-selfcheck-2.txt` | numstat 3 3、禁改路径空 diff、非根 0 diff、计数 222/215/215、adef87a 对比、`npm ping`、`git check-ignore` |

---

**结论：FRONTEND COMPLETE**（F040 依赖范围声明 + lockfile 根条目同步 + 干净 `npm ci` 取证完成；三项实装版本 6.6.6 / 4.3.3 / 4.3.3；A5 三命令 exit 0，smoke 340/0；无越界、无 Mock、无 Contract 影响；浏览器与整体验收按声明为 NOT_REQUIRED，归 F043/F045）

GIT: NONE
