# F008 统一模糊搜索与下拉交互 — Review Report

> Status: APPROVED WITH FOLLOW-UP
> Document Type: Feature Review Report
> Feature: F008（Epic E6，P0，M2）
> Branch: `feature/F008-unified-search`；Base `v2` = `ce20ae97b6bc3f7e55d57163dafc30b7da961ead`
> start_commit / merge-base：`ce20ae9`；候选 HEAD（approved）：`7fd9bd0bd663824904b240755505b242afba75c2`
> 范围 `v2...HEAD`：38 files，+4233/−204；工作区 clean
> Review 日期：2026-09-28

## 依据
`requirements-v2.md` §7.5/§8.1/§8.2/§8.3、§9.2/§9.4、§10 场景 41/37/38/35/36/39/56 与 BQ-H/BQ-W；`docs/api/F008.md`、`F001.md` §2.1、`F003.md` §2.1、`F005.md` §2.1、`F006.md` §3.1；`docs/architecture/F008-unified-search.md` 与 ADR-001…005；`docs/project/reports/F008-test-report.md`。

## 独立验证
| 验证 | 结果 |
| --- | --- |
| 后端 pytest（真实 postgres:16，全量） | **196 passed**（F008 专项 19） |
| 前端 `pnpm test`（连续 3 次） | **28 files / 534 tests passed**（3/3 稳定） |
| 前端 `pnpm build` | 成功 |
| 端点/字段/Schema 不变式 | 无新增路由、无 models/schemas 改动、无 soft-delete、无新错误码 |

## 分层结论
- 需求与领域：PASS（§8.1/§8.2 匹配内容与规则、§8.3 交互、§7.5/场景 41、仅仍存对象、无新增业务规则）。
- 架构与 Contract：PASS（无新增端点/字段/错误码；rank 权重与包含语义兼容；资源 q 行为不变；无 Schema 变更）。
- 功能正确性：PASS（allocated-ips、FuzzySelect/useRemoteOptions 竞态与错误态、资源表单网络范围下拉接入）。
- 可维护性：PASS（`app/search/matching.py` 纯函数、前端职责边界清晰）。
- 测试充分性：基本充分（F008 未直接断言「删除后 q 不返回」）。

## 缺陷
| ID | Severity | 说明 | 状态 |
| --- | --- | --- | --- |
| D-F008-01 | MEDIUM | 网络范围下拉未支持技术类型匹配、FuzzySelect 未接入。 | **修复轮 1 已闭环**（`1be29f4`） |
| R-F008-01 | LOW | `docs/api/F006.md` §3.1 缺 F008 q 排序交叉引用。 | 已同步 |
| R-F008-02 | LOW | `AdminUsersView` role/status 下拉未接入 EnumSelect。 | 按架构 §2「用户页交互可后续对齐」记入 Follow-up（非 F008 基线） |
| R-F008-03 | NOTE | 缺「删除后 q 不返回」直接断言（物理删除间接保证）。 | Follow-up |
| R-F008-04 | NOTE | 计划 `execution.current_stage` 元数据陈旧。 | 最终状态提交处理 |

无 BLOCKER/HIGH/必须修复 MEDIUM。

## 结论
核心验收满足、必要验证可信，无必须修复问题。**APPROVED WITH FOLLOW-UP**（候选 `7fd9bd0`，Base `ce20ae9`）。Merge `3e5f0bd` 由协调器按 Git Workflow 执行。

## Follow-ups（非阻塞）
1. R-F008-01：已在合并后同步 `docs/api/F006.md` §3.1 q 交叉引用（与 F001/F005 口径一致）。
2. R-F008-02：role/status 等固定枚举是否纳入 F008 基线由 Architect/协调器后续裁定；未纳入则按架构 §2 记录。
3. R-F008-03：可选补一条「删除后 q 不返回该对象」后端断言。
4. R-F008-04：最终状态提交校正 `execution.current_stage`。

## 未审查项
真实浏览器 E2E（归 F011）；`uvicorn` 独立探针 40/40 未复跑（同功能面由 pytest 覆盖）；§9.2 性能 P95 基准（`OPEN`）；键盘 ↑/↓ 高亮位移逐帧；场景 35/36 宿主去重与 F007/F010 适配点。