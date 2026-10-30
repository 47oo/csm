# F040 前端依赖版本范围与架构升级策略对齐（R07）— REVIEW 报告

- **结论**：**APPROVED WITH FOLLOW-UP**（无 BLOCKER / HIGH / 阻塞合并的必须修复 MEDIUM）
- **候选 HEAD**：`eb02b0b88e7aa1c69e9ffef84e6add2d86f398dd`；**Base**：`refs/heads/v3.4` = `abd097deb0905b8733caa830ac213173a313651f`
- **版本**：v1（2026-10-29，正式 Review，独立复核，reviewer 只读产出、协调器持久化）
- **范围**：`git diff --stat refs/heads/v3.4...HEAD` = 40 文件 / +1790 −34；4 提交（`7754c67`、`109b61d`、`32d05fe`、`eb02b0b`）；工作区 clean；`validate_project_state.py --feature F040` 与 `render_project_views.py` 通过
- **基线偏差说明（OBS-1）**：plan 记录 `start_commit=adef87a`（F038 merge 点）与真实分支起点 `abd097d` 不符（F-05）；审查与批准以 `refs/heads/v3.4`=`abd097d` 与三点式范围为基线，`adef87a..HEAD` 多出的 `docs/features/F038/review-report.md` 属 F038 交付，不计入 F040 范围

## 1. 独立执行（全部自跑，未复用报告数值）

| 项 | 实测 |
| --- | --- |
| `npm ci`（隔离目录 `/tmp/rv-f040-ci`） | exit 0，`added 150 packages`，无 `ERESOLVE`/`EUSAGE`；两文件 sha256 与仓库一致（`de893314…` / `471d775c…`）⇒ 未重写 lockfile |
| `npm ls antd tailwindcss @tailwindcss/vite` | `antd@6.6.6`、`tailwindcss@4.3.3`、`@tailwindcss/vite@4.3.3`，exit 0；`--depth=0` 11 包无 `UNMET`/`extraneous`；磁盘仅 1 份 `tailwindcss`（deduped） |
| `npm run typecheck` / `build` / `smoke:client` | 0 / 0（`✓ 3215 modules`、`index-yK5gyDbD.js 1,271.59 kB`）/ 0（**340 passed, 0 failed**） |
| lockfile 三重判定 | 非根 **221** 条逐字节等价、`added/removed = []`、`222/215/215`、`numstat 3 3`、`lockfileVersion 3`/`requires true` 不变；三项 `resolved`/`integrity` 逐字同基线 |
| `package.json` | `numstat 3 3`；`dependencies=4` / `devDependencies=7`；8 项未授权依赖仍 `^` 且逐字等于基线 |
| 禁改路径 | `frontend/src`、`vite.config.ts`、`index.css`、`scripts`、`backend`、`docs/api`、`docs/database`、`docs/product`、`docs/architecture`、`frontend/.gitignore` **全部零 diff** |
| §7 锚点 | 与 `artifacts/npm-ls.txt` **逐字节相同**，且与本次实跑输出逐字一致（仅首行路径不同）⇒ 为实测原文而非示例 |

## 2. A1–A10 结论

**全部 PASS**：A1 三项 `~` 形式一致无 `^`；A2 与 `frontend-ui-stack.md` §1/§4 逐项一致（`~6.6.6 ⇒ >=6.6.6 <6.7.0 ⊆ 6.6.x`、`~4.3.3 ⇒ <4.4.0 ⊆ 4.3.x`）；A3/A4/A5 见 §1；A6 计数 4/7 且除三项外零 diff；A7 无新增/删除且其它包三字段不变；A8 源码零 diff；A9 策略/产品/API/数据库/后端零 diff；A10 变更文件 ⊆ 白名单。

## 3. R-1..R-8

R-1/R-3/R-4/R-5/R-6/R-7 **未发生且检测有效**；R-2（`~` 允许补丁升级 + `@tailwindcss/vite` 精确钉 `tailwindcss: 4.3.3` 的潜在嵌套副本）本变更集未发生（单一实例、无嵌套目录），长期仅由「禁 `npm install` 系」过程约束防护 → F-08（NOTE）；R-8 已规避（全库无「变更集验收通过」类夸大表述；`~` 的可复现性明确归属 lockfile）。

## 4. TD 修正核验

- **D-F040-TD-05** 已落实：S-03 用 `/` 拼接 + 完整路径白名单（`dependencies/antd`、`devDependencies/tailwindcss`、`devDependencies/@tailwindcss/vite`），判定 `bad===[]` ∧ 恰 3 条 ∧ 计数 4/7。
- **严格强于旧式**：独立变异测试——`antd` 从 `dependencies` 移到 `devDependencies` 时旧式 `bad=[]`（漏判），新式捕获 `devDependencies/antd`。
- **D-F040-TE-01 属实**：`@tailwindcss/vite` 名内无 `.`，旧式在本变更集不产生假 FAIL；真实缺陷为路径特异性不足。已记录，不影响 A6 结论（A6 由更强判定式通过，并以 `git diff` 全文 + 键集 + 变异测试独立复核）。

## 5. 缺陷与跟进

**无必须修复项（无 BLOCKER / HIGH / 阻塞合并的 MEDIUM）。**

| ID | 级别 | 内容 | Owner | 必须修复 | 阻塞合并 |
| --- | --- | --- | --- | --- | --- |
| F-01 | MEDIUM | `product.md` A6 仍写 `devDependencies` 8 项（架构签核 DR-F040-05 与实测均为 7）；D-F040-TD-01 的 PM 编辑性更正未执行 | Product Manager + 协调器 | 是（文档） | 否（plan `acceptance` 不引用该计数；A6 判据已按 4/7 执行并复核） |
| F-02 | MEDIUM | 8 个 `.log` 证据被根 `.gitignore:124 *.log` 命中未入库，而报告将其列为证据路径（F028–F038 有 81 个已跟踪 `.log`，非有意策略） | 协调器 | 是（证据卫生） | 否（内容可随时重跑，Review 已独立复现 A3–A5） |
| F-03 | LOW | TD-05 理由措辞与同文 §2.7 `D-F040-TE-01` 矛盾（「scoped 名被 `.` 切碎 → 必然假 FAIL」应为「路径特异性不足」） | Architect / Tester | 否 | 否 |
| F-04 | LOW | architecture 「222 个非根键」应为「222 含根 / 221 非根」；§7 标题仍写「待补入」 | Architect | 否 | 否 |
| F-05 | LOW | plan `git.start_commit` 记为 `adef87a`（F038 merge 点），真实分支起点为 `abd097d` | 协调器 | 否 | 否 |
| F-06 | NOTE | `implementation.md` 「已顺带消除既有 `node_modules` 异常」措辞易被读成交付成果（test-report E-04 已正确标注不计交付物） | Frontend | 否 | 否 |
| F-07 | NOTE | TD 证据落点名与实际落盘名不一致，追溯需人工映射 | Tester | 否 | 否 |
| F-08 | NOTE | 未来 `npm install` 可能因上游精确钉版本产生嵌套 `tailwindcss` 副本；本变更集未发生 | 未来依赖升级 Feature | 否 | 否 |

**旧缺陷复核**：D-F040-TD-02/03/04、N-F040-TD-01/02、D-F040-TE-01、OBS-1..4 **全部关闭**（判定准确）；D-F040-TD-01 **部分闭合**（判据已按 4/7 执行，product 正文数字未改 → F-01）；D-F040-TD-05 **闭合且严格强于旧式**（理由措辞残留 → F-03）。实现层无缺陷。

## 6. FOLLOW-UP（均不阻塞合并）

| FU | 内容 | Owner |
| --- | --- | --- |
| FU-1（F-01） | product.md A6 计数改为实测 4 / 7，或标注以 DR-F040-05 为准 | Product Manager + 协调器 |
| FU-2（F-02） | 补齐 8 个 `.log` 证据（`git add -f` 或关键行落为 `.txt`），使证据路径可追溯 | 协调器 |
| FU-3（F-03/04/06） | 统一 TD-05 理由表述；修正「222 非根」与 §7 标题；implementation「顺带消除」改为「环境副作用，非交付物」 | Architect / Tester / Frontend |
| FU-4（F-05） | DONE 状态提交中把 `git.start_commit` 更正为 `abd097d`（或加注 `adef87a` 为 F038 merge 点），后续 Feature 取 preflight 提交 | 协调器 |
| FU-5（F-08） | 后续依赖升级 Feature 中 `tailwindcss` 与 `@tailwindcss/vite` 同补丁一起升级，避免嵌套副本 | 未来 Feature Owner |

## 7. 未审查项

未核验他人工具调用记录（改为对 artifacts 独立重算/重跑）；旧 `node_modules` 历史异常现场已被 `npm ci` 覆盖（无法回溯，仅确认现状健康）；未验证 registry 长期可用性与 `--offline` 变体；未验证非 linux-x64 平台 71 条 optional 条目的安装行为；浏览器/视觉/全页巡检、真实前后端集成、§31–33 整体验收 **NOT_REQUIRED**（归 F045）；F041/F043/F045 超出签核边界。

**本次 Review 的环境副作用（非 Git 变更）**：`/tmp/rv-f040-ci` 隔离 `npm ci`；`frontend/` 内 `typecheck`/`build`/`smoke:client`（`build` 重写被 gitignore 的 `frontend/dist/`）。操作前后 `git status --porcelain -uall` 均为空。

## 8. 声明

- 结论 **APPROVED WITH FOLLOW-UP**：核心验收 A1–A10 全部满足，必要验证经独立复现；无 BLOCKER / HIGH / 阻塞合并的必须修复 MEDIUM；无未决产品问题（AQ-6 已 CONFIRMED，`pending_changes=[]`）。
- **可进入 Merge Gate**，条件：候选 HEAD 仍 `eb02b0b`、Base 仍 `refs/heads/v3.4`=`abd097d`、工作区 clean、写入者结束。
- 若合并前执行 FU-1/FU-2（新增文档/证据提交），新 HEAD 超出本批准，需对该增量做限定复核；两实现文件 sha256 不变即可作为实现层批准不变的依据。
- 批准仅对上述候选 HEAD 与 Base 有效；基线、需求版本或 plan 批准变化须重新审查。
- 建议（F-03/04/06/08）不构成产品或架构决定，不改变任何验收门槛。
