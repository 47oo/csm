# F036 F032–F035 Review 跟进项收敛 — Test Report

> 同一份报告承载 TEST_DESIGN 与 TEST 两阶段，分开记录版本与证据。
> **当前状态**：§1 TEST DESIGN = **TD-F036-1（v1，2026-10-26，`TEST DESIGN READY`）**；§2 TEST EXECUTION 尚未编写。
> `TEST DESIGN READY` 仅表示方案可验证，**不是测试通过**，不批准实现、Contract 定稿或合并。

**版本记录**

| 阶段 | 版本 | 日期 | 结论 | 依据 HEAD |
| --- | --- | --- | --- | --- |
| TEST DESIGN | TD-F036-1 | 2026-10-26 | `TEST DESIGN READY` | `1ccab33`（architecture 已提交，实现未开始） |
| TEST | TE-F036-1 | （待填） | （待填） | （待填） |

---

## 1. Test Design（TD-F036-1，v1，2026-10-26）

### TD-1 Task / Status / Basis

- **Task**：F036「F032–F035 Review 跟进项收敛」（ENABLER / P2 / M27）；分支 `feature/F036-review-followup-closeout`（base `v3.3`，`start_commit` `a2e9194`，本 TD 编写时 HEAD `1ccab33`）；`plan revision` 22；需求 **revision 14**（不变）；阶段 TEST_DESIGN，Tester 只读核对 + 仅写本文件。
- **Status**：`TEST DESIGN READY`（见 TD-9；10 条 `TD-I-*` 记录项不构成不可验证项）。
- **范围**：只做设计检查（验收映射、边界与并发场景、夹具/环境、可观察结果、可验证性）。**未执行任何测试、构建或 Git 变更命令**；下文所有「期望」均为待执行断言。

| Basis | 版本 / 状态 | 用途 |
| --- | --- | --- |
| `docs/features/F036/product.md` | v1（READY FOR ARCHITECT） | §2 逐条映射（15 行）、§4 **A1–A14**、§3 排除项 |
| `docs/features/F036/architecture.md` | v1（READY FOR DESIGN，§12 待 CONTRACT 签核） | §6 **V1–V15**、§3 **DR-F036-01…11**、§5 完整性表、§7 **R-1…R-13**、§8 变更边界、§4.1 契约澄清拟文 |
| `docs/project/proposals/CHG-014` | APPROVED（用户 2026-10-26） | 范围唯一授权（§1 十项 + §2 不做 + §3 排除 F034-RV-02） |
| 缺陷原文 | `docs/features/F03{2,3,4,5}/review-report.md` §6/§8 | 判据来源（F032-RV-02/03/05/06/07、F033-RV-01/03、F034-RV-01/03/04/06/08/09、F035-FU-01/05/08） |
| 既有已签核口径 | `docs/api/F023.md` v2 §11（+§4.1 拟加澄清行）、§1.2/§12.5；F014.md v1；plan rev 22 `layers={database:false,backend:true,frontend:true}`、`api_required=true` | 断言口径；**不得**在本 Feature 内改端点/字段/错误码/`reason` 枚举/模板/上限/权限 |
| 规则与方法 | `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`AGENTS.md` §5–§9、`.pi/skills/{data-integrity,frontend-ui}/SKILL.md` | 交接/缺陷格式、验证纪律 |
| 只读代码核对（HEAD `1ccab33`） | `resource_interface_ip_import.py::_app_error_field:1318`/`_acquire_locks:1274`/`write_import:1529-1536`、`interface.py::_lock_resource:135-159`、`resource_import.py::_error_message:506`、`importForm.ts:81-124`、`resourceInterfaceIpImportForm.ts:113-221`、两面板 `currentKey/canConfirm`、`index.css:958-985`、`smoke-client.mjs:8874-8899`、`collect_host_info.py:673-706`、`test_collect_host_info.py:600/742/817`、`test_f034_csv_text_carrier.py:47/239/719`、`test_f023_*::_run_pair:406` | 判定可观察面与断言可实现性 |

### TD-2 层级记号与可验证性前提

| 记号 | 载体 | 说明 |
| --- | --- | --- |
| **U** | `npm run smoke:client`（Node 22 直载 `.ts` 纯模块）或 pytest 直调纯函数 | 纯逻辑：`importCarrierPatch`、`importTargetKey`、`canConfirm*`、placeholder 常量、`_app_error_field` |
| **I** | pytest + **真实 PostgreSQL** + 真实 `create_app`/`service`（`auth_session_factory` 真提交） | V2 竞态、V9–I、V10、V13、V15 |
| **S** | `git diff` / `grep` / `git ls-files` / `git check-ignore` | 零 diff 守卫、MAC/口令 grep、入库范围、记载项、基线与依赖计数 |
| **B** | Playwright + Chromium + 候选 `frontend/dist` + 真实后端 | V5 焦点可见性、V1 的界面回显；**必记视口/日期/截图** |
| **M** | `smoke:client` 机制级（受控 fetch，无 DOM） | 仅作 U 的宿主，不得当作 DOM 证据 |

**可验证性前提（设计期只读实测，非执行结果）**

1. **真实 PG 可用**：`csm-f035-pg`（`postgres:16`）映射 `127.0.0.1:55432` 已 Up；宿主 `5432` 关闭；`conftest` DB-D10 双守卫（库名含 `test`、≠`DATABASE_URL`）保留。I 层独占该库（`pg_engine` `DROP SCHEMA public`+`alembic upgrade head`，函数级 `TRUNCATE`）。
2. **前端工具链**：`frontend/node_modules` 就绪；Node `v22.23.3`；Playwright(Python) + `chromium-1248` 已装 ⇒ B 层可行，需**候选构建**（当前 `csmtest` 栈 :18080 为 F036 之前镜像）。
3. **实现未开始**：`a2e9194..1ccab33` 仅 docs 变更（`backend/**`、`frontend/**` 零 diff）⇒ 本阶段所有用例状态为待执行，不得读作 PASS。
4. **符号名以架构为准**（`artifact_dir()`、`IMPORT_TEXT_PLACEHOLDER`、`RESOURCE_INTERFACE_IP_TEXT_PLACEHOLDER`）：TEST 按语义断言，等价改名不判 FAIL，但须在 TEST 报告登记实际名称。
5. **不得发明规则**：预期只引用 A1–A14 / V1–V15 / DR-F036-*；契约未固定处按 TD-9 `TD-I-*` 记录，不转成断言。

### TD-3 用例矩阵（V1–V15 → 47 条 `TD3-F036-*`）

记法：`ID | 层级 | 目标 / 前置 | 步骤 | 期望（判据） | 证据`。TEST 阶段逐条标 `PASS / FAIL / BLOCKED / NOT TESTED` 并附命令与路径。

| ID | 层 | 目标 / 前置 | 步骤 | 期望（判据） | 证据 |
| --- | --- | --- | --- | --- | --- |
| `V1.1` | U | 载体切回 file 清空已选文件（A1/DR-F036-02）；前置：两 form 模块可载入 | 构造 `{carrier:"text",format:"csv",file:File,text:"..."}` 调 `importCarrierPatch(v,"file")`；同 `resourceInterfaceIpImportCarrierPatch` | 返回恰 `{carrier:"file",format:"csv",file:null}`（3 键，`file===null`）；`format` 保留 csv、**不回填** xlsx；`text` 不被触碰 | smoke 断言 + 计数 |
| `V1.2` | U | 清值后指纹与门控必然失效 | 对上一步结果调 `importTargetKey` / `resourceInterfaceIpImportTargetKey`；再用 `canConfirmResourceInterfaceIpImport({validated:{errorCount:0},validatedKey:"text:...",currentKey:<上值>,importSucceeded:false})` | 两 key **均 `=== null`**；F023 门控 **`=== false`**；F014 侧以「`currentKey===null` + 面板 `validatedKey!==null && validatedKey===currentKey` 合取」判 false（S 复核该合取仍在源码） | smoke 断言 + S grep |
| `V1.3` | M | 切 text→file 序列不产生可提交路径 | 模拟 changeInput 语义（结果态重置为 idle/validatedKey=null）+ `V1.1/V1.2` 值 | 切回后 `parseImportFormValues` 对 `file:null` 返回 `ok:false` 且 `errors.file` 非空（既有本地拦截不变，不发请求） | smoke 断言 |
| `V1.4` | B | 界面与提交值一致（T116 忠实度）；前置：候选 dist + 真实后端 | 面板选文件 → 预校验 0 错误（`确认导入`可点）→ 切「文本」→ 切回「文件」 | 无文件名回显、「确认导入」**disabled**、结果区回到空态；**记录视口/日期/截图** | `artifacts/f036-ui-browser-check.json` + 截图 |
| `V2.1` | I | **真实 PG 双会话竞态**：宿主在锁定前被并发软删 → 422 且归因 `hostname`（A2/DR-F036-01）；构造见 TD-4 | 预校验 0 错误 → A 会话 `write_import` 阻塞于 `resources` 行锁（`pg_blocking_pids` 证实）→ B 会话服务层软删并提交 → A 解阻塞 | `ImportValidationFailed`；`errors` 中**恰 1 条**该行错误：`field=="hostname"`、`row==2`（1-based）、`reason` 含服务层文本；无 `40P01`/`500` | pytest 日志 + `pg_blocking_pids` 采样 |
| `V2.2` | I | **零写入残留**（T123 整批原子性） | 接 `V2.1`，基线在竞态开始前采集 | `interfaces`/`ip_addresses`/`resources`（行数）计数**不变**；`audit_logs` 增量**仅** B 的软删产生（窗口内 `action='CREATE'` 计数 == 0）；宿主仍 `deleted_at IS NOT NULL` | 计数快照 JSON |
| `V2.3` | I | 竞态窗口**边界对照**（防「假竞态」）：软删先于写入解析 ⇒ 按新建处理（F035 V12 已批准观察） | 同一批次：先软删提交，再 `write_import` | `created==1`、新 id、原行仍软删；**不得**断言 422——若此处也 422 说明 `V2.1` 的窗口未被真正命中，须重做构造 | pytest 日志 |
| `V2.4` | I | 不弱化既有语义：宿主在写入时确实不存在/不可选 | 批次指向从未存在的 hostname；另例：宿主在其它 Cluster（范围外） | 均为该行 `field=="hostname"` + 整批 422、零残留；`_lock_resource` 的 `include_deleted` 与未删校验未被放宽 | pytest 日志 |
| `V2.5` | U | 词表映射机械断言（含零回归） | 直调 `_app_error_field`：`fields[0].field="resource"`；既有 `address`/`virtual_machine.host_resource_id`/`interface`；未知路径 | `resource→"hostname"`；`address→"ip"`、`virtual_machine.host_resource_id→"host"`、`interface→"name"` **不变**；未知路径仍走 `_template_field` | pytest 断言 |
| `V3.1` | S | 契约澄清已签核（A2 后半） | 读 `docs/api/F023.md` §11 与 §17 增补行 | 澄清行存在且覆盖 `field` 恒模板列名 / `hostname` / `reason` 自由文本 / `related_row=null` / 整批 422 / 1-based 行号 / 不新增码与字段；正文仍 **v2** | `git diff docs/api/F023.md` |
| `V3.2` | S | 契约零扩散 | `git diff` 核对 `docs/api/F014.md`、§4–§13 正文与模板/上限常量 | `F014.md` 零 diff；§11 外无实质新增；错误码/`reason` 枚举/26 列/上限零 diff | `git diff --stat` |
| `V4.1` | S | MAC 脱敏（A3/DR-F036-06） | `grep -rnE "([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}" docs/features/F032/artifacts/` | **命中 0**（掩码形如 `08:00:xx:xx:xx:xx` 不计）；范围含 `real-validate/*.csv`、`real-validate/setup.log`、`cli-smoke.log`（见 `TD-I-1`） | grep 日志 |
| `V4.2` | S | 证据可用性不被破坏 | 逐文件核对表头行/BOM/26 列/行数/列序/其余单元格 | 三 CSV 仍在，表头与行数不变；仅 `mac_address` 后 4 组替换；`REDACTION.md` 存在且含 `mac_address`+`xx`+边界声明 | `git diff` + 结构脚本 |
| `V4.3` | S | 脱敏后不再作逐字节等价性证据（R-8） | 核对 `REDACTION.md` 边界声明与 F036 报告引用方式 | 声明可见；本报告**不**以脱敏 CSV 主张字节等价；等价性证据仅取 F034 artifacts（`TD-I-5`） | 文档核对 |
| `V4.4` | S | 未越界 | `git ls-files` / `git check-ignore -v` 复核 `.gitignore`、logs、`.raw`；`git diff docs/features/F032/{test-report,review-report}.md` | `.gitignore` 零 diff；不删/不移证据；F032/F034 报告结论零改写 | 命令输出 |
| `V5.1` | S | 焦点环实现改内向且不覆盖激活条（DR-F036-05） | 读 `index.css` ≤1023 块 | 规则为 `outline:3px solid var(--csm-primary); outline-offset:-3px`；**无** `box-shadow` 覆盖；注释与实现一致；无新断点、`44px`/`padding-inline`/`scroll-snap` 零 diff | `git diff frontend/src/index.css` |
| `V5.2` | B | 375px 焦点三边可见（A4） | Chromium 375×812，聚焦首/末导航项，`scrollLeft=0` 与最大滚动各取样 | `getComputedStyle(link).outlineOffset === "-3px"`；环矩形四边落在 `nav` client 矩形内；局面截图 | `f036-ui-browser-check.json` + 截图（记视口/日期） |
| `V5.3` | B | 1023px 同判据 + 激活项 `current` 标识保留 | 同上（1023×768），聚焦激活项 | 三边完整；`box-shadow` 仍含 `inset`（左条可辨识）；与 `V5.2` 同证据集 | 同上 |
| `V6.1` | S | smoke 基线 = 实测（A5/F033-RV-01） | 记录 `cd frontend && npm run smoke:client` 的实测计数、命令、日期 | 报告中的基线数字 **==** 本次实测，且 **≥339**；注明 322/328 为历史值、F036 起以实测为基线 | `artifacts/frontend-smoke.log` |
| `V6.2` | S | 无陈旧计数残留 | `grep -rn "322\|328" docs/features/F036/` | 仅作为**历史值**出现并带说明；无「当前基线 322/328」表述 | grep 输出 |
| `V7.1` | U | placeholder 明确为片段（A6/DR-F036-04） | 载入两常量 `IMPORT_TEXT_PLACEHOLDER`、`RESOURCE_INTERFACE_IP_TEXT_PLACEHOLDER` | 均含「片段」；示例数据行逗号数 ≤3（列数 ≤4）；**不含** `TEMPLATE_COLUMNS.join(",")`；不含 `...`/`…` 截断拼接 | smoke 断言 |
| `V7.2` | S | 两面板仍引用常量、其余文案不变 | grep 两面板 `placeholder={…}` | 引用常量（非内联字面量）；`rows`/`aria-describedby`/hint/字节计数零 diff | `git diff` |
| `V7.3` | S | 模板零漂移 | `git diff` 26 列常量与上限常量 | 零 diff（不借 placeholder 之名改模板） | `git diff` |
| `V8.1` | S | 口令掩码（A7） | `grep -rnE "postgres(ql)?(\+psycopg)?://[^[:space:]]+:[^@[:space:]]+@\|csm:csmtest" docs/features/F036 docs/features/F032 docs/features/F034` | F036 自有文档命中 0（或仅 `***`/`<…>` 掩码）；F032/F034 报告内测试口令掩码化（见 `TD-I-2` 确定范围） | grep 输出 |
| `V8.2` | S | 入库范围描述与实际一致（F034-RV-04） | 并列 `git ls-files docs/features/F034/artifacts`（83 项含 `logs/**`）与 `git check-ignore -v`（`*.log`/`logs/` 规则） | 报告证据表逐项与命令输出一致；不笼统称「logs 被忽略」；忽略集合与入库集合分列 | 两条命令输出 |
| `V8.3` | S | 仓库级明文口令的范围声明 | 全仓 grep（只登记，不改历史报告） | 若仍有历史明文，登记为观察项并说明「F036 §8 禁止改写 F001–F035 历史报告」；不据此判 FAIL | grep 输出 |
| `V9.1` | U | 记忆化后纯函数等价（A8/DR-F036-03） | 60 例同输入重复调用 `importTargetKey`/`resourceInterfaceIpImportTargetKey`/`importTextDigest`（30 语料 × 2 入口，含中文/emoji/CRLF/空串） | 同一输入多次调用**逐字节相等**（digest+byteLength）；与 F034 冻结观察值相等 | smoke 断言（60 例计数） |
| `V9.2` | U | 依赖充分性：改 1 字符必换 key | 对 30 语料逐个替换 1 个 code unit（含非 ASCII） | key 必变；byteLength 可不变但 digest 变 | smoke 断言 |
| `V9.3` | S | `useMemo` 依赖集合恰为四要素 | 规范化 grep 两面板 | `currentKey` 依赖 `[values.carrier, values.format, values.file, values.text]`；`pastedByteLength` 依赖 `[values.carrier, values.text]`；`useMemo` 自 `react` 导入；`importCarrier.ts` 零改动（无 memo） | `git diff` + grep |
| `V9.4` | I | F034 等价性 60 例仍全 deep-equal + 改前改后一致 | `pytest tests/integration/test_f034_csv_text_carrier{,_scope}.py` | 60 例（30 语料 × 2 入口）`status` 与响应体深比较全等，0 差异；`TD3-T114*`、反空洞断言原样通过 | pytest 日志 |
| `V10.1` | I | 测试洁净（A9/DR-F036-08） | 跑 `test_f034_csv_text_carrier*.py` 前后各取 `git status --porcelain` | 前后**均无输出**（已跟踪 artifacts 零改动） | 两条命令输出 |
| `V10.2` | S | 产物落临时目录且可显式收集 | 检查 `CSM_TEST_ARTIFACT_DIR` 分支与写入路径 | 默认 `tempfile.gettempdir()/csm-test-artifacts/f034`；设置环境变量后落该目录；仓库树内无新文件 | `git status --porcelain --ignored` + 目录列表 |
| `V10.3` | S | 历史证据冻结 | `git diff docs/features/F034/artifacts/` | 零 diff（不改写 F034 已入库等价性证据） | `git diff --stat` |
| `V11.1` | S | T79 CLI 自动化用例存在且覆盖六参数（A10/DR-F036-07） | 读 `scripts/test_collect_host_info.py::test_cli_all_manual_params_written` | 子进程调用（非进程内 monkeypatch）；断言六参数写列 + 其余留空 + 缺 `--resource-type` 非零退出 + stderr 含 `--resource-type`；临时 `cwd` | 源码 + pytest 日志 |
| `V11.2` | S | CLI 行为零变更 | `git diff scripts/collect_host_info.py` | 仅注释/docstring 变化（DR-F036-10 11a/11b）；argparse 定义、`required=True`、`choices`、`_push` 防御检查零 diff | `git diff` |
| `V11.3` | I | 新用例 PASS 且计数 83→≥84 | `pytest scripts/test_collect_host_info.py -q` | 全部 PASS；收集数 **≥84**；既有 83 条零失败 | pytest 日志 |
| `V11.4` | I | 零文件副作用 | 缺 `--resource-type` 用例后检查临时目录 | 无新增文件；进程退出码非零 | pytest 断言 |
| `V12.1` | S | 11a/11b 记载可 grep | grep `collect_host_info.py` | `build_error_hint` docstring 含「DR-1007 / 统一追加 / `_ArgumentParser.error()` / 收窄须另立变更」；`collect` docstring 含「单测与防御边界 / CLI 仍 required」 | grep 输出 |
| `V12.2` | S | 11c/11d/11e 记载可 grep | grep F036 文档 | 11c（表头级 `unknown_columns` 既有 schema、两载体一致、收紧另立提案）、11d（既有 B 层视口 1440×1000 + 改布局须补 375/1023）、11e（5000 行性能 `NOT TESTED` + `f023-import.md` §5.7 + **不放松 V11.5 锁环判据**）均可检索到条目 ID 与触发条件 | grep 输出 |
| `V12.3` | S | F033-RV-01 记录与不改他报告 | grep 本报告 + `git diff docs/features/F033/` | 基线记录含命令/日期/实测值；F033 报告正文零 diff | `git diff --stat` |
| `V13.1` | M | `smoke:client` 不减少 | `cd frontend && npm run smoke:client` | `0 failed`；计数 **≥339**（F036 新增用例只增）；既有 F023/F034 段零失败 | `artifacts/frontend-smoke.log` |
| `V13.2` | I | F035 主体不减少 | `pytest tests/integration/test_f035_append_interface_ip_import.py -q` | **≥20 passed**，0 failed | pytest 日志 |
| `V13.3` | I | F035 Tester 验收 + 范围不减少 | `pytest tests/integration/test_f035_tester_acceptance.py tests/integration/test_f035_append_scope.py -q` | **≥18 passed**（16 + 2），0 failed | pytest 日志 |
| `V13.4` | I | F023 主体不减少 | `pytest tests/integration/test_f023_resource_interface_ip_import.py -q` | **≥28 passed**，0 failed（含 PERF） | pytest 日志 |
| `V13.5` | I | 零回归集不减少 | `pytest` 11 文件集（`test_imports` 29 / `test_import_tester_acceptance` 9 / `test_import_constraints` 4 / `test_f034_csv_text_carrier` 29 / `_scope` 2 / `test_f027_access_scope` 11 / `test_interfaces` 21 / `test_interface_constraints` 13 / `test_ip_addresses` 38 / `test_ip_address_constraints` 16 / `test_f019_interface_ip_binding` 14） | **≥186 passed**，0 failed | pytest 日志 |
| `V13.6` | I | F034 集成不减少 | 同一集合中 F034 两项 | `test_f034_csv_text_carrier` **≥29** + `_scope` **≥2** = **≥31**；0 failed | pytest 日志 |
| `V13.7` | S | 前端构建与依赖守卫 | `npm run typecheck`；`npm run build`；`git diff frontend/package.json frontend/package-lock.json` | 两条命令 exit 0；依赖零 diff（新增 npm/Python 第三方依赖 0，仅 stdlib `os`/`tempfile`） | 命令日志 |
| `V14.1` | S | 零 DDL / 零 Schema 漂移 | `git diff --stat -- backend/alembic backend/app/models`；`alembic heads` | 零 diff；head 仍 **`0015`** | 命令输出 |
| `V14.2` | S | wire 与共享 UI 零 diff | `git diff --stat -- frontend/src/api docs/api/F023.md`（对照 §4.1 范围） | `frontend/src/api/**` 零 diff；`docs/api/F023.md` 仅 §11/§17 澄清行 | `git diff` |
| `V14.3` | S | 模板/上限/权限零 diff | `git diff` 26 列常量、`IMPORT_MAX_FILE_BYTES`、5000 行上限、权限矩阵相关文件 | 全部零 diff | `git diff` |
| `V14.4` | S | 项目状态一致性 | `python3 scripts/validate_project_state.py` | 输出结构校验通过（不代表批准或 Git 证据有效） | 命令输出 |
| `V15.1` | I | 权限与范围口径不变（A14） | 既有 401/403 与行级范围用例（`test_f027_access_scope`、`test_f035_append_scope`、导入越权用例） | 全部 PASS 且断言文件零 diff；401 先于 403 的顺序不变 | pytest 日志 + `git diff` |
| `V15.2` | I | 并发锁序未被本次改动破坏 | 复跑 F035 `V11` 五例（尤其锁环 `V11.5`） | 5 例 PASS，无 `40P01`；`_acquire_locks` 零 diff | pytest 日志 |

**统计**：V1 4、V2 5、V3 2、V4 4、V5 3、V6 2、V7 3、V8 3、V9 4、V10 3、V11 4、V12 3、V13 7、V14 4、V15 2 = **47 条**（U 9 / I 16 / S 20 / B 2；M 2 计入 U/S 宿主）。

### TD-4 V2 真实 PG 双会话竞态构造（关键用例，必须真实执行）

- **为何难**：`write_import` 在组构建阶段已把该行解析为**追加组**（`existing_resource_id`），软删若发生在这之前，写入会走 F035 V12 的「按新建处理」；只有在 `_acquire_locks`（`resources` 预锁）**之后**、`prepare_interface → _lock_resource` 之前完成软删，才会命中 `_field_error("resource")` 这条极窄路径（R-2）。因此必须**强制**交错，不能只依赖 `threading.Barrier` 对称起跑。
- **构造（`TD3-F036-V2.1`）**：
  1. 前置（真实 API 建立）：Cluster `f36c` + Network + BM 宿主 `f36-host`（`role/status`/无硬件列，避免触发一致性错误）；批次 CSV 仅 1 个数据行（物理行 **2**）指向该宿主，`/validate` 独立会话跑一遍 → `error_count==0`。
  2. 会话 **B**（软删方，独立 `auth_session_factory` 会话）：`BEGIN`；记 `pidB = pg_backend_pid()`；`SELECT id FROM resources WHERE id=:host FOR UPDATE`（**持锁不放**）。
  3. 线程 **A**（写入方）：独立会话，记 `pidA`；调用 `unified.write_import(sessionA, operator, …)` —— 该会话在 `_acquire_locks` 的 `SELECT … FOR UPDATE … ORDER BY id` 上**阻塞于 B**。
  4. 主线程**轮询**（≤15s，50ms 间隔）：`SELECT pg_blocking_pids(:pidA)` 返回非空且含 `pidB` ⇒ 证明 A 已达预锁点（不靠 sleep 猜测）。轮询超时即判该用例 `BLOCKED`（构造失败，不得改判 PASS）。
  5. 会话 B 在**同一事务**内走服务层软删（`resource_service.delete_resource` 口径，保留 version 校验与审计），`COMMIT`。
  6. A 解阻塞 → `_lock_resource`（`include_deleted=True` + `deleted_at IS NOT NULL`）抛 `_field_error("resource", "resource does not exist or is not selectable")` → `_app_error_field` 映射为 `hostname` → `RowError(row=2, field="hostname", reason=_error_message(exc))` → `db.rollback()` → `_raise_validation_failed`。
  7. 断言：`ImportValidationFailed`；`errors` 恰 1 条该行错误、`field=="hostname"`、`row==2`、`reason` 含 `does not exist or is not selectable`（见 `TD-I-3`）；`thread.join(timeout=60)` 后 `not thread.is_alive()`；无 `40P01`/`InternalError`。
- **零写入残留（`V2.2`）**：基线在**步骤 2 之前**采集；结束后断言 `interfaces`/`ip_addresses` 计数不变、`resources` 行数不变（软删非物理删除）、窗口内 `audit_logs` 无 `CREATE`（仅 B 的软删审计）。不做「增量 == 0」这种会把 B 自身的审计误判为残留的粗糙断言。
- **不做**：不重试、不断言线程调度顺序、不断言究竟哪条语句阻塞（`_acquire_locks` 或 `_lock_resource` 均可接受，`TD-I-4`）；不加锁超时/重试逻辑（§12.4 不重试）。
- **夹具隔离**：hostname/IP 用 `f36-` 前缀；会话在线程内 `Session()` + `finally: close()`；每例前清库由 conftest 函数级 `TRUNCATE` 保证。

### TD-5 降级口径（环境不可用时如何如实记录）

| 缺失项 | 受影响用例 | 标注 | 禁止做法 |
| --- | --- | --- | --- |
| 真实 PG 不可达（`TEST_DATABASE_URL` 缺失/守卫拒绝/库不可达） | 全部 I 层（V2.*、V9.4、V10.1、V11.3–.4、V13.2–.6、V15.*） | **`BLOCKED`**（前置未满足），并单列原因与尝试过的命令 | 不得以 U/M/S 或构建代替；**V2 必须 `BLOCKED` 而非 PASS**；不得改用 SQLite/Mock |
| `pg_blocking_pids` 轮询超时（交错未命中） | `V2.1/V2.2` | **`BLOCKED`** 并附构造日志 | 不得改判 PASS，不得删断言换「无异常」断言 |
| 浏览器/Chromium 或候选构建不可用 | `V1.4`、`V5.2`、`V5.3` | **`NOT TESTED`**，写明原因 + 降级证据（机制级断言 + `V5.1` 静态核对） | 不得写成「DOM 已验证」；不得用 `smoke:client` 冒充界面验证 |
| B 层降级证据要求 | 同上 | 必须具备三要素：**视口尺寸**、**执行日期**、**截图或几何 JSON**（沿用 F035 `f035-browser-check.json` 记录格式，1440×1000 为既有基线，不改写） | 缺任一要素即 `NOT TESTED` |
| 候选后端/前端镜像非候选 HEAD | `V1.4`、`V5.*`（B） | `NOT TESTED` + 记录镜像与产物摘要 | 不得在旧镜像上取证后宣称通过 |
| 5000 行纯追加性能（F035-FU-08 / R-12） | — | **`NOT TESTED`**（契约无数值阈值）；触发条件按 `docs/database/f023-import.md` §5.7 复核，且**不得放松 V11.5 锁环判据** | 不得据单次抽测宣称性能达标 |
| 整体验收（需求 §31–33 跨功能） | — | 归后续整体验收；不得用本 Feature 局部 PASS 拼成整体 PASS | — |

### TD-6 判定标准

| 结论 | 条件 |
| --- | --- |
| **PASS** | 用例实际执行且断言全满足，命令 + 日志/JSON/截图齐备；`V2.*` 必须同时满足 `field`/`row`/`reason`/零残留四项硬判据 |
| **FAIL** | 与 A1–A14 / V1–V15 / DR-F036-* 不符：`field` 仍为 `resource`、载体切回 file 后仍可提交旧文件、`audit_logs`/`interfaces` 残留、placeholder 形似完整表头、MAC/口令仍有命中、已跟踪 artifacts 被测试改写、回归计数下降、`alembic head≠0015`、出现新增依赖/新端点/新字段 |
| **BLOCKED** | 前置缺失（PG/候选构建/交错未命中） |
| **NOT TESTED** | 已设计但未执行（含无浏览器时的 B 层），须写原因与降级证据，不得折算 PASS |
| **NOT_REQUIRED** | 仅限 TD-5 明列项（如 5000 行性能、整体验收）；不得用于掩盖缺失验证 |

缺陷按 `handoff.md` 格式（ID / Severity / Layer / Location / 证据 / 期望与实际 / 影响 / Owner / 是否必须修复）；相同根因沿用 ID。

### TD-7 数据完整性映射（data-integrity 口径）

| 规则 | 入口 | DB 保证 | 业务层 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §8.1 追加宿主存在且未软删 | F023 追加组 | 无（读侧 `deleted_at IS NULL`） | `_lock_resource` 加锁 + 未删校验（**不变**） | 锁定前并发软删 → 422、`field="hostname"`、零写入 | `V2.1/.2/.4` |
| §14 同 Cluster hostname 未删唯一 | 新建组 | `uq_resources_cluster_id_hostname_key` | `_attribute_integrity("hostname")` **不变** | 并发新建败方 `field="hostname"` | `V13.4`（F023 `pg05a`） |
| §24.6 / T118 既有 Resource 零改动 | 追加组 | 无 UPDATE 即无变化 | 不 stage Resource | 预锁串行化 | `V15.2`、`V13.2/.3` |
| T123 整批原子性 | 全部 | — | `_raise_validation_failed` + `db.rollback()` **不变** | 任一行失败零残留 | `V2.2` |
| 前端模板/凭证状态一致性 | 两导入面板 | — | 指纹 + 门控纯函数（算法不变，仅记忆化） | 载体切换清 `file` ⇒ `currentKey=null` ⇒ 不可确认 | `V1.*`、`V9.*` |
| 证据真实性 | F032 artifacts | — | 仅掩 `mac_address` 后 4 组，结构与行号不变 + sidecar 声明 | 不可与原始字节对比 | `V4.*` |

**Database：`NOT_REQUIRED`**（零 DDL；不引入新的数据库级不变量）——以 `V14.1` 的零漂移守卫与本表「实现未变」条目替代约束验证，不主张「新增约束已验证」。

### TD-8 Issues / 待裁定项（`TD-I-*`，交 CONTRACT Gate 裁定；不阻塞「可验证」结论）

| ID | 内容 | Owner |
| --- | --- | --- |
| `TD-I-1` | **架构事实偏差（HIGH for 范围）**：DR-F036-06 称 `setup.log`/`cli-smoke.log`「不在仓库树内」，实测 `git ls-files` 显示二者**均被跟踪**，且实测 **5 个被跟踪文件**命中 MAC 正则（3 CSV + `real-validate/setup.log`(9 处) + `cli-smoke.log`(2 处)）。A3/CHG-014 §1 item 3 的范围含这两个文件 ⇒ `V4.1` 按其**字面范围**断言命中 0（不缩窄），请 Architect 修正 DR-F036-06 的清单与脱敏格式适用性 | Architect → Tester/协调器 |
| `TD-I-2` | **口令掩码范围**：A7 写「仓库 grep 命中 0」，但实测 `docs/features/F032/test-report.md:394`（`csm:***@db:5432`）、`docs/features/F035/implementation.md:18` 等历史文档仍有明文，而 §8 禁止改写 F001–F035 历史报告。请裁定 F036 掩码扫描的**具体文件集合**（建议 `docs/features/F03{2,3,4,5}` 报告中**仅口令**行 + F036 自有文档），并明确「仓库级 0 命中」不作为 F036 验收判据 | Architect |
| `TD-I-3` | `RowError.reason` 精确文本：DR-F036-01 称不改 `_error_message` 输出（自由文本，F023 v2 §1.2 F035-RV-05）；§4.1 澄清行又给出具体文本。本 TD 只断言 `reason` **含** `does not exist or is not selectable`（子串），差异登记不判 FAIL。若要求逐字符固定，请裁定 | Architect |
| `TD-I-4` | `row` 期望值：单数据行批次固定 `row==2`（1-based）。多行组失败时契约只保证「组首行」（`interface_group.first_row`），本 TD 对多行场景只断言 `row ∈ 该组物理行集合`，不新增规则 | Architect（确认即可） |
| `TD-I-5` | 脱敏后 CSV 是否可作等价性证据：DR-F036-06 / R-8 已声明**不可**。请确认 `V4.3` 的表述，并确认等价性证据唯一来源为 `docs/features/F034/artifacts/equivalence-observations*.json` | Architect |
| `TD-I-6` | V13 基线可复现性：339/20/18/28/186/31/83 取自 F035 TE-3（不同 HEAD）。本 TD 在 TEST 开始时**先实测**这些数字并作为本轮基线（`≥` 比较），若某计数低于上表值则判 `BLOCKED` 并交协调器核对环境，而不是直接 FAIL 实现 | 协调器 |
| `TD-I-7` | V7 判据口径不一：DR-F036-04 写「示例仅 3 列」，V7 写「≤4 列」。本 TD 采用「数据行逗号数 ≤3 且列数 ≤4」的相容判据（覆盖两处措辞），不改设计 | Architect（确认即可） |
| `TD-I-8` | `_app_error_field` 的 `"resource"` 映射是否可能掩盖其他语义的 `_field_error("resource", …)`：本 TD 以 `V2.4` 的正向用例（真不存在/范围外仍 `hostname`）与 `V13.4` 归因回归共同约束，未发现冲突 | Backend（实现登记） |
| `TD-I-9` | 测试产物落点：DR-F036-08 的 `CSM_TEST_ARTIFACT_DIR` 默认系统临时目录；TEST 阶段需确认 CI/本地不会因沙箱只读临时目录失败（若失败按缺陷交 Backend/Tester，而非放宽 `V10.1`） | 协调器 |
| `TD-I-10` | F034-RV-02 仍待用户追认（需求 revision 15）：不属于 F036 交付，本 TD **不设**用例、不宣称关闭；若用户在本轮追认，需另立验证项 | Product / 用户 |

### TD-9 结论

**`TEST DESIGN READY`**

- V1–V15 全部用例化，共 **47 条** `TD3-F036-*`（U 9 / I 16 / S 20 / B 2，M 2 作为 U/S 宿主计入），逐条给出目标、层级、前置、步骤、期望与证据形式；A1–A14 全部有映射。
- 最高风险项 **V2**（并发软删归因）给出可强制交错的四步构造：独立会话 `FOR UPDATE` 持锁 → `pg_blocking_pids` 证实写入方阻塞 → 同事务服务层软删 + 提交 → 解阻塞后断言 `field="hostname"`/`row==2`/`reason` 子串/**四表零残留**，并配 `V2.3` 边界对照（软删在先 ⇒ 按新建，证明窗口真实命中）与 `V2.4` 不弱化对照。
- 降级口径（TD-5）明确：真实 PG 缺失 ⇒ I 层 `BLOCKED`（V2 尤其不得以单测代替）；浏览器缺失 ⇒ B 层 `NOT TESTED` + 三要素证据要求；5000 行性能与整体验收为 `NOT_REQUIRED` 并注触发条件。
- 发现 1 项架构事实偏差（`TD-I-1`：被跟踪的 `setup.log`/`cli-smoke.log` 仍含 MAC）与 9 条待裁定/登记项，**均不构成不可验证项**，故不返回 `TEST DESIGN BLOCKED`；请 CONTRACT Gate 在 §12 逐条裁定后再进入 TEST。
- 本阶段**未执行**任何测试、构建或 Git 变更命令；`TEST DESIGN READY` 不批准实现、Contract 定稿或合并。

## Git 声明

GIT: git status --short
GIT: git branch --show-current
GIT: git rev-parse --short HEAD
GIT: git log --oneline -6
GIT: git diff --stat a2e9194..HEAD
GIT: git ls-files docs/features/F032/artifacts
GIT: git ls-files docs/features/F034/artifacts
GIT: git check-ignore -v docs/features/F032/artifacts/real-validate/setup.log docs/features/F032/artifacts/real-validate/cli-smoke.log
GIT: git status --porcelain --ignored docs/features/F032/artifacts
GIT: git status --porcelain --ignored docs/features/F034/artifacts
GIT: git ls-files docs
