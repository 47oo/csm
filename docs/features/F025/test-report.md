# F025 采集脚本增强 — TEST 报告

- **上游依据**：`docs/product/requirements-v3.md` revision 10 §24.3、§31（T79–T84）；`docs/features/F025/product.md` v1；`architecture.md` v1；`docs/api/F023.md` v1；`docs/api/F017.md` v1。

---

## TEST DESIGN（TD-1）

- **版本**：v1；**结论**：TEST DESIGN READY
- **环境**：Python 3.8+，仅标准库；单元测试无需 root/网络；T82/T83 端到端使用运行中的真实测试栈（`compose.test.yaml`，API `http://localhost:18080`）与 ADMIN 创建的 API Key。

| 用例 | 验收点 | 测试方法 | 自动化 |
| --- | --- | --- | --- |
| T79 | 参数补全写列；未提供留空 | `EnhancementTests.test_manual_params_fill_columns`、`test_manual_absent_leaves_columns_empty` | 是 |
| T80 | `--resource-type` 写列且仅填对应类型列 | `test_resource_type_column_written_and_type_columns` | 是 |
| T81 | `--print` 不写文件、默认写文件、带/不带表头 | `test_render_csv_header_toggle`、`test_main_print_writes_stdout_not_file`、`test_main_output_file_with_bom` | 是 |
| T82 | 先 validate 后确认写入、确认前不写、写入原子 | `test_push_validate_then_confirm`、`test_push_without_yes_does_not_write`、`test_push_validation_errors_block_write` + 真实端到端 | 是 |
| T83 | Key 缺失/无效 401 非零退出、不外泄、不落盘 | `test_push_requires_url_key_and_fields`、`test_push_api_key_not_leaked` + 真实 401 | 是 |
| T84 | 默认零网络请求；F024 无回归 | `test_default_mode_does_not_call_network`、F024 全套回归 | 是 |

边界：多行多网卡、`--network` 应用于全部行、推送缺 `--api-url`/Key/`--cluster`/`--resource-type`、校验错误阻断写入、API 401。

---

## TEST EXECUTION

- **版本**：v1；**结论**：READY FOR REVIEW
- **候选基线**：`feature/F025-collector-enhancements`

### 单元测试

```
$ python3 -m unittest discover -s scripts -p 'test_collect_host_info.py'
Ran 43 tests in 0.009s
OK

$ python3 -m unittest discover -s scripts -p 'test_*.py'
Ran 72 tests in 0.624s
OK
```

### T82/T83 真实端到端（测试栈）

环境：`csmtest` 栈（db/backend/frontend/nginx），API `http://localhost:18080`；ADMIN 登录后创建 API Key（label `f025-e2e`）；创建测试 Cluster `F025E2E` 与 Network `F025-MGMT 10.10.10.0/24`、`F025-IB 192.168.10.0/24`。

1. **预校验（无 `--yes`）**：
   ```
   $ python3 scripts/collect_host_info.py --push --api-url http://localhost:18080 \
       --api-key "$KEY" --cluster F025E2E --resource-type BARE_METAL
   {"format":"csv","total_rows":2,"importable_rows":2,"error_count":0,"errors":[],"errors_truncated":false}
   预校验通过。加 --yes 以写入。
   ```
2. **确认写入（`--yes`）**：
   ```
   $ python3 scripts/collect_host_info.py --push --yes --api-url http://localhost:18080 \
       --api-key "$KEY" --cluster F025E2E --resource-type BARE_METAL
   {"format":"csv","total_rows":2,"importable_rows":2,"error_count":0,"errors":[],"errors_truncated":false}
   {"created":1,"total_rows":2,"interfaces_created":2,"ip_addresses_created":2}
   推送成功。
   ```
3. **API 复核**：`GET /api/v1/resources?cluster_id=…` → `[('luck','BARE_METAL')]`，total 1。
4. **无效 Key**：`--api-key csm_ak_invalid` → HTTP 401 `AUTH_REQUIRED`，脚本 rc=1；`grep` 确认 Key 未出现在 stdout/stderr。
5. **用法错误**：缺 `--cluster` → rc=2（`--push 需要同时提供 --cluster 与 --resource-type`）。

### T79–T84 结果

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| T79 | PASS | 单元测试 |
| T80 | PASS | 单元测试 |
| T81 | PASS | 单元测试 + 冒烟 `--print --no-header` |
| T82 | PASS | 单元测试 + 真实端到端 created=1/interfaces=2/ips=2 |
| T83 | PASS | 单元测试 + 真实 401、rc=1、无泄漏 |
| T84 | PASS | 单元测试 `test_default_mode_does_not_call_network`；F024 回归 43/72 OK |

### 未执行 / 边界

- 真实物理机免 root 采集字段矩阵（继承 F024 环境限制）。
- TLS 自签证书场景未在真实 HTTPS 端到端验证。

### 结论

T79–T84 通过；无回归。`READY FOR REVIEW`。