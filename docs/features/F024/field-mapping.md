# F024 采集脚本字段映射与用法

脚本：`scripts/collect_host_info.py`（离线、只读、手动运行，仅 Python 3 标准库）。

## 用法

```bash
# 通用（仅填 BM/VM 共有列）
python3 scripts/collect_host_info.py -o host.csv

# 按类型填充类型专属列（不写入 resource_type 单元格）
python3 scripts/collect_host_info.py --resource-type BARE_METAL -o host.csv
python3 scripts/collect_host_info.py --resource-type VIRTUAL_MACHINE -o host.csv

# 可选：包含 loopback / down 接口（默认排除）
python3 scripts/collect_host_info.py --include-loopback --include-down -o host.csv
```

输出为 CSV（UTF-8 BOM），表头与 `docs/api/F023.md` §6 冻结的 26 列逐字逐序一致。补全人工字段后经既有导入流程（预校验 → 确认 → 写入）导入。

## 逐列映射

| # | 列名 | 自动采集 | 来源 / 说明 |
| --- | --- | --- | --- |
| 1 | `cluster` | ✗ 人工 | CSM 业务归属，留空 |
| 2 | `hostname` | ✓ | `/proc/sys/kernel/hostname` 或 `hostname`；trim + ASCII 小写折叠 |
| 3 | `resource_type` | ✗ 人工 | 不推断；`--resource-type` 仅决定填哪些类型专属列，不写入本格 |
| 4 | `role` | ✗ 人工 | 业务语义，留空 |
| 5 | `status` | ✗ 人工 | 业务状态，留空 |
| 6 | `host` | ✗ 人工 | VM Host 引用需 CSM 内已存在，留空 |
| 7 | `vcpu` | ✓（VM） | `os.cpu_count()`（逻辑 CPU） |
| 8 | `memory_mb` | ✓ | `/proc/meminfo` `MemTotal` → MiB |
| 9 | `disk_gb` | ✓（VM） | `lsblk -bdn -o SIZE` 求和 → GiB |
| 10 | `hypervisor` | ✓（VM） | `systemd-detect-virt` |
| 11 | `manufacturer` | ✓（BM） | `/sys/class/dmi/id/sys_vendor`（免 root） |
| 12 | `model` | ✓（BM） | `/sys/class/dmi/id/product_name` |
| 13 | `serial_number` | ✓（BM） | `/sys/class/dmi/id/product_serial` |
| 14 | `cpu_model` | ✓（BM） | `lscpu` 或 `/proc/cpuinfo` |
| 15 | `cpu_sockets` | ✓（BM） | `lscpu` Socket(s) 或 `/proc/cpuinfo` 唯一 `physical id` |
| 16 | `cpu_cores` | ✓（BM） | `/proc/cpuinfo` `(physical id, core id)` 去重计数（物理核心，不含超线程） |
| 17 | `gpu_model` | ✓（BM） | `nvidia-smi` → `lspci` |
| 18 | `gpu_count` | ✓（BM） | `nvidia-smi` 计数；`lspci` 不可靠时留空 |
| 19 | `name` | ✓ | 网卡名称（如 `eth0`） |
| 20 | `interface_type` | ✓ | 固定 `OTHER`，不按名称推断 |
| 21 | `mac_address` | ✓ | `ip` / `/sys/class/net/<if>/address` |
| 22 | `speed_mbps` | ✓ | `/sys/class/net/<if>/speed`（不可得留空） |
| 23 | `mtu` | ✓ | `ip` / `/sys/class/net/<if>/mtu` |
| 24 | `enabled` | ✓ | operstate `up`→`true`、`down`→`false`、未知/不可判定→留空（导入默认 `true`）；未知状态不被排除 |
| 25 | `network` | ✗ 人工 | 需命中 CSM 内已存在 Network，留空；`ip` 携带掩码时 F023 可由 `/mask` 解析 Network |
| 26 | `ip` | ✓ | 本机 IPv4 **地址/掩码**（如 `10.0.0.5/24`，每地址一行）；落库剥离掩码由 F023 处理 |

## 采集降级

- 网卡/地址：`ip -j addr` → `ip -o` → `/sys/class/net`（最后一级无地址）。
- CPU：`lscpu` → `/proc/cpuinfo`。
- DMI：`/sys/class/dmi/id`（通常免 root）；不调用 `dmidecode`、不自动提权。
- GPU：`nvidia-smi` → `lspci`。

## 边界

- 默认排除 loopback 与**明确 down** 的接口、以及无 IPv4 的接口；`unknown`/`dormant` 等不可判定状态不被排除且 `enabled` 留空。
- 无 root / 命令缺失 / 字段不可得时一律留空，脚本不报错、不伪造值。
- 只读：仅读 `/proc`、`/sys` 与只读命令输出；唯一写入为 `-o` 指定文件；不连接 CSM、不上传。
- 不采集密码、私钥、token、环境变量等敏感内容。
- 产出文件包含内网拓扑与资产标识，分享前请评估。