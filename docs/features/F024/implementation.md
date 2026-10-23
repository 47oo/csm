# F024 离线主机信息采集脚本 — 实现报告

- **状态**：COMPLETE
- **上游依据**：`docs/features/F024/architecture.md` v1（最终设计定稿）；`docs/features/F024/product.md` v1；`docs/api/F023.md` v1 §6。
- **说明**：F024 的 `layers.backend/frontend/database` 均为 false，且无平台 API。本报告记录仓库工具交付物；实现与验证证据同时由 `docs/features/F024/test-report.md` 承接。

---

## 1. 交付物

| 文件 | 说明 |
| --- | --- |
| `scripts/collect_host_info.py` | 单文件、仅标准库的离线只读采集脚本 |
| `scripts/test_collect_host_info.py` | 30 个单元测试（模板漂移、归一化、单位、降级、行映射、三态 enabled、掩码、确定性、CSV 输出） |
| `docs/features/F024/README.md` | 快速开始与边界说明 |
| `docs/features/F024/field-mapping.md` | 逐列「自动采集 / 人工补全」映射与用法说明 |

## 2. 行为摘要

- 默认生成 `csm_host_info.csv`（UTF-8 BOM），表头为 `docs/api/F023.md` §6 冻结的 26 列，列名与列序逐字一致。
- 自动填充：`hostname`、`memory_mb`、网卡列（`name`/`interface_type`=OTHER/`mac_address`/`speed_mbps`/`mtu`/`enabled`）、`ip`（含 `/mask`）；按 `--resource-type` 选择填充 BM 硬件列或 VM 容量列。
- `enabled` 三态：`up`→`true`、`down`→`false`、其余（unknown/dormant/缺失）→空且不排除（RV-01）。
- 始终留空：`cluster`、`resource_type`、`role`、`status`、`host`、`network`。
- 只读；唯一写入为输出文件；无网络请求；无提权。
- 命令降级：`ip -j addr` → `ip -o` → `/sys/class/net`；`lscpu` → `/proc/cpuinfo`；DMI 免特权 `/sys/class/dmi/id`；GPU `nvidia-smi` → `lspci`。

## 3. Contract 符合性

| 契约 | 符合性 |
| --- | --- |
| F023 §6 26 列列名/列序 | 以 `TEMPLATE_COLUMNS` 常量内嵌，测试 `test_template_columns_match_f023_frozen` 守卫 |
| F023 §6.2 省略语义 | 未知/不可得字段写空单元格，不用 0 或占位值 |
| F023 §6 #20 类型不推断 | `interface_type` 固定 `OTHER` |
| D01 归一化与单位 | hostname trim+ASCII 小写折叠；memory MiB、disk GiB、speed Mbps、mtu bytes；`cpu_cores` 物理核心去重不含超线程 |
| §24.2 留空不推断 | 业务/归属字段恒为空 |

## 4. 影响范围

- 新增仓库工具与测试；**未修改**任何 F014/F023 文件、平台后端/前端/数据库/契约。
- 无 Migration、无 Schema、无 API、无 Compose 变更。

## 5. 验证

- `python3 -m unittest discover -s scripts -p 'test_collect_host_info.py'`：30 tests OK。
- `python3 -m unittest discover -s scripts -p 'test_*.py'`：59 tests OK（无回归）。
- 冒烟：容器内 `ip -j addr` 解析成功、产出 2 行且 `ip` 携带 `/24` 掩码；表头正确。
- 端到端 `validate` 验收（T77）为环境依赖，见 `test-report.md`。

**结论**：实现完成，符合设计与契约。

---

## revision 12 errata（2026-10-23，F032 承接）

> 本节只追加，不修改上文任何历史原文与证据。

- **依据**：`docs/product/requirements-v3.md` revision 12 §24.4、修订后的 §24.2 / §24.3 与 T73 / T79 / T84；`docs/features/F032/architecture.md` v2（DR-1001–DR-1016、ON-1）；`docs/features/F032/implementation.md`。
- **已变更的 CLI 表面（覆盖上文 §2 中相应表述）**：
  1. `--resource-type` 由可缺省改为**必填**，取值仅 `BARE_METAL` / `VIRTUAL_MACHINE`；缺失或非法时退出码 2，不采集、不写文件、不输出 CSV、不联网。
  2. `--role` / `--status` 增加枚举 `choices`（7 / 4 值），不做大小写折叠、无短名映射；空串视为非法。
  3. 默认输出文件名按类型区分：`csm_host_info_bare_metal.csv` / `csm_host_info_virtual_machine.csv`；`-o/--output` 优先，`--print` 不写文件。
  4. `--help` 改为分区说明模板必填、`--push` 必填、枚举值与引用语义（离线内嵌常量生成）。
  5. `BARE_METAL` + 非空 `--host` 为非法用法（退出码 2）；`--host ""` / `--cluster ""` / `--network ""` 视为未提供。
- **未变更（继续有效）**：上文 §2 的采集范围、单位与归一化、`enabled` 三态、命令降级、留空不推断规则，以及 §3 的 F023 §6 26 列/列序、§6.2 省略语义、`interface_type=OTHER`；唯一写入仍为输出文件，默认仍离线只读。
- **验证**：见 `docs/features/F032/implementation.md` §5（T100–T106 与 TD-2 R-1–R-5 自动化用例；T73 / T79 / T84 修订口径的本地部分）。

**结论**：F024 历史交付结论不变；revision 12 口径下的 CLI 表面由 F032 交付。
