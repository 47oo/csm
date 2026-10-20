# F024 离线主机信息采集脚本 — TEST 报告

- **上游依据**：`docs/product/requirements-v3.md` revision 9 §24.2、§31（T73–T78）；`docs/features/F024/product.md` v1；`docs/features/F024/architecture.md` v1；`docs/api/F023.md` v1 §6。

---

## TEST DESIGN（TD-1）

- **版本**：v1；**结论**：TEST DESIGN READY
- **环境**：Python 3.8+，仅标准库；单元测试在无 root、无 CSM 网络、无真实硬件的环境运行。端到端结构验收（T77）需真实 CSM（`POST /api/v1/imports/resource-interfaces-ips/validate`）与既存 cluster/network。

| 用例 | 验收点 | 测试方法 | 自动化 |
| --- | --- | --- | --- |
| T73 | 表头逐字逐序等于冻结 26 列；业务字段留空 | `TemplateDriftTests.test_template_columns_match_f023_frozen`、`CsvOutputTests.test_header_order_and_bom`、`RowMappingTests.test_business_fields_always_empty` | 是 |
| T74 | 归一化与单位口径；未知留空不用 0/推断 | `CpuTests`（物理核心/插槽/型号）、`MemoryTests`（MiB）、`InterfaceTests`（MTU/MAC/速率/类型不推断）、`RowMappingTests` | 是 |
| T75 | 只读、无网络写、不写 CSM；重复产出稳定 | 代码审查（唯一写入为输出文件）+ 重复运行同一 mock 输入断言输出一致 | 部分是 |
| T76 | 无 root 特权字段留空且不报错、不自动提权 | `DmiTests.test_dmi_missing_is_empty`、`CpuTests.test_cpu_missing_is_empty`、`MemoryTests`、命令降级路径 | 是 |
| T77 | 产出文件经真实 F023 `validate` 仅报业务字段行级错误 | 端到端：生成 CSV +（人工补全或直接提交）`POST /imports/resource-interfaces-ips/validate` | 环境依赖 |
| T78 | 不修改 F014/F023 模板与契约 | `TemplateDriftTests` + 变更范围审查（F014/F023 文件零改动） | 是 |

边界/异常覆盖：缺少 `ip`/`lscpu`/`nvidia-smi`/`/sys/class/dmi/id`；非 up 接口；无 IPv4 接口；loopback；多 IP 接口；`resource_type` 未指定 / BM / VM。

---

## TEST EXECUTION

- **版本**：v1；**结论**：READY FOR REVIEW（T77 端到端为环境依赖项，见下）
- **候选基线**：`feature/F024-host-info-collector`（start `2c3293f`）

### 执行命令与结果

```
$ python3 -m unittest discover -s scripts -p 'test_collect_host_info.py' -v
Ran 18 tests in 0.003s
OK

$ python3 -m unittest discover -s scripts -p 'test_*.py'
Ran 47 tests in 0.481s
OK

$ python3 scripts/collect_host_info.py --resource-type BARE_METAL -o /tmp/csm_host_info.csv
已写出 0 行到 /tmp/csm_host_info.csv
模板列：26 列（F023 §6 冻结）
请人工补全以下字段后再导入：cluster, resource_type, role, status, host, network
```

冒烟运行在容器内进行：`ip -j addr` 可用且被正确解析；容器仅有 loopback（operstate `UNKNOWN`，默认排除）故产出 0 数据行，但表头正确写出（首行为冻结 26 列、带 UTF-8 BOM）。

### T73–T78 执行映射

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| T73 | PASS | `test_template_columns_match_f023_frozen`、`test_header_order_and_bom`、`test_business_fields_always_empty` |
| T74 | PASS | `CpuTests`、`MemoryTests`、`InterfaceTests`、`RowMappingTests` |
| T75 | PASS（单元/审查） | 唯一写入路径为 `write_csv`；`build_rows` 为纯函数、无副作用 |
| T76 | PASS | `DmiTests`/`CpuTests`/`MemoryTests` 缺失即空，无异常与提权 |
| T77 | NOT EXECUTED（环境） | 需运行中的 CSM 与既存 cluster/network；结构层由 T73 表头一致性覆盖 |
| T78 | PASS | 模板漂移测试 + 本 Feature 未改动任何 F014/F023 文件 |

### 未执行项

- **T77 端到端**：本环境未运行真实 CSM Compose，无法调用 `POST /imports/resource-interfaces-ips/validate`。结构性风险（表头/列序）已由 T73 覆盖；剩余为环境依赖，部署后须补做。
- 真实物理机的免 root 字段可得性、发行版命令矩阵未实测（设计已提供分级降级并留空）。

### 结论

T73/T74/T75/T76/T78 通过；T77 为环境依赖项，需在真实 CSM 环境补做。未发现失败或回归。`READY FOR REVIEW`。