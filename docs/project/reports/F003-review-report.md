# F003 计算资源统一列表、详情与服务端分页 — Review Report

> Status: APPROVED WITH FOLLOW-UP
> Document Type: Feature Review Report
> Feature: F003（Epic E2，P0）
> Branch: `feature/F003-resource-list-detail`；Base `v2` = `ccc6f9ffece626d10482b3f6ce5b4941dc32fd12`
> start_commit / merge-base：`ccc6f9ffece626d10482b3f6ce5b4941dc32fd12`
> 候选 HEAD（approved）：`a992ae86d3f4bf48269e25b238b8ad1c02f3eb10`
> 范围 `v2...HEAD`：22 files，+3507/−22；工作区 clean
> Review 日期：2026-09-28

## 依据
`requirements-v2.md` §4.3/§6.2/§6.3/§8/§9.2/§9.4、§10 场景 8/32 与 BQ-AA/W；`docs/api/F003.md`、`docs/api/F002.md`、`docs/api/F006.md`；`docs/architecture/F003-resource-list-detail.md` 与 ADR-001…005、F001/F002/F005/F006/F013 复用基础；`docs/project/reports/F003-test-report.md`。

## 独立验证
| 验证 | 结果 |
| --- | --- |
| 后端 pytest（真实 postgres:16，全量） | **177 passed**（F003 专测 14） |
| 独立 HTTP 探针 | 通过（只读无副作用、集合写端点 405、空/不存在集群 200 等） |
| 前端 `pnpm test` | **20 files / 451 tests passed** |
| 前端 `pnpm build` | 成功 |

## 分层结论
- 需求与领域：PASS（§6.2 列表/切换/筛选/搜索/分页/作用域、§6.3 详情、§4.3/§9.4 状态含文字、场景 8/32）。
- 架构与 Contract：PASS（新增 `GET /resources`、详情复用、无新增写端点、无 DB Schema 变更、错误码）。
- 功能正确性：PASS（跨集群隔离、权重排序、分页边界、只读）。
- 可维护性/测试充分性/前端：PASS（无 N+1；竞态防护、状态/错误态）。

## 缺陷
| ID | Severity | 说明 | 状态 |
| --- | --- | --- | --- |
| F003-R-01 | LOW | 计划 `head_commit`/`status` 派生字段陈旧。 | 最终状态提交处理 |
| F003-R-02 | NOTE | 空串 `resource_type`/`status`/`sort` 返回 400；不存在集群 `scope` 字段为空串（Contract 未定义）。 | 前端不发空值；可选文档澄清 |
| F003-R-03 | NOTE | `q` 路径集群内全量后 Python 权重排序（架构 `PROPOSED`/`OPEN`）。 | 随 F011 性能基线跟进 |

无 BLOCKER/HIGH/必须修复 MEDIUM。

## 结论
核心验收满足，Contract/架构/ADR 符合，后端 177 + 前端 451 测试与 build 经独立重跑通过。**APPROVED WITH FOLLOW-UP**（候选 `a992ae8`，Base `ccc6f9f`）。Merge `34ae8fd` 由协调器按 Git Workflow 执行。

## Follow-ups（非阻塞）
1. F003-R-01：Merge 时更新 plan 派生字段（最终状态提交处理）。
2. F003-R-02：可选在 `docs/api/F003.md` 明确空串筛选参数与不存在集群 `scope` 字段口径。
3. F003-R-03：按 §9.2 在千台基线实测列表/搜索 P95（随 F011）；如超目标另立 Database 变更评估索引。

## 未审查项
真实浏览器 E2E（归 F011）；P95 性能实测；F004 类型摘要、F007 详情服务关联、F010 全局 IP 查询、F012 历史查询；Test Report 所述 56 项探针脚本未逐条重放（Reviewer 自建探针复核）。