# F032 real-validate 证据脱敏说明（F036 / F032-RV-03）

- **脱敏日期**：2026-10-26（F036 IMPLEMENTATION Gate，plan revision 22）
- **裁定来源**：`docs/features/F036/architecture.md` §3 DR-F036-06 + §12 定稿 TD-I-1（范围修正为 5 个被跟踪文件 / 20 处）。

## 1. 规则

`mac_address` 列保留前 2 个八位组，后 4 个八位组替换为字面 `xx`：

| 原值 | 脱敏后 |
| --- | --- |
| `08:00:58:00:00:05` | `08:00:xx:xx:xx:xx` |
| `d8:b3:2f:5f:a8:1f` | `d8:b3:xx:xx:xx:xx` |
| `00:ff:14:65:ff:5b` | `00:ff:xx:xx:xx:xx` |

仅替换匹配 `MAC` 正则的字面量，**不改变**任何其它字节。

## 2. 命中数矩阵（`docs/features/F032/artifacts/` 全目录、免 ignore 扫描）

| 文件 | 脱敏前命中 | 脱敏后命中 | 结构保持 |
| --- | --- | --- | --- |
| `real-validate/f032-bm-real.csv` | 3 | **0** | 4 行 × 26 列，表头不变 |
| `real-validate/f032-vm-real.csv` | 3 | **0** | 4 行 × 26 列，表头不变 |
| `real-validate/f032-vm-nohost.csv` | 3 | **0** | 4 行 × 26 列，表头不变 |
| `real-validate/setup.log` | 9 | **0** | 159 行不变 |
| `cli-smoke.log` | 2 | **0** | 352 行不变 |
| `real-validate/validate-*.json.raw`、`help.txt`、`real-validate/cleanup.log`、其余 `.log` | 0 | 0 | 未改动 |

复核命令（须**免 ignore**；`rg` 默认遵守 `.gitignore` 会漏掉 `*.log`，不得据此声称「命中 0」）：

```bash
grep -rnE "([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}" docs/features/F032/artifacts/        # 期望：0 行
grep -rnE "([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}" docs/features/F032/artifacts/ | wc -l # 期望：0
```

## 3. 入库事实

`real-validate/setup.log` 与 `cli-smoke.log` 的路径虽匹配既存 `*.log` 忽略规则，但已通过 `git add -f` 入库（`git ls-files docs/features/F032/artifacts` 可见）。F036 **未改** `.gitignore`、**未** `git rm`、**未**重跑采集脚本。

## 4. 边界声明

1. 脱敏后 CSV / `.log` 与原始采集输出的**字节不等**，因此**不得**再作为「逐字节等价性」证据；等价性证据唯一来源为 `docs/features/F034/artifacts/equivalence-observations.json`、`equivalence-observations-interface-ips.json`（TD-I-5）。
2. 采集运行的结论摘要（`total_rows` / `error_count` / `importable_rows`）见同目录 `validate-f032-*.json.raw`，未改动，比对结论不受影响。
3. 本次仅按 CHG-014 处理 `mac_address`；证据中的主机名/内网地址等其它标识**不在** F036 范围（`docs/features/F036/architecture.md` §10.1 观察项）。
