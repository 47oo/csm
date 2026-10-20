# F024 离线主机信息采集脚本 — ARCHITECTURE 阶段报告

- **状态**：READY FOR IMPLEMENTATION
- **版本**：v1（最终设计定稿）
- **上游依据**：`docs/features/F024/product.md` v1；`docs/product/requirements-v3.md` revision 9 §24.2、§24.1、§31（T73–T78）；`docs/api/F023.md` v1 §6（26 列冻结模板）；`docs/project/project-plan.yaml` revision 12。
- **签核**：Architect，2026-10-20。核对 Database `NOT_REQUIRED` 与 Test Design（`docs/features/F024/test-report.md#test-design`）后签核最终设计。

---

## 1. 方案摘要

仓库内单文件 Python 3（仅标准库）脚本 `scripts/collect_host_info.py`：在目标 Linux 主机本地手工运行，只读采集本机事实，输出 F023 §6 冻结的 26 列 CSV。

- 脚本是**导入模板的生产者**，与平台运行时、数据库、API 完全解耦；可单文件复制到目标主机运行。
- 唯一接口是**文件格式契约**：输出表头逐字逐序等于 F023 §6 的 26 列；导入仍由 F023 服务端负责全部解析与校验。
- 不引入 Compose 分发、无常驻进程、无网络回传。

## 2. Domain / Data Impact

| 维度 | 结论 |
| --- | --- |
| 新增实体/字段/迁移 | 无 |
| F014 / F023 模板与契约 | 保持不变（脚本仅消费） |
| 平台 API / Schema | 无变更 |
| 运行时依赖 | 无新增；脚本仅用标准库 |

## 3. 分层与 API 判定

- `layers.database=false`、`layers.backend=false`、`layers.frontend=false`。
- `api_required=false`。脚本不是 FastAPI 服务层，不新增路由/模型，也不调用平台 API。
- 无 Contract：不新建 `docs/api/F024.md`；输出格式**复用并消费** `docs/api/F023.md` §6 冻结模板（`not_required.contract`）。
- **交付物承载**：本 Feature 交付物是仓库工具 + 测试 + 说明；实现与验证证据落在 `docs/features/F024/implementation.md` 与 `test-report.md`（沿用 F016 对全 false 层 Feature 的处理方式）。

## 4. 技术决策（DR）

| ID | 决策 | 理由 |
| --- | --- | --- |
| DR-801 | 语言：Python 3，仅标准库（`csv`/`json`/`subprocess`/`os`/`re`/`argparse`），兼容 3.8+ | CSV 正确性、单位换算、可测性优于 Shell；目标主机无需平台环境或第三方包 |
| DR-802 | 模板同步：**编译期内嵌 26 列常量**，不运行时抓取 `GET /imports/.../templates` | 运行时抓取需连 CSM，违反离线定位；内嵌可 scp、可审计 |
| DR-803 | 模板漂移防护：pytest/unittest 断言内嵌列集逐字等于 F023 §6 冻结列 | F023 冻结版变化时测试失败提示同步 |
| DR-804 | 输出：默认 CSV，UTF-8 兼容 BOM（`utf-8-sig`），RFC 4180；`.xlsx` 一期不做 | Windows Excel 双击不乱码；F023 §7 兼容 BOM；避免主机侧第三方依赖 |
| DR-805 | `resource_type` 单元格**始终留空**（人工补全）；类型专属列仅当显式 `--resource-type` 时填充，未指定则全部留空 | 遵守 §24.2「留空不推断」并避免与 F023 §6.1 逐行适用性冲突；不指定时产出对 BM/VM 均合法的「通用」行 |
| DR-806 | 网卡 `interface_type` 默认 `OTHER`，不按名称推断；默认排除 `lo` 与 `down` 接口；无 IPv4 的接口不产出行 | 对齐 F023 §6 #20 与 §6.2；模板以每行一个 IP 为单位 |
| DR-807 | 采集降级：`ip -j addr` → `ip -o` → `/sys/class/net`；CPU 用 `lscpu` → `/proc/cpuinfo`；DMI 优先 `/sys/class/dmi/id`（免特权）→（不自动提权）；GPU `nvidia-smi` → `lspci`（计数不可靠则留空） | 无 root / 无命令时留空不报错（T76） |
| DR-808 | 单位：`memory_mb`=MiB、`disk_gb`=GiB、`speed_mbps`=Mbps、`mtu`=bytes；`cpu_cores`=整机物理核心（`(physical id, core id)` 去重，不含超线程） | 对齐 D01 / T39 / F023 §6 |
| DR-809 | 只读保证：仅读 `/proc`、`/sys` 与只读命令输出；唯一写入为 `-o` 指定文件；永不提权 | §24.2 只读 |
| DR-810 | 不采集敏感内容（密码/私钥/token/环境变量）；`/etc/shadow` 等不读取 | 安全边界 |

## 5. Frontend / Backend Work

- Frontend：无。
- Backend（平台服务层）：无。
- 仓库工具：`scripts/collect_host_info.py`（实现）、`scripts/test_collect_host_info.py`（测试）、`docs/features/F024/field-mapping.md`（逐列映射与用法）。

## 6. Test Work

详见 `docs/features/F024/test-report.md#test-design`：T73–T78 映射、命令降级/无 root/单位映射/模板漂移的单元测试、以及可选的 F023 `validate` 端到端结构验收（需真实 CSM 与既存 cluster/network）。

## 7. 风险

| ID | 风险 | 处理 |
| --- | --- | --- |
| T-R1 | 模板漂移 | DR-803 测试守卫 |
| T-R2 | 单位映射错误 | 单元测试覆盖 |
| T-R3 | 命令缺失/发行版差异 | DR-807 分级降级，留空不报错 |
| T-R4 | VM 上 DMI 返回虚拟化厂商 | 不推断 `resource_type`，仅按显式 `--resource-type` 填列 |
| T-R5 | GPU 计数在 `lspci` 下不可靠 | 计数留空 |
| T-R6 | 多网卡/多 IP 展开口径 | 默认排除 `lo`/`down`/无 IP；文档说明且可 `--include-*` 覆盖 |

## 8. 最终设计定稿

Architect 2026-10-20：核对 Database `NOT_REQUIRED`、Test Design 与实现一致，确认无平台/契约影响，最终设计 **READY FOR IMPLEMENTATION**。设计绑定需求 revision 9 与 F023 §6 v1；上游变化时复核受影响部分。