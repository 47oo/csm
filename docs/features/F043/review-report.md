# F043 前端交互回归可重复入口与 smoke 拆分（R08）— REVIEW 报告

- **结论**：**APPROVED WITH FOLLOW-UP**（无 BLOCKER / HIGH / 必须修复 MEDIUM；无未决产品问题）
- **候选 HEAD**：`0e34190`；**Base**：`refs/heads/v3.4` = `8eec63b9af897167fc448dce222a175b6852188f`（= start_commit = merge-base）
- **版本**：v1（2026-10-29，正式 Review，独立复核；reviewer 只读产出、协调器持久化）
- **范围**：26 文件（F043 docs 10、计划派生视图 3、`frontend/scripts/**` 12、`package.json` 1）；工作区 clean

## 1. 逐条结论

| # | 项 | 结论 | 关键证据 |
| --- | --- | --- | --- |
| 1 | 范围 | PASS | `frontend/src/**`、`package-lock.json`、`backend/**`、`docs/api/**`、`docs/product/**`、`docs/database/**` 实测空 diff；`package.json` numstat `1 0`，唯一新增 `test:interactions` 行（合 I-1） |
| 2 | A4（独立复跑） | PASS | `/tmp/f043_base`（`git archive` 基线）输出 354 行 vs 候选 354 行 `cmp` **BYTE-IDENTICAL**，均 `352 passed, 0 failed`；`await test(` 352=352；用例名 352/352 逐条相同；diff 仅 3 hunk（+14/−43），被删 2 行 `assert` 即 `expectApiError` 函数体逐行移入 harness |
| 3 | A1–A3 | PASS | `npm run test:interactions` 14 passed/0 failed，连跑 2 次一致；映射 C01–C03→①、C04–C05→②、C06–C07(+C08)→③、C09–C10(+C11)→④、C12–C13(+C14)→⑤；Reviewer 自建突变证明非平凡（`CANDIDATE_PAGE_SIZE` 100→50 → C01/C02 FAIL；C12 双击断言 1→2 → FAIL；`current_version` 7→8 → C06/C07 FAIL；删/改名/`test.skip` → `caseAudit` exit 1）；对 v3.4 原文件跑 `caseAudit` exit 0（台账真实） |
| 4 | S 静态边界 | PASS | C08/C11/C14 名带 `[S-STATIC]`、仅文本模式、不绑行号、只读 `src`，未计入 A3 可观察量；X4（`App.tsx`）三份文档一致标 `NOT TESTED`，无处记为 PASS |
| 5 | 侧信道 | PASS | `scripts/**` 无 `react|react-dom|antd|esbuild`、无 `playwright|puppeteer|chromium|webdriver|jsdom`、无外部主机；import 仅 `node:` 内建 + 无 JSX 的 `src/*.ts`；`lib/` 无 `process.exit`、无顶层副作用；台账仅覆盖 `smoke-client.mjs` |
| 6 | 文档一致性 | PASS（差异已披露） | 354 行 ✓；`reset()` 2 处 ✓（`ConfirmDialog.tsx:59/74`）；X2 载体 8 ✓（9 文件定义、8 文件接线）；digest 差异根因查明（TD 正则截断含引号用例名，`caseAudit` 用真实字面量解析器得 `4d43366f`，实现值正确） |

## 2. 缺陷与跟进

无必须修复项。**F043-RV-1 NOTE**（architecture §4/§5 文本与实测不符：digest 前缀、`reset()` 次数）→ Architect；**F043-RV-2 LOW**（`execution.next_action` 与 `head_commit` 记账）→ 协调器，已在状态提交处理；**F043-RV-3 LOW**（test-report §2 记 artifacts「18 文件」实为 19，TD 引用文件名与实际不对应）→ 已在状态提交按事实勘误；**F043-RV-4 NOTE**（C14 固定 `reset()` 次数，源重构即失败）与 **F043-RV-5 NOTE**（product A9 字面严于实施，已批准 plan acceptance 支持 I-1）均非阻塞。

**FOLLOW-UP**：TN-4（给 `caseAudit` 增加 npm 门禁，需 Architect 放宽 I-1）；Architect 订正 architecture §4/§5；product 措辞后续同步。

## 3. 未审查项

`npm run build` 未复跑（`scripts` 不进构建产物、`src` 零 diff；`typecheck` 已复核 exit 0）；浏览器/DOM 真实行为、真实 ≥101 对象落库与服务端 409 真路径 = **NOT TESTED**（由 F041 I 层与 F045 整体验收承担）；重复性仅 2 次抽样。

## 4. 声明

可进入 Merge Gate（APPROVED WITH FOLLOW-UP）。批准仅对候选 HEAD `0e34190` 与 Base `8eec63b` 有效；任一变化须重新验证与 Review。Merge 与 DONE 由协调器按 Git Workflow §5 判定。
