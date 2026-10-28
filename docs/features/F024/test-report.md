# F024 离线主机信息采集脚本 — TEST 报告

- **上游依据**：`docs/product/requirements-v3.md` revision 9 §24.2、§31（T73–T78）；`docs/features/F024/product.md` v1；`docs/features/F024/architecture.md` v1（含 RV-01/02/07 修复）；`docs/api/F023.md` v1 §6。

---

## TEST DESIGN（TD-1）

- **版本**：v1；**结论**：TEST DESIGN READY
- **环境**：Python 3.8+，仅标准库；单元测试在无 root、无 CSM 网络、无真实硬件的环境运行。端到端结构验收（T77）需真实 CSM（`POST /api/v1/imports/resource-interfaces-ips/validate`）与既存 cluster/network。

| 用例 | 验收点 | 测试方法 | 自动化 |
| --- | --- | --- | --- |
| T73 | 表头逐字逐序等于冻结 26 列；业务字段留空 | `TemplateDriftTests.test_template_columns_match_f023_frozen`、`CsvOutputTests.test_header_order_and_bom`、`RowMappingTests.test_business_fields_always_empty` | 是 |
| T74 | 归一化与单位口径；未知留空不用 0/推断 | `CpuTests`（物理核心/插槽/型号）、`MemoryTests`（MiB）、`InterfaceTests`（MTU/MAC/速率/类型不推断/掩码）、`RowMappingTests` | 是 |
| T75 | 只读、无网络写、不写 CSM；重复产出稳定 | 代码审查（唯一写入为输出文件）+ `RowMappingTests.test_rows_are_deterministic`（同输入重复构建逐字一致） | 是 |
| T76 | 无 root 特权字段留空且不报错、不自动提权 | `DmiTests`/`CpuTests`/`MemoryTests`/`GpuTests`/`VmTests` 缺失即空；`InterfaceTests.test_ip_o_text_fallback`、`SysfsFallbackTests` 降级路径 | 是 |
| T77 | 产出文件经真实 F023 `validate` 仅报业务字段行级错误 | 端到端：生成 CSV + `POST /imports/resource-interfaces-ips/validate` | 环境依赖 |
| T78 | 不修改 F014/F023 模板与契约 | `TemplateDriftTests` + 变更范围审查（F014/F023 文件零改动） | 是 |

回归用例（Review 后新增）：`InterfaceTests.test_unknown_operstate_kept_and_enabled_empty`（RV-01）、`test_ipv4_includes_mask`（RV-02）、`test_negative_speed_is_empty`、`NormalizationTests.test_hostname_removes_control_characters`（RV-07）。

---

## TEST EXECUTION

- **版本**：v2（含 Review 修复后复测）；**结论**：READY FOR REVIEW
- **候选基线**：`feature/F024-host-info-collector`

### 执行命令与结果

```
$ python3 -m unittest discover -s scripts -p 'test_collect_host_info.py' -v
Ran 30 tests in 0.005s
OK

$ python3 -m unittest discover -s scripts -p 'test_*.py'
Ran 59 tests in 0.558s
OK

$ python3 scripts/collect_host_info.py --resource-type BARE_METAL -o /tmp/f024.csv
已写出 2 行到 /tmp/f024.csv
模板列：26 列（F023 §6 冻结）
```

真实环境冒烟（容器）：`ip -j addr` 解析成功；产出 2 行，`ip` 携带 `/24` 掩码、MAC/MTU/速率正确，业务字段为空。表头为冻结 26 列、带 UTF-8 BOM。

### T73–T78 执行映射

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| T73 | PASS | `test_template_columns_match_f023_frozen`、`test_header_order_and_bom`、`test_business_fields_always_empty` |
| T74 | PASS | `CpuTests`、`MemoryTests`、`InterfaceTests`（含掩码）、`RowMappingTests` |
| T75 | PASS | `test_rows_are_deterministic` + 只读审查（唯一写入 `write_csv`） |
| T76 | PASS | `DmiTests`/`CpuTests`/`MemoryTests`/`GpuTests`/`VmTests`、`test_ip_o_text_fallback`、`SysfsFallbackTests` |
| T77 | PASS（Review 独立执行） | 见 `review-report.md#t77-端到端真实集成reviewer-独立执行`：测试栈 `POST /imports/resource-interfaces-ips/validate` 原始输出仅报 cluster/resource_type，补全后 `error_count=0` |
| T78 | PASS | 模板漂移测试 + 本 Feature 未改动任何 F014/F023 文件 |

### 未执行项

- **T77 端到端**：已在 Review 阶段由 Reviewer 对运行中的测试栈独立执行并通过（证据见 `review-report.md`）；本节保留候选测试时的环境限制说明。
- 真实物理机免 root 字段可得性与发行版命令矩阵未实测（设计已提供分级降级并留空）。

### 结论

T73–T78 均通过（T77 由 Review 补充执行）；Review 修复（RV-01/02/03/07）后复测通过。`READY FOR REVIEW`。