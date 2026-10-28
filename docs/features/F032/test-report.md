# F032 采集脚本类型必填、帮助信息与按类型生成 — TEST 报告

- **Task**：F032 / TEST_DESIGN + TEST（Tester）；writeScope `docs/features/F032/test-report.md` 与 `docs/features/F032/artifacts/`。
- **状态**：TEST_DESIGN 有效版本 **TD-2 / v2 / 2026-10-23（§11，结论 TEST DESIGN READY）**；TEST 执行有效版本 **TR-1 / v3 / 2026-10-23（§12，结论 READY FOR REVIEW）**。TD-1 / v1（§1–§10）保留为历史基线（失效/增量范围见 §11.1）；§9 与 §11.6 记录的 `NOT TESTED` 已由 §12 取代，历史文本不删除。
- **Basis**：
  - `docs/product/requirements-v3.md` **revision 12**：§24.4（CONFIRMED 全节）、经 §24.4 修订的 §24.2 / §24.3、§31 T100–T106 与修订后的 T73 / T79 / T84、§35.1 revision 12 确认记录。
  - `docs/features/F032/product.md` v1（READY FOR ARCHITECT；A1–A11）；`docs/features/F032/architecture.md` **v2**（2026-10-23，READY FOR DESIGN；DR-1001–DR-1016、ON-1、R-1–R-7；含吸收 TD-D01–TD-D03 的 DR-1015 / DR-1016 与 DR-1004 / DR-1008 修订）。TD-1 依据的 architecture v1 已被 v2 取代，差异见 §11.1。
  - `docs/database/f032-collector-cli.md`（Database 2026-10-23 签核 `NOT_REQUIRED`）：F032 无 Schema / Migration / 索引 / 约束 / 回填变更，TD-2 已逐项核对该签核与 §5 契约核对结论一致。
  - `docs/api/F023.md` v1 §5 / §6（消费，零改动）；`docs/api/F014.md` v1（零改动）。
  - `docs/project/project-plan.yaml` plan_revision 18（用户 2026-10-23 批准）；F032 `git.start_commit=89a5d4ff61f9df35f8f4393887701e7015bc26d8`、`git.base_branch=v3.3`、`git.branch=feature/F032-collector-help-type-import`。
  - 既有基线：`docs/features/F024/test-report.md`（T73–T78）、`docs/features/F025/test-report.md`（T79–T84）、`docs/project/implementation-rules.md`（验证与交付）、`docs/project/handoff.md`（交接与缺陷格式）。
- **规范应用**：本次无数据库/持久化变更，`.pi/skills/data-integrity/SKILL.md` 逐表判定为 `NOT_REQUIRED`（无唯一性、生命周期、并发、Migration 变更）；唯一完整性相邻项是「内嵌 26 列模板与 F023 §6 冻结列集一致」的守卫测试（T78 既有 `TemplateDriftTests`）。

---

## 1. TEST DESIGN（TD-1，历史基线 / v1）

> **TD-2 提示**：本节及 §2–§10 为 TD-1 / v1 原始记录，保留历史证据用途。其中已被 TD-2 替换的条目（T100 / T102 / T105 映射增补、§4.1 B-21–B-23 裁定、§10 TD-D01–TD-D03 关闭）以 §11 为准；未被点名的条目继续有效，不需要重做。

- **TD 编号 / 版本 / 日期**：**TD-1 / v1 / 2026-10-23**
- **结论**：**TEST DESIGN READY**
- **含义边界（重要）**：READY **仅表示** T100–T106 与 T73 / T79 / T84 的验收点已被映射为可观察、可重复执行的验证项，环境与夹具方案可行；**不表示任何用例已通过，不构成实现批准、Review 通过或合并许可**。实现完成后须按 §8 实际执行并另出 `TEST` 版本记录与证据（§9）。
- **核对版本**：product.md v1、architecture.md v1、requirements revision 12、F023 §5/§6 v1。若上游任一版本变更（尤其 §24.4 口径、DR-1001–DR-1010、F023 §6 列集），本 TD 失效并重做。
- **Database 设计差异核对**：F032 `database: NOT_REQUIRED`（架构 §4、plan `not_required.database`）；本 TD 无 DB 断言项，与最终数据库设计无差异需要吸收。若 Test 阶段发现脚本改动引入任何写入/迁移需求，本 TD 立即失效并返回 Architect。

---

## 2. 环境与可验证性

### 2.1 本次可验证性探测（本日只读检查，作为设计可行性证据）

| 项 | 结果 | 意义 |
| --- | --- | --- |
| `python3 --version` | `Python 3.12.7` | 满足"仅标准库、Python 3.8+"基线 |
| `ip -j addr` | 可用（OK） | 真实采集路径可执行，T73/T104 的真实运行可行 |
| `python3 scripts/collect_host_info.py --print --no-header --resource-type BARE_METAL` | rc=0，输出 3 条数据行、26 列、业务字段空、`ip` 带 `/24` 掩码 | 本机可作为"代表性 Linux 主机"执行真实采集冒烟（当前为 F032 变更前的实现，故尚不含 T100–T106 行为） |
| `docker images` | `csm-csm-backend:test`、`csm-csm-frontend:test` 已构建 | 真实 F023 `/validate` 预校验栈具备启动前提 |
| `docker compose -f compose.test.yaml ps` | 空（栈当前未运行） | 真实预校验需先启动测试栈（§7），否则如实记 NOT TESTED |
| `.env.test` | 存在（`NGINX_HTTP_PORT=18080`、`DATABASE_URL` 指向测试库） | 端口与测试库约定可用 |
| `git status --porcelain=v1` | clean | 测试执行不会误判实现改动来源 |
| `git diff --stat 89a5d4f -- docs/api docs/product scripts .gitignore` | 空 | T106 契约零 diff 基线 `${start_commit}` 有效 |

### 2.2 执行环境要求

- **单元/CLI 层**：Linux 或 macOS，Python 3.8+，仅标准库；无需 root、无需网络、无需真实硬件。测试必须可在无 `nvidia-smi` / `lspci` / DMI 的容器内通过（缺失即留空）。
- **真实运行冒烟（T73 / T104 / T84）**：代表性 Linux 主机（本机或 `csmtest` 栈容器内）；`ip` 可用；`--print` 形式执行以避免污染工作区。
- **真实 F023 预校验（T77 / T102 / T103 / T106 的端到端部分）**：`compose.test.yaml` + `docker compose -p csmtest` 测试栈，API `http://localhost:18080`，测试 PostgreSQL；**禁止**指向生产或未知数据库/环境。
- **测试隔离规则（强制）**：
  1. 断言默认文件名（相对路径）的用例必须 `tempfile.TemporaryDirectory()` + `os.chdir`，并在 `finally` 恢复 cwd；测试结束 `git status --porcelain=v1` 仍为 clean，仓库工作区不得出现 `csm_host_info*.csv`。
  2. 采集函数、`collect()`、`post_import()`、`urllib.request.urlopen` 一律以 injected/monkeypatch 方式替换，避免真实网络与真实主机依赖；`main()` 的 `SystemExit(2)` 必须被 `assertRaises` 捕获，不能逃逸到测试进程。
  3. `--push` 用例只允许请求 `http://localhost:18080`；`--yes` 仅在本 Feature 显式声明"写入语义无回归"的用例中使用，且只对 `F032*` 前缀夹具。默认**不写入**（T100–T106 无写入要求）。
  4. 夹具命名前缀 `F032`（Cluster `F032CHK`、Network `F032-MGMT`、Host `f032host`、API Key label `f032-validate`），便于识别与清理；不得复用或改动既有 Feature 的历史夹具。

### 2.3 可验证性结论

- **可观察面充分**：退出码（2/1/0）、stderr/stdout 文本、文件存在性与内容、`parser.choices` 与 help 常量一致性、monkeypatch 探针（网络/采集是否被调用）、真实 `/validate` JSON，均为确定性可观测量。
- **无需新增可观察面**：现有 CLI 已输出行数/列数提示到 stderr，`_push` 返回码语义明确（§24.4 未要求新输出格式，TD 不为可测性发明新行为）。

---

## 3. 验收映射表（T100–T106 + 修订后的 T73 / T79 / T84）

测试文件：`scripts/test_collect_host_info.py`（新增类名/用例名为本 TD 建议，实现阶段可微调命名，但**断言语义不得弱化**）。

| 验收 | 验收点（来自 §24.4 / §31） | 验证项（自动化） | 手工/端到端 | 类型 |
| --- | --- | --- | --- | --- |
| **T100** | `--help` 标注 `--resource-type` 必填并列出两类型；`--role`/`--status` 列全部允许值；`--cluster`/`--host`/`--network` 说明引用对象与"须已存在"；按「模板必填」与「`--push` 必填」分区；与真实行为一致 | `CliHelpTests.test_help_marks_type_required_with_both_values`；`…test_help_lists_all_role_values` / `…status_values`；`…test_help_has_template_required_section` / `…push_required_section`（含"脚本必填 ≠ 模板必填"与"未给 `--cluster` 仍可离线生成"表述）；`…test_help_reference_semantics`（cluster code/UUID、host hostname/UUID、network name/CIDR + "须已存在且未软删"）；`…test_epilog_values_equal_parser_choices`（DR-1014 一致性守卫）；`…test_help_makes_no_network_call` | `python3 scripts/collect_host_info.py --help` 人工通读，与上述断言逐条对照 | 单元 + 手工 |
| **T101** | 缺少 `--resource-type` 的 4 种调用形式：非零退出、stderr 含缺失必填说明 + 允许值、不创建/不覆盖文件、stdout 无 CSV 行、零网络 | `RequiredResourceTypeTests`：`test_missing_type_no_args` / `…only_print` / `…only_output`（`-o <tmp>/x.csv`）/ `…only_push`（含 `--api-url`/`--api-key`/`--cluster`/`--yes`）；每条均断言 `SystemExit.code == 2`、stderr 含两枚举值与 `--help` 提示、目标文件不存在或内容未变（预置哨兵内容）、stdout 无 `cluster,` 起始行、`post_import` 与 `urllib.request.urlopen` 未被调用（`side_effect=AssertionError`）；`test_missing_type_subprocess_rc`（`subprocess` 运行真实 CLI，rc==2） | — | 单元 + 子进程 |
| **T102** | BM：`resource_type` 列 = `BARE_METAL`；硬件列可填；`host`/`vcpu`/`disk_gb`/`hypervisor` 恒空；表头 = F023 §6 26 列同序 | `BmOutputTests.test_bm_row_type_and_hardware_columns`；`…test_bm_vm_columns_always_empty`；`…test_bm_header_is_frozen_26_columns`（CSV 首行 == `FROZEN_COLUMNS`）；`…test_bm_cli_print_rows`（`main(["--print","--resource-type","BARE_METAL"])`，限定 patched `collect`） | 真实主机 `--print` 冒烟（§7.1）+ 真实 `/validate`（§7.2） | 单元 + 端到端 |
| **T103** | VM：`resource_type` 列 = `VIRTUAL_MACHINE`；硬件列恒空；`--host` 未提供 → `host` 留空且不推断；提供 → 写入；`vcpu`/`disk_gb`/`hypervisor` 可填 | `VmOutputTests.test_vm_row_type_and_vm_columns`；`…test_vm_hardware_columns_always_empty`；`…test_vm_host_absent_is_empty`；`…test_vm_host_given_is_written`；`…test_vm_header_is_frozen_26_columns` | 真实 `/validate`（VM 文件，`--host f032host` 与不带 `--host` 各一次） | 单元 + 端到端 |
| **T104** | 默认文件名按类型区分且互不覆盖；`-o/--output` 显式优先；`--print` 时即使给 `-o` 也不写文件 | `DefaultOutputNameTests.test_bm_default_filename`（`csm_host_info_bare_metal.csv`）；`…test_vm_default_filename`（`csm_host_info_virtual_machine.csv`）；`…test_two_runs_do_not_overwrite`（先 BM 后 VM，BM 文件字节不变）；`…test_output_flag_overrides_default`（`-o custom.csv` 生效，且不生成类型默认名）；`…test_print_with_output_writes_nothing`（`--print -o p.csv` → `p.csv` 不存在、stdout 有 CSV）；`…test_legacy_default_name_not_used`（不再默认 `csm_host_info.csv`） | 真实运行 + `ls`/`sha256sum` 复核 | 单元 + 手工复核 |
| **T105** | 非法枚举 fail-fast：退出码非零、不写文件、stdout 无 CSV、零网络、错误列出允许值；不回退、不折叠大小写、不映射短名 | `InvalidEnumTests`：`--resource-type` ∈ {`bare_metal`,`Bare_Metal`,`bm`,`""`,`PHYSICAL`,`bare metal`}；`--role` ∈ {`compute`,`ADMIN`}；`--status` ∈ {`running`}；每条断言 `SystemExit.code == 2`、stderr 含该参数允许值全集、无文件、stdout 无 CSV、网络探针未触发；`…test_no_case_folding_no_alias`（`bare_metal` 与 `bm` 均失败，不得被接受为 `BARE_METAL`） | — | 单元 |
| **T106** | 契约零 diff；`--print`/`--no-header`/`-o`/`--push`（预校验→`--yes`→写入、Key 不落盘不漏出）语义不变；T75/T77/T82/T83 无回归；无 `--push` 时零网络 | 既有守卫全部保留通过：`TemplateDriftTests.test_template_columns_match_f023_frozen`、`CsvOutputTests.test_header_order_and_bom`、`EnhancementTests.test_render_csv_header_toggle`、`test_main_print_writes_stdout_not_file`、`test_main_output_file_with_bom`、`test_push_validate_then_confirm`、`test_push_without_yes_does_not_write`、`test_push_validation_errors_block_write`、`test_push_requires_url_key_and_fields`、`test_push_api_key_not_leaked`、`test_default_mode_does_not_call_network`、`RowMappingTests.test_rows_are_deterministic`；新增 `test_multipart_filename_unchanged`（multipart filename 仍为 `csm_host_info.csv`，DR-1009）；新增 `test_offline_run_has_no_network_and_no_api_key_write` | **契约零 diff（Git 只读）**：`git diff --stat 89a5d4ff61f9df35f8f4393887701e7015bc26d8 -- docs/api/F023.md docs/api/F014.md` 为空；真实 `/validate` 端到端（§7.2） | 单元 + Git 只读 + 端到端 |
| **T73（修订）** | 代表性 Linux 主机运行成功并产出文件；表头列名/列序与冻结模板逐字一致；无法采集的业务字段为空（`resource_type` 由必填参数提供，不写占位值） | `test_bm_header_is_frozen_26_columns`、`test_business_fields_always_empty`（沿用）、`test_rows_are_deterministic`（T75 联动） | §7.1 真实主机 `--print` 冒烟：26 列、业务字段空、`resource_type=BARE_METAL` | 单元 + 端到端 |
| **T79（修订）** | `--cluster`/`--resource-type`/`--role`/`--status`/`--host`/`--network` 写入对应列；除 `--resource-type` 外未提供字段仍留空；参数补全后无需手工编辑即可通过预校验（除仍无法获得字段） | `EnhancementTests.test_manual_params_fill_columns`（沿用）、`test_manual_absent_leaves_columns_empty`（沿用）、`test_resource_type_column_written_and_type_columns`（沿用）+ 新增 CLI 级 `test_cli_all_manual_params_written`（`main(["--print","--resource-type","BARE_METAL","--cluster","C","--role","COMPUTE","--status","IDLE","--network","n"])`） | §7.2 真实 `/validate`（参数补全后的 BM/VM 文件） | 单元 + 端到端 |
| **T84（修订）** | 默认（无 `--push`）完全离线、零网络请求；除 §24.4 明示的必填与类型化默认名外，F024 既有文件输出、表头与 T73–T78 无回归 | `test_default_mode_does_not_call_network`（沿用）、`test_offline_run_has_no_network_and_no_api_key_write`；F024/F025 全套回归（`TemplateDriftTests`…`EnhancementTests` 全部通过） | `git diff --stat` 确认 `docs/api/F014.md`、`docs/api/F023.md` 零改动 | 单元 + Git 只读 |

### 3.1 关联回归项（不属新增验收，但 T106 明确要求无回归）

| 项 | 保护点 | 验证方式 |
| --- | --- | --- |
| T75 | 全程只读、不发网络写、重复运行稳定 | `test_rows_are_deterministic`；代码审查确认唯一文件写入仍为 `write_csv` |
| T77 | 产出文件经真实 `/validate` 仅报待人工补全字段行级错误 | §7.2（F032 生成的 BM/VM 真实文件，不使用 F024/F025 历史结论代替） |
| T78 | 不改 F014/F023 模板与契约；内嵌模板守卫 | `TemplateDriftTests` + `git diff` 零改动 |
| T81 | `--print` 不写文件、默认写文件、表头开关 | 既有 `test_render_csv_header_toggle` 等 + T104 新增用例 |
| T82 | `--push` 先预校验、未确认不写、确认后写入 | 既有 3 个 `_push` 用例（本次仅做回归，不新增写入场景） |
| T83 | Key 缺失/非法 401 非零退出、不外泄、不落盘 | 既有 `test_push_requires_url_key_and_fields`、`test_push_api_key_not_leaked`；本 TD 追加**Key 泄露静态检查**（见 §4 R-7） |

---

## 4. 边界与失败场景（必须覆盖）

| # | 场景 | 预期（依据） | 验证方法 |
| --- | --- | --- | --- |
| B-1 | 缺 `--resource-type`，无参调用 | rc=2；stderr 含"必填/required" + 两枚举 + `--help`；无文件、stdout 空、零网络（§24.4 / T101） | `test_missing_type_no_args` |
| B-2 | 缺 `--resource-type`，仅 `--print` | 同上；stdout 不得出现任何 CSV 行（含表头）（T101） | `test_missing_type_only_print` |
| B-3 | 缺 `--resource-type`，仅 `-o <已存在文件>` | rc=2；**已存在文件内容不被覆盖**（哨兵字节比较）（T101） | `test_missing_type_only_output` |
| B-4 | 缺 `--resource-type`，仅 `--push`（含有效 api-url/key/cluster/`--yes`） | rc=2；`post_import`/`urlopen` 零调用；不产生写入（T101） | `test_missing_type_only_push` |
| B-5 | `--resource-type` 非法：小写 `bare_metal`、混合大小写、短名 `bm`、空串 `""`、未知 `PHYSICAL`、含空格 `bare metal` | 全部 rc=2；错误信息列出允许值；无文件/stdout/网络；**不做大小写折叠、不做短名映射、不回退留空**（T105） | `InvalidEnumTests` 参数化 |
| B-6 | `--role` / `--status` 非法值（`compute`/`ADMIN`/`running`） | rc=2，列出各自允许值，无副作用（T105） | `InvalidEnumTests` |
| B-7 | `--print` 与 `-o` 同时给出 | 只写 stdout，`-o` 指定文件不创建；不生成类型默认名（DR-1006 / T104） | `test_print_with_output_writes_nothing` |
| B-8 | 同一目录先 BM 后 VM 两次默认名运行 | 两个文件并存、内容互不覆盖、文件名按类型（T104） | `test_two_runs_do_not_overwrite` |
| B-9 | `-o` 显式路径 | 该路径优先于类型默认名（T104） | `test_output_flag_overrides_default` |
| B-10 | `--print --no-header` | 首行即数据行，列数 26，列序与冻结模板一致（§24.4 / T81） | 既有 `test_render_csv_header_toggle` + CLI 级断言 |
| B-11 | BM 列适用性 | `host`/`vcpu`/`disk_gb`/`hypervisor` 恒空；硬件列 #11–#18 可填；`memory_mb` 可填（F023 §6.1 / T102） | `BmOutputTests` |
| B-12 | VM 列适用性 | 硬件列 #11–#18 恒空；`--host` 未提供 → `host` 空且不推断；提供 → 写入；`vcpu`/`disk_gb`/`hypervisor` 可填（F023 §6.1 / T103） | `VmOutputTests` |
| B-13 | 一次运行只产出一类行 | 所有数据行 `resource_type` 取值一致；不存在 BM/VM 混合文件（DR-1010 / §24.4） | 遍历写出行的 `resource_type` 断言唯一值 |
| B-14 | `--push` 回归：缺 `--api-url` / 缺 Key（无 `CSM_API_KEY`） / 缺 `--cluster` | rc=2 且给出对应提示；不发起请求（§24.3 / T106） | 既有 `test_push_requires_url_key_and_fields` |
| B-15 | `--push` 两步流程：`/validate` 有错误 / 无 `--yes` / `--yes` | 有错误→rc=1 且不写；无 `--yes`→只 validate、rc=0；`--yes`→validate 后写入（T82 回归） | 既有 3 个 `_push` 用例 |
| B-16 | Key 不泄露 | `--api-key supersecretkey` 与 `CSM_API_KEY` 两条路径：stdout/stderr/异常文本均不含 Key；不落盘（T83 / T106） | `test_push_api_key_not_leaked` 两条路径 + §4.1 静态检查 |
| B-17 | 默认模式零网络 | 无 `--push` 时 `post_import`/`urlopen` 零调用，且不读取 `CSM_API_KEY` 相关写文件行为（T84） | `test_default_mode_does_not_call_network` + `test_offline_run_has_no_network_and_no_api_key_write` |
| B-18 | `--help` 零网络 | 生成 help/epilog 时不请求 F023 模板端点（§24.2 离线 / DR-1003） | `test_help_makes_no_network_call` |
| B-19 | help 与真实 choices 漂移 | epilog 中列出的枚举/必填项与 `parser` 实际 `choices`/`required` 逐字一致（DR-1014 / T100"与真实行为一致"） | `test_epilog_values_equal_parser_choices` |
| B-20 | 既有测试调用点适配 | 原 `main([...])` 3 处补 `--resource-type` 后全部通过，**不得**通过放宽 `required` 让旧用例通过（R-1） | 全量 `unittest` 通过 + 代码审查确认无 `required=False` 回退 |

### 4.1 需 Architect / Product 裁定的未定义边界（本 TD 不自行发明预期）

> **TD-2 更新（2026-10-23）**：B-21 / B-22 / B-23 已由 Architect 裁定关闭，现行预期与验证项见 §11.4。下表保留 TD-1 当时的 OPEN 记录，不再作为执行依据。

| # | 边界 | 现状与风险 | 处理 |
| --- | --- | --- | --- |
| B-21 | **`--resource-type BARE_METAL` + 显式 `--host`** | §24.4 与 T102 要求 BM 行 `host` **恒空**；F023 §6.1 规定"BM 行 `host` 非空"为行错误。现有 `build_rows()` 对 `--host` 无条件写入（`scripts/collect_host_info.py` 中 `for column in ("cluster","role","status","host","network")`），架构 DR-1001–DR-1014 未定义该组合应"拒绝 / 忽略 / 写入"，产物会是必然预校验失败的 BM 文件 | 交 Architect 裁定（必要时 Product）；裁定前该场景记为 **OPEN / NOT TESTED**，TD 不为它预设 PASS。若裁定为"本地 fail-fast"，则追加断言 rc=2；若"忽略并提示"，则断言 `host` 为空 + stderr 提示 |
| B-22 | `--role ""` / `--status ""` 空串 | 加 `choices` 后空串被拒（rc=2）；旧实现把空串当"未提供"。§24.4 只对 `--resource-type` 明确"空串"非法 | 交 Architect 确认归类；TD 仅对 `--resource-type ""` 断言 rc=2，role/status 空串待裁定后补充 |
| B-23 | `--print` 与 `--push` 同时给出 | §24.4 未定义；两动作可并存（先打印再推送） | 记为低风险观察项，不纳入本 Feature PASS 结论；如需覆盖，由 Architect 明确语义后在 T106 回归中补充 |

---

## 5. 契约与数据库核对（F032 范围）

| 项 | 核对内容 | 方法 | 预期 |
| --- | --- | --- | --- |
| F023 §6 列集/列序 | 26 列逐字逐序 | `TemplateDriftTests` + 生成 CSV 首行比较 | 完全一致，零 diff |
| F023 §5/§6 端点、校验、上限、错误口径 | 不新增/不修改 | `git diff --stat 89a5d4f… -- docs/api/F023.md` | 空 |
| F014 BM 14 / VM 10 列模板 | 未改动 | `git diff --stat 89a5d4f… -- docs/api/F014.md` | 空 |
| multipart 请求体 | 文件字段名/文件名/`format=csv` 不变 | `test_multipart_body_contains_fields` + 新增 `test_multipart_filename_unchanged` | filename 仍为 `csm_host_info.csv`（DR-1009） |
| 数据库 Schema / Migration / 约束 | 无变更 | `database: NOT_REQUIRED` | 不执行 DB 测试；若出现 Schema 变更需求即返回 Architect |

---

## 6. 测试命令建议（TEST 阶段执行）

```bash
# 1) 采集脚本单元 + CLI 层（含 T100–T106 新增用例与 T73–T84 回归）
python3 -m unittest discover -s scripts -p 'test_collect_host_info.py' -v

# 2) scripts 目录全量（其他脚本无回归）
python3 -m unittest discover -s scripts -p 'test_*.py'

# 3) help 人工通读（保存原始输出作为证据）
python3 scripts/collect_host_info.py --help

# 4) 缺必填 / 非法枚举的 substprocess 级退出码核验（示例，逐条执行并记录 rc/stderr）
python3 scripts/collect_host_info.py ; echo "rc=$?"
python3 scripts/collect_host_info.py --print ; echo "rc=$?"
python3 scripts/collect_host_info.py --resource-type bare_metal --print ; echo "rc=$?"
python3 scripts/collect_host_info.py --resource-type BARE_METAL --role compute --print ; echo "rc=$?"

# 5) 默认文件名与优先级（在临时目录内执行，勿污染工作区）
tmp=$(mktemp -d) && cd "$tmp" \
  && python3 /path/to/csm/scripts/collect_host_info.py --resource-type BARE_METAL \
  && python3 /path/to/csm/scripts/collect_host_info.py --resource-type VIRTUAL_MACHINE \
  && ls -l && sha256sum *.csv

# 6) 契约零 diff（只读）
git diff --stat 89a5d4ff61f9df35f8f4393887701e7015bc26d8 -- docs/api/F023.md docs/api/F014.md

# 7) 执行后工作区洁净
git status --porcelain=v1 --untracked-files=all
```

期望：1)–2) 全绿且用例数 ≥ 现有 43 + 新增；4) 全部 rc=2 且 stderr 含允许值；5) 产出 `csm_host_info_bare_metal.csv`、`csm_host_info_virtual_machine.csv`；6) 空输出；7) 无脚本生成物残留。

---

## 7. 真实 F023 `/validate` 证据方案（只预校验，不写入）

**原则**：F032 需要"生成的 BM/VM 真实文件能通过预校验（仅剩人工待补字段行错误）"的证据（T77 承接 / T102 / T103 / T106）。必须使用真实 F023 端点；**不得用单元测试 Mock 代替**；禁止对生产或未知数据库执行；**只调用 `/validate`，不调用写入端点**。

### 7.1 真实主机采集冒烟（T73 / T104 / T84 部分）

1. 在代表性 Linux 主机（本机或 `csmtest` 容器）执行 `--print` 形式，避免写文件污染工作区：
   ```bash
   python3 scripts/collect_host_info.py --print --resource-type BARE_METAL > /tmp/f032-bm.out 2>/tmp/f032-bm.err; echo rc=$?
   python3 scripts/collect_host_info.py --print --resource-type VIRTUAL_MACHINE > /tmp/f032-vm.out 2>…; echo rc=$?
   ```
2. 断言：首行 26 列列名/列序 == 冻结列；`resource_type` 列分别为 `BARE_METAL` / `VIRTUAL_MACHINE`；BM 的 `host`/`vcpu`/`disk_gb`/`hypervisor` 全空；VM 的硬件列全空；`cluster`/`role`/`status`/`host`(未给)/`network` 为空；无占位值。
3. 记录命令、rc、原始输出片段到本报告 TEST 章节。

### 7.2 真实 `/validate` 预校验（T77 / T102 / T103 / T106 端到端）

1. **启动测试栈**（仅测试环境）：
   ```bash
   docker compose --env-file .env.test -f compose.yaml -f compose.test.yaml -p csmtest up -d --no-build
   curl -s http://localhost:18080/api/v1/health/ready   # 期望 200
   ```
2. **凭据与夹具**（ADMIN，`IMPORT` 权限）：
   - 登录获取凭据 / 创建 API Key（label `f032-validate`）。
   - 建立夹具 Cluster `F032CHK`；Network `F032-MGMT` 的 CIDR 取本机采集到的第一个 IPv4 掩码对应网段（本日探测为 `10.10.10.0/24`，实际以执行时采集结果为准）。
   - VM 预校验需要同 Cluster 已存在的 `BARE_METAL` Host `f032host`（F023 §6 #6"批外已存在"）；经既有 Resource API 创建，作为夹具（**非**本 Feature 导入写入）。
3. **生成待校验文件**（显式 `-o` 到 `/tmp`，不用默认名避免污染工作区）：
   ```bash
   python3 scripts/collect_host_info.py --resource-type BARE_METAL \
       --cluster F032CHK --network F032-MGMT -o /tmp/f032-bm-real.csv
   python3 scripts/collect_host_info.py --resource-type VIRTUAL_MACHINE \
       --cluster F032CHK --host f032host --network F032-MGMT -o /tmp/f032-vm-real.csv
   ```
4. **仅预校验**（两种任一，均无写入副作用）：
   - `curl -sS -X POST -H "Authorization: Bearer $KEY" -F format=csv -F file=@/tmp/f032-bm-real.csv http://localhost:18080/api/v1/imports/resource-interfaces-ips/validate`
   - 或脚本两步流程的**第一步**：`--push --api-url http://localhost:18080 --api-key "$KEY" --cluster F032CHK --resource-type BARE_METAL`（**不带 `--yes`**；预校验未通过时脚本返回 1 且拒绝写入，通过时仅提示"加 `--yes` 以写入"）。
   - **禁止**带 `--yes` 执行（本 Feature 无写入验收需求）。
5. **预期结果**（逐条核对并记录原始 JSON）：
   - HTTP 200，`format=csv`，`error_count` 为 0 或仅包含"人工待补字段"行错误；
   - **不得**出现 `IMPORT_INVALID_FILE` / 422（表头、列缺、列序、编码类）；
   - 行错误的 `field` 只允许是仍无法自动获取的列（如 VM 未建 host 夹具时的 `host`、或 `ip` 落在 Network CIDR 外的网络归属类错误——此时应调整 Network 夹具后重跑，而非把该错误当预期）；
   - **不得**出现类型/格式类错误（如 BM 行 `vcpu` 非空导致的 `field:vcpu`）。
6. **环境不可用时**：若 docker 不可用、测试栈无法启动、镜像缺失或端口被占用，则在 TEST 章节**如实标记 T77/T102/T103/T106 端到端项 `NOT TESTED` 并写明原因**；不得以单元测试结果冒充端到端 PASS，不得以 F024/F025 历史结论替代 F032 文件的实际预校验。

---

## 8. TEST 阶段执行清单（供执行时勾选）

1. 确认候选基线（协调器给出 branch + `git.start_commit` + HEAD）与工作区 clean；记录 `git rev-parse HEAD`。
2. 运行 §6 全部命令，保存原始日志（若需落盘到 `docs/features/F032/artifacts/`，需协调器扩展 writeScope）。
3. 逐条填写 §3 验收映射的 PASS / FAIL / BLOCKED / NOT TESTED 与证据引用。
4. 执行 §7 真实预校验并记录原始 JSON 与命令；不可用则按 §7.6 如实标注。
5. B-21/B-22/B-23 已由 Architect 裁定（DR-1015 / DR-1016 / ON-1），执行时按 **§11.4** 的现行预期断言；该项不再是“待裁定”，但**裁定可验证 ≠ 已通过**。
6. 复核 §6 第 7 步工作区洁净、无 `csm_host_info*.csv` 残留；`.gitignore` 是否已按 DR-1013 追加类型化默认名并保留旧条目。
7. 缺陷按 `docs/project/handoff.md` 格式登记（ID/Severity/Layer/Location/证据/期望与实际/影响/Owner/是否必须修复），相同根因沿用 ID。

---

## 9. TEST EXECUTION

- **版本**：未产生（PENDING）
- **结论**：**NOT TESTED** —— Test Design 阶段不执行验收；`implementation.md` 尚不存在，T100–T106 的自动化用例与 CLI 行为（`--resource-type` 必填、`choices`、分区 help、类型化默认文件名、`resolve_output_path`）均未落地，当前 `scripts/collect_host_info.py` 仍为 F025 基线（` --resource-type` 可缺省、默认名 `csm_host_info.csv`、`--role`/`--status` 无 `choices`）。
- **已执行的非验收探测**：仅 §2.1 的环境可行性只读检查（Python 版本、`ip` 可用性、`--print` 冒烟、docker 镜像存在性、栈状态、`git status`、契约零 diff 基线有效性）。这些**不构成任何验收 PASS**。
- **PASS 填充规则**：TEST 阶段必须独立执行 §6/§7 并附命令与输出；不得引用开发者自测结论、不得将本 TD 的"可验证"表述转写为 PASS。

---

## 10. Issues / Next

| ID | Severity | Layer | Location | 证据 / 说明 | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TD-D01 | MEDIUM | 设计（CLI 行为边界） | §24.4 / T102 与 F023 §6.1；`scripts/collect_host_info.py` `build_rows()` 手工字段写入循环 | B-21：BM + `--host` 组合语义未定义；现有实现无条件写入 `host` | 期望：BM 行 `host` 恒空（T102）；实际：会被写入且无提示 → 产物必然预校验失败 | 用户可生成必然失败的 BM 文件，T102 与 B-21 无法判定 PASS/FAIL | Architect（必要时 Product） | 是（裁定后才可判定 T102 边界） |
| TD-D02 | LOW | 设计（参数语义） | §24.4 枚举口径；`--role ""` / `--status ""` | B-22：空串归类未定义（`choices` 拒绝 vs 视为未提供） | 期望：需明确；实际：加 `choices` 后必被拒（rc=2），与旧"空串=未提供"不同 | 影响 T105 边界覆盖范围与文档一致性 | Architect | 否（可先按 arguments 校验通用行为执行，裁定后补充用例） |
| TD-D03 | NOTE | 设计（组合语义） | §24.4 `--print` / `--push` | B-23：二者同时给出未定义 | 期望：需明确；实际：可能既打印又推送 | 低；不影响 T100–T106 主路径 | Architect | 否 |
| TD-D04 | HIGH（环境依赖，非实现缺陷） | 验证环境 | §7.2 真实 F023 `/validate` | 测试栈当前未运行（`docker compose ps` 空）；镜像与 `.env.test` 齐备，可启动 | 期望：可执行真实预校验并产出 T77/T102/T103/T106 端到端证据；实际：需在 TEST 阶段先启动测试栈 | 若无法启动，T77 及端到端项只能如实标 NOT TESTED，F032 不能得出完整 READY FOR REVIEW | 协调器（环境）/ Tester（执行） | 是（进入正式 Review 前须有结论） |
| TD-D05 | LOW | 测试基础设施 | `.gitignore`（DR-1013） | 当前 `.gitignore` 仅有 `csm_host_info.csv` | 期望：追加 `csm_host_info_bare_metal.csv` / `csm_host_info_virtual_machine.csv` 并保留旧条目；实际：未追加 | 默认名运行可能污染工作区，影响 TEST 洁净性核验 | Backend（实现阶段） | 是（T106 洁净性检查依赖） |

**TD-2 更新（2026-10-23）**：本表 TD-D01 / TD-D02 / TD-D03 已由 Architect 裁定并**关闭**（DR-1015 / DR-1016 / ON-1，关闭记录见 §11.7）；TD-D04（环境，HIGH）/ TD-D05（`.gitignore`，LOW）仍 OPEN。

**Blocking Questions（Test Design 层）**：**None**。TD-D01/D02/D03 是**边界语义未定义**，已明确标为 OPEN 且**不阻塞** T100–T106 主路径的可验证性判定（主路径预期全部由 §24.4 直接确定）；TD-D04 是环境前提，已在 §7.6 规定如实标注路径。（TD-2 后状态：D01–D03 已由 Architect 关闭，D04 仍为环境前提，见 §11.7。）

**Next**：
1. Architect：裁定 TD-D01（BM + `--host`），建议同时确认 TD-D02 / TD-D03；裁定后本 TD 以 **TD-2** 记录增量（保留 TD-1 版本与失效范围），不覆盖本版。
2. Architect：吸收本 TD 后定稿 `READY FOR IMPLEMENTATION`（记录其核对的 Test Design 版本 TD-1 / 2026-10-23）。
3. Backend：实现 `scripts/collect_host_info.py` + 测试（含 §4 B-1–B-20 覆盖与 DR-1013 `.gitignore` 条目），产出 `docs/features/F032/implementation.md`。
4. 协调器：提供 Review 基线（branch + start_commit + HEAD）；TEST 阶段前启动 `csmtest` 测试栈或明确环境禁止。
5. Tester：按 §6/§7/§8 独立执行，产出 TEST 版本记录与证据，给出 `READY FOR REVIEW` / `RETURN TO IMPLEMENTATION` / `TEST BLOCKED` / `PARTIAL TEST ONLY`。
6. 整体验收边界：本报告只覆盖 F032 范围（T73/T79/T84 修订口径与 T100–T106）；`project.acceptance=COMPLETE` 所需的 §31–§33 跨功能整体验收由协调器结合 F001–F031 历史证据核验，**不以本 Feature 的局部 PASS 拼成整体 PASS**。

---

## 11. TEST DESIGN（TD-2 / v2 / 2026-10-23）

- **TD 编号 / 版本 / 日期**：**TD-2 / v2 / 2026-10-23**
- **结论**：**TEST DESIGN READY**
- **含义边界（重要）**：READY **仅表示** TD-2 增量项（`--host` 适用性说明、BM + `--host` 反例、枚举/自由文本空串口径）已被映射为可观察、可重复执行的验证项，且与 architecture v2 及 Database `NOT_REQUIRED` 签核一致；**不表示任何用例已通过，不构成实现批准、Review 通过或合并许可**。TD-1 的同一限定继续适用。
- **核对版本**：product.md v1；architecture.md **v2**（DR-1015 / DR-1016 / ON-1 及 DR-1004 / DR-1008 修订）；requirements **revision 12** §24.4 / §31 T100–T106（含修订后 T73 / T79 / T84）；`docs/api/F023.md` v1 §5 / §6；`docs/database/f032-collector-cli.md`（2026-10-23 `NOT_REQUIRED`）。上游任一再变更（尤其 T102 / T105 口径、DR-1015 / DR-1016、F023 §6.1 行适用性）则本 TD 失效并重做。
- **Database 差异核对**：Database 已签核 `NOT_REQUIRED`（无实体/字段/Schema/Migration/索引/约束/回填变更；CLI 枚举集合与既有 `resources` CHECK 一致，DB 仍为权威兜底）。TD-2 无 DB 断言项，与最终数据库设计**无差异需吸收**，TD-1 §5 结论继续有效。

### 11.1 增量与失效范围（相对 TD-1）

| TD-1 条目 | TD-2 处理 |
| --- | --- |
| §2 环境与可验证性探测、§2.2 执行环境要求、§2.3 可观察面 | **保留有效**（不含已变更行为断言） |
| §3 映射中 T101 / T103 / T104 / T106 / T73 / T79 / T84 | **保留有效**，断言不变 |
| §3 映射中 **T100** | **增量**：追加 `--host` 适用性说明断言（§11.3 R-1） |
| §3 映射中 **T102** | **增量**：追加 BM + 非空 `--host` 反例与 `--host ""` 视为未提供（§11.3 R-2） |
| §3 映射中 **T105** | **增量**：追加 `--role ""` / `--status ""` 必为 rc=2，及自由文本空串=未提供（§11.3 R-3、R-4） |
| §4 B-1–B-20 | **保留有效** |
| §4.1 B-21 / B-22 / B-23 | **失效（OPEN 记录已结）**：由 §11.4 现行预期替换 |
| §5 契约核对、§6 命令、§7 真实 `/validate` 方案、§7.6 环境不可用处置 | **保留有效**（§11.5 重申关键约束并补一条命令） |
| §8 执行清单第 5 项 | **已更新**为按 §11.4 断言 |
| §9 TEST EXECUTION | **保留 NOT TESTED**，状态见 §11.6 |
| §10 TD-D01 / TD-D02 / TD-D03 | **关闭**（§11.7）；TD-D04 / TD-D05 仍 OPEN |

**不需要重做的部分**：TD-1 的 T101 / T103 / T104 / T106 / T73 / T79 / T84 映射、B-1–B-20、测试隔离规则与真实预校验方案均不受 DR-1015 / DR-1016 影响。

### 11.2 裁定依据与“产品规则未变更”说明

| 裁定 | 依据 | 是否改变产品规则 |
| --- | --- | --- |
| **DR-1015**（BM + 非空 `--host` → 本地 fail-fast rc=2，零文件/stdout/网络；`--host ""` 视为未提供） | T102 已确认「BM 行 `host` 恒空」+ F023 §6.1「BM 行 `host` 非空」为行错误 + §24.4 / CHG011-BQ03 的本地 fail-fast 口径 | **否**。T102 的“恒空”约束已在 revision 12 CONFIRMED；DR-1015 只确定“遇到冲突输入时用已批准 fail-fast 方式拒绝”，属已批准边界内的技术裁定，不新增、不放宽任何业务规则 |
| **DR-1016**（枚举参数空串=非法 rc=2；自由文本 `--cluster`/`--host`/`--network` 空串=未提供；`--push --cluster ""` 不变） | §24.4「非法枚举 / 其它枚举参数非法值同样本地失败」+ §24.4「未提供时仍留空」保持段 | **否**。空串归类沿用两条已确认口径的直接推论，未新增取值集合或默认值 |
| **ON-1**（`--print` + `--push` 保持 F025 现状） | §24.4 未定义该组合；F025 既有行为为范围内基线 | **否**（明确不新增规则） |

**结论**：TD-D01 / TD-D02 / TD-D03 均为 Architect 在已确认需求边界内的技术裁定，**不需要用户重新裁定**，也不触发 `docs/project/change-control.md` 的用户批准要求。若后续用户要求 BM 接受 `--host` 并静默置空、或为 `--print --push` 定义新语义，则属需求变更，须走 change-control，届时 TD-2 相应条目失效。

### 11.3 验收映射增量

测试文件：`scripts/test_collect_host_info.py`（类/用例名为建议名，断言语义不得弱化）。

| # | 归属验收 | 验收点 | 验证项（自动化） | 手工/端到端 | 类型 |
| --- | --- | --- | --- | --- | --- |
| **R-1** | T100（增量） | `--help` 需明确 `--host` 仅适用于 `VIRTUAL_MACHINE`，且 `BARE_METAL` 行 `host` 恒空 | `CliHelpTests.test_help_states_host_applicability`：断言 `build_epilog()` 文本同时含 `VIRTUAL_MACHINE`（作为 `--host` 适用类型）与 `BARE_METAL` + `host` 恒空/不适用的语义表述；断言 help 中不存在暗示 BM 可填 `host` 的表述 | `python3 scripts/collect_host_info.py --help` 人工通读，对照 DR-1004 ④ 与 §24.4 引用语义段 | 单元 + 手工 |
| **R-2** | T102（增量，反例） | BM + **非空** `--host` → 本地 fail-fast：rc=2、零文件/stdout/网络，错误说明 `host` 仅适用于 VM | `BmOutputTests.test_bm_with_host_rejected`（或 `ValidateArgsTests.test_bm_host_fail_fast`）：`main(["--print","--resource-type","BARE_METAL","--host","f032host"])` → `SystemExit.code == 2`；stderr 含 `--host` / `VIRTUAL_MACHINE` 语义提示（不要求逐字）；`collect` / `post_import` / `urllib.request.urlopen` 均未调用（`side_effect=AssertionError`）；stdout 无 `cluster,` 起始行<br>`…test_bm_with_host_rejected_does_not_touch_output`：预置 `-o <tmp>/sentinel.csv` 哨兵内容 + 默认名场景，断言两者均不存在/字节不变<br>`…test_bm_host_empty_string_is_unset`：`--host ""` → 正常生成（rc=0），`host` 列空（DR-1015）<br>`…test_vm_host_still_accepted`：VM + `--host f032host` 仍写入（防误伤 T103）<br>`…test_bm_with_host_subprocess_rc`：`subprocess` 真实 CLI，rc==2 | — | 单元 + 子进程 |
| **R-3** | T105（增量） | `--role ""` / `--status ""` 空串 → 本地 fail-fast rc=2、列允许值全集、零副作用（不回退为“未提供”） | `InvalidEnumTests.test_empty_string_enum_rejected`（参数化 `--role ""` / `--status ""`，各含 `--print` 与 `-o` 组合）：`SystemExit.code == 2`；stderr 含该参数允许值全集与 `--help` 提示；无文件（哨兵不被覆盖）、stdout 无 CSV、网络探针未触发 | — | 单元 |
| **R-4** | T105 / T102（增量） | 自由文本 `--cluster ""` / `--network ""`（以及 T102 中的 `--host ""`）= 未提供 → 生成成功且对应列留空；`--push --cluster ""` 行为**不变**（不做放宽） | `FreeTextEmptyStringTests.test_empty_free_text_is_unset`：`main(["--print","--resource-type","BARE_METAL","--cluster","","--network",""])` → rc=0，`cluster` / `network` 列空、无占位值<br>`test_push_empty_cluster_behaviour_unchanged`：`--push --cluster ""` 沿用既有 `_push()` 前置校验结果（断言与 F025 基线一致，不新增写入场景、不带 `--yes`） | — | 单元 |
| **R-5** | T100 / T106（守卫保持） | help 增补文本不得引入网络或与 `choices` 漂移 | `test_help_makes_no_network_call`、`test_epilog_values_equal_parser_choices` 须在 TEST 阶段继续通过（DR-1014，属待执行的检查项而非已得结论）；DR-1015 / DR-1016 不新增可观察面，multipart filename 仍为 `csm_host_info.csv` | `git diff --stat 89a5d4ff61f9df35f8f4393887701e7015bc26d8 -- docs/api/F023.md docs/api/F014.md` 为空 | 单元 + Git 只读 |

**验收口径归属说明**：R-2 / R-4 不扩充 §31 T102 / T105 的文字，而是把已确认的「BM `host` 恒空」「非法枚举 fail-fast」落到可执行反例上（依据 §24.4、T102、T105、F023 §6.1、DR-1015 / DR-1016）。

### 11.4 B-21 / B-22 / B-23 状态更新

| # | TD-1 状态 | TD-2 状态 | 依据 | 现行预期 | 验证项 |
| --- | --- | --- | --- | --- | --- |
| **B-21** | OPEN / NOT TESTED（交 Architect） | **CLOSED-AS-DESIGN**（裁定完成，可判定；未执行） | DR-1015 / T102 / F023 §6.1 | `--resource-type BARE_METAL` + 非空 `--host` → 本地 fail-fast rc=2，零文件/stdout/网络，错误说明 `host` 仅适用于 VM；`--host ""` 视为未提供，`host` 列空 | §11.3 R-2 |
| **B-22** | OPEN / NOT TESTED（交 Architect） | **CLOSED-AS-DESIGN**（裁定完成，可判定；未执行） | DR-1016 / §24.4 | `--role ""` / `--status ""` → rc=2（argparse `choices`）；`--cluster ""` / `--host ""` / `--network ""` → 视为未提供，rc=0 且列留空；`--push --cluster ""` 行为不变 | §11.3 R-3、R-4（`--host ""` 见 R-2） |
| **B-23** | OPEN（低风险观察项） | **ON-1 / NOT_REQUIRED**（不设 PASS/FAIL 判据） | ON-1（保持 F025 现状） | `--print` + `--push` 同时给出时保持 F025 既有顺序行为；不新增规则、不计入本 Feature 验收结论；若 TEST 阶段观察到与 F025 基线不同则作为回归缺陷上报，而非按新语义断言 | 不纳入验收映射；仅在 TEST 记录现状观察（不写 PASS/FAIL） |

> “CLOSED-AS-DESIGN” 仅表示**边界已裁定且预期可判定**，**不等于已通过**。

### 11.5 保留不变的关键约束（真实 F023 `/validate` 与环境限制）

1. **真实 `/validate` 方案不变**：T77 / T102 / T103 / T106 端到端证据仍按 §7.2 使用真实 F023 端点 `POST /api/v1/imports/resource-interfaces-ips/validate`；**不得用 Mock 代替**；只做预校验、**禁止带 `--yes`**；仅对 `compose.test.yaml` + `-p csmtest` 测试栈（`http://localhost:18080`，测试 PostgreSQL）执行，**禁止**指向生产或未知数据库/环境。
2. **环境限制处置不变（TD-D04 仍 OPEN）**：测试栈当前未运行；若 TEST 阶段 docker 不可用、镜像缺失或端口被占用，则 T77 与端到端项**如实标 `NOT TESTED` 并写明原因**，不得以单元测试冒充端到端 PASS，不得用 F024/F025 历史结论替代 F032 文件的实际预校验。
3. **增量项与环境的独立性**：R-1 / R-2 / R-3 / R-4 均为纯本地 CLI 断言（零网络），可在测试栈不可用时独立执行；但其结果**不能**推导出端到端项通过。
4. **测试隔离规则继续强制**：临时目录 + `os.chdir` 复原；真实网络与真实主机调用一律 monkeypatch；`SystemExit(2)` 必须被 `assertRaises` 捕获；执行后 `git status --porcelain=v1` 保持 clean、仓库不得出现 `csm_host_info*.csv`（TD-D05 修复后含类型化默认名）。
5. **§6 命令增补**（TD-2 追加，均在临时目录或 `--print` 形式执行）：

```bash
# BM + 非空 --host 反例（期望 rc=2，stderr 含 host 仅适用 VIRTUAL_MACHINE）
python3 scripts/collect_host_info.py --print --resource-type BARE_METAL --host f032host; echo "rc=$?"
# BM + --host ""（期望 rc=0，host 列空）
python3 scripts/collect_host_info.py --print --resource-type BARE_METAL --host "" | head -2; echo "rc=$?"
# role / status 空串（期望 rc=2，stderr 列出允许值）
python3 scripts/collect_host_info.py --print --resource-type BARE_METAL --role ""; echo "rc=$?"
python3 scripts/collect_host_info.py --print --resource-type BARE_METAL --status ""; echo "rc=$?"
# 自由文本空串=未提供（期望 rc=0，cluster/network 列空）
python3 scripts/collect_host_info.py --print --resource-type BARE_METAL --cluster "" --network "" | head -2; echo "rc=$?"
# help 中 --host 适用性说明（保存原始输出）
python3 scripts/collect_host_info.py --help | grep -n -i "host"
```

### 11.6 TEST EXECUTION 状态（不变）

- **结论**：**NOT TESTED**（继承 §9，TD-2 未改变该状态）。
- **理由（只读复核，非验收）**：截至本次 TD 更新，`scripts/collect_host_info.py` 仍为 F025 基线——`--resource-type` 无 `required=True`、无 `_validate_args()`、无 `resolve_output_path()`、无 `DEFAULT_OUTPUT_BY_TYPE`；`docs/features/F032/implementation.md` 不存在。因此 T100–T106 与 R-1–R-5 的自动化用例与被测行为均未落地。
- **PASS 填充规则**：TEST 阶段必须独立执行 §6（含 §11.5 第 5 条）与 §7 并附命令与输出；不得引用开发者自测结论，不得把本 TD 的“可验证”表述转写为 PASS。

### 11.7 Issues（TD-2 增量）

| ID | 状态（2026-10-23） | Severity | Layer | 说明 | Owner |
| --- | --- | --- | --- | --- | --- |
| TD-D01 | **CLOSED**（Architect 裁定 DR-1015） | MEDIUM → 已关闭 | 设计（CLI 行为边界） | B-21 由 OPEN 转为可判定；现行预期见 §11.4。关闭不需用户重新裁定（§11.2） | Architect（已完成） |
| TD-D02 | **CLOSED**（Architect 裁定 DR-1016） | LOW → 已关闭 | 设计（参数语义） | B-22 空串口径统一；现行预期与验证项见 §11.3 R-3 / R-4 | Architect（已完成） |
| TD-D03 | **CLOSED as ON-1**（明确不设判据） | NOTE → 已关闭 | 设计（组合语义） | B-23 保持 F025 现状；不纳入验收映射，不写 PASS/FAIL | Architect（已完成） |
| TD-D04 | **OPEN**（不变） | HIGH（环境依赖，非实现缺陷） | 验证环境 | 真实 F023 `/validate` 仍需测试栈；不可用时按 §11.5 第 2 条如实标 NOT TESTED | 协调器（环境）/ Tester（执行） |
| TD-D05 | **OPEN**（不变） | LOW | 测试基础设施 | `.gitignore` 需追加 `csm_host_info_bare_metal.csv` / `csm_host_info_virtual_machine.csv` 并保留旧条目（DR-1013） | Backend（实现阶段） |

**新增缺陷**：无（TD-2 为设计增量，未在实现或环境中发现新缺陷）。

**Next**：
1. **Architect**：吸收 TD-2 后把 `docs/features/F032/architecture.md` 定稿为 `READY FOR IMPLEMENTATION`，并记录其核对的 Test Design 版本（TD-2 / v2 / 2026-10-23）。
2. **协调器 / Project Manager**：把 plan 的 `implementation.test_design` 与 `evidence.test_design` 指向本报告 §11 锚点；Database 已签核 `NOT_REQUIRED`（`docs/database/f032-collector-cli.md`），TD-2 已核对一致。
3. **Backend**：实现 `scripts/collect_host_info.py`（DR-1001–DR-1016）与测试（含 §4 B-1–B-20、§11.3 R-1–R-5）及 `.gitignore` 条目，产出 `docs/features/F032/implementation.md`。
4. **协调器**：提供 Review 基线（branch + `start_commit` + HEAD）；TEST 阶段前启动 `csmtest` 测试栈或明确环境禁止。
5. **Tester**：按 §6 / §7 / §8 / §11.5 独立执行，给出 TEST 版本记录与 `READY FOR REVIEW` / `RETURN TO IMPLEMENTATION` / `TEST BLOCKED` / `PARTIAL TEST ONLY`。
6. **整体验收边界不变**：本报告只覆盖 F032（T73/T79/T84 修订口径与 T100–T106）；`project.acceptance=COMPLETE` 所需的 §31–§33 跨功能整体验收由协调器结合 F001–F031 历史证据核验，**不以本 Feature 的局部 PASS 拼成整体 PASS**。

---

## 12. TEST EXECUTION（TR-1 / v3 / 2026-10-23）

- **版本 / 结论**：**TR-1 / v3 / 2026-10-23** — **READY FOR REVIEW**（全部适用验收项 PASS，无必须修复缺陷；未验证项见 §12.10，均属设计禁止或与本 Feature 无关）。
- **角色**：Tester（独立验证）。本节的每个 PASS 均由 Tester 本人重新执行命令取得证据，不复制 `docs/features/F032/implementation.md` §5 的开发者结果（实现报告仅用于交叉核对，差异见 §12.9 OB-3）。
- **基线**：
  - 分支 `feature/F032-collector-help-type-import`，**HEAD `5cbe00970b6eb01241bf8233dc23d5ee46aee6ef`**（`feat(F032): require resource type and generate typed import files`），`start_commit=89a5d4ff61f9df35f8f4393887701e7015bc26d8`。
  - 执行前 `git status --porcelain=v1 --untracked-files=all` 为空（工作区 clean），执行后仍无 tracked 变更（全部证据写在本报告与 `docs/features/F032/artifacts/`）。
  - `docs/features/F032/architecture.md` **v2**（§9 CONTRACT 签核 `READY FOR IMPLEMENTATION` / Contract `NOT_REQUIRED`，DR-1001–DR-1016 + ON-1）；本报告 **TD-2 / v2**（§11）；`docs/project/project-plan.yaml` plan_revision 18。
  - 需求依据：`docs/product/requirements-v3.md` revision 12 §24.4、§31 T100–T106 与修订后的 T73 / T79 / T84；消费契约 `docs/api/F023.md` v1 §6（26 列冻结）、`docs/api/F014.md` v1；数据库 `docs/database/f032-collector-cli.md`（`NOT_REQUIRED`）。
- **证据目录**：`docs/features/F032/artifacts/`（下表 §12.11）。

### 12.1 Environment（实际执行环境）

| 项 | 值 |
| --- | --- |
| 主机 / 内核 | Linux（WSL2），代表性 Linux 主机（具备 `ip -j addr`、`lsblk`、`lscpu`、`systemd-detect-virt`） |
| Python | `Python 3.12.7`（脚本仅标准库） |
| 采集到的接口（默认排除 loopback / down） | `eth0 10.10.10.23/24`、`eth6 192.168.10.221/24`、`eth4 10.100.24.211/32`；hostname 归一化后 `luck`（3 条数据行） |
| 测试栈 | `docker compose -p csmtest`：`csmtest-nginx-1`（`0.0.0.0:18080->80`）、`csmtest-backend-1`（healthy）、`csmtest-db-1`（postgres:16, healthy）、`csmtest-frontend-1`；`GET /api/v1/health/ready` = **200** |
| 数据库 | 测试 PostgreSQL（`.env.test`：`csm` / `csm:***@db:5432/csm`，独立 `csm_test` 保留给后端集成测试）。**未连接、未写入任何生产或未知数据库。** |
| 凭据 | `admin`（ADMIN，含 `IMPORT`）经 `POST /api/v1/auth/login` 取得 `csm_session` Cookie；另创建一次性 API Key（label `f032-validate`）仅用于脚本 `--push` 预校验腿，**明文仅存 `/tmp` 且用完即删、未出现在任何报告或输出中** |
| 测试隔离 | 所有会写文件的用例在 `mktemp -d` 临时目录执行；单元测试用 `tempfile.TemporaryDirectory()` + `chdir` 复原；仓库工作区未出现本次执行产生的 `csm_host_info*.csv`（见 §12.9 OB-1 的既有残留说明） |
| 写入边界 | **只调用 `/validate` 预校验**；全程未带 `--yes`、未调用写入端点 `POST /imports/resource-interfaces-ips`，未触发 `scripts/collect_host_info.py` 的写入腿 |

### 12.2 实际执行的命令与结果（Verification）

| # | 命令 | 结果 |
| --- | --- | --- |
| C1 | `python3 -m unittest discover -s scripts -p 'test_collect_host_info.py' -v` | **Ran 83 tests … OK**（rc=0）。类/用例数：`CliHelpTests 9`、`RequiredResourceTypeTests 5`、`BmOutputTests 8`、`VmOutputTests 3`、`DefaultOutputNameTests 6`、`InvalidEnumTests 5`、`FreeTextEmptyStringTests 2`、`ContractMultipartTests 1`、`ContractGuardTests 1`（新增 40）+ 既有 43（含 `TemplateDriftTests`、`EnhancementTests`、`RowMappingTests`、`CsvOutputTests` 等） |
| C2 | `python3 -m unittest discover -s scripts -p 'test_*.py'` | **Ran 112 tests … OK**（rc=0）；`scripts` 目录无其它回归 |
| C3 | `python3 scripts/collect_host_info.py --help` | rc=0；usage 行为 `--resource-type {BARE_METAL,VIRTUAL_MACHINE}`（不在 `[]` 内即必填）；help `options` 段标注「必填。」；epilog 五区齐全（①②③④⑤）——原始输出见 `artifacts/help.txt` |
| C4 | CLI 冒烟矩阵 S1–S28（缺必填 / 非法枚举 / BM+`--host` / role·status 空串 / 哨兵不被覆盖 / 默认名 / `--print -o` / `--no-header` / 重复运行 / `-o ""`） | 全部符合 §24.4；rc=2 场景的 stdout 均为 **0 字节**、无文件创建、已存在文件（哨兵）字节不变。详见 `artifacts/cli-smoke.log` |
| C5 | 零网络验证：`strace -f -e trace=connect,socket` 包裹 6 个场景（无参 / 非法枚举 / BM+`--host` / `--role ""` / 离线正常跑 / `--help`） | 六个场景 **`AF_INET`/`AF_INET6` 计数全部为 0** |
| C6 | 契约零 diff：`git diff --stat 89a5d4ff -- docs/api/F023.md docs/api/F014.md` | **空输出（零 diff）**；另 `git diff --stat 89a5d4f -- backend frontend` 亦为空（无后端/前端/Migration 改动） |
| C7 | 独立列集核对：从 `docs/api/F023.md` §6 表格正则提取 26 列名，与 3 个真实生成文件表头逐字比较 | `identical & same order: True`（26 列） |
| C8 | 真实 F023 `/validate`（测试栈，session cookie） | BM：`200` `total_rows=3 error_count=0`；VM（含 `--host`）：`200` `error_count=0`；VM（无 `--host`）：`200` `error_count=3`，3 条均为 `{"field":"host","reason":"host is required"}`。原始 JSON 见 `artifacts/real-validate/validate-*.json.raw` |
| C9 | 脚本 `--push` 两步流程**第一步**（真实测试栈，无 `--yes`；BM 与 VM 各一次） | 均 `200` `error_count=0`，脚本 rc=0，stderr `预校验通过。加 --yes 以写入。`；**未发生任何写入** |
| C10 | 只读副作用核对：`GET /api/v1/resources?cluster_id=<F032CHK>`、`?q=luck`、`GET /ip-addresses?cluster_id=…`、`GET /networks?cluster_id=…` | F032CHK 内 Resource **total=1（仅夹具 `f032host`）**、IPAddress **total=0**、Network total=3（夹具）；`q=luck` 命中的 2 条均为 2026-10-20/21 的 F025 历史夹具（非本次产生）→ `/validate` 无业务写副作用 |
| C11 | T83：无效 Key / 缺失 Key 调用 `--push`（真实测试栈，无 `--yes`） | 无效 Key → 响应 `401 AUTH_REQUIRED`，脚本 **rc=1**，Key 在 stdout+stderr 中出现 **0** 次；缺失 Key → **rc=2** 且未发起请求 |
| C12 | 测试充分性自证（mutation）：把 `collect_host_info.py` 与测试文件复制到 `/tmp` 后分别注入 5 个回归（`required=True→False`、类型化默认名回退、移除 role/status `choices`、移除 DR-1015 守卫、help 删除 `--host` 适用性说明） | 基线副本 83 OK；5 个变异**全部 FAILED**（4/3/6/3/1 项失败）→ 新增守卫能捕获对应回归。仓库代码未改动。见 `artifacts/mutation-check.log` |
| C13 | 计划一致性：`python3 scripts/validate_project_state.py --feature F032`（只读） | rc=0 `PROJECT STATE VALID (structure/gates/files…)`；仅结构与 Gate 检查，不证明批准来源/Git/测试真实性 |
| C14 | 夹具清理 | `DELETE` resource / 3×network / cluster → 各 `204`；API Key revoke → `200 REVOKED`；清理后 `clusters?q=F032` total=0。见 `artifacts/real-validate/cleanup.log` |

### 12.3 验收映射（逐项判定）

| 验收 | 判定 | 证据（Tester 实际执行） | 备注 |
| --- | --- | --- | --- |
| **T100**（+ TD-2 R-1 / R-5） | **PASS** | C3 + `artifacts/help.txt` + `CliHelpTests` 9 项 + C1；S15-F `--help` inet=0 | ①模板必填区列 `cluster、hostname、resource_type、name、ip` 且「VIRTUAL_MACHINE 行另需 host」；②`--push` 必填区列 `--api-url`/`API Key`/`--cluster` 且含「脚本必填 ≠ 模板必填」「未提供 --cluster 仍可离线生成 CSV」；③三个枚举全量逐字列出；④引用语义含「Cluster code（大小写不敏感）或 UUID」「hostname 或 UUID」「name 或 CIDR」「须存在且未软删」「/mask 解析」，并含 R-1 要求的「仅适用于 VIRTUAL_MACHINE / BARE_METAL 行 host 恒空」；epilog 与 `parser.choices`/`required` 逐字一致（DR-1014 守卫通过） |
| **T101** | **PASS** | C4 S1/S2/S10/S11 + `RequiredResourceTypeTests` 5 项 + 子进程 rc=2 用例；C5-A inet=0 | 无参 / 仅 `--print` / 仅 `-o`（哨兵 `sentinel-bytes` 未被覆盖）/ 仅 `--push --yes`（零网络）→ 均 rc=2，stderr 含「the following arguments are required: --resource-type」+ 三个枚举允许值 + `--help` 提示，stdout 0 字节，无新文件 |
| **T102**（+ TD-2 R-2） | **PASS** | C4 S6/S28 + C7 + C8（BM 真实预校验 200/0 错误）+ `BmOutputTests` 8 项 | `resource_type` 列全 `BARE_METAL`；`host`/`vcpu`/`disk_gb`/`hypervisor` 全空；硬件列实际填写 `cpu_model/cpu_sockets/cpu_cores/gpu_model/gpu_count`（manufacturer/model/serial 因 WSL 无 DMI 而空，属「未知留空」非占位）；表头 == F023 §6 26 列同序；BM + 非空 `--host` → rc=2、零文件/stdout/网络且错误说明 host 仅适用 VM；`--host ""` → rc=0、`host` 列空 |
| **T103** | **PASS** | C8（VM 含 host：0 错误；VM 无 host：仅 `host` 行错误）+ C4 S21 + `VmOutputTests` 3 项 | `resource_type` 列全 `VIRTUAL_MACHINE`；硬件列 8 项全空；`--host f032host` → 写入；未提供 → 留空且无推断；`vcpu=16`、`disk_gb=2054`、`hypervisor=wsl` 实际填充 |
| **T104** | **PASS** | C4 S12/S13/S26 + `DefaultOutputNameTests` 6 项 | 两次默认名运行产出 `csm_host_info_bare_metal.csv`(`fe0361e8…`) 与 `csm_host_info_virtual_machine.csv`(`049b0ec0…`)，并存且 BM 文件字节不变；旧名 `csm_host_info.csv` 未被使用；`-o custom.csv` 生效且不产类型默认名；`--print -o p.csv` → p.csv 不存在而 stdout 有 CSV |
| **T105**（+ TD-2 R-3） | **PASS** | C4 S3/S4/S5/S7/S8/S9/S28 + `InvalidEnumTests` 5 项 + C5-B/D | `--resource-type` ∈ {`bare_metal`,`Bare_Metal`,`bm`,`BAREMETAL`,`""`,`PHYSICAL`,`bare metal`}；`--role` ∈ {`compute`,`ADMIN`,`""`}；`--status` ∈ {`running`,`""`} → 全部 rc=2、stdout 0 字节、无文件、零网络，stderr 列出该参数允许值全集 + `--help` 提示，报错为 argparse 原始 `invalid choice` 语义；无大小写折叠/短名映射/静默回退 |
| **T106** | **PASS** | C6 + C7 + C1（既有守卫全绿）+ C5-E + C9/C11 + `ContractMultipartTests`/`ContractGuardTests` | `docs/api/F023.md`/`docs/api/F014.md` 零 diff；26 列与文档逐字一致；multipart filename 仍为 `csm_host_info.csv`（DR-1009，守卫通过）；`--print`/`--no-header`/`-o` 语义按 S12/S20 不变；`--push` 预校验腿真实可用且未确认不写入；Key 不外泄、不落盘（模块仅 1 处文件写 `write_csv`）；离线零网络 |
| **T73（修订）** | **PASS** | C4 S13/S14 + C7 + C8 | 代表性 Linux 主机运行成功并产出文件（3 行）；表头 26 列逐字同序；业务/归属列未提供时为空、无占位/推断值；`resource_type` 由必填参数写入 |
| **T79（修订）** | **PASS** | C4 S19 + C8/C9 | `--cluster/--resource-type/--role/--status/--host/--network` 均写入对应列（S19 实测 6 列）；未提供的字段留空（`f032-vm-nohost.csv` 的 host/role/status 空）；参数补全后的 BM/VM 文件**无需手工编辑**即通过真实预校验（`error_count=0`） |
| **T84（修订）** | **PASS** | C5-E（离线跑 inet=0）+ C2 + C4 S13 | 默认模式零网络；除 §24.4 明示的 `--resource-type` 必填与类型化默认名外，F024 既有文件输出与表头行为无回归（既有 43 项全绿） |
| **T75**（回归） | **PASS** | C4 S27 + C5-E + 代码核对 | 同一主机连续 `--print` 两次输出**逐字节相同**；模块内唯一文件写入为 `write_csv`（`open(..., "w")` 仅 1 处），无其它写路径；无网络写 |
| **T77**（回归，F032 承接） | **PASS** | C8 | F032 生成的**真实文件**经真实 F023 预校验：补全参数后 0 错误；仅缺 `host` 时只报 `field:"host"` 行级错误，**无表头/列/列序/编码/类型类错误**（无 `IMPORT_INVALID_FILE`/422） |
| **T78**（回归） | **PASS** | C6 + C7 + `TemplateDriftTests` | F014/F023 模板与契约零 diff；内嵌 26 列与冻结列集一致性守卫通过 |
| **T81**（回归） | **PASS** | C4 S12/S20 + 既有 `test_main_print_writes_stdout_not_file` / `test_render_csv_header_toggle` / `test_main_output_file_with_bom` | `--print` 不写文件；默认写文件；`--print --no-header` 首行即数据行且 26 列同序 |
| **T82**（回归） | **PASS**（回归口径） | C9 + 代码核对 `_push`/`post_import`/`IMPORT_PATH` 零改动 + 既有 `test_push_validate_then_confirm` 等 3 项 | 真实栈验证：先调用 `/validate` 并展示结果，无 `--yes` 时不写入（DB 复核 C10）。**真实 `--yes` 写入腿 NOT TESTED by design**（architecture §9.3 明确禁止本 Feature 端到端写入），该腿的回归依据为 `_push()` 代码零 diff + 既有 mock 用例，见 §12.10 |
| **T83**（回归） | **PASS** | C11 + 既有 `test_push_requires_url_key_and_fields` / `test_push_api_key_not_leaked` | 无效 Key 真实返回 401 且脚本 rc=1；缺失 Key rc=2 且不请求；Key 不出现在 stdout/stderr（0 次命中），不落盘 |

**汇总**：T100–T106 与 T73/T79/T84 修订口径 **11/11 PASS**；回归项 T75/T77/T78/T81/T82/T83 **6/6 PASS**（T82 真实写入腿按设计未执行，见 §12.10）。无 FAIL、无 BLOCKED、无 NOT TESTED 的必测项。

### 12.4 数据库验证

- `docs/database/f032-collector-cli.md` = **`NOT_REQUIRED`**：F032 无实体/字段/Schema/索引/约束/Migration/回填变更；`git diff --stat 89a5d4f -- backend frontend` 为空（无 alembic 迁移、无模型改动）→ 本阶段**无 Migration 与约束需在真实数据库核对**，不执行 DB 断言（`.pi/skills/data-integrity/SKILL.md` 判为 `NOT_REQUIRED`）。
- 与最终数据库设计**无差异需吸收**：脚本枚举集合与既有 `resources` CHECK 一致，DB 仍为权威兜底。
- 唯一涉库动作是夹具（Cluster / 3×Network / 1×BARE_METAL Host / 1×API Key）经正式 REST API 创建，验证后已**软删 + 吊销**（C14），未触碰他人夹具。

### 12.5 接口验证（真实 F023 `/validate`）

| 项 | 结果 |
| --- | --- |
| 端点 / 认证 | `POST http://localhost:18080/api/v1/imports/resource-interfaces-ips/validate`，`csm_session` Cookie（ADMIN），`multipart/form-data`（`format=csv` + `file`） |
| BM 文件 | `200 {"format":"csv","total_rows":3,"importable_rows":3,"error_count":0,"errors":[],"errors_truncated":false}` |
| VM 文件（`--host f032host`） | `200` `total_rows=3`、`importable_rows=3`、`error_count=0` |
| VM 文件（无 `--host`） | `200` `importable_rows=0`、`error_count=3`，errors 均为 `{"row":2/3/4,"field":"host","reason":"host is required","related_row":null}` → 恰为「仍待补字段」的行级错误，**无表头/列/格式/类型错误** |
| 响应类型/错误语义 | 成功为 200 + 契约 JSON（`total_rows`/`importable_rows`/`error_count`/`errors`/`errors_truncated`）；非法 Key 为 401 `AUTH_REQUIRED` 统一信封（C11） |
| 只读确认 | 预校验后 F032CHK 内 Resource=1（仅夹具 Host）、IPAddress=0；CSV 中的 hostname `luck` 未落库 |
| 夹具约束说明 | 本机采集到 3 个不同网段，单值 `--network` 无法覆盖全部行，故真实预校验**不传 `--network`**，由 `ip` 的 `/mask` 按 F023 §6 #25 解析（已建 3 个 Network 分别覆盖 `10.10.10.0/24`、`192.168.10.0/24`、`10.100.24.211/32`）。`--network` 的列写入语义另由 C4 S19 覆盖 |

### 12.6 前端验证

**NOT_REQUIRED** —— `layers.frontend=false`（architecture §4）：F032 无页面、组件、交互或样式改动，`git diff --stat 89a5d4f -- frontend` 为空；已批准范围不要求前端集成，故不做前端验证。

### 12.7 集成 / 端到端

- 真实前后端集成已在 §12.5 完成（脚本产物 → 真实 nginx → 真实 FastAPI → 真实测试 PostgreSQL），**未使用 Mock 代替**。
- 覆盖：T77 / T102 / T103 / T106 的端到端部分（BM & VM 文件实际预校验）+ T79「参数补全后无需手改文件即通过预校验」+ T82 预校验腿 + T83 无效 Key。
- 未覆盖：`--yes` 真实写入腿（设计禁止，见 §12.10）；§31–§33 跨功能整体验收（协调器职责，不以本 Feature PASS 拼成整体 PASS）。

### 12.8 测试代码审查（Review 范围提示）

- 无既有断言被删除或放宽：`git diff 89a5d4f -- scripts/test_collect_host_info.py` 的删除行仅模块 docstring 与 3 处 `main([...])` 调用点补 `--resource-type`（B-20 / R-1 合规），未出现 `required=False` 回退（实现内 `grep required=False` 无命中）。
- 用例隔离合规：所有 CLI 用例经 `_CliTestCase`（`tempfile` + `chdir` + 采集/`post_import`/`urlopen` 三重探针），实测无真实网络、无工作区污染。
- 守卫有效性由 C12 的 5 个变异验证（全部被捕获）。测试代码仍属 Review 范围，本报告只提供充分性证据，不代替 Review。

### 12.9 Defects（含观察项）

**无 BLOCKER / HIGH / MEDIUM 缺陷；无必须修复项。**

| ID | Severity | Layer | Location | 证据 / 复现 | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F032-T-OB1 | NOTE（非 F032 缺陷，既有残留） | 工作区 | `scripts/csm_host_info.csv` | `stat` mtime `2026-10-23 13:43:03`（早于 F032 源码改动 14:03），内容为 F024 旧口径（`resource_type` 空、`role/status` 有值）；`git check-ignore` 命中 `.gitignore:175`，`git status` 中仅显示为 ignored（`!!`） | 期望：仓库无常驻采集产物；实际：存在 1 个被忽略的历史产物。**非本次 TEST 产生**（本次所有默认名运行均在 `mktemp -d` 中） | 仅影响工作区洁净观感，不影响 tracked 状态、构建或测试 | 协调器（可择机删除） | 否 |
| F032-T-OB2 | NOTE | 验证范围 | `scripts/collect_host_info.py` `_push()` 写入腿 | architecture §9.3 明确「禁止 `--yes` 写入」；本阶段只执行预校验腿 | 期望：F032 不引入写入行为变更；实际：`_push`/`post_import`/`IMPORT_PATH` 零 diff，写入腿回归由既有 mock 用例覆盖 | T82 的真实写入证据缺失（已在 §12.10 列为未验证项，不影响 F032 无回归结论） | 协调器（若需真实写入证据，另立场景并由 Product/Architect 授权） | 否 |
| F032-T-OB3 | NOTE（口径澄清，非缺陷） | 验证方法 | 真实 `/validate` 夹具 | 本机采集到 `10.10.10.0/24`、`192.168.10.0/24`、`10.100.24.211/32` 三个网段，单值 `--network` 只能命中其中一段 | 期望：真实预校验只暴露待补字段错误；实际：改为**不传 `--network`**、建 3 个 Network 由 `ip/mask` 解析；`--network` 写入语义改由 S19 覆盖 | 与 TD-2 §7.2 示例命令（`--network F032-MGMT`）措辞不同；若照抄会把另外 2 行变成网络归属行错误（不属 F032 缺陷）。不涉及实现或产品规则 | Tester（已在本报告说明） | 否 |
| F032-T-OB4 | NOTE | CLI 细节 | `-o ""` / 自由文本空白串 | S26 / S24：`-o ""` → rc=0 回落类型默认名；`--cluster "  "` → 视为未提供 | 与 `implementation.md` §7 记录一致，且符合 DR-1016「自由文本空串/空白 = 未提供」；非 §24.4 显式验收项 | 无 | — | 否 |
| F032-T-OB5 | NOTE | 环境 | `csmtest` 共享测试栈 | 栈内存在 F025 等历史夹具（如 hostname `luck` 的 2 条 F025 记录） | 期望：不影响 F032 结论；实际：F032CHK 内对象独立计数（C10） | 无（同名 hostname 属不同 Cluster，符合 §2.1 跨 Cluster 允许） | — | 否 |

### 12.10 未验证项（明确声明，不得当作 PASS）

| 项 | 状态 | 原因 / 归属 |
| --- | --- | --- |
| `--push --yes` 真实写入腿（`created`/`interfaces_created`/`ip_addresses_created`） | **NOT TESTED by design** | architecture v2 §9.3 与 TD-2 §11.5 明确禁止 F032 端到端 `--yes` 写入；`_push()` 零 diff + 既有 mock 用例覆盖回归 |
| `--print` + `--push` 组合（B-23） | **NOT_REQUIRED**（ON-1 不设 PASS/FAIL 判据） | 保持 F025 现状即可；本轮未观测到与 F025 基线的偏离（代码顺序未改），故不记录判据 |
| F014（BM 14 / VM 10 列）模板与既有导入行为的运行期验证 | **NOT_REQUIRED** | F032 只做零 diff（C6）与 F023 26 列核对（C7）；F014 行为验收属 F014 历史证据 |
| PostgreSQL 侧约束/迁移行为 | **NOT_REQUIRED** | `docs/database/f032-collector-cli.md` = `NOT_REQUIRED`，无 Schema/Migration 变更 |
| 前端 | **NOT_REQUIRED** | 见 §12.6 |
| §31–§33 跨功能整体验收 | **未在本报告范围内** | 协调器结合 F001–F031 历史证据核验；本报告局部 PASS 不构成整体 PASS |
| `scripts` 之外的测试面（`backend/tests`、`frontend`） | **NOT_REQUIRED** | F032 无 backend/frontend 代码改动（C6） |

### 12.11 结论与 Next

- **结论**：**READY FOR REVIEW**。T100–T106 与修订后的 T73/T79/T84 全部 PASS；T75/T77/T78/T81/T82/T83 无回归；契约零 diff；真实 F023 `/validate` 端到端完成且只读（无写副作用）；无必须修复缺陷。
- **边界重申**：本结论只覆盖 F032 的验收与回归，**不构成 Review 批准、合并许可或整体 §31–§33 验收结论**；`project.acceptance=COMPLETE` 由协调器另行核验。
- **Next**：
  1. **Reviewer**：按 `docs/project/git-workflow.md` 以 `5cbe009` 为 Review 基线审查实现与测试代码（本报告 §12.8 提供充分性证据）。
  2. **协调器**：确定是否要求补充 `--yes` 真实写入场景（OB-2）；如需，须先由 Product/Architect 授权改变 F032 的写入禁令。
  3. **协调器**：可择机清理既有忽略产物 `scripts/csm_host_info.csv`（OB-1）；夹具已软删，若需重跑 TEST，可按 `artifacts/real-validate/cleanup.log` 记录的 ID 与 `restore` 调用恢复，或按 `artifacts/real-validate/setup.log` 步骤 3–5 重建。
- **产物清单**（`docs/features/F032/artifacts/`）：
  - `test-collect-host-info.log`（C1 全量 -v 输出，83 tests OK）
  - `test-scripts-all.log`（C2，112 tests OK）
  - `help.txt`（C3 `--help` 原始输出）
  - `cli-smoke.log`（C4/C5/C7/S19–S28：CLI 冒烟矩阵、strace 零网络、列集核对、T75 重复运行）
  - `mutation-check.log`（C12 测试充分性变异验证）
  - `project-state-validate.log`（C13 计划一致性只读校验）
  - `real-validate/setup.log`（C8–C11：登录、夹具创建、文件生成、`/validate` 原始响应、`--push` 预校验腿、无效/缺失 Key、只读副作用核对）
  - `real-validate/validate-f032-bm-real.json.raw`、`validate-f032-vm-real.json.raw`、`validate-f032-vm-nohost.json.raw`（原始响应）
  - `real-validate/f032-bm-real.csv`、`f032-vm-real.csv`、`f032-vm-nohost.csv`（被测真实文件，含生成时 sha256，见 setup.log §6）
  - `real-validate/cleanup.log`（C14 软删/吊销与恢复路径）

> **提交提示（协调器）**：`*.log` 被 `.gitignore:124` 忽略，本目录下的 `*.log` 证据需按 F028–F031 同类产物的既有做法以 `git add -f` 纳入提交（`.json.raw` / `.csv` / `.txt` 不受该规则影响，已正常出现在 `git status` 未跟踪列表）。Tester 未执行任何 Git 写操作。

**Git 声明**：本次仅执行**只读** Git 命令（`git rev-parse --short HEAD`、`git status --porcelain=v1 --untracked-files=all [--ignored]`、`git log --oneline`、`git diff [--stat] 89a5d4f`、`git check-ignore -v`、`git ls-files`），未执行任何改变 Git 状态的命令（无 add / commit / branch / switch / merge / stash / reset / clean）；HEAD 全程为 `5cbe009`。

---

GIT: NONE
