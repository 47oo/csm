# F018 全局搜索字段组合展示 — Review Report

- **裁定**：`APPROVED WITH FOLLOW-UP`
- **候选 HEAD**：`33d0fea3147fe4754aff117cacc77792da31fd76`
- **Base / start_commit**：`ce91adb3dec222a65425ccaa29e77b961c7adbc1`（base_branch `codex/v3.1`）
- **merge-base**：`ce91adb`（= start_commit）
- **日期**：2026-10-15

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F018-search-columns` |
| start_commit | `ce91adb3dec222a65425ccaa29e77b961c7adbc1` |
| HEAD（候选） | `33d0fea3147fe4754aff117cacc77792da31fd76` |
| Base | `codex/v3.1` |
| merge-base | `ce91adb` |
| 完整范围 | `ce91adb..33d0fea`，18 files，+2807/−53 |
| 权威依据 | `docs/api/F013.md` v2；`docs/features/F018/{product,architecture,implementation,test-report}.md`；requirements-v3 revision 5 §17.1/T50–T53 |

## 适用层结论

| 层 | 结论 |
| --- | --- |
| 产品/领域 | 符合 A1–A12、T50–T53；无范围扩张，未引入新对象/关系/状态/权限/错误码 |
| 架构/依赖 | 符合 DR-319–DR-331；`database=false`，无 Schema/索引/迁移（`alembic heads` 未变） |
| API/契约 | 与 F013 v2 §2.2/§2.9/§4/§5 一致；纯加法兼容；非 resource 行 `related`/`related_total` 恒 null |
| 数据完整性 | 只读派生视图；排序全序、软删随模式、未绑定 IP 排除，均有真 PG 证据 |
| 前端 | 九字段选择器 + localStorage 回退 +「还有 N 条」机制级覆盖；非 resource 行不变 |
| 测试 | A1–A12/T50–T53 逐条映射并实跑；真 PG 证据齐备 |
| 安全/范围 | 无新增依赖、无写入口、无审计写入、无无关变更 |

## Findings

| # | Severity | 位置 | 说明 |
| --- | --- | --- | --- |
| 1 | LOW（观察） | `backend/app/services/search.py::_load_related` | 采用单次 JOIN 而非 DR-319 推荐的三段批量 IN。架构 §4.1 明确允许「保持相同软删语义与排序时等价、可接受」，软删/排序已由真 PG 用例验证。非缺陷 |
| 2 | LOW | `backend/app/schemas/search.py::SearchRelatedInterface` | `interface_type` 声明为 `str` 而非契约标注的七值 enum，响应无运行时枚举校验。取值来自 F007 已约束的 DB 列并原样回显（B21 通过），风险极低 |
| 3 | LOW | `test_search_related_tester_acceptance.py::test_related_explain_references_existing_indexes` | 断言正则含泛化 `Index`，证据强度偏弱。架构已声明正确性不依赖索引，仅为补充证据 |
| 4 | INFO | `docs/project/project-plan.yaml` git 字段 | `base_branch: codex/v3.1` 与 git-workflow §2 名义值 `v3` 不同；与 F017 先例一致，且实际指向 start_commit，属环境事实记录 |

未发现 BLOCKER / HIGH / 必须修复 MEDIUM；未发现产品未决问题。

## 旧缺陷复核

- **F018-TE-NOTE-1**（F010 `test_concurrent_gateway_change_and_allocation` 偶发失败，NOTE，F018 范围外）：独立复跑 3/3 passed，与 Tester 判断一致。维持 NOTE，无需修复。

## A1–A12 / T50–T53 覆盖核对（独立确认）

全部 ✅。关键独立证据：`test_resource_row_related_superset`、`test_related_ordering_collate_c_and_inet_numeric`、`test_related_limit_and_total`、`test_two_interfaces_two_ips_each`、`test_deleted_association_exclude_include_only`、`test_unbound_ip_not_in_related_but_searchable`、`test_related_does_not_change_result_set`、`test_related_search_is_idempotent_and_writes_no_audit`、`test_search_route_is_get_only`、`smoke F1–F5`。真实浏览器 DOM 未测（替代证据：机制级 smoke + typecheck + build + 真 PG 集成 + 源码静态核对）。

## 只读立场

确认：`app/api/v1/search.py` 未改动；`/api/v1/search` methods == `{GET}`；无写端点、无请求体、无 CSRF；搜索前后 `audit_logs` 无变化；重复调用幂等。符合 A10/T53。

## 范围纪律

确认：改动全部落在 F018；`database=false` 无迁移，`alembic heads` 未变，无新增依赖，无无关重构。

## Follow-ups（非阻塞）

1. 真实浏览器 DOM 验证（A11 跨刷新持久化、A6 文本渲染、窄屏/焦点）：仓库无 DOM 工具链，本期仅机制级 + 源码静态核对。Owner：Frontend / Tester。
2. （可选）`interface_type` 如需响应层强校验可改为 enum；当前回显已满足契约。
3. （可选）`EXPLAIN` 用例断言可收紧到具体索引名。

## 未审查项

- 真实浏览器端到端联调（环境缺失，Tester 已列明替代证据）。
- `test_f016_acceptance.py`（需 env flag）与 `test_migrations.py` V3b（非 superuser）默认 SKIP，非 F018 范围。

## 裁定

**APPROVED WITH FOLLOW-UP**。核心验收 A1–A12 / T50–T53 全部满足且经真 PG 独立复跑确认；只读立场与范围纪律符合；无 BLOCKER/HIGH/必须修复 MEDIUM，无产品未决。批准仅对候选 `33d0fea` 与 Base `codex/v3.1`（merge-base `ce91adb`）有效；Merge / DONE 由协调器按 Git Workflow 判定。

## Git 声明

本次 Review 仅执行只读 Git 命令（`log`、`diff`、`show`、`status`、`branch`、`rev-parse`、`merge-base`、`show-ref`、`ls-files`），未执行任何改变 Git 状态的命令。审查期间在独立临时 PG 库运行测试并已 DROP，未修改仓库工作区。