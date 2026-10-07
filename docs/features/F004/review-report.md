# F004 Resource 核心登记 — 正式 Review Report

- **Feature**：F004（FEATURE，P0，M2）
- **角色**：Reviewer（只读）
- **日期**：2026-10-08
- **Status**：`APPROVED WITH FOLLOW-UP`

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F004-resource-core` |
| base_branch / start_commit | `v3` = `7b8e5dfa794c05e28ea1054e8ac29c8fd720ce00` |
| merge-base | `7b8e5df`（= start_commit） |
| 候选 HEAD（批准对象） | `9c6f569050df4fa8e83beb55c0ee396e20dff53d` |
| 完整范围 | `7b8e5df..9c6f569`，10 commits，30 files，+5817/−29；工作区 clean |
| 测试证据 | `docs/features/F004/test-report.md` TD-2 + TE-1（A1–A13 / B1–B46 全 PASS） |

批准链核对：plan_revision 4 含 F004；D01 v3 / D02（审计·乐观锁）/ Contract v1 / DB v1 签核链完整；pending_changes 空；state valid。

## 适用层结论

| 层 | 结论 |
| --- | --- |
| 产品与领域 | PASS（仅 Resource 公共字段；枚举/默认/显式 null/hostname 唯一/cluster 归属/不可改/软删恢复审计权限符合；范围未扩张，不建 F005/F006 明细） |
| 架构与依赖 | PASS（DR-34–DR-45、复用 F003 基座、引用检查注册表机制） |
| 数据与 Migration | PASS（0004 单一 head、列/CHECK/部分唯一/FK RESTRICT/触发器/索引与 DB v1 一致；真库 up/down/up 可逆） |
| API 与实现 | PASS（7 端点/错误码/nullable/分页排序过滤符合 Contract；含 LOW 偏差 F004-REV-01） |
| 标识符 | PASS（hostname ASCII-only 折叠 + (cluster_id,hostname_key) 部分唯一 WHERE deleted_at IS NULL，与 D01 v3 一致） |
| 前端 | PASS（列表/详情/创建/编辑，三态显式，version 随写、409 不静默重试，已删开关与恢复） |
| 测试 | PASS（TE-1 未迎合实现；约束/部分唯一/触发器/迁移/并发真实 PG；含 LOW 跟进 F004-REV-02） |
| 安全与范围 | PASS（鉴权/CSRF/乐观锁；审计白名单无敏感；无越权/无关重构） |
| 变更与批准 | PASS |

独立验证：候选源码 docker build + 真实 PG `pytest tests`→119 passed,1 skipped（与 TE-1 一致）；独立 raw SQL 复现部分唯一谓词、translate 折叠方向（STRASSE→strasse、STRAßE→straße、İST→İst）、**6 连接真并发仅 1 成功**（B38 独立确认）；前端 typecheck/build/smoke 43 passed；validate_project_state VALID。

## Findings（均非阻塞）

| ID | Severity | Location | 问题 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- |
| F004-REV-01 | LOW | api/F004.md §6.4 / services/resource.py update | PATCH 语义校验顺序与 Contract §6.4 文本不完全一致（语义 body 校验在 404/409 之后；Pydantic 层在前）；无数据/安全影响 | Backend/Architect | 否 |
| F004-REV-02 | LOW | test_resources.py | B38 真并发仅单元级断言，TE-1 双连接脚本未固化入仓库（Review 已独立复现通过） | Tester | 否 |
| F004-REV-03 | NOTE | services/resource.py _raise_update_conflict | 条件 UPDATE rowcount=0 且并发软删时返 409 而非 404（窗口极窄） | Backend | 否 |
| F004-REV-04 | NOTE | services/resource.py update | 仅 version 的空 PATCH 会 version+1 并写 before==after UPDATE 审计（Contract 未禁止，前端已阻止） | Backend | 否 |
| F004-REV-05 | NOTE | test_cluster_constraints.py | F003 head 断言由 ==0003 放宽为 >=0003（意图不变） | Tester | 否 |

无 BLOCKER / HIGH / 必须修复 MEDIUM。

## 旧缺陷复核

F004-TD-1-01（LOW，TD-1 hostname_key 折叠方向笔误）：**CLOSED**。TD-2 已改为小写 translate；实现/DB CHECK/D01 v3/Contract 四者一致，独立 raw 断言方向正确且无 lower(。

## Follow-ups（非阻塞）

1. F004-REV-01：Backend 统一 PATCH 语义校验顺序，或 Architect 按实现收敛 Contract §6.4 措辞（二选一）。
2. F004-REV-02：B38 真双连接并发用例固化入仓库回归。
3. F004-REV-03/04：Backend 后续清理项。

## 未审查项

浏览器 DOM/组件级交互自动化未执行（同 F001–F003 口径）；未重跑 Compose 全栈（TE-1 已执行并记录）；F005/F006/F013/F014/F015/F016 及完整 §31/§32 不在 F004 范围。

## 正式结果

**`APPROVED WITH FOLLOW-UP`** — A1–A13 满足，验证可信，无 BLOCKER/HIGH/必须修复 MEDIUM，无未决产品问题；仅存明确非阻塞跟进项。批准仅对候选 `9c6f569` 与 Base `7b8e5df` 有效。Merge/DONE 由协调器按 Git Workflow §5 判定。
