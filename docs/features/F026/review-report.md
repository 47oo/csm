# F026 正式 Review Report

- Feature Branch：feature/F026-cluster-grants
- start_commit / Base / merge-base：3c8d2d982454460661ec0e1e350c10f1318f26de（v3.2）
- 候选 HEAD：f9c7e859ef5897f59d1d3a72e1b1a10fd066ddc5
- 审查范围：3c8d2d9..f9c7e85（8 commits，39 files，+3395/−84）
- 工作区：clean；无未跟踪文件；无进行中的 merge/rebase
- 权威依据：requirements revision 11（§3/§5/§21–§23.2/§27/§28/§31 T85–T99）；CHG-010；plan_revision 14；F026 product A1–A33；F026 architecture v1 + §10；docs/api/F026.md v1；F002 v3 / F015 v3 errata；docs/database/f026-cluster-authorization.md v1（DB-D401–D420）；F026 test-report TD-1 / TEST-1 / RV-1；implementation.md

## 独立验证

| 检查 | 结果 |
| --- | --- |
| git status / rev-parse / merge-base / log / diff --stat / ls-files --others | clean；HEAD/Base/merge-base 与给定基线一致 |
| alembic heads | 单一 head：0015_user_cluster_authorizations |
| git grep "get_access_scope\|AccessScope" backend/app | 仅 core/access_scope.py，既有 api/services 无引用 |
| pytest tests/integration/test_cluster_authorizations.py（真实 PostgreSQL） | 8 passed |
| render_project_views.py（只读） | PROJECT VIEWS VALID |
| 前端 typecheck/build/smoke | 未重跑（无 node_modules）；依赖 Tester 记录 322 passed |

## 分层结论

- 产品/领域：范围与 §23.2 一致；未新增角色/权限/实例级授权；F026/F027 边界正确（既有端点未过滤）；无未决产品问题。
- 数据/迁移：表/约束/部分唯一/触发器/回填/断言/单 head/ORM 一致；无 Schema 漂移；audit_logs 无 Schema 变更。
- API/Contract：三端点、字段/nullable、effective、分页/过滤、错误语义与 P-1 一致；D-TEST-F026-01 已修复并独立复跑。
- Auth/Security/Audit：AccessScope 语义正确、无缓存/API Key 继承；仅 USER_ADMIN；Audit 同事务、白名单、无敏感内容。
- 前端：Tab 门控、列表/授予/撤销、三态与披露基本符合；有 LOW 偏差（撤销 409 未关闭刷新、候选过滤仅当前页）。
- 测试：核心行为真实 PG 证据可信；TD-1 的部分用例仍为一次性探针，需在 F028 前固化。

## Findings

| ID | Severity | Layer | 结论 | 必须修复 |
| --- | --- | --- | --- | --- |
| F026-RV-01 | LOW | Contract/Backend | 未知 user + 非法 q 时语义 422 先于路径 404；q 控制字符规则未写入 Contract | 否 |
| F026-RV-02 | LOW | Frontend | 撤销 409 时保持 Modal 内联错误，未按 D-5 关闭并刷新 | 否 |
| F026-RV-03 | MEDIUM | Tests | TD-1 的并发/生命周期/缓存/审计查询等用例未全部固化为可重复测试 | 否（F028 前跟进） |
| F026-RV-04 | LOW | Docs | CHG-010 状态与计划 F026–F028 的 PROPOSED 锚点未同步 | 否 |
| F026-RV-05 | LOW | Evidence | evidence.test 指向旧 RETURN 结论，应指向 Repair Verification 1 | 否 |
| F026-RV-06 | LOW | Frontend | 候选排除仅基于当前授权列表页 | 否 |
| F026-RV-07 | NOTE | Backend | grant 的 IntegrityError 统一映射 409 | 否 |
| F026-RV-08 | LOW | Tests | 触发器异常未断言 SQLSTATE；downgrade 对象对称性未逐项断言 | 否 |
| F026-RV-09 | NOTE | Docs | Product A-1/A-2/A-3 标签滞后于 Contract/Architecture | 否 |

## 旧缺陷复核

- D-TEST-F026-01（MEDIUM）：CLOSED。list 在查询前校验用户存在；回归断言入仓；独立复跑 8 passed。
- OBS-TEST-F026-1 审计同刻 flake：本轮未复现。
- OBS-TEST-F026-2 A9–A11 浏览器级：F028 承接。
- OBS-TEST-F026-3/4：转 F026-RV-08 / F026-RV-01。

## Follow-ups

1. F028 前固化 TD-1 高价值用例：A2 并发、A16–A18 生命周期、A25/A26 缓存/路由边界、A27 重跑不复活、A32 /audit 查询与失败回滚。
2. Architect 明确 q 校验与路径 404 的次序，并决定是否保留 q 控制字符限制。
3. Frontend 对齐撤销 409 的 D-5 行为；评估服务端候选过滤。
4. Coordinator 同步 CHG-010 状态、计划锚点与 evidence.test。
5. Backend 收窄 grant 的 IntegrityError 映射。
6. Tester 补充 SQLSTATE 与 downgrade 对象对称性断言，迁移夹具自清理。
7. Product 将 A-1/A-2/A-3 标记为已按 Contract 关闭。

## 未审查项

- 未重跑全量后端 pytest（708 passed / 2 skipped 依赖 TEST/RV 记录）。
- 未重跑前端三命令（无 node_modules）。
- 真实浏览器/Compose/T85–T99 端到端、T01–T84 全量回归归 F028。
- EXPLAIN 基线属 Database 阶段证据，未重跑。

## 裁定

**Status：APPROVED WITH FOLLOW-UP**

无 BLOCKER / HIGH / 必须修复 MEDIUM；旧缺陷已闭环；批准仅对候选 HEAD f9c7e85 与 Base 3c8d2d9 有效。Merge / DONE 由协调器按 Git Workflow §5 判定。

GIT: NONE
