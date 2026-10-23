# F032 采集脚本类型必填、帮助信息与按类型生成 — ARCHITECTURE 阶段报告

- **状态**：READY FOR DESIGN
- **版本**：v2（2026-10-23，吸收 Test Design TD-D01–TD-D03 裁定）
- **上游依据**：`docs/features/F032/product.md` v1（READY FOR ARCHITECT）；`docs/product/requirements-v3.md` revision 12 §24.4、修订后的 §24.2/§24.3、§31 T100–T106 与 T73/T79/T84；`docs/api/F023.md` §5/§6（消费，零改动）；F024/F025 architecture；`docs/project/project-plan.yaml` plan_revision 18（用户批准）。
- **范围**：仅采集脚本 CLI、帮助文本、默认输出名、测试与用法文档；不改平台 API、Schema、前端、权限或 F014/F023 模板。

## 1. 方案摘要

F032 是 CLI 表面变更，不触碰数据路径：

| 变更点 | 现状 → 目标 |
| --- | --- |
| `--resource-type` | `choices` + `default=None` → `required=True` + `choices=RESOURCE_TYPE_VALUES` |
| `--role` / `--status` | 自由字符串 → `choices=ROLE_VALUES` / `STATUS_VALUES`，不做大小写折叠或短名映射 |
| `--help` | 零散说明 → 离线内嵌常量生成的分区说明：模板必填、`--push` 必填、枚举值、引用型参数语义 |
| 默认输出名 | 固定 `csm_host_info.csv` → 按类型 `csm_host_info_bare_metal.csv` / `csm_host_info_virtual_machine.csv` |
| `-o/--output` | 静态默认路径 → 默认 `None`，解析后按类型回填 |
| 非法枚举 | 部分被接受 → 统一 argparse 退出码 2，零文件/CSV/网络副作用 |
| 数据路径 | 不变：同一 26 列模板、同一 `build_rows` 类型分支、同一 F023 端点、同一 `--push` 两步流程 |

帮助文本与实际 `choices` 由同一组常量生成，避免“帮助说的”和“实际接受的”不一致。

## 2. 模块边界

| 边界 | 内容 | 归属 |
| --- | --- | --- |
| CLI 层 | `parse_args()`、`_ArgumentParser.error()`、`build_epilog()`、常量区、`resolve_output_path()` | `scripts/collect_host_info.py` |
| 行组装/渲染层 | `build_rows()` / `render_csv()` / `write_csv()` | 不改 |
| 推送层 | `_multipart_body()` / `post_import()` / `_push()` | 仅保留；端点、multipart 文件名、两步流程不变 |
| 测试层 | `scripts/test_collect_host_info.py` | 新增 T100–T106，适配既有 `main()` 调用 |
| 文档/配置 | `docs/features/F024/{README.md,field-mapping.md,implementation.md}`、`docs/features/F025/implementation.md` 用法片段、`.gitignore` | 更新用法与忽略项，不改历史证据 |

无新增模块、无新增运行时依赖（仍仅标准库）。

## 3. 技术决策

| ID | 决策 |
| --- | --- |
| **DR-1001** | `--resource-type` 改为 `required=True, choices=("BARE_METAL","VIRTUAL_MACHINE")`；任一调用形式缺省时在 `parse_args()` 阶段失败。 |
| **DR-1002** | `--role` / `--status` 增加 `choices`：role 为 `COMPUTE/LOGIN/MANAGEMENT/STORAGE/SERVICE/GPU/OTHER`，status 为 `IDLE/ALLOC/DOWN/UNKNOWN`；`default=None`，未提供仍留空；不做大小写折叠、无短名/别名映射。 |
| **DR-1003** | 帮助文本离线内嵌、由常量生成：`TEMPLATE_REQUIRED_COLUMNS`、`TEMPLATE_REQUIRED_VM_EXTRA`、`PUSH_REQUIRED_ITEMS` + `build_epilog()`，使用 `RawDescriptionHelpFormatter`；不联网读取模板端点。 |
| **DR-1004** | 帮助分区：①模板必填（cluster/hostname/resource_type/name/ip，VM 另需 host；脚本须补 cluster 及 VM host）；②`--push` 必填（--api-url、API Key、--cluster；`--resource-type` 已全局满足；说明“脚本必填 ≠ 模板必填”）；③枚举值逐字列出；④引用语义（cluster code/UUID、host hostname/UUID、network name/CIDR），并说明 `--host` 仅适用于 VIRTUAL_MACHINE、BARE_METAL 行 `host` 恒空。 |
| **DR-1005** | 默认输出名：`DEFAULT_OUTPUT_BY_TYPE = {"BARE_METAL": "csm_host_info_bare_metal.csv", "VIRTUAL_MACHINE": "csm_host_info_virtual_machine.csv"}`；`-o` 默认 `None`，由 `resolve_output_path(args)` 回填。 |
| **DR-1006** | 输出优先级：`--print` > `-o/--output` > 类型默认名；`--print` 即使同时给 `-o` 也不写文件；`--no-header` 只控制表头。 |
| **DR-1007** | 自定义 `_ArgumentParser.error()`：保留 argparse 原始错误行，追加允许值与 `--help` 提示，统一退出码 2；覆盖缺失必填与非法枚举。 |
| **DR-1008** | 零副作用由顺序保证：`main()` 前两句为 `parse_args(argv)` + `_validate_args(parser, args)`，任何参数错误在采集、写文件、stdout、网络之前终止；`main()` 不捕获 `SystemExit`。 |
| **DR-1009** | `--push` multipart filename 保持 `csm_host_info.csv` 不变；本地默认文件名变化不传播到请求体。 |
| **DR-1010** | 一次运行只产出一类行：`--resource-type` 单值；不新增 BM/VM 混合输出路径。 |
| **DR-1011** | 不修改 F014/F023：`TEMPLATE_COLUMNS` 26 列、`IMPORT_PATH`、端点、错误口径、上限不动；不新建 Contract。 |
| **DR-1012** | `_push()` 保留 `--api-url`/API Key/`--cluster` 前置校验和 `resource_type` 防御性检查；主路径由全局必填保证。 |
| **DR-1013** | `.gitignore` 追加两个类型化默认文件名，保留旧 `csm_host_info.csv`。 |
| **DR-1014** | 帮助与枚举一致性守卫：测试断言 `build_epilog()` 含全部枚举值/必填列，且 parser `choices` 与常量逐字相等。 |
| **DR-1015** | `_validate_args(parser, args)` 在 `parse_args()` 后、采集前执行：`--resource-type BARE_METAL` + 非空 `--host` 视为非法用法，`parser.error()` 退出码 2，零文件/stdout/网络副作用；`--host ""` 视为未提供。依据 T102、F023 §6.1、CHG011-BQ03。 |
| **DR-1016** | 空串口径统一：枚举参数（`--resource-type`/`--role`/`--status`）空串 = 非法（argparse `choices`，rc=2）；自由文本参数（`--cluster`/`--host`/`--network`）空串 = 未提供（列留空）；`--push` 的 `--cluster ""` 行为不变。依据 §24.4 与 T105。 |
| **ON-1** | `--print` + `--push` 同时给出保持 F025 现状（先 stdout、再预校验/写入），不新增规则、不设 PASS/FAIL 判据；若未来定义须走需求变更。 |

## 4. 分层与 API 判定

| 字段 | 值 | 理由 |
| --- | --- | --- |
| `layers.database` | false | 无 Schema/Migration/索引/约束变更，脚本不写库 |
| `layers.backend` | false | 不改 FastAPI 路由、Service、模型、权限 |
| `layers.frontend` | false | 无页面/组件/交互 |
| `api_required` | false | 不定义平台 API；仅消费 F023 §3/§4/§5/§6 |

Contract：`NOT_REQUIRED`。F032 变更面是本地 CLI 表面；F023 §5/§6 与 F014 零 diff。

## 5. 实现工作

- `scripts/collect_host_info.py`：常量区、`_ArgumentParser`、`build_epilog()`、`resolve_output_path()`、required/choices、`-o` 默认 None、`--print` 优先级。
- `scripts/test_collect_host_info.py`：新增 T100–T106；既有 `main([...])` 调用补 `--resource-type`（3 处），不放宽 `required`。
- 文档：F024 README/field-mapping/implementation 与 F025 implementation 的用法示例；`.gitignore` 加两行。
- 证据：`docs/features/F032/implementation.md`、`test-report.md`。

## 6. 验证策略

| 组 | 断言 | 映射 |
| --- | --- | --- |
| 帮助 | `--help` 含 required 标注、两类型、role/status 全枚举、两个必填分区、引用语义；epilog 与 choices 一致 | T100 |
| 缺失必填 | 无参/仅 `--print`/仅 `-o`/仅 `--push` 均退出 2；无文件、stdout 空、零网络、collect/post_import 未调用 | T101 |
| BM | `resource_type=BARE_METAL`；host/vcpu/disk/hypervisor 空；硬件列可填；26 列同序 | T102 |
| VM | `resource_type=VIRTUAL_MACHINE`；硬件列空；host 未给留空/给了写入；vcpu/disk/hypervisor 可填 | T103 |
| 默认名/优先级 | 两类型默认名不同且不覆盖；`-o` 优先；`--print -o` 不落盘 | T104 |
| 非法枚举 | 小写/短名/空串/未知值 + role/status 非法值：退出 2，无文件/stdout/网络，列出允许值；BM + 非空 `--host` 同样退出 2 且零副作用（DR-1015） | T105 / T102 |
| 零 diff/回归 | 26 列守卫、端点/multipart filename 不变；`--print`/`--no-header`/`-o`/`--push` 语义不变；无 push 零网络 | T106 |
| 回归 | T73/T75/T77/T78/T79/T82/T83/T84 | 既有用例 + 真实 F023 `/validate` |

真实 `/validate`：用生成的 BM/VM 文件只做预校验，不写入；预期仅人工待补字段行错误。环境不可用时如实记录未验证项，不以单测冒充。

## 7. 风险与兼容性

| ID | 风险 | 处理 |
| --- | --- | --- |
| R-1 | 旧无 `--resource-type` 调用失败 | 属 §24.4 已批准破坏；帮助列允许值；更新 F024/F025 用法；执行前 grep 仓库调用点 |
| R-2 | 默认文件名变化 | `-o csm_host_info.csv` 可复现旧名；文档说明；`.gitignore` 保留旧条目 |
| R-3 | 新默认名污染工作区 | `.gitignore` 追加两项 |
| R-4 | 帮助与枚举漂移 | 常量生成 + DR-1014 守卫 |
| R-5 | argparse 缺失必填消息不含允许值 | 自定义 `error()` 追加允许值与 `--help` |
| R-6 | 上传文件名误解 | DR-1009：multipart filename 保持 `csm_host_info.csv` |
| R-7 | 真实 `/validate` 环境依赖 | 如实记录；不得以单测代替 |

明确不改：F014/F023 模板与契约、DB Schema/Migration、平台 Service Layer/路由/模型/权限、前端、F024/F025 历史 test/review 证据。

## 8. 结论

方案在 §24.4 与 T100–T106 的已确认边界内，无新增业务规则、无平台行为、无 Contract 变更。**READY FOR DESIGN**；待 Database `NOT_REQUIRED` 签核与 Test Design 后，由 Architect 定稿为 `READY FOR IMPLEMENTATION`。

## 9. CONTRACT / 最终设计签核

- **设计版本**：v2（§1–§8 正文与 DR-1001–DR-1016、ON-1 未修改；本段为 CONTRACT 阶段签核记录）
- **签核阶段 / 日期**：CONTRACT，2026-10-23
- **签核者**：Architect
- **结论**：**READY FOR IMPLEMENTATION**
- **Contract 状态**：**NOT_REQUIRED**（`api_required = false`）

### 9.1 核对输入（版本绑定）

| 输入 | 版本 / 依据 | 核对结果 |
| --- | --- | --- |
| `docs/features/F032/product.md` | v1（READY FOR ARCHITECT，A1–A11，Blocking Questions = None） | 一致 |
| `docs/product/requirements-v3.md` | revision 12 §24.4、修订后 §24.2/§24.3、§31 T100–T106 与 T73/T79/T84、§35.1 | 一致，无新增业务规则 |
| `docs/features/F032/architecture.md` | v2（DR-1001–DR-1016、ON-1、R-1–R-7） | 本次签核对象 |
| `docs/database/f032-collector-cli.md` | 2026-10-23，`NOT_REQUIRED`（Database 签核） | 与 DR-1011/DR-1009 无冲突 |
| `docs/features/F032/test-report.md` | TD-2 / v2 / 2026-10-23（TEST DESIGN READY）；TD-D01–D03 CLOSED | 覆盖 DR-1004④ / DR-1015 / DR-1016（R-1–R-5） |
| `docs/api/F023.md` | v1 §5 / §6（消费，零改动；§6 #6 / §6.1 为 DR-1015 上游依据） | 一致 |
| `docs/api/F014.md` | v1（零改动） | 一致 |
| `docs/project/project-plan.yaml` | plan_revision 18（用户 2026-10-23 批准并授权实施 F032） | 授权有效 |

### 9.2 一致性与约束结论

1. 需求、架构、Database `NOT_REQUIRED`、TD-2 四者无冲突；TD-D01（BM + `--host`）、TD-D02（空串口径）、TD-D03（`--print` + `--push`）已分别由 DR-1015、DR-1016、ON-1 裁定并被 TD-2 §11.3/§11.4 吸收，无需用户重新裁定。
2. **Contract NOT_REQUIRED 理由**：F032 不新增或修改任何 Endpoint / 参数 / Schema / 错误码 / 权限 / 上限；唯一 API 消费面为 F023 既有端点；变更面为本地 CLI 表面（参数、help、默认文件名），其字段面由 DR-1001–DR-1016 与 DR-1014 守卫确定；`--cluster`（code/UUID）、`--host`（hostname/UUID）、`--network`（name/CIDR）完全引用 F023 §6 已冻结寻址规则，不新增允许字符；字段与枚举唯一权威仍为 `docs/api/F023.md` §6，不建第二份契约。
3. **layers**：`database=false`（脚本不写库、无 Schema/Migration）、`backend=false`（不改 FastAPI 路由/Service/模型/权限，且无 Migration 需承接）、`frontend=false`（无 UI）。脚本与测试改动由 Backend 角色实施，证据落 `docs/features/F032/implementation.md`，不改变上述 layers 判定。
4. **验证映射补充（不改 DR）**：architecture §6 未逐字列出 DR-1004④（`--host` 仅适用 VM）与 DR-1016 自由文本空串的验证行，由 TD-2 §11.3 **R-1 / R-4** 承接，二者随本签核成为必测项。

### 9.3 实现放行条件（强制遵守）

- 必须实现 DR-1001–DR-1016；ON-1 不作为验收判据（偏离 F025 现状按回归缺陷上报）。
- 必须覆盖 T100–T106、T73/T79/T84（修订口径）、B-1–B-20 及 TD-2 R-1–R-5，并保持 T75/T77/T78/T81/T82/T83 无回归。
- 端到端仅对 `compose.test.yaml` + `-p csmtest`（`http://localhost:18080`）执行 **`/validate` 预校验**，禁止 `--yes` 写入；环境不可用时如实标 `NOT TESTED`，不得以单测冒充。
- F014/F023 模板、端点、校验、上限、错误口径零 diff；`TEMPLATE_COLUMNS` 26 列与 multipart filename `csm_host_info.csv` 不变。

### 9.4 遗留项与风险

| ID | 影响 | Owner | 状态 |
| --- | --- | --- | --- |
| TD-D04（真实 `/validate` 环境） | 不阻塞实现启动；阻塞 `READY FOR REVIEW`（端到端项可能只能标 NOT TESTED） | 协调器 / Tester | OPEN |
| TD-D05（`.gitignore` 类型化默认名） | T106 洁净性检查依赖；DR-1013 明确归实现阶段 | Backend | OPEN |
| `-o ""`、`--role/--status` 旧自由字符串用法、DR-1007 消息须含 DR-1015 专属原因 | 实现细节提示，不新增业务规则、不设 PASS/FAIL 判据 | Backend | NOTE |

### 9.5 签核效力

本签核绑定上述输入版本与 TD-2 / v2、Database `NOT_REQUIRED` 签核。若 §24.4 / T100–T106 口径、DR-1001–DR-1016、ON-1、F023 §5/§6 列集或行适用性任一变更，本签核对应部分失效并按 `docs/project/change-control.md` 复核；未变更部分不要求重复设计。
