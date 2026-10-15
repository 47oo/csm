# F017 API Key 机器凭据 — Review Report

- **裁定**：`APPROVED WITH FOLLOW-UP`
- **候选 HEAD**：`0ef28636c7ecaacd4e384b2fedffc4bd96fd8be8`
- **Base / start_commit**：`77fbb4c494c9d65ea9006c77c8ee11fbab8089c0`（base_branch `codex/v3.1`）
- **merge-base**：`77fbb4c`（= start_commit）
- **日期**：2026-10-15

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F017-api-key` |
| start_commit | `77fbb4c494c9d65ea9006c77c8ee11fbab8089c0` |
| HEAD（候选） | `0ef28636c7ecaacd4e384b2fedffc4bd96fd8be8` |
| Base | `codex/v3.1` |
| merge-base | `77fbb4c`（与 `codex/v3.1`） |
| 完整范围 | `77fbb4c..0ef2863`，7 commits，49 files，+5195/−109 |
| 权威依据 | `docs/api/F017.md` v1；`docs/database/f017-api-key.md` v1（DB-D301–DB-D316）；`docs/features/F017/architecture.md`（DR-301–DR-318）、`product.md`、`test-report.md` |

## 适用层结论

- **Database**：迁移 `0014_api_keys`（建表 + 索引 + `audit_logs.api_key_label` + CHECK；`down_revision=0013_search_indexes`；单 head；up/down 对称）、列/约束/索引命名与 DB-D301–DB-D316 逐条一致；模型与迁移无漂移。**符合**。
- **API / Backend**：四端点、ApiKeyRow 字段与 nullable、status 派生（REVOKED > EXPIRED）、分页/排序/过滤、401→403→422 顺序、401 等价、一次性明文、`already_revoked`(409)、审计白名单（不含 hash/明文）、`SENSITIVE_FIELDS` 扩充、CSRF Bearer 豁免、Bearer 优先，均与 Contract §1–§8 对应。**符合**（见 F017-RV-01 边界）。
- **Frontend**：`SystemPage` 第三个 Tab（`USER_ADMIN` 门控）、`ApiKeyManagementPanel` 四态、创建表单本地镜像校验、一次性明文 Modal（关闭清除、不入 storage/日志）、吊销确认与 409/404 呈现，与 DR-312 及 Contract §4/§5 一致。**符合**。
- **跨 Contract**：F002 v2、F015 v2 修订与 Contract §9 列明的差异面逐条落实。**符合**。

## Findings

| ID | Severity | Layer | Location | 期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F017-RV-01 | LOW | Contract/Backend | `docs/api/F017.md` §1；`backend/app/core/security.py::parse_bearer_authorization`；`backend/app/core/auth.py::get_current_operator` | Contract「携带 Bearer（scheme 合法、token 非空）→ 走 API Key 路径，否则走 Cookie」；实现把任意 Bearer scheme（含空 token）判为 present，空 token → 401，即使同时有有效 Cookie | 仅「空 token Bearer + 有效 Cookie」边界；语义冲突源自 Contract 自身两句，且 TD-1 B14 期望空 token→401 | Architect（澄清文字） | 否 |
| F017-RV-02 | LOW | Backend | `backend/app/api/v1/api_keys.py`（应用时钟派生 status）vs `backend/app/services/api_key.py`（`func.now()` 过滤） | status 过滤按 DB `now()`，响应字段按应用时钟派生；时钟偏斜时可能不一致 | 轻微；合理场景不触发 | Backend | 否 |
| F017-RV-03 | NOTE | 流程 | `docs/product/requirements-v3.md` T48（`37d4871` 于 ARCHITECTURE gate 修改） | 收敛措辞为「省略默认 90 天」，与 §35.1 revision 4 一致，并在 architecture §8.2 / F017-OPEN-2 记录；未走正式 proposal | 无行为偏差 | Coordinator / Product | 否 |
| F017-RV-04 | NOTE | Contract | `ApiKeyCreateRequest` 使用 `extra="forbid"` + `strict=True` | 比 Contract 更严格（`90.0`、额外字段 → 422），测试已断言 | 无 | Architect（如需明示） | 否 |
| F017-RV-05 | NOTE | Frontend | 一次性明文 Modal | DR-312「复制后不可再取」实现为「关闭弹窗后不可再取」 | 语义一致 | — | 否 |
| F017-RV-06 | NOTE | Docs | `docs/api/F015.md` v2 §7 | 仍写迁移链单 head `0013_search_indexes`；F017 后全局 head 为 `0014_api_keys` | 易误读 | Coordinator | 否 |
| F017-RV-07 | LOW | Git 基线 | `project-plan.yaml` F017 `base_branch: codex/v3.1` vs `git-workflow.md` §2 `v3` | 本地 `v3` 落后于 `start_commit`；F017 diff 相对 `77fbb4c` 完整，工作区 clean | 内容审查不受影响；基线归属由协调器确认 | Coordinator | 否 |

## 旧缺陷复核

- `OBS-F017-1`（LOW，非 F017 缺陷）：`test_ip_addresses.py::test_concurrent_gateway_change_and_allocation` 偶发；本次审查环境无 PostgreSQL，未独立复跑，按报告接受「与本 Feature 文件无关、非阻塞」。

## Follow-ups

1. Architect 收敛 Contract §1「Bearer token 非空/空 token」措辞（F017-RV-01）。
2. Backend 统一 list 过滤与响应 status 的时钟来源，或文档化（F017-RV-02）。
3. Coordinator 核对 `codex/v3.1` vs `v3` 基线归属（F017-RV-07），补记 T48 依据（F017-RV-03），并消歧 F015 v2 §7（F017-RV-06）。

## 未审查项

- 未重跑真实 PostgreSQL 集成（审查环境无 `TEST_DATABASE_URL`），约束/唯一/FK/迁移/并发结论基于静态比对与已提交测试报告。
- 前端真实浏览器 E2E、真实前后端串联、`EXPLAIN (ANALYZE)` 规模基线（与 `test-report.md` 未验证项一致）。

## 裁定

**APPROVED WITH FOLLOW-UP**。核心验收 A1–A8 / T42–T49 的代码与文档一致；无 BLOCKER / HIGH / 必须修复 MEDIUM。唯一边界偏差 F017-RV-01 属 Contract 自相矛盾，需 Architect 澄清而不必先改实现。F017-OPEN-1 / F017-OPEN-3 已按 Contract 的 PROPOSED 默认实现并明确标为非阻塞。

本批准仅对候选 `0ef2863` 与基线 `77fbb4c` 有效；Merge / DONE 由协调器按 Git Workflow 判定。

## Git 声明

本次 Review 仅执行只读 Git 命令（`rev-parse`、`log`、`status`、`merge-base`、`diff`、`branch`、`show`），未执行任何改变 Git 状态的命令。