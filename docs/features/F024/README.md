# F024 离线主机信息采集脚本 — README

在目标 Linux 主机本地手工运行，读取本机信息并生成符合 CSM「资源 + 网卡 + IP」导入模板（`docs/api/F023.md` §6 冻结的 26 列）的 CSV，减少人工逐列填写。

> **用法修订（revision 12 / F032）**：`--resource-type` 现为**必填**参数，默认文件名按类型区分。本节用法、枚举值与默认文件名已按 §24.4 更新；F024 的其余行为与历史交付证据不变（见 `docs/features/F024/implementation.md` 末尾 errata）。

## 快速开始

```bash
# 1. 复制脚本到目标主机（无需安装依赖，仅需 Python 3.8+）
scp scripts/collect_host_info.py user@host:~/

# 2. 在目标主机运行（--resource-type 必填，取值仅 BARE_METAL / VIRTUAL_MACHINE）
python3 collect_host_info.py --resource-type BARE_METAL
#   → 默认写出 csm_host_info_bare_metal.csv
python3 collect_host_info.py --resource-type VIRTUAL_MACHINE --host bm-node01
#   → 默认写出 csm_host_info_virtual_machine.csv（VM 行 host 需为已存在的 BM Host）

# 3. 人工补全 cluster / role / status / network 后，
#    通过 CSM 导入界面预校验 → 确认 → 导入
```

未给 `-o/--output` 时默认文件名按类型区分；显式 `-o` 优先；`--print` 只输出标准输出、不写文件（即使同时给出 `-o`）。缺少或非法 `--resource-type` 时脚本本地失败（退出码 2），不采集、不写文件、不输出 CSV、不联网。

## 参数枚举与引用语义（revision 12）

| 参数 | 允许值 / 语义 |
| --- | --- |
| `--resource-type` | **必填**：`BARE_METAL` / `VIRTUAL_MACHINE`（不做大小写折叠、无短名映射） |
| `--role` | `COMPUTE` / `LOGIN` / `MANAGEMENT` / `STORAGE` / `SERVICE` / `GPU` / `OTHER` |
| `--status` | `IDLE` / `ALLOC` / `DOWN` / `UNKNOWN` |
| `--cluster` | Cluster `code`（大小写不敏感）或 UUID；须存在且未软删；仅 `--push` 时必填 |
| `--host` | 同 cluster 内已存在、未软删的 `BARE_METAL` Host 的 hostname 或 UUID；**仅适用于 `VIRTUAL_MACHINE`**，`BARE_METAL` 行 `host` 恒空（BM + 非空 `--host` 本地失败） |
| `--network` | 同 cluster Network 的 `name` 或 CIDR；留空时由 `ip` 的 `/mask` 解析 |

模板必填（与逐行导入校验一致）：`cluster`、`hostname`、`resource_type`、`name`、`ip`；`VIRTUAL_MACHINE` 行另需 `host`。脚本可自动获得 `hostname` / `name` / `ip`，`resource_type` 由 `--resource-type` 自动写入；须人工或经参数补全的模板必填项为 `cluster`（及 VM 的 `host`）。

`--help` 同时分区列出「模板必填」「`--push` 必填」「枚举值」「引用语义」与默认文件名，文本离线内嵌（不联网）。

## 特性

- **离线、只读、手动**：不连接 CSM、不调用 API、不上传、不写库；唯一写入为输出文件。
- 自动采集：hostname、CPU（型号/插槽/整机物理核心）、内存、GPU、网卡（名称/类型/MAC/速率/MTU）、IPv4 地址/掩码。
- 业务/归属字段（`cluster`、`role`、`status`、`host`、`network`）未提供时一律留空，不推断、无占位值；`resource_type` 由必填参数提供。
- 无 root 时优先读免特权来源（`/sys/class/dmi/id`），其余字段留空且不报错，不自动提权。
- 不改动 F014 / F023 既有模板（26 列同表头同列序）与导入端点、校验行为。

## 文档

- 逐列「自动采集 / 人工补全」映射与采集降级：`docs/features/F024/field-mapping.md`
- 设计方案：`docs/features/F024/architecture.md`
- 模板契约：`docs/api/F023.md` §6

## 测试

```bash
python3 -m unittest discover -s scripts -p 'test_collect_host_info.py'
```