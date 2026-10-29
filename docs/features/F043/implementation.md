# F043 前端实现报告（交互回归可重复入口与 smoke 拆分）

- **状态**：`FRONTEND COMPLETE`
- **版本**：IMPL-F043-1 v1；依据 `docs/features/F043/architecture.md`（ARCH-F043-1 v1，2026-10-29 签核）
- **范围 / UI 影响**：仅测试资产（`layers.frontend=false`）；`frontend/src/**`、`package-lock.json`、`backend/**`、`docs/api/**` **零 diff**；无呈现 / 交互 / 文案变化（未做设计检索），`frontend-ui` SKILL 的 `smoke:client` 验证已执行

## 1. 文件清单

| 文件 | 层 | 内容 |
| --- | --- | --- |
| `frontend/scripts/lib/caseAudit.mjs` | L0 | 签到点扫描（注释/字符串掩码）、计数白名单、名称摘要、skip 扫描；`--emit` / 只读审计 |
| `frontend/scripts/lib/case-ledger.json` | L0 | 基线台账：`{"scripts/smoke-client.mjs":352}`、`total=352`、`digest=4d43366f…`、`digest_sorted=bdc26411…`、`skip_hits=0` |
| `frontend/scripts/lib/harness.mjs` | L1 | `createHarness({label,resolveRespond,onTestStart})` → `{test,calls,passed,failed,handlerCalls,countUnauthorized,setRespond,jsonResponse,expectApiError,restore}` |
| `frontend/scripts/lib/report.mjs` | L1 | `report({passed,failed})`：打印 `\n<p> passed, <f> failed` 并**返回**退出码（不 `process.exit`） |
| `frontend/scripts/interaction/{candidate,auth,conflict,importCarrier,dangerousAction,tsxBoundary.static}.mjs` | L2 | 5 交互族 + 1 静态族，各 `export default register(h)` |
| `frontend/scripts/test-interactions.mjs` | L3 | runner：Node ≥22.18 校验 → 固定顺序 `register(h)` → `restore()` → `process.exit(report(...))` |
| `frontend/package.json` | L3 | **仅**新增 1 行 `"test:interactions": "node scripts/test-interactions.mjs",` |
| `frontend/scripts/smoke-client.mjs` | L1 | 仅替换原语（fetch 桩 / `calls` / `jsonResponse` / `expectApiError` / `test` / report）；14+/43-，用例体与顺序未动 |

## 2. C01–C14 ↔ 判定式（架构 §6；层：P 纯逻辑 / R 请求层 / S 静态）

| ID | 层 | 落地断言（文件内用例名以 `Cxx` 开头） |
| --- | --- | --- |
| C01 | P | `buildCandidateQuery` → `page=1,page_size=100,type=BARE_METAL,cluster_id=c1,q=bm`；`total=154 > 100` ⇒ `truncated===true`，文案含 `154` 与 `100`；pinned 第 101 位 id 在 `candidateOptions` 中恰 1 次、label 未退化，页内 100 id 各 1 次 |
| C02 | R | `listResources` 单次调用：`calls.length===1`，URL 同时含 `q=bm`/`page=1`/`page_size=100`/`type=BARE_METAL`/`cluster_id=c1` |
| C03 | R | 解析 URL：`page=1`（<2）、`page_size=100`（≤100）、无 `include`/`only`/`deleted` 参数；仍 1 次请求 |
| C04 | R | 401 首错 `isApiError && status===401 && code==="AUTH_REQUIRED"` 未被吞，`handlerCalls===1`；显式重试后 `calls.length===2` 且 200 |
| C05 | R | 单次 401：`calls.length===1`、`handlerCalls===1`（无自动重试） |
| C06 | R | 409 ⇒ `versionConflict===true && currentVersion===7`；`updateCluster(6)`→`getCluster`→`updateCluster(7)` 后 `calls.length===3`、`JSON.parse(calls[2].init.body).version===7` |
| C07 | R | 409 后 `calls.length===1`（无自动刷新/重试）；旧 `version=5` 重提仍 409（payload 未被改写）、`handlerCalls===0` |
| C08 | S | X2：同一文件同时含 `function refreshAfterConflict()` 与 `onRefresh={refreshAfterConflict}` 的载体 **8** 个（≥8），定义各 1 次 `[S-STATIC]` |
| C09 | P | `importCarrierPatch(v,"text")==={carrier:"text",format:"csv"}`（xlsx 亦强制 csv）；切回 `{carrier:"file",format:"csv",file:null}`；两载体 `importTargetKey` 均非 null 且不等 |
| C10 | P/R | 切换后 `validatedKey!==currentKey` ⇒ 门控 `validatePassed===false`、`canConfirm===false`、`busy||!canConfirm===true`；本地解析/空白拦截期间 `calls.length===0` |
| C11 | S | X3：`ResourceImportPanel.tsx` 含 `validatedKey !== null`、`validatedKey === currentKey`、`error_count === 0`、`importState.kind !== "success"`、`if (busy || !canConfirm)` `[S-STATIC]` |
| C12 | P/R | `tryBegin()===true` → `deleteCluster` 1 次（`DELETE …?version=3`）；第二次 `tryBegin()===false` → 仍 1 次；`settle()` 后可再次手动提交 |
| C13 | P/R | `tryBegin()→reset()`：`isInFlight()===false && calls.length===0`；重开后可再次 `tryBegin()===true` 且不发请求 |
| C14 | S | X1：`ui/ConfirmDialog.tsx` 含 `maskClosable={!confirmLoading}`、`keyboard={!confirmLoading}`、`disabled: confirmLoading`、`okButtonProps={{ danger }}`；`tryBegin()` 1 次、`settle()` 1 次、`reset()` **2** 次 `[S-STATIC]` |

禁词检查：新脚本 `正常|正确|符合预期` 命中 **0**。静态族 3 项带 `[S-STATIC]`，**不计入 A3 可观察量**；X4（`App.tsx` 处理器注册点）**NOT TESTED**。
## 3. 实际执行证据（Node v22.23.3，HEAD 7b67289，工作区含本 Feature 改动）
```text
L0 node scripts/lib/caseAudit.mjs --emit
  → {"scripts/smoke-client.mjs":352} total=352 digest=4d43366f… (prefix 4d43366f) sorted=bdc26411… skip_hits=0
L0 node scripts/lib/caseAudit.mjs（拆分后复跑）→ caseAudit: OK … skip_hits=0（exit 0）
L1 npm run smoke:client  → 358 行（352 PASS + 空行 + 汇总 + npm 头 3 行）、352 passed, 0 failed（exit 0）
L1 node scripts/smoke-client.mjs > /tmp/f043-after.log
   diff -q /tmp/f043-before.log /tmp/f043-after.log → 空（拆分前基线同命令采集，354 行）
L4 npm run typecheck        → exit 0（tsc --noEmit 无输出）
L4 npm run build            → ✓ built in 23.80s（exit 0；仅既有 >500kB chunk 警告）
L4 npm run test:interactions→ 14 passed, 0 failed（exit 0）；连续两次输出 diff 为空
自检 git diff --stat -- frontend/src frontend/package-lock.json backend docs/api → 空
自检 git diff -U0 -- frontend/package.json → 仅 1 行新增（--numstat 1 0），匹配 ^\+\s+"test:interactions":\s+"node scripts/test-interactions\.mjs",?$
自检 grep -rE 'from "(react|react-dom|antd|esbuild)' frontend/scripts → 0 命中
R4  /tmp/f043-iso（仅 scripts+src，无 node_modules）→ test-interactions 14/0、smoke-client 352/0
```

Mock / 桩：受控响应由 `lib/harness.mjs` 的 `setRespond` + `jsonResponse` 安装（`globalThis.fetch`），与既有 smoke 同一机制；替换真实 API 的方式 = 删除桩、调用同一 `src/api/*.ts` 函数。Mock 通过不等同集成通过。

## 4. 与架构文本的差异（按真实代码调整，未改 `src`，未放宽判据）

1. **行数 358 的口径**：`node scripts/smoke-client.mjs` 实测 **354** 行（352 PASS + 空行 + 汇总）；358 = `npm run` 包装后的行数（多 4 行 npm 头/空行）。门禁以同命令逐字节 diff 为准，结果为空。
2. **名称摘要前缀**：架构 §4 记 `b3f230b7`，实测 `4d43366f`（算法定为 `sha256(names.join("\n"))`，`smoke-client.mjs` 自 start_commit `8eec63b` 起无变更，`git diff --stat 8eec63b HEAD` 空）。台账以实测值为权威，审计模式 exit 0。
3. **X1 `reset()` 计数**：源码实际 **2** 处（`open=false` 副作用 + `onCancel`），非「各恰 1 次」；C14 断言按真实源码 2 次，`tryBegin`/`settle` 各 1 次。
4. **X2 / X3 文本口径**：`error_count === 0` 实际为 `validateState.data.error_count === 0`（子串命中，不绑行号）；9 文件含 `function refreshAfterConflict()`，其中 8 文件同时含 `onRefresh={refreshAfterConflict}`（`AccountManagementPanel.tsx` 仅定义未接线）⇒ 8，满足 ≥8。
5. **`lib/harness.mjs` API 增补**：多出 `resolveRespond` / `onTestStart` 两个选项、`passed` / `failed` 取值器，用于让 `smoke-client.mjs` 保留模块级 `respond` 与 `handlerCalls`（用例体零改动）；`expectApiError` 复用 `src/api/client.ts` 的 `isApiError`，断言与拆分前一致。
6. **C10 的 `canConfirm`**：`ResourceImportPanel.tsx` 不可加载，判据由 `importTargetKey`（真实导出）的 key 不等性 + 面板谓词的测试内镜像给出，结构真实性由 C11 静态断言兜底——已在用例内注明，不视为行为证据。

## 5. 未验证 / 风险
- **未验证**：X4（`App.tsx` 处理器注册点）；真实 ≥101 对象落库与服务端 409 真路径（属 F041 I 层 / F045）；浏览器 E2E（仓库无 Playwright/Chromium 依赖，按 A7 不作为保证）；只跑了 2 次重复性验证。
- **风险**：静态族绑定源文本模式，§5 的 `.tsx` 改写会使其失败（预期行为，防静默移除接线）；台账 `digest` 依赖「按登记顺序取首个字符串字面量」，新增用例会改变 `digest`（需同 PR 复跑 `--emit` 并解释）；`test()` 打印体依赖 harness 单点维护，再次改动须复跑 L1 门禁。

GIT: git rev-parse --short HEAD
GIT: git status --porcelain
GIT: git log --oneline -3
GIT: git diff --stat 8eec63b HEAD -- frontend/scripts/smoke-client.mjs
GIT: git cat-file -t 8eec63b
GIT: git diff --stat -- frontend/scripts/smoke-client.mjs
GIT: git diff -U0 -- frontend/package.json
GIT: git diff --numstat -- frontend/package.json
GIT: git diff --stat -- frontend/src frontend/package-lock.json backend docs/api
