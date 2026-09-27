# F006 IPv4 分配与同一表单 IP 集成 — Review Report

> Status: APPROVED WITH FOLLOW-UP
> Document Type: Feature Review Report
> Feature: F006（Epic E4，P0，M1）
> Branch: `feature/F006-ip-allocation`；Base `v2` = `75162137351f789f2d8f383534309137b57b01a8`
> start_commit / merge-base：`75162137351f789f2d8f383534309137b57b01a8`
> 候选 HEAD（approved）：`9662f2c1a006be0ca3eca308939de3e59ab5d69a`
> 范围 `v2...HEAD`：40 files，+7055/−239；工作区 clean
> Review 日期：2026-09-27（含两轮修复后）

## 依据
`requirements-v2.md` §4.2/§4.4/§4.5/§5/§6.4/§7.1/§7.3/§7.4/§9.3、§10 场景 3/4/9/11/19–27/30/31/43/44/45/46/52/60/62/65 与 BQ-AB/W/Z/AC；`docs/api/F006.md`、`docs/api/F002.md`、`docs/api/F005.md`；`docs/architecture/F006-ip-allocation.md` 与 ADR-001…005、F001/F002/F005/F013 复用基础；`docs/database/F006.md`；`docs/project/reports/F006-test-report.md`。

## 独立验证
| 验证 | 结果 |
| --- | --- |
| 后端 pytest（真实 postgres:16，全量） | **163 passed** |
| 前端 `pnpm test` | **15 files / 391 tests passed** |
| 前端 `pnpm build` | 成功 |
| 独立 HTTP/DB/并发探针 | 通过（含修复前 500→修复后 409 的双向验证） |

## 分层结论
- 需求与领域：PASS（手动/自动选址、排除集、`/31`//32、耗尽不切换、释放复用、未选网段、改段须释放、整单原子、管理 IP 四态、删除/网段保护、保留/网关冲突）。
- 架构与 Contract：PASS（资源端点扩展 + `allocated-ips` 只读端点、错误码、`conflicts`、`errors[].field` 下标、F005 端点扩展同步）。
- 数据与 Migration：PASS（`ip_addresses`、`management_ip_id`、附加唯一约束、循环 FK `use_alter`、幂等增量、无破坏性变更）。
- 功能正确性：PASS（修复后）；并发 create 同址映射 409。
- 可维护性/测试充分性/前端：PASS。

## 缺陷与处理
| ID | Severity | 说明 | 状态 |
| --- | --- | --- | --- |
| F006-T-01 | HIGH | `SEGMENT_HAS_ALLOCATIONS` 不可达（删除网段先命网卡 FK）。 | **已修复**（`c704d16`，删除前置优先序） |
| F006-T-02 | MEDIUM | DB 测试断言不可隔离约束。 | **已修复**（`c704d16`） |
| F006-N-01 | NOTE | 数据库文档对 `SEGMENT_HAS_ALLOCATIONS` 描述不准。 | **已处理**（文档澄清） |
| F006-RV-01 | MEDIUM | `POST /resources` 并发同址返回 500 而非 409。 | **已修复**（`9662f2c`，commit/写入映射 + 并发回归；旧码 3 用例全红验证） |
| F006-RV-02 | LOW | 测试报告状态/候选滞后。 | **已处理** |
| F006-RV-04 | NOTE | Contract 未列 `IP_INVALID` 子码。 | **已处理**（文档补记） |

无 BLOCKER/HIGH/必须修复 MEDIUM（修复后）。第三轮复核结论 **APPROVED WITH FOLLOW-UP**（候选 `9662f2c`）。

## 结论
F006 实现、设计、Schema 与测试满足已确认需求与 Contract，真实 PG 集成、DB 约束与前端验证可信。**APPROVED WITH FOLLOW-UP**（候选 `9662f2c`，Base `7516213`）。Merge `6fc6cd4` 由协调器按 Git Workflow 执行。

## Follow-ups（非阻塞）
1. F006-RV-03：plan 派生字段在 Merge 时更新（最终状态提交处理）。
2. F011（M4）：场景 22/23 千节点并发唯一与耗尽端到端复核。
3. 场景 65 重叠网段/`/31`//32 完整计数口径可后续加深（Tester/Reviewer 标 PARTIAL）。

## 未审查项
前端↔后端真实端到端联验（F006 架构仅要求 Vitest，归 F011）；类型详情/宿主（F004）与服务关联（F007）；IP 历史管理员查询（F012）；`name` collation 部署差异；第三方依赖供应链审计。