# CSM V1 计划 — 冻结快照

> Status: **FROZEN**（不再维护）
> 冻结于：`v1.0.0-demo`（tag → `563eda3`，冻结分支 `release/v1`）
> 归档日期：2026-09-24

本目录保存 CSM V1 的项目计划与人类可读视图，作为 `v1.0.0-demo` 的历史记录：

| 文件 | 内容 |
|---|---|
| `project-plan.yaml` | V1 机器可读计划（Source of Truth），M1–M12 全部 DONE（21 DONE + 1 CANCELLED） |
| `backlog.md` | V1 Backlog 视图 |
| `dependency-map.md` | V1 Feature 依赖图 |
| `milestones.md` | V1 Milestone 视图 |
| `_planning-findings.md` | V1 规划阶段盘点（Stage 1/2） |

## 说明

* 本目录内容对应 `v1.0.0-demo` 时刻的计划状态，**不再更新**。
* 2026-09-24 起，V1 设计文档（`docs/product/`、`docs/architecture/`、`docs/database/`、`docs/api/`、`docs/deployment/`、
  `docs/reviews/`、`docs/test-reports/`）与应用代码已从 `v2` 分支移除，以减少对 V2 重构的干扰；
  它们完整保存在 `release/v1` 分支与 tag `v1.0.0-demo`（可用 `git show release/v1:<path>` 查看）。
* 当前（v2）计划的 Source of Truth 为 `docs/project/project-plan.yaml`；v2 需求与规划见
  `docs/product/requirements-v2.md` 与 `docs/project/v2/planning-intake.md`。
* V1 已部署形态与版本边界见 `docs/project/releases.md`。