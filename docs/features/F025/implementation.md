# F025 采集脚本增强 — 实现报告

- **状态**：COMPLETE
- **上游依据**：`docs/features/F025/architecture.md` v1；`docs/api/F023.md` v1；`docs/api/F017.md` v1。

---

## 1. 交付物

| 文件 | 变更 |
| --- | --- |
| `scripts/collect_host_info.py` | 新增 CLI 参数补全、`--print`/`--no-header`、`--push`（F023 两步流程 + Bearer API Key）；新增 `render_csv`、`post_import`、`_push`、`_multipart_body`；`build_rows` 支持 `manual` 覆盖并写入 `resource_type` |
| `scripts/test_collect_host_info.py` | 新增 13 个用例（参数补全、类型列、header 开关、multipart、推送两阶段/阻断/用法/无泄漏/离线）；并按 §24.3 更新 1 条既有断言 |
| `.gitignore` | 忽略本地生成的 `csm_host_info.csv` |

## 2. 行为摘要

- `--cluster/--role/--status/--host/--network` 写入对应列；`--resource-type` 写列并决定类型专属列；未提供仍留空。
- `--print` 输出 stdout（提示走 stderr）；`--no-header` 去表头；默认写文件（UTF-8 BOM）。
- `--push`：`POST /api/v1/imports/resource-interfaces-ips/validate` → `error_count==0` 且 `--yes` → `POST /api/v1/imports/resource-interfaces-ips`；`Authorization: Bearer`；Key 取自 `--api-key` 或 `CSM_API_KEY`，不落盘、不打印。
- 默认（无 `--push`）零网络请求。

## 3. Contract 符合性

| 契约 | 符合性 |
| --- | --- |
| F023 §6 26 列列名/列序 | 不变（`TEMPLATE_COLUMNS`，漂移测试守卫） |
| F023 §3/§4 端点与 `IMPORT` 权限 | `validate` 与写入端点逐字复用；multipart `file`+`format=csv` |
| F023 §6.1 逐行适用性 | `--resource-type` 只填对应类型列 |
| F017 Bearer 认证 | `Authorization: Bearer <API Key>`；401 语义 |
| §24 两步流程 / 原子性 | 先预校验、确认后写入；写入由服务端整批原子 |
| §24.3 默认离线 | 仅 `--push` 联网 |

## 4. 未改范围

- 未改 F014/F023 模板、契约或平台代码；无 Schema/迁移/平台 API。
- F024 历史交付与证据保持不变。

## 5. 验证

- `python3 -m unittest discover -s scripts -p 'test_collect_host_info.py'`：43 tests OK。
- `python3 -m unittest discover -s scripts -p 'test_*.py'`：72 tests OK。
- 真实端到端推送（测试栈）：预校验 `error_count=0` → 写入 `created=1/interfaces_created=2/ip_addresses_created=2`；API 复核通过；无效 Key 401 rc=1 且无泄漏。
- 详见 `docs/features/F025/test-report.md`。

**结论**：实现完成，符合设计与契约。