# F043 前端交互回归可重复入口与 smoke 拆分（R08）— TEST REPORT

- **状态**：§1 **TEST DESIGN READY（TD-F043-1）**。该词仅表示「方案可验证」，**不是测试通过**，不批准实现或合并；执行结果待实现完成后另立 §2（本文件当前无 §2、无任何执行 PASS）。
- **版本**：TD-F043-1 v1（2026-10-29）；角色 tester；Feature F043（ENABLER / P2 / M30，`layers` 全 false、`api_required=false`、`depends_on: []`）。
- **分支 / 基线**：`feature/F043-test-entry`；`start_commit=8eec63b`；核对时 `HEAD=e7eec88`（PRODUCT READY FOR ARCHITECT）；工作树 clean（`git status --porcelain` 空）；plan revision 25 / requirements revision 16。
- **Basis**：`docs/features/F043/product.md` v1（A1–A10、§3 五类交互、N1–N8、ON-1..ON-7）；requirements rev16 §31；AQ-4=B；`docs/project/handoff.md`；`docs/project/implementation-rules.md`；先例 `docs/features/F041/test-report.md` §1。写权限：仅写本文件 §1，未改代码/计划/契约/Schema，探测临时文件在 `/tmp/f043probe/`，无 Git 写操作。

## 1. TEST DESIGN

### 1.1 分层能力与非适用项

| 层 | 载体 | 可断言 / 不可断言 | 依据（本轮实测） |
| --- | --- | --- | --- |
| **P**（纯逻辑） | 无 JSX 的 `src/**/*.ts`，由 `.mjs` 直接 `import`（node type stripping） | 状态机、谓词、文案、查询/payload 构造、错误描述器 | `node v22.23.3`；smoke 已加载 38 个 `src/**/*.ts` |
| **R**（请求层） | 同一 `.mjs`：`globalThis.fetch` 替换 + `calls[]`（url/init）+ `handlerCalls` | URL/method/payload/调用次数/401-409 错误语义/「不重试」 | `frontend/scripts/smoke-client.mjs:657-699` |
| **S**（静态结构） | grep / `git diff --stat` / 计数脚本 | 零 diff、无浏览器依赖、逐文件计数白名单、用例名摘要 | A5/A7/A9 |
| **`.tsx` 渲染与行为** | 无既有入口可执行 | **不可断言**：`import(...tsx)` → `Unknown file extension ".tsx"`；`maskClosable`/`keyboard` 等行为 props 也不出现在静态 markup | §1.4 |

| 项 | 判定 | 依据 |
| --- | --- | --- |
| 数据库 / Migration / 后端 / 契约 | `NOT_REQUIRED` | plan F043 `layers` 全 false、`api_required=false`；无 DB、无 API 变更 |
| 真实前后端集成 / 浏览器 E2E | `NOT_REQUIRED`（附缺口，§1.6） | AQ-4=B 限定「仅逻辑/请求级可重复入口，不引入浏览器依赖」 |
| 性能指标 | `NOT_REQUIRED` | product 未设时延阈值；只约束「请求次数与数据量无关」 |
| 一期整体验收（§31–§33） | `NOT_REQUIRED`（本 Feature） | A10：由 F045 承接，不得以本 Feature PASS 拼整体 PASS |

### 1.2 现状实测（本轮真实执行输出）

| 探测 | 命令 | 结果 |
| --- | --- | --- |
| Node | `node -v`（`frontend/`） | `v22.23.3` |
| smoke 基线 | `npm run smoke:client \| tail -3` | `352 passed, 0 failed`；`real 0m0.789s`；exit 0 |
| 确定性 | 连续两次 `npm run smoke:client` → `diff -q run1 run2` | **byte-identical**；各 358 行输出、352 行 `PASS:` |
| 用例计数 | `grep -c 'await test(' scripts/smoke-client.mjs` | `352`（文件 9,717 行；单文件） |
| 用例名摘要 | 正则 `await test\(\s*['"]([^'"]+)['"]` | 352 个名称、**全部唯一**（0 重复）；`sha256(顺序)=b3f230b7…`、`sha256(排序)=7c82b686…`；6 例用单引号名（`2129/2583/2602/3068/3087/3772`），提取正则须两种引号兼容 |
| typecheck | `npm run typecheck` | exit 0（`real 0m10.192s`） |
| `.tsx` 加载 | `node -e 'import("…/p.tsx")'` | `Unknown file extension ".tsx"` |
| 可复用性 | `node -e 'import("./scripts/smoke-client.mjs")'` | 打印 `352 passed, 0 failed` 后 **`process.exit(0)` 终止导入方**（`IMPORT-RETURNED` 未输出）→ ON-1 的直接 import 复用被末尾 `process.exit` 阻断 |
| 备选渲染（ON-4） | `import("react-dom/server")` / `import("antd")` / `esbuild` | `renderToStaticMarkup` 可用；antd 可 import（79 exports）；`esbuild 0.21.5`（vite 传递 devDep，**非新增依赖**），详见 §1.5 |

**领域块粗分（供 Architect 定拆分粒度，ON-2）**：`F003 16 / F004 17 / F005 9 / F006 12 / F007 22 / F008 22 / F009 25 / F010 30 / F011 24 / F012 24 / F013 13 / F018 9 / F014 17 / F015 23 / F017 12 / F019 8 / F020 4 / F021 2 / F022 7 / F023 18 / F030 6 / F034+F036 10 / F041 12` = **342**，加 banner 缺失的基础块（`707–840`，F001/F002 client 层）**10** 例 = **352**（可复算）。

### 1.3 TD-F043-1：A1–A10 → 验证项映射

| A | 层 | 用例 / 判定式 | 证据落点 |
| --- | --- | --- | --- |
| A1 入口可重复、exit 0、打印数、两次一致 | R/S | `F043-R01`：`npm run <name>` → `exit=0 && /(\d+) passed, 0 failed/` 且 `\1>=352`；连跑两次 `diff -q` 无差异 | `artifacts/run-1.log`、`run-2.log`、`diff.txt` |
| A2 五类交互均有用例 + 映射表 | S | `F043-S01`：§1.5 表中交互 ①–⑤ 各 `>=2` 行（正+负），每行有唯一用例 ID | 本文件 §1.5 |
| A3 每类 ≥1 正 +1 负、断言可观察量 | P/R | `F043-S01b` + §1.5 全部判定式：仅允许次数/URL/payload/状态机输出/文案；黑名单词 `正常\|正确\|符合预期` 不出现 | 本文件 §1.5 + 测试代码 review |
| A4 总数不减、无静默删除/skip/放宽 | S | `F043-S02`：`Σ 逐文件白名单计数 == 汇总打印数` 且 `>=352`；名称摘要含基线 `b3f230b7…`（顺序）或为其超集；无 `test.skip\|xit\|describe.skip`、无注释停用 | `artifacts/counts.txt` |
| A5 `frontend/src/**` 零 diff | S | `F043-S03`：`git diff --stat start_commit..HEAD` 仅含 `frontend/scripts/**`、`docs/features/F043/**`（+ 经裁定的 `package.json` scripts 行，见 I-1）；`frontend/src/**` 空 | 同左 + diff 清单 |
| A6 typecheck/build 通过、smoke 仍 352/0 | S | `F043-S04`：`npm run typecheck` && `npm run build` exit 0；`npm run smoke:client` 仍 `352 passed, 0 failed` | `artifacts/typecheck.log`、`build.log`、`smoke.log` |
| A7 无浏览器/网络依赖、离线可跑 | S | `F043-S05`：`grep -RE 'playwright\|puppeteer\|chromium\|webdriver' frontend/scripts` 无命中；无 `http(s)://` 外部主机、无 npm 安装步骤 | `artifacts/offline.log` |
| A8 证据入库 | S | `F043-S06`：§1.2 每条命令在 `docs/features/F043/artifacts/**` 有对应文件；未执行项标注为 NOT TESTED | 目录清单 |
| A9 不新增依赖 | S | `F043-S07`：`git diff --stat` 中 `frontend/package-lock.json` 零 diff；`dependencies`/`devDependencies` 零变更（`package.json` 的 `scripts` 口径见 I-1） | diff 清单 |
| A10 不等同 F045 | 声明 | `NOT TESTED`（非缺陷）：本 Feature 不声明 T127/T128/整体验收通过，不改已 DONE 证据 | 本文件 §1.6 |

### 1.4 TD-F043-1：五类交互用例矩阵（正/负例、判定式、证据落点）

| ID | 交互 | 层 | 正/负 | 夹具（既有模块，全为 `.ts`/`.mjs`） | 判定式（可观察量） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F043-C01 | ① | P | 正 | `buildCandidateQuery("host",{clusterId:"c1",search:" bm "})`；`applyCandidateResponse(loading,1,1,{kind:"success",items:100,total:154,pageSize:100})`；`candidateTruncation`；`candidateOptions(state,{id:"h101",label:"bm-101"})` | `q.page===1 && q.page_size===100 && q.type==="BARE_METAL" && q.cluster_id==="c1" && q.q==="bm"`；`truncated===true && text.includes("154") && text.includes("100")`；`options.filter(o=>o.value==="h101").length===1 && 该 option.label==="bm-101"` | `interaction-candidate.log` |
| F043-C02 | ① | R | 正 | 同 C01 的 query → `listResources`；`respond` 返回 100 项/total 154 | `calls.length===1`；`calls[0].url` 含 `page=1`、`page_size=100`、`type=BARE_METAL`、`cluster_id=c1` | 同左 |
| F043-C03 | ① | R | 负 | 追加一次「翻页/加量」尝试（`page:2`、`page_size:101` 的入参不进入请求构造路径） | `calls.length===1`（无循环翻页、无第二请求）；全部 URL 不匹配 `/page=([2-9]\|\d{2,})/`、不匹配 `/page_size=(1[0-9]{2}\|[2-9]\d{2})/`；不含 `include=` / `only=` / `deleted=` | 同左 |
| F043-C04 | ② | R | 正 | `respond` 第 1 次 401 `{code:"AUTH_REQUIRED"}`、第 2 次 200；用户显式「重试」= 再次调用 | `calls.length===2 && handlerCalls===1`；首次 `isApiError(err) && err.status===401 && err.code==="AUTH_REQUIRED"`（未被吞）；第 2 次返回 200 body | `interaction-401.log` |
| F043-C05 | ② | R | 负 | 单次 401 后不再调用 | `calls.length===1 && handlerCalls===1`（无自动重试；登录态只清一次）。既有 `smoke-client.mjs:734` 同断言**保留不删**（N1/A4） | 同左 |
| F043-C06 | ③ | R | 正 | `PATCH` `{version:6}` → 409 `{code:"VERSION_CONFLICT",details:{current_version:7}}`；`describeResourceActionError`；GET 详情 → `PATCH {version:7}` | `described.versionConflict===true && described.currentVersion===7`；`calls.length===3`；`JSON.parse(calls[2].init.body).version===7`（新 version 被采用） | `interaction-409.log` |
| F043-C07 | ③ | R | 负 | 收到 409 后不改用手动刷新；再以旧 `version:6` 提交一次 | 409 后 `calls.length===1`（无自动增长）；旧 version 再提交仍 `versionConflict===true && status===409` 且 `calls.length===2`（仅由用户动作+1），`handlerCalls===0`（不静默覆盖） | 同左 |
| F043-C08 | ③ | `.tsx` | 负 | 页面「刷新最新数据」接线：`ResourceDetailPage.tsx:526 refreshAfterConflict`、`NetworksPage.tsx:298`、`IpPoolsPage.tsx:259`、`IpAddressesPage.tsx:367` | **NOT TESTED**（无纯谓词；§1.5 交 Architect） | §1.6 |
| F043-C09 | ④ | P | 正 | `importCarrierPatch({carrier:"file",format:"xlsx",file}, "text")`；再 `(…, "file")`；`importTargetKey` 两载体 | `deepEqual(patch,"{carrier:'text',format:'csv'}")`；切回 file → `{carrier:"file",format:"csv",file:null}`（不回填 xlsx）；`importTargetKey(text)!==importTargetKey(file)`（两载体目标键不相等，且均非 null） | `interaction-carrier.log` |
| F043-C10 | ④ | P/R | 负 | 切换后原预校验指纹 `validatedKey` vs 当前 `importTargetKey`；确认门控 `canConfirmResourceInterfaceIpImport({…,targetKey:null})` | `validatedKey!==currentKey`（既有预校验/写入结果失效）；未显式校验/确认前 `calls.length===0`；`canConfirm===false` | 同左 |
| F043-C11 | ④ | `.tsx` | 负 | 单一资源导入面板 `ResourceImportPanel.tsx:216` 的内联 `canConfirm`（无纯谓词）与按钮 `disabled` | **NOT TESTED** / 或由 Architect 抽谓词后升级（§1.5） | §1.6 |
| F043-C12 | ⑤ | P/R | 正 | `createConfirmCommitGuard()` + 派发 `deleteResource`（mock fetch） | 确认路径：`tryBegin()===true` → `calls.length===1`；双击（第二次 `tryBegin()===false`）→ 仍 `calls.length===1` | `interaction-confirm.log` |
| F043-C13 | ⑤ | P/R | 负 | `tryBegin() → reset()`（取消 / Esc / 遮罩关闭在逻辑上等价 reset） | `guard.isInFlight()===false && calls.length===0`（取消不产生请求）；`settle()` 本身不派发新请求 | 同左 |
| F043-C14 | ⑤ | `.tsx` | 负 | 提交态取消入口不可用：`ConfirmDialog.tsx` `cancelButtonProps.disabled={confirmLoading}`、`maskClosable/keyboard={!confirmLoading}`、`okButtonProps.danger` | **NOT TESTED** / 待抽 `confirmDialogControls(confirmLoading)` 纯谓词（§1.5） | §1.6 |

**覆盖边界**：① 的真实 ≥101 对象落库与提交被服务端接受属 F041 I 层与 F045 整体验收；本 Feature 只证逻辑/请求级，不声明 T127/T128。

### 1.5 断言点可植入位置（交 Architect 裁定 ON-1/ON-2/ON-4）

**可在纯 `.ts`/`.mjs` 断言**：①全部（`candidateSelectModel.ts`）；②全部（`api/client.ts` + `setUnauthorizedHandler` 计数）；③冲突识别与刷新后重提（`api/resources.ts:442-531` 描述器 + request 层三次调用序列）；④全部核心（`importCarrier.ts`、`importForm.ts:86-126`、`resourceInterfaceIpImportForm.ts:91-121/213`）；⑤守卫与取消/确认路径（`confirmDialogState.ts`）。

**必须 `.tsx`（逐条列出，不得默认通过）**：
| # | 位置 | 断言内容 | 无纯逻辑时的处置 |
| --- | --- | --- | --- |
| X1 | `src/components/ui/ConfirmDialog.tsx:44-97` | `maskClosable/keyboard=!confirmLoading`、`cancelButtonProps.disabled`、`okButtonProps.danger`、`width=520`、守卫接线（C14） | 抽 `confirmDialogControls()` 谓词（须列入 A5 放行清单）否则 `NOT TESTED` |
| X2 | `src/pages/ResourceDetailPage.tsx:525-531 refreshAfterConflict` 及 `NetworksPage.tsx:298`、`IpPoolsPage.tsx:259`、`IpAddressesPage.tsx:367` 等 | 「刷新最新数据」按钮采用 `current_version`、重置表单（C08） | 同上（抽「409 → 刷新 → 新 version」谓词） |
| X3 | `src/components/ResourceImportPanel.tsx:216` | 单一资源导入面板内联 `canConfirm`（C11；三方导入已有纯 `canConfirmResourceInterfaceIpImport`） | 同上 |
| X4 | `src/App.tsx` 处理器注册点 | ② 的「清登录态只一次」页面侧（client 层已由 `handlerCalls` 覆盖） | 记为 NOT TESTED（不重复覆盖） |

**ON-4 可行性实测结论**：`react-dom/server.renderToStaticMarkup` 与 `antd` 在 node 中可加载，但 `.tsx` 无法被 node 直接加载；要走静态渲染必须引入 `esbuild 0.21.5`（现有 vite 传递依赖，**不新增包**）的 transform 步骤，且行为类 props（`keyboard`/`maskClosable`）在静态 markup 中不可观察 → 只能验证 DOM 文案/属性。**建议优先级：抽纯谓词 > 静态渲染 > NOT TESTED**；无论哪种都需 Architect 在 architecture 中明确并给出 A5 放行清单。

### 1.6 防静默删除判据（ON-3）可行性实测

| 判据 | 实测可行性 | 用法 |
| --- | --- | --- |
| 逐文件 `grep -c 'await test('` 白名单 | **可行**：现为 `scripts/smoke-client.mjs=352`；拆成 N 个文件后按文件名→期望数写死白名单，`Σ == 汇总打印数` | 主判据 `F043-S02`，抵抗「文件内被删一段」 |
| 用例名摘要比对 | **可行**：352 名称唯一，顺序 `sha256=b3f230b7…`、排序 `sha256=7c82b686…`；提取正则须兼容单/双引号（6 例单引号） | 次判据：**同时**断言「基线 352 名称 ⊆ 新集合」+「集合大小 >= 352」；排序摘要用于证明「未改名」 |
| 组合 | 建议两者并用：计数白名单抓删除，名称子集抓改名/停用；另加 `grep -E 'test\.skip&#124;xit\(\|describe\.skip'` 为 0 防止注释停用 | `artifacts/counts.txt` 保存两个摘要与逐文件计数 |

### 1.7 未验证项与降级规则

1. C08 / C11 / C14（X1–X3）在 Architect 未给出纯谓词或静态渲染方案前一律 `NOT TESTED`，**不得**以「实现看起来正确」记 PASS（N8）；A10、真实浏览器视觉/DOM、性能、整体验收为 `NOT_REQUIRED`/`NOT TESTED`（§1.1），不得用局部 PASS 拼整体 PASS。
3. 若入口改为「拆出用例」，A6「既有 `npm run smoke:client` 仍 352」与 A4「总数不减」必须同时满足 → 允许的实现是「保留 `smoke-client.mjs` 独立运行仍 352（导出 `run()` + `import.meta.main` 守卫）并由汇总 runner 组装」，否则两条验收互斥，`TEST BLOCKED`。
4. 任一执行步骤依赖网络安装/浏览器二进制 → 直接判 A7 FAIL（非降级）。

### 1.8 Issues / Next（责任角色：Architect）

- **I-1（须裁定，MEDIUM）**：A1 要求 `npm run <name>`、A9 要求 `package.json` 零 diff，而新增 scripts 行必然改动 `package.json`。TD 建议口径：A9 解释为「`dependencies`/`devDependencies` 与 `package-lock.json` 零变更，`scripts` 仅允许新增入口行并逐条列入 A5 放行清单」；若需改需求措辞，交 Product Manager / 用户，不由 Tester 决定。
- **I-2（ON-1）**：直接 `import("./scripts/smoke-client.mjs")` 复用被末尾 `process.exit(0)` 阻断（实测），需 refactor 为「可导入 `run()` + 独立执行仍打印 352」或按约定复制 fetch 替换/计数模式；任一选择须说明对 A6 的影响。
- **I-3（ON-2）**：拆分粒度按 §1.2 的 24 个 banner 块 + 1 个基础块（10 例）为候选单元；须给出「全部计数可复算」的机器校验位置。
- **I-4（ON-4）**：X1–X3 处置（抽谓词 / 静态渲染 / NOT TESTED）须在 `docs/features/F043/architecture.md` 明确，并由 Tester 在升版 TD 中复核（记录新版本与证据），随后进入 TEST 执行。

**结论**：`TEST DESIGN READY`（仅代表 A1–A10 已可映射为可重复、可观察的验证项；未执行任何用例，不代表测试通过，不批准实现或合并）。

GIT: NONE
