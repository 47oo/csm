# F032 采集脚本类型必填、帮助信息与按类型生成 — 实现报告

- **状态**：BACKEND COMPLETE（本地实现与自动化验证完成；真实 `/validate` 端到端留给 TEST，见 §6）
- **角色**：Backend（仓库脚本实现）
- **上游依据**：`docs/features/F032/product.md` v1；`docs/features/F032/architecture.md` v2（DR-1001–DR-1016、ON-1，§9 CONTRACT 签核 READY FOR IMPLEMENTATION / Contract NOT_REQUIRED）；`docs/features/F032/test-report.md` TD-2（v2）；`docs/product/requirements-v3.md` revision 12 §24.4（含修订后的 §24.2 / §24.3 与 T73 / T79 / T84）；`docs/database/f032-collector-cli.md`（`NOT_REQUIRED`）；`docs/api/F023.md` v1 §5 / §6（消费，零改动）；`docs/api/F014.md` v1（零改动）。
- **规范应用**：`docs/project/implementation-rules.md`（验证与交付）；`.pi/skills/data-integrity/SKILL.md` 按 F032 Database `NOT_REQUIRED` 判为 `NOT_REQUIRED`（无唯一性、关系、生命周期、并发分配、导入或 Migration 变更）；唯一完整性相邻项为「内嵌 26 列模板与 F023 §6 冻结列集一致」的既有守卫 `TemplateDriftTests`。
- **说明**：本报告只记录 F032 范围内的 CLI 表面实现与本地验证证据，不复制产品/契约规则正文；业务口径以引用为准。

---

## 1. 实现范围

仅采集脚本的本地 CLI 表面（参数必填/枚举、帮助文本、默认输出文件名）与配套测试、用法文档：

1. `--resource-type` 全局必填 + `choices`；`--role` / `--status` 增加 `choices`，不做大小写折叠、无短名映射。
2. 自定义 `argparse` 错误：保留原始错误行，追加允许值与 `--help` 提示，统一退出码 2；`main()` 参数解析与本地校验先于采集、写文件、stdout 与网络。
3. `--help` 分区说明（模板必填 / `--push` 必填 / 枚举值 / 引用语义 / 输出默认名），由离线内嵌常量生成，使用 `RawDescriptionHelpFormatter`。
4. 默认输出文件名按类型区分，`-o/--output` 优先，`--print` 不写文件；`--no-header` 语义不变。
5. `BARE_METAL` + 非空 `--host` 本地 fail-fast；`--host ""` 视为未提供；自由文本空串视为未提供，枚举空串视为非法。
6. 不变量保持：`TEMPLATE_COLUMNS` 26 列、`IMPORT_PATH` 与端点、multipart filename `csm_host_info.csv`、`--push` 两步流程、API Key 不落盘、无 `--push` 零网络。

不在范围（未改动）：F014 / F023 模板与契约、数据库 Schema / Migration、平台 Service Layer / 路由 / 模型 / 权限 / 审计、前端、`docs/project/project-plan.yaml`、架构 / 产品 / Test Report、F032 之外的 Feature 证据。

## 2. 实际修改文件

| 文件 | 变更 |
| --- | --- |
| `scripts/collect_host_info.py` | 新增 `RESOURCE_TYPE_VALUES` / `ROLE_VALUES` / `STATUS_VALUES` / `DEFAULT_OUTPUT_BY_TYPE` / `TEMPLATE_REQUIRED_COLUMNS` / `TEMPLATE_REQUIRED_VM_EXTRA` / `PUSH_REQUIRED_ITEMS`；新增 `build_epilog()`、`build_error_hint()`、`_ArgumentParser.error()`、`build_parser()`、`_text_or_none()`、`_validate_args()`、`resolve_output_path()`；`--resource-type` 改 `required=True` + `choices`；`--role`/`--status` 加 `choices`；`-o/--output` 默认改 `None`；`main()` 前置解析+校验并按优先级解析输出路径；模块 docstring 更新口径 |
| `scripts/test_collect_host_info.py` | 新增 40 个用例（`CliHelpTests` 9、`RequiredResourceTypeTests` 5、`BmOutputTests` 8、`VmOutputTests` 3、`DefaultOutputNameTests` 6、`InvalidEnumTests` 5、`FreeTextEmptyStringTests` 2、`ContractMultipartTests` 1、`ContractGuardTests` 1）；既有 3 处 `main([...])` 调用补 `--resource-type`（未放宽 `required`）；新增 `_CliTestCase`（临时目录 + chdir 复原 + 采集/网络探针） |
| `.gitignore` | 追加 `csm_host_info_bare_metal.csv`、`csm_host_info_virtual_machine.csv`，保留旧条目 `csm_host_info.csv` |
| `docs/features/F024/README.md` | 用法与枚举/引用语义更新为 revision 12 口径（`--resource-type` 必填、类型化默认名、role/status 枚举、BM `host` 恒空） |
| `docs/features/F024/field-mapping.md` | 用法示例与逐列表 #1–#6、#25 说明更新为 revision 12 口径（`resource_type` 由参数写入） |
| `docs/features/F024/implementation.md` | 仅末尾追加「revision 12 errata」小节，历史原文与证据未改 |
| `docs/features/F025/implementation.md` | 仅末尾追加「revision 12 errata」小节，历史原文与证据未改 |
| `docs/features/F032/implementation.md` | 本报告（新建） |

## 3. 设计决策（DR）对照

| DR | 实现位置 | 状态 |
| --- | --- | --- |
| DR-1001 | `build_parser()`：`--resource-type` `required=True, choices=RESOURCE_TYPE_VALUES` | 已实现 |
| DR-1002 | `build_parser()`：`--role` `choices=ROLE_VALUES`、`--status` `choices=STATUS_VALUES`，`default=None`，无归一化 | 已实现 |
| DR-1003 | 常量区 + `build_epilog()`，`RawDescriptionHelpFormatter`；不读取 F023 模板端点 | 已实现 |
| DR-1004 | `build_epilog()` ①模板必填 ②`--push` 必填（含「脚本必填 ≠ 模板必填」）③枚举值 ④引用语义（含 `--host` 仅适用 VM、BM 行 `host` 恒空）⑤默认文件名 | 已实现 |
| DR-1005 | `DEFAULT_OUTPUT_BY_TYPE` + `-o` 默认 `None` + `resolve_output_path()` 回填 | 已实现 |
| DR-1006 | `main()`：`--print` 分支不调用 `write_csv`（即使给出 `-o`）；`--no-header` 仅控制表头 | 已实现 |
| DR-1007 | `_ArgumentParser.error()`：`print_usage` + 原始 `prog: error: <message>` + `build_error_hint()`（允许值 + `--help`），`exit(2)` | 已实现 |
| DR-1008 | `main()` 首步构造 parser、`parse_args()` + `_validate_args()` 先于 `collect()` / `write_csv()` / stdout / 网络；不捕获 `SystemExit` | 已实现 |
| DR-1009 | `post_import()` multipart filename 仍为 `csm_host_info.csv`（未随默认名变化） | 已实现（守卫 `ContractMultipartTests`） |
| DR-1010 | 单值 `--resource-type`，一次运行只产出一类行，无混合输出路径 | 已实现（未新增分支） |
| DR-1011 | `TEMPLATE_COLUMNS` 26 列、`IMPORT_PATH`、端点、错误口径、上限未改动 | 已实现（零 diff + `TemplateDriftTests`） |
| DR-1012 | `_push()` 保留 `--api-url` / API Key / `--cluster` 前置校验与 `resource_type` 防御性检查 | 已实现（未改 `_push` 逻辑） |
| DR-1013 | `.gitignore` 追加两个类型化默认名并保留旧条目 | 已实现 |
| DR-1014 | 帮助文本由同一组常量生成；测试断言 epilog 枚举/必填项与 `parser` 的 `choices` / `required` 逐字一致 | 已实现（`test_epilog_values_equal_parser_choices`） |
| DR-1015 | `_validate_args()`：`BARE_METAL` + 非空 `--host` → `parser.error()`（rc=2，零文件/stdout/网络）；`--host ""` 视为未提供 | 已实现（4 个用例，含子进程 rc） |
| DR-1016 | 枚举空串由 `choices` 拒绝（rc=2）；`--cluster` / `--host` / `--network` 空串经 `_text_or_none()` 视为未提供；`--push --cluster ""` 行为不变 | 已实现 |
| ON-1 | `--print` + `--push` 顺序未改动（先 stdout、再 `_push()`），未新增语义、未设判据 | 遵守（无改动） |

## 4. 验收映射（自动化部分）

| 验收 | 覆盖用例 |
| --- | --- |
| T100 / R-1 / R-5 | `CliHelpTests` 全部 9 项（必填标注与两类型、role/status 全枚举、模板必填分区、`--push` 必填分区、引用语义、`--host` 适用性、epilog↔choices 一致、help 零网络） |
| T101 | `RequiredResourceTypeTests` 5 项（无参 / 仅 `--print` / 仅 `-o`（哨兵不被覆盖）/ 仅 `--push` / 子进程 rc=2），均断言零采集、零网络、无文件、stdout 无 CSV |
| T102 | `BmOutputTests` 8 项（类型列与硬件列、冻结 26 列表头、CLI 打印行、BM+`--host` 拒绝与零副作用、`--host ""` 视为未提供、VM `--host` 未被误伤、子进程 rc=2） |
| T103 | `VmOutputTests` 3 项（类型列与 VM 列、`--host` 未给留空、冻结表头） |
| T104 | `DefaultOutputNameTests` 6 项（两类型默认名、互不覆盖、`-o` 优先、`--print -o` 不落盘、旧默认名不再使用） |
| T105 / R-3 | `InvalidEnumTests` 5 项（`--resource-type` 小写/混合大小写/短名/空串/未知值/含空格，`--role`/`--status` 非法值，枚举空串，无大小写折叠与短名映射） |
| R-4 | `FreeTextEmptyStringTests` 2 项（自由文本空串=未提供；`--push --cluster ""` 行为不变） |
| T106 | 既有回归用例全部通过 + `ContractMultipartTests.test_multipart_filename_unchanged`（端点与 multipart filename 不变）+ `ContractGuardTests.test_offline_run_has_no_network_and_no_api_key_write`（零网络、Key 不外泄、`--print` 不落盘）+ 契约零 diff（§5.3） |
| T73 / T79 / T84（修订口径，本地部分） | 冻结表头守卫、手工参数写入列（既有 `EnhancementTests`）、离线零网络（既有 + 新增）；真实主机冒烟见 §5.4 |

B-1–B-20 由上述用例覆盖（B-3 哨兵、B-7 `--print -o`、B-8 两次运行不覆盖、B-13 单类型行、B-18 help 零网络、B-19 epilog↔choices、B-20 既有调用点补参数后全绿）；B-21 / B-22 / B-23 按 TD-2 §11.4 现行预期断言或按 ON-1 不作判据。

## 5. 实际执行的验证（本机，2026-10-23）

### 5.1 指定测试命令

```bash
$ python3 -m unittest discover -s scripts -p 'test_collect_host_info.py' -v
Ran 83 tests in 0.305s
OK
```

```bash
$ python3 -m unittest discover -s scripts -p 'test_*.py'
Ran 112 tests in 0.869s
OK
```

基线（实现前，同一工作区）：`test_collect_host_info.py` 43 tests OK、`scripts` 全量 72 tests OK。即新增 40 个用例、0 个既有用例被放宽或删除。

### 5.2 CLI 行为冒烟（真实主机，均在临时目录执行）

| 命令 | 结果 |
| --- | --- |
| `python3 collect_host_info.py --help` | rc=0；usage 显示 `--resource-type {BARE_METAL,VIRTUAL_MACHINE}` 且 `--role` / `--status` 枚举；epilog 含 ①模板必填 ②`--push` 必填 ③枚举值 ④引用语义 ⑤默认文件名 |
| `python3 collect_host_info.py`（无参） | rc=2；stderr = argparse 原始行 `the following arguments are required: --resource-type` + 允许值 + `使用 --help …`；无文件、stdout 空 |
| `--print --resource-type bare_metal` | rc=2；stderr 保留 `invalid choice: 'bare_metal'` + 允许值；无文件、stdout 空 |
| `--print --resource-type BARE_METAL --host f032host` | rc=2；stderr `argument --host: BARE_METAL 行的 host 恒空，--host 仅适用于 VIRTUAL_MACHINE`；无文件、stdout 空 |
| `--print --resource-type BARE_METAL --host ""` | rc=0；`host` 列空 |
| `--print --resource-type BARE_METAL --cluster "" --network ""` | rc=0；`cluster` / `network` 列空 |
| `--print --resource-type BARE_METAL --push --api-url … --api-key k --cluster ""` | rc=2；stderr `错误：--push 需要同时提供 --cluster 与 --resource-type。`（F025 现状不变） |
| `--resource-type BARE_METAL` / `--resource-type VIRTUAL_MACHINE`（临时目录） | rc=0；分别产出 `csm_host_info_bare_metal.csv` / `csm_host_info_virtual_machine.csv`，两文件同时存在且 `sha256sum` 不同（`fe0361e8…` / `049b0ec0…`）；不产出旧名 `csm_host_info.csv` |
| `--print --resource-type BARE_METAL -o p.csv` | rc=0；`p.csv` 不存在，stdout 有 CSV |
| 真实主机 `--print --resource-type BARE_METAL` | rc=0；4 行输出（表头 + 3 数据行），首行即 F023 §6 冻结 26 列同序，`resource_type` 列全为 `BARE_METAL`，`host`/`vcpu`/`disk_gb`/`hypervisor` 与业务/归属列空 |

### 5.3 契约零 diff 与工作区洁净

```bash
$ git diff --stat 89a5d4ff61f9df35f8f4393887701e7015bc26d8 -- docs/api/F023.md docs/api/F014.md
（无输出 = 零 diff）
```

```bash
$ git status --porcelain=v1 --untracked-files=all
 M .gitignore
 M docs/features/F024/README.md
 M docs/features/F024/field-mapping.md
 M docs/features/F024/implementation.md
 M docs/features/F025/implementation.md
 M scripts/collect_host_info.py
 M scripts/test_collect_host_info.py
?? docs/features/F032/implementation.md
```

`.gitignore` 忽略项生效（DR-1013）：

```bash
$ git check-ignore -v csm_host_info.csv csm_host_info_bare_metal.csv csm_host_info_virtual_machine.csv
.gitignore:175:csm_host_info.csv	csm_host_info.csv
.gitignore:176:csm_host_info_bare_metal.csv	csm_host_info_bare_metal.csv
.gitignore:177:csm_host_info_virtual_machine.csv	csm_host_info_virtual_machine.csv
```

仓库工作区无 `csm_host_info*.csv` 残留（默认文件名冒烟全部在 `mktemp -d` 目录内执行，测试用例通过 `tempfile` + `chdir` 隔离并在 `finally` 复原 cwd）。

## 6. 未验证项（明确留给 TEST）

| 项 | 原因 / 归属 |
| --- | --- |
| F023 真实 `/validate` 端到端（T77 承接、T102 / T103 / T106 端到端部分） | 需启动 `compose.test.yaml` + `-p csmtest` 测试栈（`http://localhost:18080`）与夹具 Cluster / Network / BM Host；本阶段未启动测试栈，**NOT TESTED**，不得以单元测试冒充 |
| BM / VM 真实文件经预校验后的行级错误清单 | 同上，属 TEST 阶段 |
| `--push` 真实写入路径（`created` / `interfaces_created` / `ip_addresses_created`） | F032 无写入验收需求；T82 仅做回归，且 F032 规范禁止 `--yes` 端到端写入 |
| PostgreSQL 侧约束行为 | F032 Database `NOT_REQUIRED`（`docs/database/f032-collector-cli.md`），脚本不写库 |
| 跨 Feature 整体验收（§31–§33） | 协调器结合 F001–F031 历史证据核验，不以本 Feature 局部结果代替 |

## 7. 实现细节提示（不新增业务规则）

- `-o ""`（空串）按未提供处理，回落到类型默认文件名；`--role` / `--status` 空白串与空串同属非法（`choices`，rc=2）；自由文本空白串视为未提供。
- `--print` + `--push` 组合按 ON-1 保持 F025 顺序，本 Feature 未定义新语义、未纳入判据。
- 自定义错误文本中的 `prog: error:` 前缀为 argparse 原始格式，`build_error_hint()` 只做追加，未改写原始错误语义。
- `build_parser()` 为新增的模块内构造函数，供 `--help`、`parse_args()` 与 DR-1014 一致性守卫复用；未新增模块或第三方依赖（仍仅标准库）。

## 8. 结论

实现覆盖 DR-1001–DR-1016，ON-1 遵守未改动；F014 / F023 模板、端点、校验与错误口径零 diff；`scripts` 全量单元测试 112 项通过、采集脚本 83 项通过；工作区无脚本生成物残留。真实 `/validate` 端到端与整体验收按 §6 留待 TEST / 协调器。

**BACKEND COMPLETE**

GIT: NONE
