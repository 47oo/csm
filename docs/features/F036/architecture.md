# F036 F032–F035 Review 跟进项收敛 — ARCHITECTURE 阶段报告

- **状态**：READY FOR DESIGN（定稿与裁定见 §12，由 CONTRACT Gate 填写）
- **版本**：v1（2026-10-26）；ENABLER / P2 / M27；分支 `feature/F036-review-followup-closeout`；plan revision 22；**需求 revision 14（不变）**
- **上游依据**：`docs/features/F036/product.md` v1（READY FOR ARCHITECT；15 行映射 + A1–A14）；`docs/project/proposals/CHG-014`（APPROVED）；plan revision 22（`layers={database:false,backend:true,frontend:true}`、`api_required=true`）；缺陷原文 `docs/features/F03{2,3,4,5}/review-report.md`；已签核既有设计（消费不重开）`docs/features/F035/architecture.md` §12、`F034/architecture.md` §12、`docs/api/F023.md` **v2**；代码只读核对 `resource_interface_ip_import.py`、`interface.py`、两 form/两面板、`importCarrier.ts`、`index.css`、`smoke-client.mjs`、`collect_host_info.py`、`test_collect_host_info.py`、`test_f034_csv_text_carrier.py`；方法 `.pi/skills/{frontend-ui,data-integrity}/SKILL.md`。

## 1. 范围与性质

收敛型 ENABLER：只修 F032–F035 已交付内容的缺陷、忠实度与证据/文档精度，**不新增业务规则**；不改对象 / 关系 / 状态 / 唯一性 / 生命周期 / 权限项 / 错误码 / `reason` 枚举 / 响应字段 / 26 列模板与列序 / 字节与行数上限 / 端点 / Schema；需求 revision 保持 14。

用户可感知行为变化仅两项，且都是把实现拉回已批准口径：①`F034-RV-01` 界面状态须与提交值一致（§24.5 T116 忠实度）；②`F035-FU-01` `RowError.field` 恒为模板列名（§31 T67/T119/T120 与 F023 v2 §11）。

不承接：F034-RV-02（用户追认动作）；F032-RV-01/RV-04、F033-RV-02/04–08、F034-RV-05/RV-07、F035-RV-02/03/04/07/09/10、F035-FU-02/03/04/06/07。不重构、不加依赖、不做条目外清理。

## 2. 分层判定

| 字段 | 值 | 依据 |
| --- | --- | --- |
| `layers.database` | **false** | 唯一后端改动是错误标签词表 +1 项；零表/列/索引/约束/触发器/Migration；无 SQL 与锁序变更 |
| `layers.backend` | **true** | DR-F036-01；DR-F036-10 的两处注释（`scripts/collect_host_info.py`） |
| `layers.frontend` | **true** | DR-F036-02/03/04（两 form + 两面板）、DR-F036-05（`index.css`） |
| `api_required` | **true** | 仅 `docs/api/F023.md` §11 一条归因澄清（不升版、无新端点/字段/错误码/`reason`）；`docs/api/F014.md` 无影响 |
| DATABASE | **`NOT_REQUIRED`** | 零 DDL；不引入新的数据库级不变量 |

**零 DDL 机械守卫**：`git diff --stat` 对 `backend/alembic/**`、`backend/app/models/**`、`frontend/src/api/**` 为空；`alembic head` 仍 `0015`；26 列与上限常量零 diff。

## 3. 逐项设计

### DR-F036-01（F035-FU-01）`RowError.field` → 模板列 `hostname`

- **位置**：`backend/app/services/resource_interface_ip_import.py::_app_error_field`（:1318–1336），唯一调用点 `write_import` 的 `except AppError`（:1529–1536）。
- **方案**：既有 `mapped` 词表新增一条映射 + 注释：

  ```python
  # ``interface._lock_resource`` 以 ``_field_error("resource", ...)`` 表示
  # 「宿主不存在 / 已软删 / 不可选」；导入语境下行标识资源的列恒为 ``hostname``
  # （F023 v2 §11 归因澄清，F036 / F035-FU-01）。
  "resource": "hostname",
  ```

- **最小性**：`_app_error_field` 的唯一职责就是「Service Layer 点路径 → 冻结模板列名」，词表已有 3 条同类映射；不新增分支、不改控制流。放在调用处需先区分新建组/追加组再分别构造 `field`，代码更多且重复既有映射逻辑。
- **语义正确性（不止修标签）**：`_lock_resource` 的失败语义是「该行资源不可选」，模板中标识资源的就是 `hostname`（组键列，§8.1/§11）。映射对新建组/追加组通用。
- **不做**：不改 `interface.py::_lock_resource`（`include_deleted` + `deleted_at IS NOT NULL` 检测完整保留 ⇒ 并发软删仍捕获、仍整批 422、不弱化、不静默改新建）；不改 `_attribute_integrity`（`uq_resources_cluster_id_hostname_key → field="hostname"` 保持，F035 DR-F035-09）；不新增错误码 / `IMPORT_INVALID_FILE.details.reason` 取值 / 响应字段；不改 `_error_message` 产出的 `RowError.reason` 文本（自由文本，见 F023 v2 §1.2 F035-RV-05 澄清）；不改行号口径（1-based 物理行；多行组沿用 `interface_group.first_row`）。
- **风险**：R-1「`resource"` 语义若漂移会误导归因」（MEDIUM，靠 §11 澄清 + V2 用例 + 实现登记）；R-2「路径极窄、常规用例覆盖不到」（MEDIUM，V2 真实 PG 双会话强制争用）。

### DR-F036-02（F034-RV-01）载体切回「文件」时清空已选文件

- **位置**：`frontend/src/components/importForm.ts::importCarrierPatch`（:81–86）、`resourceInterfaceIpImportForm.ts::resourceInterfaceIpImportCarrierPatch`（:86–91）。**两面板无需改动**：切载体已走 `changeInput`（:155–161），它已重置 `localErrors`/`validateState`/`importState`/`validatedKey`。
- **方案**：目标载体为 `"file"` 时补丁追加 `file: null`：

  ```ts
  export function importCarrierPatch(values, carrier) {
    if (carrier === "text") return { carrier, format: "csv" };
    // 切回「文件」：原生 input 在文本载体下已卸载，重挂载后为空；
    // 保留 values.file 会让界面看不到文件却提交旧文件（F034-RV-01）。
    return { carrier, format: values.format, file: null };
  }
  ```

- **最小性**：不新增交互分支/确认弹窗；不复位 `text`；不改 `format` 规则（切 text 强制 csv、切回 file 保留当前 format 不回填历史 xlsx）。清值后 `importTargetKey` 返回 `null` ⇒ 既有门控（`canConfirm*` 要求 `validatedKey !== null && === currentKey`）自动使「确认导入」不可用。
- **T116 核对**：①切换载体仍全量失效旧结果（`validatedKey → null`）；②文本内容仍保留；③结果区空态语义不变 ⇒ 不破坏 T116，且补齐界面—提交值一致性缺口。
- **不做**：不清 `values.text`；切到 text 时不清 `file`（该值在 text 载体下不参与指纹与提交）；不改 `empty*Values`；不给 file input 加 `key`/`ref`（当前条件渲染，重挂载即空）。
- **测试面（必须同步，否则 smoke 必红）**：`frontend/scripts/smoke-client.mjs:8874-8899` 三处 `deepEqual(…CarrierPatch…)` 期望加入 `file: null`，并新增断言：切回 file 后 `importTargetKey === null`、`canConfirm* === false`。
- **风险**：R-3 file input 若改常驻挂载需 ref/key 复位（LOW，本次不做）；R-4 纯函数返回值由 2 键变 3 键（MEDIUM，内部 API，wire 零变化，实现登记）。

### DR-F036-03（F034-RV-06）哈希/字节计数记忆化

- **位置**：`ResourceImportPanel.tsx`（`currentKey`/`pastedByteLength`，:198–200）、`ResourceInterfaceIpImportPanel.tsx`（:224–227）；`useEffect, useState` → 追加 `useMemo`。
- **方案**：`currentKey = useMemo(() => importTargetKey(values), [values.carrier, values.format, values.file, values.text])`；`pastedByteLength = useMemo(() => values.carrier === "text" ? utf8ByteLength(values.text) : 0, [values.carrier, values.text])`。纯逻辑模块零改动。
- **键的理由**：两函数均为纯函数，输入恰为 `(carrier, format, file, text)`；四要素全列入依赖 ⇒ 依赖不变则输出不变；`values.text` 为字符串按值比较 ⇒ 同内容必命中同一结果，摘要（FNV-1a + djb2，按 UTF-16 code unit）与 UTF-8 字节数逐字节等于改前。
- **不做**：不改指纹算法/位数、不改 `importCarrier.ts` 导出、不引入 memo 库、不改门控语义；不缓存 `File` 字节（DR-F034-11 仍要求写入阶段按当前载体重新构造）；`useMemo` 是性能优化而非语义保证（不得据此删除 `changeInput` 复位）。
- **风险**：R-5 依赖漏项 ⇒ 陈旧指纹（HIGH，依赖集合固定四要素 + 「改 1 字符换 key」断言）；R-6 误当语义保证（LOW，注释写明）。

### DR-F036-04（F034-RV-03）文本载体 placeholder 明确为「片段」

- **位置**：文案抽为导出常量便于 U 层机械断言：`importForm.ts::IMPORT_TEXT_PLACEHOLDER`、`resourceInterfaceIpImportForm.ts::RESOURCE_INTERFACE_IP_TEXT_PLACEHOLDER`；两面板 `placeholder={…}` 引用常量。
- **规格（两面板同主体）**：

  ```
  示例片段（非完整表头，勿整段照抄；请先复制「查看模板」中的表头行）
  cluster,hostname,resource_type
  N96P,cn001,BARE_METAL
  ```

  第 1 行含「片段」；示例仅 3 列（取冻结模板前 3 列）；**不得**出现 26 列全列表头、不得以 `...` 模拟截断表头。`rows`、`aria-describedby`、字节计数、hint、错误呈现不变。
- **机械断言（A6）**：常量含「片段」；26 列面板常量不含 `TEMPLATE_COLUMNS.join(",")`；示例行逗号数 ≤3；不含 `...` 拼接。
- **风险**：R-7 仍可能被照抄（LOW，既有 hint 与「查看模板」路径继续承担；不新增本地表头校验）。

### DR-F036-05（F033-RV-03）≤1023px 导航焦点环可见性

- **位置**：`frontend/src/index.css` 窄屏块 `.app-nav .nav-link:focus-visible`（:981–985）。
- **成因（代码事实）**：`.app-nav` 在 ≤1023 为 `overflow-x:auto; overflow-y:hidden`（:958–968），滚动容器只绘制内边距盒内内容 ⇒ 外向 `outline`（全局 `outline-offset:3px`）与 `--csm-focus-ring` 外阴影被裁切；该规则又用 `box-shadow` 覆盖激活项的 `inset 3px 0 0`（current 左条）。
- **方案**：改内向聚焦环且不覆盖 `box-shadow`：

  ```css
  /* 滚动容器（overflow-x:auto / overflow-y:hidden）只裁切元素盒外内容，
     故窄屏把聚焦环画在元素内侧，任意滚动位置三边（含左右边缘）完整可见；
     不覆盖 box-shadow，激活项的 inset 左条（current 标识）保持原样。 */
  .app-nav .nav-link:focus-visible {
    outline: 3px solid var(--csm-primary);
    outline-offset: -3px;
  }
  ```

- **不越界**：不新增断点（仍在既有 `@media (max-width:1023px)` 内）、不动 `--csm-touch-target:44px`/`min-height`/`padding-inline`/`scroll-snap`/`.nav-scroller::after`、不动桌面侧栏；`outline` 不参与布局。
- **不做**：不给容器加 `padding-inline`（移动内容、破坏 snap）、不改 `overflow`（破坏横向滚动）、不加 `:focus-within` 容器环、不改全局 `--csm-focus-ring`。
- **证据（A4）**：视口 375 与 1023，聚焦首/末导航项，`scrollLeft=0` 与最大滚动各取样；判据 `getComputedStyle(link).outlineOffset === "-3px"` 且聚焦环矩形四边在 `nav` client 矩形内、激活项仍具背景与 inset 左条；记录视口与日期并截图。

### DR-F036-06（F032-RV-03）已入库证据 MAC 脱敏

- **范围（代码事实）**：仓库中命中 MAC 正则的仅 `docs/features/F032/artifacts/real-validate/{f032-bm-real.csv,f032-vm-nohost.csv,f032-vm-real.csv}`；`validate-*.json.raw`、`help.txt` 命中 0；`setup.log`/`cli-smoke.log` **不在仓库树内**（`.gitignore:124 *.log`、`:125 logs/`），以 `git ls-files`/`git check-ignore -v` 复核即可，不改写。
- **格式（确定性）**：`mac_address` 保留前 2 个八位组，后 4 组替换为字面 `xx`：`08:00:58:00:00:05 → 08:00:xx:xx:xx:xx`、`d8:b3:2f:5f:a8:1f → d8:b3:xx:xx:xx:xx`、`00:ff:14:65:ff:5b → 00:ff:xx:xx:xx:xx`。
- **回写**：逐字节仅替换对应单元格值；保留 BOM、表头行、26 列、4 行、列序、其余单元格与行尾。
- **标注**：新增 `docs/features/F032/artifacts/real-validate/REDACTION.md`（脱敏日期、规则、受影响文件与列、边界声明「仅掩盖 `mac_address` 后 4 组，结构与行号不变；运行摘要见同目录 `validate-*.json.raw`，比对结论不受影响」）；**不**在 CSV 内插注释行。
- **不做**：不改 `.gitignore`、不移动/删除证据、不重跑采集、不改写 F032/F034 报告结论。
- **机械断言（A3）**：MAC 正则命中 0；三 CSV 仍在且表头与行数不变；`REDACTION.md` 含「mac_address」与「xx」。
- **风险**：R-8 脱敏后与原始字节不等 ⇒ 禁止再作逐字节等价性证据（sidecar 声明）；R-9 证据中真实 `hostname`/内网 IP 仍在 ⇒ **超 CHG-014 范围**，登记观察项交 Product/用户。

### DR-F036-07（F032-RV-02）T79 CLI 自动化用例

- **位置**：`scripts/test_collect_host_info.py`，在既有 `EnhancementTests` 内新增 `test_cli_all_manual_params_written`；复用既有子进程模式（`:740-746`、`:815-821`）与 `_parse_csv` helper。
- **构造**：①BM 批：`--print --resource-type BARE_METAL --cluster F036CLI --role COMPUTE --status IDLE --network f036net` → `rc==0`，首行 == `FROZEN_COLUMNS`，全部数据行断言 `cluster/role/status/network/resource_type` 对应写入且 `host==""`；②VM 批：加 `--host f036host`、`--resource-type VIRTUAL_MACHINE` → `host` 列全为该值（采集列不断言，环境噪声）；③不带五个可选参数重跑 → 五列全为空串；④缺 `--resource-type` → `returncode != 0`、stderr 含 `--resource-type`、临时目录无新增文件。
- **为何子进程**：T79 验收对象是 CLI→列端到端路径（含 argparse `required`/`choices` 与 `_validate_args`），进程内 monkeypatch 无法证明 exit code 与零副作用。
- **不做**：不改脚本行为；不引入 pytest；不写仓库树（`--print` + `cwd=tmpdir`）。本文件计数 83 → ≥84。

### DR-F036-08（F034-RV-09）测试写回被跟踪 artifacts → 临时目录

- **位置**：`backend/tests/integration/test_f034_csv_text_carrier.py`（`ARTIFACTS` 常量 :47；写入 :239–241、:719–733）。
- **方案**：

  ```python
  import os  # stdlib

  def artifact_dir() -> Path:
      """测试产物落点：默认系统临时目录，可用 CSM_TEST_ARTIFACT_DIR 显式收集证据。"""
      base = Path(os.environ.get("CSM_TEST_ARTIFACT_DIR") or tempfile.gettempdir())
      out = base / "csm-test-artifacts" / "f034"
      out.mkdir(parents=True, exist_ok=True)
      return out
  ```

  两处写入目标改为 `artifact_dir() / "<同文件名>"`。
- **断言语义不变**：这两处写入不被任何断言读取（`observations` 仅用于本函数内比较与反空洞集合）；TD-5 `assert_equivalent`、TD3-T114、反空洞断言原样；已跟踪 JSON 作为 F034 历史证据冻结不改。
- **验证（A9）**：跑 `pytest tests/integration/test_f034_csv_text_carrier*.py` 后 `git status --porcelain` 为空；临时目录出现同名产物。

### DR-F036-09（F033-RV-01 / F034-RV-04 / F032-RV-06）证据与安全事实修正

| 子项 | 落点 | 做法 |
| --- | --- | --- |
| F033-RV-01 | F036 `test-report.md`（不改 F033 报告正文） | 记录实测命令（`cd frontend && npm run smoke:client`）、日期、实测计数（≥339）；说明 322/328 为历史值，F036 起以实测为基线 |
| F034-RV-04 | F036 `test-report.md` 证据表 | 用 `git ls-files docs/features/F034/artifacts` 与 `git check-ignore -v` 逐项列出实际入库（含 `logs/**`）与忽略集合，二者并列，不笼统称「logs 被忽略」 |
| F032-RV-06 | F036 文档 | 口令一律 `***`；断言 `grep -rnE "postgres(ql)?://[^:]+:[^@]+@" docs/features/F036` 命中 0（或仅掩码） |

### DR-F036-10（11a–11e）记载项（不改行为）

| 子项 | 落点 | 要点 |
| --- | --- | --- |
| 11a F032-RV-05 | `collect_host_info.py::build_error_hint` docstring | 「任意 argparse 错误统一追加三组枚举允许值」是 DR-1007 既有取舍；触发点 `_ArgumentParser.error()`；收窄须另立变更 |
| 11b F032-RV-07 | `collect_host_info.py::collect` docstring | `resource_type: str \| None` 仅供 `build_rows` 单测与防御边界；CLI 侧 `--resource-type` 仍 `required=True`；`_push` 防御检查保留 |
| 11c F034-RV-08 | §7 R-10 + F036 `test-report.md` | 表头级 `details.unknown_columns`/`missing_columns` 回显表头原文属 F014/F023 既有 schema、两载体逐字段一致；收紧须另立提案 |
| 11d F035-FU-05 | §7 R-11 + 证据表 | 登记既有 B 层视口（`f035-browser-check.json` = 1440×1000，不改写）；改追加提示区布局 ⇒ 必须补 375/1023 证据 |
| 11e F035-FU-08 | §7 R-12 | 5000 行纯追加性能仍 `NOT TESTED`；触发时按 `docs/database/f023-import.md` §5.7 复核；**不得放松 V11.5 锁环判据** |

### DR-F036-11 零依赖 / 零 Schema / 零 wire

不新增 npm 或 Python 第三方依赖（仅 stdlib `os`）；`frontend/src/api/**`（wire）、`ui/controls.tsx`、`ImportErrorsTable.tsx` 零 diff；无 `crypto.subtle`；26 列模板与上限常量零 diff；`.gitignore` 零 diff。

## 4. 契约影响

### 4.1 `docs/api/F023.md` §11 归因澄清（拟加精确文字）

- **位置**：§11「文件内重复与现存冲突」末尾（现 :185 之后），作为该节最后一条 bullet。
- **拟加文字**：

  ```markdown
  - **归因澄清（`F035-FU-01` / F036，2026-10-26，不升版）**：`RowError.field` 恒为冻结模板列名。① 追加组 Resource 级列与既有规范化值不一致 → `field` = 对应列名（`resource_type` 同样）；② 宿主在写入阶段因**并发软删 / 不再可选**导致资源侧锁定失败（`prepare_interface` 的 `_lock_resource`）→ `field="hostname"`（该行的资源标识列），`reason` 为服务层**自由文本** `resource does not exist or is not selectable`，`related_row=null`；③ 数据库唯一约束兜底仍按 §12.5 归因（`uq_resources_cluster_id_hostname_key` → `hostname`）。三种情形一律整批 422 `IMPORT_VALIDATION_FAILED`、行号为 1-based 物理行号、零写入残留；不新增错误码、`IMPORT_INVALID_FILE.details.reason` 取值、响应字段或模板列。
  ```

- **修订表**：§17 追加一行「v2 增补（F036）：§11 归因澄清（`field` 恒为模板列名，含并发软删竞态的组键列 `hostname`）；正文版本保持 v2」。
- **状态**：本 Gate = DRAFT；CONTRACT Gate 由 Architect 签核后 READY。`docs/api/F014.md` **无影响**（F014 不创建 Interface、不经过 `_app_error_field`）。

## 5. 数据完整性对照（data-integrity）

| 规则 | 入口 | DB 保证 | 业务层保证 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §14 同 Cluster hostname 未删唯一 | F023 新建组 | `uq_resources_cluster_id_hostname_key` | 二态判定 + `_attribute_integrity("hostname")`（**不变**） | 并发新建败方 `field="hostname"` | V13 既有用例 |
| §8.1 追加宿主存在且未软删 | F023 追加组 | 无（读侧 `deleted_at IS NULL`） | `_lock_resource` 加锁 + 未删校验（**不变**） | 锁定前被并发软删 → 422、`field="hostname"`（**本次修正点**）、零写入 | **V2（真实 PG）** |
| §24.6/T118 既有 Resource 零改动 | F023 追加组 | 无 UPDATE 即无变化 | 不 stage Resource | `FOR UPDATE` 串行化 | V13（F035 V2 用例） |
| T123 整批原子性 | 全部 | — | `_raise_validation_failed` + `db.rollback()`（**不变**） | 任一行失败零残留 | V2、V15 |
| 模板/凭证状态一致性（前端） | 两导入面板 | — | 指纹 + 门控纯函数（算法不变，仅记忆化） | 载体切换清 `file` ⇒ key=null | V1、V9 |
| 证据真实性 | F032 artifacts | — | 脱敏只改 MAC 值，结构与行号不变，sidecar 声明 | 不可与原始字节对比 | V4 |

**Database：`NOT_REQUIRED`**（无 Schema 交付；不引入新的数据库级不变量；`_lock_resource` 的加锁与未删校验原样保留）。

## 6. 验证策略（交 Tester 出 TEST_DESIGN）

| ID | 覆盖 | 层级 | product 判据 |
| --- | --- | --- | --- |
| V1 | 载体切回 file：`file` 置空、结果态重置、`currentKey=null`、`canConfirm*=false`；切 text 仍强制 csv、切回 file 不回填 xlsx | U（smoke 纯函数）+ B（浏览器留证，记视口） | A1 |
| V2 | **真实 PG 双会话**：追加组预校验通过 → 另一会话持 `resources` 行锁并软删宿主提交 → 写入锁争用后 `_lock_resource` 失败 ⇒ 422、`error_count≥1`、该行 `field=="hostname"`、`row==2`、`reason` 含服务层文本、零写入（interfaces/ip_addresses/audit_logs/resources 计数不变） | **I（必须真实 PostgreSQL）** | A2（前半） |
| V3 | 契约核对：§11 澄清行存在且措辞覆盖 `hostname`/自由文本/`related_row=null`/整批回滚；正文仍 v2；`F014.md` 零 diff | S | A2（后半） |
| V4 | 脱敏：MAC 正则命中 0；三 CSV 仍在且表头行数不变；`REDACTION.md` 含规则与影响列；logs 入库范围复核 | S | A3 |
| V5 | 窄屏焦点：375/1023 聚焦首末导航项（两种滚动位置）三边可见、current 标识保留；记录视口 | B（无 DOM 环境时人工留证 + 几何脚本） | A4 |
| V6 | smoke 基线：文档计数 == 实测计数且 ≥339，含命令与日期 | S + 实跑 | A5 |
| V7 | placeholder：常量含「片段」、不含完整 26 列表头、示例 ≤4 列、无 `...` 拼接 | U | A6 |
| V8 | 口令 grep 命中 0；入库范围表与 `git ls-files`/`check-ignore -v` 逐项一致 | S | A7 |
| V9 | 记忆化等价：同文本同 key/同字节数；改 1 字符（含中文/emoji）换 key；F034 等价性 60 例仍全 deep-equal | U + I | A8 |
| V10 | 测试洁净：跑 F034 套件后 `git status --porcelain` 为空；产物落临时目录 | I + S | A9 |
| V11 | T79 CLI：六参数写入、其余留空、缺 `--resource-type` 非零退出且零文件副作用 | CLI 子进程 | A10 |
| V12 | 记载项可 grep：11a–11e 与 F033-RV-01 条目 ID + 触发条件文字 | S | A11 |
| V13 | 回归计数不减少：`smoke:client` ≥339、F035 `20`、F035 验收+范围 `18`、F023 `28`、零回归集 `186`、F034 集成 `31`、`test_collect_host_info.py` ≥83（新增后 ≥84）；无新增 FAIL | I + 前端命令 | A12 |
| V14 | 守卫：`alembic head`=`0015`；alembic/models/api/模板/上限零 diff；`typecheck`/`build` exit 0；新增依赖 0 | S + 构建 | A13 |
| V15 | 权限与范围口径不变：401/403 与行级范围用例零 diff 且 PASS | I | A14 |

**环境前提**：真实 PG（`TEST_DATABASE_URL`）用于 V2/V9/V10/V13/V15；`-p csmtest` 栈仅用于需真 HTTP 的用例；不可用时标 `NOT TESTED`，不得以单测/构建代替。前端必跑 `typecheck && build && smoke:client`。**B 层局限**：仓库无 DOM/E2E 依赖（不加依赖），V1 的 DOM 断言与 V5 焦点可见性以「机制级断言 + 浏览器人工留证（记视口/日期/截图）」交付，不得写成「DOM 已验证」。

## 7. 风险登记

| ID | 风险 | 级别 | 处理 |
| --- | --- | --- | --- |
| R-1 | `"resource"` 映射语义漂移会误导归因 | MEDIUM | §11 澄清 + V2 用例 + 实现登记 |
| R-2 | 并发软删路径极窄，普通用例覆盖不到 | MEDIUM | V2 真实 PG 强制争用；不可跑则 `NOT TESTED` |
| R-3 | file input 若常驻挂载，清值不对齐控件 | LOW | 本次不加 ref/key |
| R-4 | `importCarrierPatch` 键数变化影响 smoke 期望 | MEDIUM | DR-F036-02 已列必改点；smoke 必须同步 |
| R-5 | `useMemo` 依赖漏项 ⇒ 陈旧指纹 | HIGH | 依赖固定四要素 + 「改 1 字符换 key」断言 |
| R-6 | 把 `useMemo` 误当语义保证 | LOW | 注释写明；`changeInput` 复位不可删 |
| R-7 | placeholder 仍被照抄 | LOW | 既有 hint 与「查看模板」路径不变 |
| R-8 | 脱敏后 CSV 与原始字节不等 | MEDIUM | `REDACTION.md` 声明边界；禁止作逐字节等价性证据 |
| R-9 | 证据中真实 `hostname`/内网 IP 仍在 | LOW | **超范围**，观察项交 Product/用户 |
| R-10 | 表头级 `unknown_columns` 回显表头原文 | LOW | 记载为既有 schema；收紧另立变更 |
| R-11 | B 层证据视口缺失 | LOW | 新证据必记视口；改布局须补窄屏 |
| R-12 | 5000 行追加性能未测 | LOW | `NOT TESTED` + 触发条件（§5.7，不放松 V11.5） |
| R-13 | 真实 PG 并发用例在受限环境不可跑 | MEDIUM | 明确 `NOT TESTED`，不得折算 PASS |

## 8. 变更边界

**禁止**：改错误码 / `IMPORT_INVALID_FILE.details.reason` 枚举 / 响应字段 / 26 列模板与列序 / 字节与行数上限 / 权限矩阵与 §23.2 / 端点与查询参数 / Schema·Migration·索引·约束·触发器 / 审计口径 / 整批原子性 / 行号口径；改 `interface._lock_resource` 或 `_attribute_integrity`；新增依赖；新增断点或改 44px、A1–A11 布局口径；重写 F001–F035 报告结论与历史证据；实现或宣称关闭 F034-RV-02。

**升级到用户/变更控制**：①需新增或收窄业务规则（含把并发软删改为「按新建处理」或「重试」）；②契约面变化（端点/字段/错误码/`reason` 集合/模板/上限/权限）；③出现 Schema 需求（`layers.database` 变 true）；④脱敏范围扩到 `hostname`/IP；⑤需 DOM/E2E 基础设施或新依赖；⑥plan `layers`/`api_required` 变更。

**普通设计内可自行调整**（登记实现报告）：注释措辞、`artifact_dir()` 名称、placeholder 常量名、`REDACTION.md` 排版、`useMemo` 拆分粒度。

## 9. Implementation Layers

| Layer | 内容 | 负责 |
| --- | --- | --- |
| L1 | DR-F036-08（测试产物临时目录）+ DR-F036-07（T79 CLI 用例） | Backend/Tester |
| L2 | DR-F036-01（词表映射）+ 新增 A2/V2 真实 PG 用例 | Backend |
| L3 | DR-F036-02/03/04（两 form + 两面板）+ `smoke-client.mjs` 期望同步 | Frontend |
| L4 | DR-F036-05（`index.css`）+ 375/1023 浏览器证据 | Frontend/Tester |
| L5 | DR-F036-06（脱敏 + `REDACTION.md`）+ DR-F036-09/10 | Tester/协调器 |
| L6 | §4.1 契约澄清签核 | Architect |
| L7 | 全量回归与守卫（V13–V15） | Tester |

`layers={database:false, backend:true, frontend:true}`；`api_required=true`（仅 §4.1）。

## 10. 待核对与事实偏差

1. **脱敏范围**：F032 证据中真实 `hostname`/内网 IP 保留（本次仅按 CHG-014 处理 MAC）；是否扩大属 Product/用户决定。
2. **F034-RV-02**：仍需用户追认（需求 revision 15）；F036 不实现、不宣称关闭。
3. **Base/start_commit 口径**（协调器已核）：F036 分支基点为 `a2e9194`（v3.3 上的文档收口提交），`023bced` 是 F036 的第一个功能提交（plan revision 22 批准记录）——`git.start_commit` = `a2e9194` 正确；Review 时 Base 取 `refs/heads/v3.3` 实测 SHA。
4. **plan `not_required.database` 文案**（协调器已改正为 F036 事实：零 DDL）。

## 11. 结论

全部条目落在 CHG-014 §1 与 requirements revision 14 的既有口径内：无新业务规则、无新端点/字段/错误码/`reason` 集合/模板/上限/权限、无 Schema 变更、无新依赖。两项用户可感知变化（F034-RV-01、F035-FU-01）均为把实现拉回已批准口径。**READY FOR DESIGN**（交 Database / Tester 检查；定稿见 §12）。

## 12. 定稿与裁定（CONTRACT Gate 填写）

- **状态**：`（待填）`
- **签核**：Architect，`（日期）`；本节与 §1–§11 冲突时以本节为准。
- **核对输入**：`（requirements revision 14 / plan revision 22 / Test Design 版本 / Database 结论 / F023 澄清行签核状态）`
- **Contract 状态**：`（本 Gate DRAFT；CONTRACT 签核后 READY）`
- **layers**：`{database:false, backend:true, frontend:true}`；`api_required=true`
- **定稿裁量表（对 Tester `TD-I-*`）**：`（待填）`
- **一致性核对**：`（设计 ↔ 契约 §11 ↔ Test Design ↔ V2 判据）`
- **技术决策冻结**：DR-F036-01…11
- **变更边界**：绑定 `（requirements revision 14 / plan revision 22 / F023 v2 + §4.1 澄清 / Test Design / Database NOT_REQUIRED）`
- **后续关注**：R-1…R-13、§10 两项上游确认

NEXT: TEST_DESIGN
