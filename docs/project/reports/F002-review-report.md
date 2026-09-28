# F002 计算资源登记、无 IP 网卡与一次原子提交基础 — Review Report

> Status: APPROVED
> Document Type: Feature Review Report
> Feature: F002（Epic E2，P0）
> Branch: `feature/F002-resource-registration`；Base `v2` = `93921ed1f26b3b0f098e7dfaf31b35ef7066aed3`
> start_commit / merge-base：`93921ed1f26b3b0f098e7dfaf31b35ef7066aed3`
> 候选 HEAD（approved）：`1e6274111c566ccac5cb5fee49732e8d4ec34005`
> 范围 `v2...HEAD`：27 files，+6351/−29；工作区 clean
> Review 日期：2026-09-27（含前两轮发现与修复）

## 依据
`requirements-v2.md` §4.1/§4.2/§4.3（BQ-AA）/§4.4/§4.5/§2.1/§2.2/§6.4/§7.1–7.4/§9.1、§10 场景 2/5/6/28/29/30/34/42/46/47/48/50 与 BQ-AA/AB/W/Z；`docs/api/F002.md`；`docs/architecture/F002-resource-registration.md` 与 ADR-001…005、F001/F005/F013 复用基础；`docs/database/F002.md`；`docs/project/reports/F002-test-report.md`。

## 独立验证
| 验证 | 结果 |
| --- | --- |
| 后端 pytest（真实 postgres:16，全量） | **120 passed** |
| 前端 `pnpm test` | **14 files / 329 tests passed** |
| 前端 `pnpm build` | 成功 |
| 独立 HTTP/PG 探针（Tester 60/60；Reviewer 自建复核） | 通过 |

## 分层结论
- 需求与领域：PASS（名称统一唯一、只读字段、网卡 0..1 同集群、整单原子、删除前置、二次确认、状态来源 BQ-AA）。
- 架构与 Contract：PASS（4 端点、错误码、problem+json 扩展成员、显式网卡 op、乐观锁）。
- 数据与 Migration：PASS（2 新表、复合 FK 同集群、RESTRICT、幂等初始化；对 F005 表附加 UNIQUE(id,cluster_id) 安全无破坏）。
- 功能正确性：PASS（两处 LOW 边界见下）。
- 可维护性/测试充分性/前端：PASS。

## 缺陷与处理
| ID | Severity | 说明 | 状态 |
| --- | --- | --- | --- |
| REVIEW-F002-1 | MEDIUM | 计划中 F004/F006/F007 `implementation` 被误标 COMPLETE。 | **已修复**（`19122d5`） |
| REVIEW-F002-2 | MEDIUM | `counts.BLOCKED` 与 `blocked_draft_features` 不自洽。 | **已修复**（`1e62741`） |
| REVIEW-F002-3 | LOW | `execution.current_stage` 陈旧。 | **已修复**（`1e62741`） |
| REVIEW-F002-4 | LOW | `backlog.md` 头部叙述残留 F002 IN_PROGRESS。 | 最终状态提交修复 |
| REVIEW-F002-5 | LOW | `planning_status.note` / `status_evidence` 历史陈旧值。 | 最终状态提交修复 |
| REVIEW-F002-2-functional | LOW | 同请求内接口名互换（终态合法）被瞬时唯一冲突拒绝。 | 跟进（非阻塞，F002-R-06） |
| REVIEW-F002-3-functional | LOW | 并发唯一冲突路径未返回 `existing_resource_id/type`。 | 跟进（非阻塞，F002-R-07） |
| NOTE-F002-1 | NOTE | PATCH 同值仍自增 version 并写空变更历史（同 F001 FU-4 / F005 NOTE-F005-3）。 | Product/Architect 确认 |

无 BLOCKER/HIGH；阻塞性 MEDIUM 均已修复。第三轮复核结论 **APPROVED**（候选 `1e62741`）。

## 结论
F002 实现、设计、Schema 与测试满足已确认需求与 Contract，真实 PG 集成与 DB 约束验证可信。**APPROVED**（候选 `1e62741`，Base `93921ed`）。Merge `1b682e2` 由协调器按 Git Workflow 执行。

## Follow-ups（非阻塞）
1. F002-R-04/R-05：backlog 叙述与 plan 历史 note/status_evidence 陈旧（最终状态提交处理）。
2. F002-R-06：评估同请求接口名互换（终态合法）是否需支持集合语义。
3. F002-R-07：并发唯一冲突路径补齐 `existing_resource_id/type`。
4. NOTE-F002-1：Product/Architect 确认同值 PATCH 是否计为一次变更。
5. 后续闭环：场景 46/48 的管理 IP 与 IP 历史归 F006；VM/服务实例删除拒绝归 F004/F007；管理员历史查询归 F012；跨对象权限一致性归 F009。

## 未审查项
真实浏览器 E2E 与前后端真实联调（F002 Test Work 仅要求 Vitest）；F004/F006/F007 引入关联后的端到端删除保护；`name` collation 部署差异；第三方依赖供应链审计。
---

## Follow-up 修复记录（post-merge，2026-09-27）

- **F002-R-06（LOW）已修复**：`uq_network_interfaces_resource_name` 改为 `DEFERRABLE INITIALLY IMMEDIATE`，资源写事务内 `SET CONSTRAINTS ... DEFERRED`；`create_schema` 幂等重建已存在库约束。同一 PATCH 内接口名互换（终态合法）可保存，终态冲突仍 `409 INTERFACE_NAME_TAKEN`。
- **F002-R-07（LOW）已修复**：兜底命中 `uq_resources_cluster_name` 时 `RESOURCE_NAME_EXISTS` 回填 `existing_resource_id`/`existing_resource_type`。
- 分支 `fix/F002-followups`，批准 HEAD `9508da1`；独立复核真实 postgres:16 全量 **125 passed**（基线 120），约束重建幂等、数据保全、事务级 `SET CONSTRAINTS` 无泄漏；Reviewer 结论 **APPROVED WITH FOLLOW-UP**（唯一跟进为补记本验证）。
- **Merge**：`1e6a13e`（父 = Base `c80155b` 与批准 HEAD `9508da1`）。
- 文档同步：`docs/database/F002.md` 已记录 deferrable 约束与幂等重建。
- 仍保留：NOTE-F002-1（同值 PATCH 是否计为一次变更，待 Product/Architect 确认；非缺陷）。
