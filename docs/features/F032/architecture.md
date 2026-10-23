# F032 采集脚本类型必填、帮助信息与按类型生成 — ARCHITECTURE 阶段报告

- **状态**：READY FOR DESIGN
- **版本**：v1
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
| **DR-1004** | 帮助分区：①模板必填（cluster/hostname/resource_type/name/ip，VM 另需 host；脚本须补 cluster 及 VM host）；②`--push` 必填（--api-url、API Key、--cluster；`--resource-type` 已全局满足；说明“脚本必填 ≠ 模板必填”）；③枚举值逐字列出；④引用语义（cluster code/UUID、host hostname/UUID、network name/CIDR）。 |
| **DR-1005** | 默认输出名：`DEFAULT_OUTPUT_BY_TYPE = {"BARE_METAL": "csm_host_info_bare_metal.csv", "VIRTUAL_MACHINE": "csm_host_info_virtual_machine.csv"}`；`-o` 默认 `None`，由 `resolve_output_path(args)` 回填。 |
| **DR-1006** | 输出优先级：`--print` > `-o/--output` > 类型默认名；`--print` 即使同时给 `-o` 也不写文件；`--no-header` 只控制表头。 |
| **DR-1007** | 自定义 `_ArgumentParser.error()`：保留 argparse 原始错误行，追加允许值与 `--help` 提示，统一退出码 2；覆盖缺失必填与非法枚举。 |
| **DR-1008** | 零副作用由顺序保证：`parse_args(argv)` 是 `main()` 第一句，任何参数错误在采集、写文件、stdout、网络之前终止；`main()` 不捕获 `SystemExit`。 |
| **DR-1009** | `--push` multipart filename 保持 `csm_host_info.csv` 不变；本地默认文件名变化不传播到请求体。 |
| **DR-1010** | 一次运行只产出一类行：`--resource-type` 单值；不新增 BM/VM 混合输出路径。 |
| **DR-1011** | 不修改 F014/F023：`TEMPLATE_COLUMNS` 26 列、`IMPORT_PATH`、端点、错误口径、上限不动；不新建 Contract。 |
| **DR-1012** | `_push()` 保留 `--api-url`/API Key/`--cluster` 前置校验和 `resource_type` 防御性检查；主路径由全局必填保证。 |
| **DR-1013** | `.gitignore` 追加两个类型化默认文件名，保留旧 `csm_host_info.csv`。 |
| **DR-1014** | 帮助与枚举一致性守卫：测试断言 `build_epilog()` 含全部枚举值/必填列，且 parser `choices` 与常量逐字相等。 |

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
| 非法枚举 | 小写/短名/空串/未知值 + role/status 非法值：退出 2，无文件/stdout/网络，列出允许值 | T105 |
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
