---
description: 恢复或调度已批准的 V2 Feature，按项目计划持续执行
argument-hint: "[任务或 Feature ID]"
---

# Project Execution Orchestrator

输入：$ARGUMENTS（可选 Feature ID）

本入口只负责项目调度。单 Feature 阶段由 `.pi/prompts/feature.md` 定义；Git 操作与恢复由 `docs/project/git-workflow.md` 定义；字段与状态映射由 `docs/project/project-state.md` 定义。

## 1. 读取与恢复

读取 `AGENTS.md`、已提交 Plan 与工作区差异及上述规范。先按 Git Workflow 核对是否存在中断的 Merge / 状态提交；不得把未提交 DONE 当成完成。

优先恢复 current_feature 或唯一进行中 Feature，保留阶段和 next_action。输入 ID 与恢复目标冲突、多个候选、Git 证据无法核对时停止，不新建任务。

无恢复任务时检查 Project Gate：DRAFT 输出 `PROJECT PLAN APPROVAL REQUIRED`；DONE 仅在完成证据有效时输出 `PROJECT ALREADY COMPLETE`；只有 ACCEPTED / IN_PROGRESS 且完整计划可实施。

## 2. 选择与调用

按项目状态规范重算 READY。显式 ID 仅可选择 READY 或恢复中的任务；否则依 P0→P1→P2、依赖链解锁价值、稳定 ID 排序。同一时刻只执行一个 Feature。

调用 `.pi/prompts/feature.md`，传入身份、已核对恢复信息及权威文档引用。由 Feature 流程负责分支生命周期、阶段执行及检查点更新；本入口不另维护阶段算法或重复创建分支。

## 3. 继续或停止

Feature 返回完成时，核对最终状态提交后重新计算依赖，继续下一 READY Feature。返回阻塞时保留检查点，输出项目进展、责任者与恢复动作，不选择其他 Feature 绕过当前任务。

没有 READY 时区分待确认、阻塞和真正完成。达到项目完成条件后按 Git Workflow 保存最终状态；提交成功且证据有效才输出 `PROJECT IMPLEMENTATION COMPLETE`。

项目统计和输出遵循项目状态规范，不另维护一份管理状态。此次执行授权覆盖已确认范围内 feature.md 定义的有限修复，不覆盖新的业务或架构决定。
