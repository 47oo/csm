# F040 前端依赖版本范围与架构升级策略对齐（R07）— ARCHITECTURE 设计记录 + CONTRACT 最终签核

- **状态**：§1 ARCHITECTURE = `READY FOR DESIGN`；§2 CONTRACT = `NOT_REQUIRED`（判定成立）；§6 最终设计签核 = `READY FOR IMPLEMENTATION`（2026-10-29）
- **版本**：v1（2026-10-29）；ENABLER / P1 / M30；分支 `feature/F040-dependency-ranges`（交付线 `v3.4`，start_commit `adef87a43d9c73465c815fe85b2577d5dd17a1f2`）；plan revision 25；requirements revision 16
- **角色产物**：architect 只读产出，协调器持久化
- **上游依据**：AQ-6 = (i)（CONFIRMED：仅收敛 `antd` / `tailwindcss` / `@tailwindcss/vite` 为 `~` 并同步 lockfile，不改架构策略文档）；plan revision 25 F040（`kind: ENABLER`、`layers={database:false,backend:false,frontend:true}`、`api_required=false`、`depends_on: []`）；`docs/features/F040/product.md` v1（A1–A10、ON-1..ON-6）；`docs/features/F040/test-report.md` §1 TD-F040-1（28 用例；D-F040-TD-01..05、N-F040-TD-01..02；`npm ci` 方案；基线 smoke 340）；`docs/architecture/frontend-ui-stack.md` §1/§2/§4；requirements revision 16 §29 / §28 / §3；CHG-015 §2/§3 R07/§4 AQ-6/§5/§8
- **文件基线（只读核对）**：`frontend/package.json` = `dependencies` **4** 项 + `devDependencies` **7** 项（`tailwindcss`/`@tailwindcss/vite` 属 devDependencies）；`package-lock.json` `lockfileVersion=3`、`packages` 222 条（215 带 `resolved`+`integrity`）、`packages[""]` 与 `package.json` 逐字相同、三项安装版本 6.6.6 / 4.3.3 / 4.3.3；`@tailwindcss/vite@4.3.3` 以**精确版本**依赖 `tailwindcss: 4.3.3`；`vite.config.ts` 默认导入插件（无版本耦合代码）；`frontend/.gitignore` 含 `node_modules/`、`dist/`；全仓仅一个 `package.json`。

## 1. 设计结论

把**已批准架构策略**落实到声明范围：唯一变更面 = `package.json` 三处范围 + `package-lock.json` 的 `packages[""]` 同三处；零代码、零 Schema、零契约、零权限、零可观察业务行为变化。

### 1.1 ON-1 裁定：三项统一用 `~`（不用精确版本）

`~6.6.6` / `~4.3.3` / `~4.3.3`。理由：① plan revision 25 F040 `acceptance` 已写 `~`，精确版本会与之冲突并需改计划；② AQ-6=(i) 原文为「收敛为 `~`」，精确版本超出已批准选项字面；③ §4 允许集合正是同 minor 内补丁升级，`~x.y.z` 精确对应（拒绝 6.7.x / 4.4.x）；④ 可复现性由 lockfile 承担（§1「依赖通过 package.json 与 package-lock.json 固定」），无需靠精确范围；⑤ 与 product A1「`~` 或精确版本」相容。选 `~` 使 TD 的 S-12 自动 `NOT_APPLICABLE`、D-F040-TD-02 自愈。

### 1.2 ON-3 裁定：`@tailwindcss/vite` 与 `tailwindcss` 不作等号绑定

§1/§4 只约束同一区间 4.3.x，未要求两包同版本；按 AGENTS §2.2 不新增规则。上游包自身以精确版本依赖 `tailwindcss: 4.3.3`，联动由上游保证。若需更强联动须先扩写 §4（架构变更，不在 F040 范围）。

### 1.3 三项目标字符串（可直接粘贴）

```json
"dependencies": { "@ant-design/icons": "^6.3.4", "antd": "~6.6.6", "react": "^18.3.1", "react-dom": "^18.3.1" },
"devDependencies": { "@tailwindcss/vite": "~4.3.3", "@types/react": "^18.3.11", "@types/react-dom": "^18.3.1",
  "@vitejs/plugin-react": "^4.3.2", "tailwindcss": "~4.3.3", "typescript": "^5.6.3", "vite": "^5.4.9" }
```

| # | 段 | 键 | 前 | 后 |
| --- | --- | --- | --- | --- |
| 1 | dependencies | `antd` | `^6.6.6` | `~6.6.6` |
| 2 | devDependencies | `@tailwindcss/vite` | `^4.3.3` | `~4.3.3` |
| 3 | devDependencies | `tailwindcss` | `^4.3.3` | `~4.3.3` |

`package.json` 预期 diff = 恰好 6 条变更行（`git diff --numstat` = `3 3`）；`tailwindcss` 不得移入 `dependencies`（A6/A7）。

### 1.4 lockfile 根条目同步（A3 硬前置）与「其它包不变」判定

`packages[""].dependencies` / `packages[""].devDependencies` 三处必须与 §1.3 逐字一致（漏改 → `npm ci` 报 `EUSAGE`）。不得改写其它包条目的判定（三重，缺一不可）：

1. **非根条目逐字节等价**：以 `git show adef87a:frontend/package-lock.json` 为基线，对 222 个非根键逐条 `JSON.stringify` 比较，要求 `non-root-entry-diffs === []`（同时覆盖 `version` / `resolved` / `integrity`）。
2. **规模不变**：`packages` / 带 `resolved` / 带 `integrity` = `222 / 215 / 215`；`added === []` ∧ `removed === []`。
3. **行级规模**：`git diff --numstat -- frontend/package-lock.json` = `3 3`。
4. 补充：三项 `resolved` / `integrity` 与基线逐字相同；`lockfileVersion: 3` 与 `requires: true` 保持。

### 1.5 layers / api_required 复核

`layers.frontend=true`（变更落两个前端工程文件）、`database=false`（无 DDL；data-integrity 不适用）、`backend=false`（无后端/接口/镜像依赖）、`api_required=false`、`not_required.{database,backend,contract}` 均成立。

### 1.6 与 `frontend-ui-stack.md` §1/§4 的一行式符合性核对（A2 骨架）

| # | 依赖 | 实现后声明 | 策略条目 | 核查 |
| --- | --- | --- | --- | --- |
| 1 | `antd` | `~6.6.6`（dependencies） | §1「Ant Design 6.6.x」+ §4「仅 6.6.x 内升级」 | 一致：允集 `>=6.6.6 <6.7.0` ⊆ 6.6.x，拒绝 6.7.x；无 `^` |
| 2 | `tailwindcss` | `~4.3.3`（devDependencies） | §1「Tailwind CSS 4.3.x」+ §4「仅 4.3.x 内升级」 | 一致：允集 `>=4.3.3 <4.4.0` ⊆ 4.3.x；无 `^` |
| 3 | `@tailwindcss/vite` | `~4.3.3`（devDependencies） | §1「官方 @tailwindcss/vite 插件」+ 4.3.x | 一致：同一已批准区间；不作等号绑定；`vite.config.ts` 零 diff |

未被授权收敛的 8 项保持 `^` 原值（`react`、`react-dom`、`vite`、`typescript`、`@ant-design/icons`、`@types/react`、`@types/react-dom`、`@vitejs/plugin-react`）；`@ant-design/icons` 仍 `^6.3.4`（§4 未覆盖图标包，本次不收紧）。策略文档零 diff；AQ-6=(ii)/(iii) 未采纳。

### 1.7 实现硬边界

1. 只允许 `frontend/package.json` 与 `frontend/package-lock.json` 两文件（手工编辑，6 处字符串，其余字节不变）。
2. 零 diff 禁止：`frontend/src/**`、`vite.config.ts`、`index.css`、`scripts/**`、`backend/**`、`docs/api/**`、`docs/database/**`、`docs/product/**`、`frontend-ui-stack.md`、`frontend/.gitignore`、任何 `overrides`/`resolutions`/`npm-shrinkwrap.json`/`.npmrc`。
3. **禁止 `npm install` / `npm update` / `npm install --package-lock-only` / `npm pkg set`**（会重解析并改动 `version`/`resolved`/`integrity`，违反 A7）；安装只允许 `npm ci`。
4. 不得新增/删除依赖（4 + 7 不变，不得「补第 8 项」）、不得升级（三项安装版本仍 6.6.6 / 4.3.3 / 4.3.3）。
5. `node_modules/**`、`dist/**` 不入库；`npm ci` 不产生 Git 变更。
6. 证据落 `docs/features/F040/artifacts/**`（先 `mkdir -p`）；`npm ls` 原文写入本文 §7 锚点。

## 2. CONTRACT：`NOT_REQUIRED`

`docs/api/` 零 diff，不新建 `docs/api/F040.md`。12 维逐项无变化：端点/方法/路径、请求响应 Schema、错误码与 `details`、空态与 NotFound、认证与权限（含 §23.2）、分页排序过滤、软删可见性、IP 分配冲突、整批导入错误报告、409 版本冲突与审计、标识寻址、**前端行为契约**（组件事件/受控值/请求参数/权限门控/错误呈现零变化）。放宽为 `^` 或升级到 6.7.x / 4.4.x 属新变更，须走 AQ-6=(ii) 架构变更程序。

## 3. 与 TD-F040-1 一致性核对

A1–A10 与 28 条用例（S-01..S-12 / E-01..E-10 / D-01..D-06）逐条覆盖一致；每个 A 条目至少 1 条用例，无 UNMAPPED。

| TD 发现 | 裁定 |
| --- | --- |
| **D-F040-TD-01**（product A6 写 `devDependencies` 8 项） | **DR-F040-05**：A6 判据取实测 **4 / 7**；「8」为笔误，**禁止**通过新增依赖凑数；product.md 由 Product Manager 作编辑性更正（不改验收语义） |
| **D-F040-TD-03**（现有 `node_modules` 不可信：11×UNMET、隐藏 lockfile 150 vs 222、自引用符号链接） | 接受：**A4/A5 证据必须取自干净 `npm ci` 树**；既有异常非 F040 引入、不记为缺陷；干净树仍报 `UNMET`/`extraneous` 则按 A4 FAIL 另立 |
| **D-F040-TD-05**（S-03 判定式把 scoped 包名按 `.` 切分 → 任何正确实现都假 FAIL） | **必须修复（口径修正）**：路径用 `/` 拼接并保留完整 scoped 名，白名单为完整路径 `dependencies/antd`、`devDependencies/tailwindcss`、`devDependencies/@tailwindcss/vite`；判定 `bad === []` ∧ `allowed-diff` 恰为上述 3 条 ∧ 计数 4/7 |
| TD §1.7 编号 `D-10` → 应为 `D-01b` | NOTE：TEST 前更正 |
| `semver` 可用性（传递依赖提供） | NOTE：TEST 前 `require.resolve('semver')` 探测，缺失则用等价正则判定（不得跳过 D 层） |
| `tee` 到 `docs/features/F040/artifacts/**` | NOTE：先 `mkdir -p` |

TD 的「**不得用 `npm ls` 冒充 `npm ci`**」降级规则**有效且保留**（`npm ls` 只读磁盘树，无法证明 lockfile 自洽）。

## 4. Database / Frontend 影响

Database `NOT_REQUIRED`（无 DDL / Migration / 索引 / 数据行为；`docs/database/**` 零 diff；data-integrity 启用条件不成立）。Frontend 仅两文件 + 本文 §7 锚点补入 `npm ls` 原文。

## 5. 风险

| ID | 风险 | 级别 | 检测 |
| --- | --- | --- | --- |
| R-1 | lockfile 与声明不同步 → `npm ci` `EUSAGE` | HIGH | S-02（11 项双向一致，先于 `npm ci`）、E-01（隔离目录 exit 0 且无 `EUSAGE`/`ERESOLVE`）、`npm ci` 前 pre-state（`sha256sum` + `git status`） |
| R-2 | `~` 仍允许补丁升级：若用 `npm install` 解析可能与 `@tailwindcss/vite@4.3.3` 的**精确** `tailwindcss: 4.3.3` 产生嵌套副本，并改动三项 `resolved`/`integrity` | MEDIUM | 禁 `npm install` 系命令；E-08（`npm ci` 后两文件 sha256 不变 + `git status` 0 行）；D-04；`npm ls tailwindcss --all` 单一 4.3.3 且无嵌套目录 |
| R-3 | npmmirror 与官方 registry 解析差异（lockfile `resolved` 全指向 npmmirror） | MEDIUM | 记录 `npm config get registry` 与失败 URL、`npm ping`；不可达则 `NOT TESTED`/`--offline` 变体并标注；**禁止**改 `resolved` / `.npmrc` |
| R-4 | 现有 `node_modules` 污染造成假证据 | MEDIUM | 必须原地 `npm ci`（备份到仓库外）后的树取证；E-03 无 `UNMET`/`invalid`/`extraneous`；报告声明既有异常非交付物 |
| R-5 | 手工编辑 lockfile 破坏格式/语义（误改相邻条目、漏改 devDependencies 位置） | MEDIUM | `node -e 'require("./package-lock.json")'` + S-05 全条目逐字节比对 + `numstat 3 3` + 计数 222/215/215 + `npm ci` 成功 |
| R-6 | 实现越界（顺带收敛其它库 / 新增 overrides） | HIGH | S-04（diff 行集合 ⊆ 6 行）、D-06（8 项仍 `^` 且等于基线）、S-06、S-10 白名单 |
| R-7 | 证据链缺口（§7 未补 `npm ls` 或拿旧树输出顶替） | MEDIUM | S-09 填后校验三行与 `artifacts/npm-ls.txt` 逐字一致；未填前判 `BLOCKED` 而非 PASS |
| R-8 | 把局部 PASS 写成整体验收 | LOW | 禁止「变更集验收通过」表述；整体归 F045 |

## 6. 最终设计签核（CONTRACT Gate）

```text
签核：Architect；日期 2026-10-29；对象：architecture.md v1（§1 READY FOR DESIGN、§2 NOT_REQUIRED、§6 最终签核）。
上游依据：AQ-6=(i)（CONFIRMED）；requirements revision 16 §29/§28/§3；frontend-ui-stack.md §1/§4；CHG-015 §2/§3/§4/§5/§8；plan revision 25 F040；F040 product.md v1；F040 test-report.md §1 TD-F040-1。
定稿核对：TD-F040-1 覆盖 A1–A10（28 用例）逐条一致；裁定 D-F040-TD-01（判据 4/7）、D-F040-TD-03（证据取自干净 npm ci 树）、D-F040-TD-05（S-03 判定式修正为完整路径白名单）；TD 降级规则保留；ON-1 选 ~ 使 S-12 NOT_APPLICABLE、D-F040-TD-02 自愈；Database NOT_REQUIRED；契约 NOT_REQUIRED（12 维无变化）；需求/领域零影响。
覆盖：F040 仅此一项（不覆盖 F041/F043/F045）。放行写入：frontend/package.json、frontend/package-lock.json、docs/features/F040/**（architecture §7 锚点、implementation、test-report §2、artifacts）；docs/project/** 由协调器维护。
零 diff 禁止：frontend/src/**、vite.config.ts、index.css、scripts/**、backend/**、docs/api/**、docs/database/**、docs/product/**、frontend-ui-stack.md、frontend/.gitignore、任何新增依赖清单文件、F001–F039 历史证据。
结论：READY FOR IMPLEMENTATION。
```

## 7. `npm ls` 原始输出（锚点，待 Frontend 在干净 `npm ci` 后补入）

> 填写规则：E-02 完成后执行 `cd frontend && npm ls antd tailwindcss @tailwindcss/vite 2>&1 | tee ../docs/features/F040/artifacts/npm-ls.txt; echo "exit=${PIPESTATUS[0]}"`，把**完整原始输出逐字粘贴**到下方锚点之间（含首行路径、树形符号与 `exit=`），不得改写或节选；同时记录 `npm --version` 与执行时间。

<!-- F040-NPMLS-BEGIN -->
（待 Frontend 粘贴；未填前 S-09 判 BLOCKED）
<!-- F040-NPMLS-END -->

**A2 复核（填后生效）**：粘贴内容须含 `antd@6.6.6`、`tailwindcss@4.3.3`、`@tailwindcss/vite@4.3.3` 三行，且与 `artifacts/npm-ls.txt` 逐字一致。
