# F043 前端交互回归可重复入口与 smoke 拆分（R08）— ARCHITECTURE + CONTRACT

- **状态**：`READY FOR IMPLEMENTATION`（Architect 签核，2026-10-29）
- **版本**：ARCH-F043-1 v1；ENABLER / P2 / M30；`layers`={database:false, backend:false, frontend:false}；`api_required=false`
- **分支 / 基线**：`feature/F043-test-entry`；start_commit `8eec63b`；plan rev25 / requirements rev16
- **Basis**：`F043/product.md` v1（A1–A10、§3 五类交互、N1–N8、ON-1..7）；`F043/test-report.md` §1（TD-F043-1：C01–C14 / X1–X4 / I-1..I-4）；只读核对 `scripts/smoke-client.mjs`（9,718 行 / 352 `await test(`）、`src/api/client.ts`、`src/components/{candidateSelectModel,confirmDialogState,importCarrier,importForm}.ts`、`src/components/ui/ConfirmDialog.tsx`、`src/components/ResourceImportPanel.tsx`、`package.json`

## 1. 方案摘要

- 交付**测试基础设施**：抽 `frontend/scripts/lib/` 共享原语层（首个「逐步拆分」步骤），新建 `frontend/scripts/interaction/` 五个交互族 + `scripts/test-interactions.mjs` runner，入口 `npm run test:interactions`。
- **不拆 352 个既有 smoke 用例**：本次只把「登记器 / fetch 桩 / 计数 / report」抽到 `lib/`，`smoke-client.mjs` 改为 import 之，用例体与顺序不动 ⇒ A4/A6 天然成立。
- 零新增依赖：node v22.23.3 type stripping 加载无 JSX 的 `src/**/*.ts`；入口链**不得 import** `react`/`react-dom`/`antd`/`esbuild`（`node_modules` 缺失时仍可执行，缓解 R4）。
- 五类交互全部落在 **P（纯逻辑）/ R（fetch 桩请求层）/ S（静态结构）** 三层，无 `.tsx` 执行依赖；`frontend/src/**` 零 diff。

## 2. I-1 裁定（`npm run <name>` vs A9 零 diff）

放行 `frontend/package.json` **仅新增 `scripts` 一行**：

1. 允许 `"test:interactions": "node scripts/test-interactions.mjs"`（唯一新增行）。
2. 禁止改/删既有 `dev|build|preview|typecheck|smoke:client`，禁止改 `name`/`private`/`version`/`type`。
3. `dependencies`/`devDependencies` **零 diff**；`frontend/package-lock.json` **零 diff**（lockfile v3 不记 `scripts`）。
4. A9 口径 = 「无新增依赖」，由 `F043-S07` 断言：lock 无条目 + `git diff -U0 -- frontend/package.json` 变更行数 == 1 且匹配 `^\+\s+"test:interactions":\s+"node scripts/test-interactions\.mjs",?$`。
5. A5 放行清单收录该行；不放宽 `frontend/src/**` 零 diff。

## 3. 模块结构（ON-1 / ON-6）

| 文件 | 职责 | 硬约束 |
| --- | --- | --- |
| `scripts/lib/harness.mjs` | `createHarness({label})` → `{test, calls, setRespond, handlerCalls, jsonResponse, expectApiError, restore}`：安装/还原 `globalThis.fetch`、`calls[]` 计数、`test()` 前清计数 | `test()` 打印体与原 `smoke-client.mjs` **逐字节等价**（`PASS: ${label}${name}`）；smoke 传 `label=""` |
| `scripts/lib/report.mjs` | `report({passed,failed})` 打印 `\n${passed} passed, ${failed} failed` 并**返回退出码** | **不得 `process.exit`**（否则重现 ON-1 阻断） |
| `scripts/lib/caseAudit.mjs` + `case-ledger.json` | 防静默删除审计（§4） | 只读被测文件 |
| `scripts/smoke-client.mjs` | 仅替换原语（fetch 安装、`calls`、`jsonResponse`、`expectApiError`、`test`、`report`）；`setUnauthorizedHandler` 与用例体不动 | 输出与拆分前**逐字节一致**（352 `PASS:` 行、358 行、`352 passed, 0 failed`） |
| `scripts/interaction/{candidate,auth,conflict,importCarrier,dangerousAction,tsxBoundary.static}.mjs` | 交互族；各导出 `default function register(h)`，内部 `await h.test(...)` | 只读 `src/**` |
| `scripts/test-interactions.mjs` | runner：`createHarness({label:"F043 "})` → 固定顺序 `register(h)` → `restore()` → `process.exit(report(...))` | 固定顺序、无并发、无时序依赖（A1） |

**I-2**：不把 `smoke-client.mjs` 重构为可 import 的 `run()`（runner 不 import 它），`process.exit` 只存在入口脚本层；`lib/` 三文件无顶层副作用、无 `process.exit`。

## 4. 拆分粒度与防静默删除（ON-2 / ON-3）

- **粒度**：`lib` 原语层 + 5 个交互族（+1 静态族）；不按 24 个域拆 352 用例（超范围且提高 A4 漂移风险）。
- **主判据 `F043-S02`**（`caseAudit.mjs`）：① 逐文件计数白名单 `{"scripts/smoke-client.mjs": 352}` 必须相等且总和 = 352；② 名称摘要 `sha256(顺序连接)` 等于 baseline 快照（采集于拆分前，前缀 `b3f230b7`），且「基线名称集合 ⊆ 新集合」；③ skip/停用扫描（`test.skip|xit(|describe.skip`、`// await test(`、块注释内 `await test(`）命中 0。
- 台账范围**仅** `scripts/smoke-client.mjs`；交互族不进台账（总数由 runner 打印，期望 14 = C01..C14）。
- baseline 生成：实现首步（改任何文件前）跑 `node scripts/lib/caseAudit.mjs --emit` 落 `case-ledger.json` 并提交，此后只读。

## 5. X1–X4 的 `.tsx` 边界处置（ON-4 / I-4）

**否决**：(a) 抽纯谓词需改 `frontend/src/**`（A5 禁止）；(b) `react-dom/server` 渲染 `.tsx` 需 transform，唯一可用加载器 `esbuild` 是 vite 传递依赖，**明令不得直接使用** ⇒ 本 Feature 使用 `react-dom/server` 的项数 = **0**（不可达，非降级）。

| # | 处置 | 实现与断言 |
| --- | --- | --- |
| X1（C14 ConfirmDialog 接线） | S 层静态结构 | `ui/ConfirmDialog.tsx` 源文本含 `maskClosable={!confirmLoading}`、`keyboard={!confirmLoading}`、`disabled: confirmLoading`、`danger`、`guardRef.current.tryBegin()`/`reset()`/`settle()` 各恰 1 次；不断言行号 |
| X2（C08 409 后刷新接线） | S 层静态结构 | 载体源文本含 `function refreshAfterConflict()` 且 `onRefresh={refreshAfterConflict}`，命中载体 ≥8（按**文本模式**，不断言行号） |
| X3（C11 单资源导入 `canConfirm`） | S 层静态结构 | `ResourceImportPanel.tsx` 含 `validatedKey !== null`、`validatedKey === currentKey`、`error_count === 0`、`importState.kind !== "success"`、`if (busy || !canConfirm)` |
| X4（`App.tsx` 处理器注册点） | **NOT TESTED** | `handlerCalls` 已在 client 层覆盖「只清一次」；如实标注，不计 PASS、不计缺口 |

**为何不影响 A2/A3**：A3 的「可观察量」由 ⑤ 的 C12/C13、③ 的 C06/C07 在 P/R 层给出正负例；X1–X3 为附加结构证据，**不得计入 A3 的可观察量列**。

## 6. 五类交互断点表（C01–C14，零新增依赖）

| ID | 交互 | 层 | 正/负 | 判定式 |
| --- | --- | --- | --- | --- |
| C01 | ① | P | 正 | 查询对象 `page=1`、`page_size=100`、`type=BARE_METAL`、`cluster_id=c1`、`q=bm`；`truncated===true` 且文案含总数与 100；`options` 中第 101 位 id **恰 1 次**、label 不退化 |
| C02 | ① | R | 正 | `calls.length===1`；`calls[0].url` 同时含 `page=1`/`page_size=100`/`type=BARE_METAL`/`cluster_id=c1` |
| C03 | ① | R | 负 | `calls.length===1`；URL 不含 `page≥2`、`page_size≥100+`、`include=`/`only=`/`deleted=` |
| C04 | ② | R | 正 | `calls.length===2 && handlerCalls===1`；首错 `isApiError && status===401 && code==="AUTH_REQUIRED"` 未被吞；第 2 次 200 |
| C05 | ② | R | 负 | 单次 401：`calls.length===1 && handlerCalls===1`（无自动重试） |
| C06 | ③ | R | 正 | `versionConflict===true && currentVersion===7`；刷新后 `calls.length===3`；`JSON.parse(calls[2].init.body).version===7` |
| C07 | ③ | R | 负 | 409 后 `calls.length===1`；旧 version 重提仍 409 且 `handlerCalls===0` |
| C08 | ③ | S | 负 | §5 X2 静态结构（≥8 载体接线） |
| C09 | ④ | P | 正 | `patch(values,"text")` = `{carrier:"text",format:"csv"}`；切回 `{carrier:"file",format:"csv",file:null}`；两载体 `importTargetKey` 不相等且非 null |
| C10 | ④ | P/R | 负 | 切换后 `validatedKey!==currentKey`；`canConfirm…===false`；未「校验/确认」前 `calls.length===0` |
| C11 | ④ | S | 负 | §5 X3 静态结构 |
| C12 | ⑤ | P/R | 正 | `tryBegin()===true` → `calls.length===1`；第二次 `tryBegin()===false` → 仍 1 |
| C13 | ⑤ | P/R | 负 | `tryBegin()→reset()`：`isInFlight()===false && calls.length===0` |
| C14 | ⑤ | S | 负 | §5 X1 静态结构 |

可观察量仅限请求次数 / URL / payload / 状态机输出 / 文案谓词；禁词 `正常|正确|符合预期`（`F043-S01b`）。

## 7. Domain / Data Impact、实施层、Contract

- Domain/Data：无（`layers.database=false`，Database `NOT_REQUIRED`）。Backend `NOT_REQUIRED`；`backend/**`、`docs/api/**`、`docs/product/**`、`docs/database/**` 零 diff。
- Frontend Work：仅测试资产（`scripts/lib/**`、`scripts/interaction/**`、`scripts/test-interactions.mjs`、`smoke-client.mjs` 原语替换）；产品语义零 diff。
- Contract：`NOT_REQUIRED`（无 Endpoint/参数/Schema/错误语义变更）。
- **放行写入（A5 清单）**：① `frontend/scripts/**`；② `frontend/package.json`（仅 §2 一行 `scripts`）；③ `docs/features/F043/**`。
- **零 diff**：`frontend/src/**`、`frontend/package-lock.json`、`backend/**`、`docs/api/**`、`docs/product/**`、`docs/database/**`。
- 实施层级：L0 采 baseline（`caseAudit --emit`，禁改代码）→ L1 `lib/` + smoke 原语替换（**门禁：输出逐字节一致 + 352/0 + 358 行**）→ L2 交互族 + 静态族 → L3 runner + `package.json` 一行 → L4 全跑 + 证据落 `docs/features/F043/artifacts/**`；执行顺序 `typecheck → smoke:client → test:interactions`，不串接进既有 script。

## 8. 风险

| # | 风险 | 缓解 / 判据 |
| --- | --- | --- |
| R1 | 输出字节漂移（`lib` 的 `test()` 打印/清计数顺序微差） | L1 前后各存 `run1.log`，`diff -q` 必须空、358 行、`352 passed, 0 failed`；不一致回退 L1 |
| R2 | 静态断言被误当行为证据 | 测试名强制 `[S-STATIC]` 后缀；与 A3 表分离；不计入 A3 可观察量 |
| R3 | type stripping 版本依赖（Node <22.18） | 入口首行断言 `process.versions.node` ≥ 22.18，失败显式报错退出，不静默跳过 |
| R4 | `npm run` 在无 `node_modules` 环境失败 | 入口链无第三方 import；`F043-S05` 断言 `grep -E 'from "(react\|react-dom\|antd\|esbuild)'` 命中 0 |
| R5 | 计数白名单漂移 | 逐文件相等校验 + 名称集合超集；本 Feature 冻结 352 |
| R6 | 静态断言绑死行号 | 只断言文本模式，禁行号常量 |

## 9. 签核

```text
签核：Architect；日期 2026-10-29。
依据：F043/product.md v1（A1–A10 / N1–N8）、TD-F043-1 v1（C01–C14 / X1–X4）、docs/project/implementation-rules.md。
裁定：I-1（A9 放宽为「无新增依赖」+ scripts 一行）、I-2（不重构 smoke 为可 import）、I-3（台账只覆盖 smoke-client.mjs）、I-4（X1–X3 S 静态 / X4 NOT TESTED）。
放行写入：frontend/scripts/**、frontend/package.json（仅 scripts 一行）、docs/features/F043/**。
零 diff：frontend/src/**、frontend/package-lock.json、backend/**、docs/api/**、docs/product/**、docs/database/**。
结论：READY FOR IMPLEMENTATION（无阻塞）。NOT_TESTED 项不得记 PASS。
```
