# F005 网段、保留地址与网段历史写入 — Review Report

> Status: APPROVED WITH FOLLOW-UP
> Document Type: Feature Review Report
> Feature: F005（Epic E4，P0）
> Branch: `feature/F005-network-segments`；Base `v2` = `dd6e22bf7aa57b9b6c7f4dbee6518ba5afcd1aa9`
> start_commit / merge-base：`dd6e22bf7aa57b9b6c7f4dbee6518ba5afcd1aa9`
> 候选 HEAD（approved）：`49a242989eb8328fd632ec62476e4bb8b2155de6`
> 范围 `v2...HEAD`：29 files，+6196/−22；工作区 clean
> Review 日期：2026-09-27

## 依据
`requirements-v2.md` §4.6/§5/§6.5/§4.4/§2.1/§9.1/§10 场景 10/12/53/60/51/52/65/82 与 BQ-M/N/O/R/W/Z；`docs/api/F005.md`；`docs/architecture/F005-network-segments.md` 与 ADR-001…005、F001/F013 复用基础；`docs/database/F005.md`；`docs/project/reports/F005-test-report.md`。

## 独立验证
| 验证 | 结果 |
| --- | --- |
| 后端 pytest（真实 postgres:16，全量） | **91 passed** |
| 前端 `pnpm test` | **11 files / 266 tests passed** |
| 前端 `pnpm build` | 成功 |
| Schema 核对（pg_constraint/pg_indexes/生成列/confdeltype） | 与 `docs/database/F005.md` 一致 |
| 独立探针（真实 HTTP+PG） | 计数/CIDR 收窄/幂等清网关/校验边界等符合 Contract |

## 分层结论
- 需求与领域：PASS（§4.6/§5/§6.5/§4.4/§2.1/§9.1）。
- 架构与 Contract：PASS（9 端点、错误码、乐观锁、二次确认、CIDR 规范化、复用 F001/F013）。
- 数据与 Migration：PASS（2 新表、无破坏性变更、约束与生成列一致、保留地址可真删）。
- 功能正确性：PASS（含 1 非阻塞 MEDIUM，见下）。
- 可维护性/测试充分性/前端：PASS。

## 缺陷
| ID | Severity | 说明 | 状态 |
| --- | --- | --- | --- |
| REVIEW-F005-1 | MEDIUM（非阻塞） | PATCH 未在读取既有保留地址前对父行 `SELECT ... FOR UPDATE`；并发交错下可将 CIDR 收窄至保留地址之外，违反 §5「保留地址须在 CIDR 内」。 | 跟进，建议 F006 前修复 |
| NOTE-F005-1 | NOTE | 报告/计划引用候选与分支 HEAD 滞后（文档态）。 | 最终状态提交收敛 |
| NOTE-F005-2 | NOTE | 架构 §9 错误码摘要未列 `PURPOSE_INVALID`/`TECHNOLOGY_INVALID`（Contract 已列，实现一致）。 | 跟进（文档） |
| NOTE-F005-3 | NOTE | PATCH 同值仍 version+1 并写 `change={}`（与 F001 FU-4 同类）。 | Product/Architect 确认 |
| NOTE-F005-4 | NOTE | backlog 派生视图滞后。 | 最终状态提交更新 |

无 BLOCKER/HIGH/必须修复 MEDIUM。

## 结论
核心验收（场景 10/12/53/60/82 及本对象鉴权/审计/历史写入）满足，真实 PG 集成与 DB 约束验证可信。**APPROVED WITH FOLLOW-UP**（候选 `49a2429`，Base `dd6e22b`）。Merge `102e348` 由协调器按 Git Workflow 执行。

## Follow-ups（非阻塞）
1. REVIEW-F005-1：PATCH 取父行锁后再校验保留地址包含性，补并发/回归测试；**建议 F006 引入真实分配前落地**。
2. NOTE-F005-2：同步架构 §9 摘要与 Contract §0 错误码集合。
3. NOTE-F005-3：Product/Architect 确认 PATCH 同值是否计为一次变更。
4. 后续闭环：场景 52/65 端到端分配归 F006；`SEGMENT_HAS_ALLOCATIONS`/`CIDR_IMMUTABLE` 归 F006、`SEGMENT_HAS_INTERFACES` 归 F002；场景 61/64 管理员历史查询归 F012；场景 40 跨对象一致性归 F009。

## 未审查项
真实浏览器 E2E；跨集群 collation 大小写确定性；F002/F006/F012 引入引用后的端到端行为；第三方依赖供应链审计。