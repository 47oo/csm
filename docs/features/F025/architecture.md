# F025 采集脚本增强 — ARCHITECTURE 阶段报告

- **状态**：READY FOR IMPLEMENTATION
- **版本**：v1（最终设计定稿）
- **上游依据**：`docs/features/F025/product.md` v1；`docs/product/requirements-v3.md` revision 10 §24.3、§24、§23.1、§31（T79–T84）；`docs/api/F023.md` v1（导入端点与 26 列模板）；`docs/api/F017.md` v1（Bearer API Key）；`docs/project/project-plan.yaml` revision 13。
- **签核**：Architect（coordinator 代行），2026-10-20。核对 Database `NOT_REQUIRED` 与 Test Design 后签核最终设计。

---

## 1. 方案摘要

在 `scripts/collect_host_info.py` 上以向后兼容方式新增 CLI 能力：

- 参数补全 → 行组装阶段写入模板列。
- `--print`/`--no-header` → 渲染层新增表头开关与 stdout 输出。
- `--push` → 新增最小 API 客户端，使用标准库 `urllib.request` 调用 F023 的 `validate` 与写入端点，`Authorization: Bearer`。

默认路径（无 `--push`）仍是离线、只读、零网络请求。

## 2. Domain / Data Impact

| 维度 | 结论 |
| --- | --- |
| 实体/字段/迁移 | 无 |
| 平台 API / Schema | 无变更 |
| Contract | 不新增；**消费** F023 §5/§4 端点与 F017 Bearer 认证 |
| F014/F023 模板 | 不变；输出仍为冻结 26 列 |

## 3. 分层与 API 判定

- `layers.database/backend/frontend=false`；`api_required=false`（脚本消费既有 API，不定义平台 API）。
- 无 Contract：不新建 `docs/api/F025.md`；`not_required.contract` 说明消费 F023。

## 4. 技术决策（DR）

| ID | 决策 | 理由 |
| --- | --- | --- |
| DR-901 | 参数补全写入模板列；`--resource-type` 同时写列并决定类型列；其余字段未提供仍留空 | §24.3；修订 §24.2「resource_type 一律留空」 |
| DR-902 | `render_csv(rows, include_header)` 统一渲染；文件用 UTF-8 BOM，stdout 不带 BOM | T81；管道友好且文件兼容 Excel |
| DR-903 | `--print` 时提示信息改走 stderr，避免污染 stdout CSV | 保证 stdout 可被管道消费 |
| DR-904 | 推送：`POST …​/validate` → 解析 `error_count` → `error_count==0` 且 `--yes` 时才 `POST …` 写入 | §24 两步流程；确认前无写入 |
| DR-905 | 认证：`Authorization: Bearer <API Key>`；Key 取自 `--api-key` 或环境变量 `CSM_API_KEY`；不落盘、不打印 | F017；T83 |
| DR-906 | 仅标准库 `urllib.request` + 手写 multipart/form-data | 零第三方依赖 |
| DR-907 | 推送前置校验：需要 `--api-url`、Key、`--cluster`+`--resource-type`，否则退出码 2 | BQ10 |
| DR-908 | 默认输出 `csm_host_info.csv` 加入 `.gitignore` | 本地生成物，避免污染工作区 |
| DR-909 | 退出码：0 成功/仅预校验；1 API/校验失败；2 用法/Key 缺失 | 可脚本化 |

## 5. Backend / Frontend Work

- Frontend：无。
- Backend（平台服务层）：无。
- 仓库工具：增强 `scripts/collect_host_info.py`，扩展 `scripts/test_collect_host_info.py`。

## 6. Test Work

见 `docs/features/F025/test-report.md#test-design`：T79–T84 映射，含真实测试栈端到端推送（Bearer API Key、两步流程、无泄漏）与失败路径（401、用法错误、Key 不外泄）。

## 7. 风险

| ID | 风险 | 处理 |
| --- | --- | --- |
| T-R9 | 推送与打印同时使用导致 stdout 混杂 | T-R9 NOTE：建议分开使用；文档说明 |
| T-R10 | `--include-down` help 文案与三态语义 | F024 遗留 LOW，非本 Feature 阻塞 |
| T-R11 | 自签 TLS / 重定向 | 使用标准 `urlopen`，超时可控；不新增跳过校验开关 |

## 8. 最终设计定稿

Architect（coordinator 代行）2026-10-20：核对 Database `NOT_REQUIRED`、Test Design 与实现一致，确认无平台/契约影响，最终设计 **READY FOR IMPLEMENTATION**。绑定需求 revision 10 与 F023/F017 契约版本。