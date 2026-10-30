# F045 CHG-015 变更集整体回归与部署等价验收 — REVIEW 报告

- **结论**：**APPROVED**（附状态/文档收口条件，见 §4）
- **批准基线**：`141a3f9294ffceae51bc6d188541aca85cd893b1`（plan F045 `git.head_commit`）；分支 tip `fbbb1a3`（仅 bookkeeping）；**Base** `refs/heads/v3.4` = `fa8a568b912d7aea9806a58616e98867a5786808`（= start_commit = merge-base）
- **版本**：v1（2026-10-29，终审第七轮通过；前六轮分别为 CHANGES REQUESTED / 两次口径修正）
- **范围**：31 文件（`docs/features/F045/**`、计划派生视图、`backend/tests/integration/test_f038_parse_bounds.py`）；`backend/app`、`backend/alembic`、`frontend/src`、`backend/package*.json`、`docs/api`、`docs/product`、`docs/database`、`compose*.yaml`、`.gitignore` **零 diff**；工作区 clean

## 1. 验收结论

| A | 结论 | 证据 |
| --- | --- | --- |
| A1 | **PASS（run3，无排除项）** | `artifacts/full-pytest.log`：`969 passed, 6 skipped, 0 failed`（1174.76s，真实 PostgreSQL 16.15） |
| A2 | PASS | `artifacts/a02-import-parse.log` 147 passed（四端点 × 8 类解析异常 → 422 `IMPORT_INVALID_FILE{reason:"unreadable"}`；T27/T28/T72/T107–T116/T126） |
| A3 | PASS | `artifacts/a03-capacity.log` 27 passed（§20 口径、`q_svc` 恒 11、EXPLAIN 无 Seq Scan） |
| A4 | PASS | `artifacts/a04-scope.log` 48 passed（§23.2 搜索/关联行/Dashboard/候选分页不泄露规模） |
| A5 | PASS | `artifacts/frontend-*.log`：typecheck 0 / build 0 / smoke 352 / interactions 14 |
| A6 | PASS | `artifacts/scripts-pytest.log` 113 passed |
| A7 | PASS | `artifacts/compose-up.log`、`compose-ps.log`、`http-acceptance.log`：真实 Compose（nginx :18080）、空卷 `0001→0015` 全链、`created initial admin`、§32 关键路径（round-1 42 步含 5 步驱动签名错误 / round-2 15-15 / round-3 空卷冒烟 4 步） |
| A8 | PASS | `artifacts/plan-validate.log`、`plan-render.log`、`alembic.log`（VALID / 无漂移 / `heads=0015`） |
| A9 | PASS | `artifacts/a09-review-classification.md`：六份 Review 的 NOT TESTED/BLOCKED 逐条归类；F039 唯一 BLOCKED 转实测通过；F038 F-2（3× ruff F811）如实保留 |
| A10 | PASS（含已披露缺口） | 21 个 `.log` + 3 份文档全部 `git ls-files` 跟踪；header 缺口（`full-pytest-run2-concurrent.log`、`alembic.log`、`compose-ps.log`、`plan-validate.log`、`plan-render.log`、`compose-up.log`、三份 perf 日志）已分级披露 |
| A11 | 遵循 | 未执行项一律 `NOT TESTED`/`BLOCKED`；无估算值冒充实测；2 个 perf 节点未写 PASS |
| A12 | 本报告批准 | 合并后追加证据并把 `project.acceptance.status` 恢复 `COMPLETE`（条件见 §4） |

## 2. 已知环境限制（用户裁定选项 a）

`tests/integration/test_import_performance.py::test_import_near_max_rows_baseline` 与 `tests/integration/test_f023_resource_interface_ip_import.py::test_perf03_near_max_rows_baseline`：

- 与本变更集代码无关（`backend/app` 全程零 diff）；同命令在本会话较早时段（Tester 第一轮、run3）通过，之后（含换全新 PG 集群）稳定失败；
- 三组对照实验否证了「库状态」假设（`perf-idle-check.log`、`perf-warm-db-check.log`、`perf-fresh-cluster-check.log` 均 `write≈700s`，而 `[D03-1] validate` 恒 27s 未变）；
- 用户 2026-10-29 裁定：登记为 **ENVIRONMENT_FLAKY**，**不计 PASS、不改阈值、不改产品代码**；将来如需重定阈值或定位根因，另立 Feature 走变更控制。
- 因此本报告**不声明**「导入写入性能无回归」，也**不声明** CHG-015 引入性能回归。

## 3. 六轮 Review 的收敛

| 轮 | 结论 | 主要问题 |
| --- | --- | --- |
| R1–R2 | CHANGES REQUESTED | A7「61 步 0 FAIL」口径、A8 未执行、A10 header、a09 未同步 |
| R3 | CHANGES REQUESTED | 并发重叠陈述不实（HIGH）、header 不全、A10 过度陈述 |
| R4 | CHANGES REQUIRED | 证据账本计数错、perf 归因不足（要求隔离复跑 + 负载证据） |
| R5 | CHANGES REQUESTED | 跨节点比较（validate 27s vs 114s）无效、§3.2b 与 §6.4 矛盾、head 未落记录 |
| R6 | CHANGES REQUIRED | MEDIUM-3（3.2b 矛盾）、MEDIUM-4（head 未记录） |
| R7 | **APPROVED** | 前 5 项全部闭环；余 3 项 LOW 在 DONE/状态提交内收口 |

## 4. 收口条件（已在 DONE/状态提交执行）

1. `project.acceptance`：追加 6–8 条证据锚点、既有 52 条不删、basis 覆盖 plan revision 25 / requirements revision 16，并写入「2 个 perf 节点为已知环境限制、不计 PASS、不改阈值/代码」。
2. `artifacts/env.md` head 标注「以 plan `git.head_commit` 为准」。
3. plan F045 `last_result` / `execution.last_result` 清除「归因为并发 + 膨胀库」「差异在宿主吞吐」等已被否证或超出 §6.4 口径的表述。
4. A10 表述调整为「PASS（含已披露缺口）」。

## 5. 未审查项

未重跑 pytest/Compose/前端（依据已入库日志与本轮独立抽查）；F037–F043 的历史合并内容超出本 Feature 范围；浏览器视觉/DOM/屏幕阅读器交互（AQ-4=B，NOT TESTED）；真实 OOM、无 lxml 镜像、非 linux-x64 与 registry 长期可用性。
