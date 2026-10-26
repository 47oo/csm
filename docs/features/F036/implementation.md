# F036 F032–F035 Review 跟进项收敛 — IMPLEMENTATION 阶段报告

- **版本**：v1（2026-10-26）；plan revision 22；需求 revision 14（不变）
- **状态**：**BACKEND COMPLETE / FRONTEND COMPLETE / DATABASE NOT_REQUIRED 确认**；证据与记载项见 `docs/features/F036/evidence-notes.md`（DR-F036-06 脱敏记录见 `docs/features/F032/artifacts/real-validate/REDACTION.md`）。

## 1. Backend

Backend（2026-10-26，F036 IMPLEMENTATION Gate，分支 `feature/F036-review-followup-closeout`；DR-F036-01 / 07 / 08 / 10 全部落地）。写入面：`backend/app/services/resource_interface_ip_import.py`、`backend/tests/integration/test_f036_attribution.py`（新增）、`backend/tests/integration/test_f034_csv_text_carrier.py`、`scripts/collect_host_info.py`（仅 docstring）、`scripts/test_collect_host_info.py`。零错误码 / `reason` 枚举 / 响应字段 / 模板 / 上限 / 权限 / 端点 / Schema 变更；零新依赖（仅 stdlib `os`）。

### 1.1 逐项落地

| 条目 | 文件:行 | 落地内容 |
| --- | --- | --- |
| DR-F036-01（F035-FU-01） | `backend/app/services/resource_interface_ip_import.py:1331-1345` | `_app_error_field` 的 `mapped` 新增第 4 条 `"resource": "hostname"`（`:1343`）+ 8 行注释（`:1335-1342`）说明产生点（`interface._lock_resource`）、语义（行资源标识列恒为 `hostname`，F023 v2 §11）与 TD-I-8 登记位置。未改 `_error_message` / `_field_error` 文案、`_lock_resource`、`_attribute_integrity`、`_acquire_locks`（均零 diff）；未新增分支，未知点路径仍走 `_template_field` 兜底 |
| DR-F036-01 真实 PG 用例（V2） | `backend/tests/integration/test_f036_attribution.py:295-522` | `_race_soft_delete_during_write`（`:295`）固定交错：会话 B `SET TRANSACTION ISOLATION LEVEL READ COMMITTED` → `SELECT … FOR UPDATE` 持 `resources` 行锁 → 线程 A（`:236` `_Writer`，独立会话、显式 READ COMMITTED、先报 backend pid）调 `write_import` 在 `_acquire_locks` 阻塞 → `pg_blocking_pids` 轮询（`:326`，20s 期限，超时以 **BLOCKED** 措辞失败，不靠固定 sleep）证实交错 → B 同事务走 `resource_service.delete_resource`（内部 commit）→ A 解阻塞、`_lock_resource` 失败。三用例：并发软删归因（`:374`，断言 422 `IMPORT_VALIDATION_FAILED`、`field=="hostname"`、`row==2`、`reason` 含子串 `does not exist or is not selectable`、`related_row is None`、`interfaces`/`ip_addresses`/`resources` 计数与窗口内 `CREATE` Audit 均不变）；多行组（`:423`，`row ∈ {2,3}`，TD-I-4）；对照（`:473`，软删早于写入预校验 ⇒ `created==1`）。两会话与失败信息均记录实测隔离级别（断言 == `read committed`） |
| DR-F036-01 单测（V2.5，TD-I-8 守卫） | `test_f036_attribution.py:231`、`:275` | AST 读回 `mapped` 字面量并精确断言**恰四项**（`address→ip`、`virtual_machine.host_resource_id→host`、`interface→name`、`resource→hostname`，无新增键）；`_app_error_field` 行为断言四项 + 兜底（`hardware.model→model`、空→`resource_type`）；AST 枚举 `_field_error("resource", …)` 代码产生点 == 既定 4 处（新增产生点即失败，强制复核语义） |
| DR-F036-08（F034-RV-09） | `backend/tests/integration/test_f034_csv_text_carrier.py:50-77`、`:267`、`:748` | 原 `ARTIFACTS = REPO_ROOT/docs/features/F034/artifacts` 改为 `artifact_dir()`（`CSM_TEST_ARTIFACT_DIR` 或 `tempfile.gettempdir()`，子目录 `csm-test-artifacts/f034`）+ `write_artifact()` 写助手；目录/文件不可写即 `pytest.skip` 并登记（TD-I-9），**绝不回退仓库树**；两处产物文件名不变、断言语义不变；已跟踪 JSON 冻结不改 |
| DR-F036-07（F032-RV-02） | `scripts/test_collect_host_info.py:392-457` | 新增 `test_cli_all_manual_params_written`（`EnhancementTests`，子进程 + 临时 cwd，`--include-loopback` 仅使采集行数与硬件无关）：①BM 批 `cluster/role/status/network/resource_type` 写入且 `host==""`；②VM 批 `host` 写入；③不带五个可选参数重跑五列全 `""`；④缺 `--resource-type` 非零退出、stderr 含 `--resource-type`、临时目录零新增文件 |
| DR-F036-10（11a/11b，仅注释） | `scripts/collect_host_info.py:656-665`、`:480-490` | `build_error_hint` docstring 记载「任意 argparse 错误统一追加三组枚举允许值」属 DR-1007 既有取舍、触发点 `_ArgumentParser.error()`、收窄须另立变更；`collect` docstring 记载 `resource_type: str \| None` 仅供 `build_rows` 单测与防御边界、CLI 侧 `--resource-type` 仍 `required=True`、`_push` 防御检查保留。零行为变更（diff 仅 docstring 行） |

**TD-I-8 登记：`_field_error("resource", …)` 全部产生点**（`grep -rn '_field_error("resource"' backend/app/` + AST 枚举，2026-10-26 实测）：

| 位置 | 语句 | 导入路径可达 | 归因 |
| --- | --- | --- | --- |
| `app/services/interface.py:156` | `_lock_resource`：`resource does not exist or is not selectable` | **是**（`prepare_interface` → `_lock_resource`） | `field="hostname"`（本次修正点） |
| `app/services/service.py:111` | `resolve_resource`：`resource is required` | 否（POST body 解析） | 不经过 `_app_error_field` |
| `app/services/service.py:116` | `resolve_resource`：`resource must be a valid UUID` | 否 | 同上 |
| `app/services/service.py:124` | `resolve_resource`：`resource does not exist or is not selectable` | 否 | 同上 |

（`grep` 另命中 `_app_error_field` 内注释行 `:1336` 的同一字面量，属文档串而非调用点；AST 枚举已排除。）

### 1.2 验证（实际执行）

环境：`export TEST_DATABASE_URL='postgresql+psycopg://csm:***@127.0.0.1:55432/csm_test'`（容器 `csm-f035-pg`，PostgreSQL 16.15），命令均从 `backend/` 或仓库根执行。

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `python3 -m pytest tests/integration/test_f036_attribution.py -q` | **5 passed**（V2.5 ×2、V2 并发软删、多行组、对照） |
| 2 | `python3 -m pytest tests/integration/test_f023_resource_interface_ip_import.py -q` | **28 passed**（零回归） |
| 3 | `python3 -m pytest tests/integration/test_f034_csv_text_carrier.py tests/integration/test_f034_csv_text_carrier_scope.py -q` | **31 passed** |
| 4 | `python3 -m pytest scripts/test_collect_host_info.py -q`（仓库根） | **84 passed**（基线 83，+1 为新用例，≥84） |
| 5 | 产物落点核对 | 三份 JSON 出现在 `/tmp/csm-test-artifacts/f034/`；运行前后 `git status --porcelain` 快照 `diff` **完全一致**；`git status --porcelain -- docs/features/F034 docs/features/F032 docs/features/F035` **为空**（未回退仓库树） |

### 1.3 Contract / Database 影响

- Contract：仅落实现 `docs/api/F023.md` §11 归因澄清 bullet（`field` 恒为冻结模板列名，含并发软删的标志列 `hostname`；`reason` 自由文本，TD-I-3 只断子串；`related_row=null`）。无错误码 / `IMPORT_INVALID_FILE.details.reason` 取值 / 响应字段 / 模板列增删。
- Database：**`NOT_REQUIRED` 不变**（`alembic head` 仍 `0015`、零 DDL、零数据操作）；`_lock_resource` 的 `FOR UPDATE` + `deleted_at` 读侧校验、`_attribute_integrity` 的 `uq_resources_cluster_id_hostname_key → hostname` 全部零 diff。V2 以 PG 默认 READ COMMITTED 为前提，已在两会话内显式 `SET` 并断言实测隔离级别。
- data-integrity：§8.1 追加宿主存在且未软删 → 并发软删败方 422 + 零写入，由 SAVEPOINT +`db.rollback()`（T123 不变）+ 真实行锁串行化保证，用例零残留断言覆盖 `interfaces` / `ip_addresses` / `resources` / `CREATE` Audit。

### 1.4 未验证项

1. **B 层 / 前端证据不在本角色范围**（DR-F036-02…09 的前端与证据项由 Frontend / Tester 交付）。
2. **REPEATABLE READ 下的行为未测**：设计已裁定该竞争会变为 40001 → 500 `INTERNAL_ERROR`（既有行为），按 BLOCKED 记录，未在本分支实测（未改产品隔离级别）。
3. **F035 追加导入回归套件未在本角色重跑**：`_app_error_field` 只改变此前未映射的 `resource` 原始值 → `hostname`，`grep` 确认 F035/F023/F034 用例中无 `field=="resource"` 断言；F023 `pytest -q` 28 项已作为直接回归守卫（F035 全量属 Tester 的 TEST 阶段）。
4. **DR-F036-10 无新用例**：纯注释登记，由既有 84 项脚本用例证明零行为变更。

## 2. Frontend

Frontend（2026-10-26，F036 IMPLEMENTATION Gate，分支 `feature/F036-review-followup-closeout`；DR-F036-02/03/04/05 全部落地）。写入面：`frontend/src/components/{importForm.ts, resourceInterfaceIpImportForm.ts, ResourceImportPanel.tsx, ResourceInterfaceIpImportPanel.tsx}`、`frontend/src/index.css`、`frontend/scripts/smoke-client.mjs`。零依赖、零 wire、零模板常量 diff。

### 2.1 逐项落地

| 条目 | 文件:行 | 落地内容 |
| --- | --- | --- |
| DR-F036-02（F034-RV-01） | `importForm.ts:75-92`、`resourceInterfaceIpImportForm.ts:82-99` | 目标载体为 `"file"` 时补丁返回 3 键且含 `file: null`（切 `"text"` 仍只返回 `{carrier, format:"csv"}`，不清 `file`/`text`）；注释写明「input 重挂载为空 ⇒ 界面与提交值须一致」与「清值后 key=null ⇒ 既有门控自动禁用确认导入」。**两面板未改**（切载体走 `changeInput` 已重置结果态） |
| DR-F036-03（F034-RV-06） | `ResourceImportPanel.tsx:199-212`、`ResourceInterfaceIpImportPanel.tsx:225-238` | `currentKey` 用 `useMemo`，依赖恰为 `[values.carrier, values.format, values.file, values.text]`；`pastedByteLength` 用 `useMemo`，依赖 `[values.carrier, values.text]`；两处注释「仅省算力，语义不依赖缓存」。指纹算法 / `importCarrier.ts` 零改动 |
| DR-F036-04（F034-RV-03） | `importForm.ts:198-208`（`IMPORT_TEXT_PLACEHOLDER`）、`resourceInterfaceIpImportForm.ts:228-238`（`RESOURCE_INTERFACE_IP_TEXT_PLACEHOLDER`）、`ResourceImportPanel.tsx:311`、`ResourceInterfaceIpImportPanel.tsx:377` | 文案抽为导出常量，两面板 `placeholder={…}` 引用；内容 `示例片段（非完整表头，勿整段照抄；请先复制「查看模板」中的表头行）` + 表头行 `cluster,hostname,resource_type` + 数据行 `N96P,cn001,BARE_METAL`（示例数据行 3 列，满足 TD-I-7「≤4」唯一判据；无 26 列 `join(",")`、无 `...`）。`rows` / `aria-*` / 字节计数 / hint / 错误呈现不变 |
| DR-F036-05（F033-RV-03） | `index.css:981-990` | 窄屏 `.app-nav .nav-link:focus-visible` 改为 `outline: 3px solid var(--csm-primary); outline-offset: -3px;`，**删除** `box-shadow: var(--csm-focus-ring)` 覆盖（激活项 inset 左条保留）；注释说明 `overflow-x:auto / overflow-y:hidden` 滚动容器裁切盒外 outline。未新增断点，未动 44px / `padding-inline` / `scroll-snap` / `overflow` / 桌面侧栏 / 全局 `--csm-focus-ring` |
| smoke 期望同步（R-4） | `smoke-client.mjs:8884-8952`、`8954-8993`、`8868-8876` | 三处 `deepEqual(…CarrierPatch…)` 期望补 `file: null`；新增切回 file 后 `resourceInterfaceIpImportTargetKey === null`、`canConfirmResourceInterfaceIpImport === false`、`importTargetKey === null`、`text` 保留断言；新增占位符常量用例（含「片段」/ 非完整表头 / 示例行字段数 ≤4 / 无 `...`·`…` / 两常量同主体）；文本指纹用例新增 emoji（代理对）改 1 字符换 key + 同文本同 key 断言 |

### 2.2 验证（实际执行）

- `cd frontend && npm run typecheck` → exit 0（无输出错误）。
- `cd frontend && npm run build` → exit 0（`✓ built in 18.18s`，仅既有 chunk >500kB 提示）。
- `cd frontend && npm run smoke:client` → **340 passed, 0 failed**（改动前基线 339 passed, 0 failed；+1 为新增「F036 文本占位符常量」用例，其余为既有用例内新增断言）。均 ≥339，无 FAIL。
- 负向对照（不进仓库，`/tmp` 一次性脚本）：以 26 列全列表头 + `N96P,...` 构造的坏 placeholder 在「含片段 / 不含 26 列 / 无 `...`」三项上均被判否，证明新断言具备区分力。

### 2.3 守卫与零 diff

- `git diff --stat` 显示改动仅上述 6 个在册文件（另 `backend/app/services/resource_interface_ip_import.py` 为 Backend 角色的并行改动，非本角色写入）。
- `git diff --stat -- frontend/src/api frontend/package.json backend/alembic backend/app/models` → **空**（wire / 依赖 / Schema 零 diff）；`RESOURCE_INTERFACE_IP_TEMPLATE_COLUMNS`、`IMPORT_MAX_FILE_BYTES`、`IMPORT_MAX_ROWS` 零 diff；未新增 npm 依赖；未新增或修改断点。
- 契约符合：DR-F036-02 不新增交互分支/确认弹窗、不复位 `text`、不改 `format` 规则；DR-F036-03 不改指纹算法与位数、不改门控语义（`changeInput` 复位保留）；DR-F036-04 不改服务端权威（表头仍以 templates 端点 /「查看模板」为准）；DR-F036-05 仅 `outline`（不参与布局）。

### 2.4 未验证项与交接

1. **窄屏焦点环浏览器证据（A4/V5）未做**：仓库无 DOM/E2E 依赖（F036 禁新增），本角色只交付机制级 CSS 改动与理由注释；375 / 1023 视口下聚焦首末导航项、`scrollLeft=0` 与最大滚动各取样的截图与 `getComputedStyle(link).outlineOffset === "-3px"` 几何核对由 Tester 在 B 层执行（须记视口与日期）。
2. **DR-F036-02 的 DOM 层证据未做**：切回「文件」后原生 input 重挂载为空、界面无文件、确认导入按钮 `disabled` 的浏览器观测属 B 层（本资产只做纯函数 + 门控断言）。
3. **真实 API / Mock**：本次未新增 Mock，未改 `frontend/src/api/**`；Mock 通过不等于集成通过，端到端由 Tester 的 V13/V15 覆盖。
4. **useMemo 的运行时收益未度量**：属性能优化，不作为语义保证；不做基准测量（无需求依据）。

FRONTEND COMPLETE（仅前端实现与适用验证；契约冲突无；窄屏浏览器证据与全量回归按 §6 交 Tester）。

## 3. Database（NOT_REQUIRED 确认）

Database（2026-10-26，F036 DATABASE Gate）结论 **`DATABASE NOT_REQUIRED CONFIRMED`**（`layers.database=false`），四项判定：

1. **零表/列/索引/约束/触发器/Migration**：唯一后端改动为 `_app_error_field` 词表 +1（`"resource": "hostname"`，纯字符串映射）；`_lock_resource` / `_attribute_integrity` / `_acquire_locks` 零 diff；`alembic head` 仍 `0015`（守卫归 V14）。
2. **词表不需 DB 支持**：`RowError.field` 是响应字段取值（冻结模板列名），DB 不参与归因；23505 / CHECK / 触发器仍由 `_attribute_integrity` 按 `diag.constraint_name` + 消息口径归因（F023-DB-02 不变）。
3. **并发软删由既有行锁 + 读侧校验兜底，归因属应用层**：`_lock_resource` 以 `include_deleted=True` 取 `FOR UPDATE`，获锁后重读 `deleted_at` → `_field_error("resource", …)` → 整批 422。DB 提供的是既有 PK 行锁的串行化与 READ COMMITTED 获锁后重读语义，非新增对象。不能表达为数据库不变式的理由：`resources.deleted_at` 经软删入口合法变更；FK RESTRICT 只证行存在（软删行仍在）；部分唯一索引只约束未删行标识唯一；CHECK/触发器无法区分「宿主随后被合法软删」与「追加非法」——与 `docs/database/f023-import.md` §5.5 同型（入口级行为规则）。
4. **足以支撑 V2 断言**：422 来自应用层 AppError 路径；零写入由 `write_import` 的 `db.rollback()`(:1539，T123) 保证；三条部分唯一索引（均 `WHERE deleted_at IS NULL`）只仲裁 23505 身份冲突，与本场景正交。

无回填、无升级动作、无回滚风险（退回仅撤销词表一行，无数据状态需还原）；无新索引（§5.6 查询谓词与既有部分唯一索引完全匹配）。

**Issue 状态**（`docs/database/f023-import.md` §5.9）：`F023-DB-01` CLOSED（不变，`_acquire_locks` 零 diff）；`F023-DB-02` / `F023-DB-03` 继续有效；`F035-DB-NOTE-01` 继续有效；**新增 `F036-DB-NOTE-01`**（NOTE）：`RowError.field` 的并发软删归因标签 `resource` → `hostname` 属应用层/契约层措辞修正（F023 v2 §11 澄清），不改 DB 对象、不改约束归因口径、不引入新不变量。

**环境前提（交 Tester）**：V2 的 422 期望以 PG 默认 **READ COMMITTED** 为前提（`core/db.py` 未设 `isolation_level`）；若测试会话为 REPEATABLE READ，同一竞争返回 40001 → 500 `INTERNAL_ERROR`（既有行为，F036 未改），V2 须记录隔离级别。

**观察项（非阻塞，交 Architect）**：`docs/database/f023-import.md` §5.7 第 6 项字面「预校验→写入间宿主被软删 ⇒ 报错需要 DB 侧支持」与 F035 已交付实现（既有 `FOR UPDATE` + 读侧校验，无需 DDL，§5.8 已如此记载）存在读法差异；建议在 CONTRACT §12 记录该读法。两种读法下 F036 均零 DDL。
