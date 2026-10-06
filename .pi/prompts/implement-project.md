---
description: 恢复或调度已批准的 V3 Feature，按项目计划持续执行
argument-hint: "[Feature ID | --all | --from Feature ID]"
---

# Project Execution Orchestrator

输入：$ARGUMENTS。显式 Feature ID 默认为 SINGLE，只完成该项；`--all` 或无 ID 的“实施项目”请求为 CONTINUOUS；`--from Fxxx` 表示从指定项开始持续执行。自然语言明确限定的范围优先，冲突参数停止核对。持续执行也仅限用户授权和计划批准共同覆盖的范围。

本入口只负责项目调度。单 Feature 阶段由 `.pi/prompts/feature.md` 定义；Git 操作与恢复由 `docs/project/git-workflow.md` 定义；字段与状态映射由 `docs/project/project-state.md` 定义。

只调度 CSM V3 一期，需求基线为 `docs/product/requirements-v3.md`。空 DRAFT 骨架不是可执行计划；文档维护指令不代表实施授权。依需求 §35 核验受影响问题与建议的确认状态，不能用已有状态词绕过产品裁定。

## 1. 读取与恢复

读取 `AGENTS.md`、已提交 Plan 与工作区差异、`docs/project/change-control.md` 及上述规范。先按 Git Workflow 核对是否存在中断的 Merge / 状态提交，再运行状态一致性校验；不得把未提交 DONE 当成完成。proposal 分支只允许规划，不在其上调度实施。

优先恢复 current_feature 或唯一进行中 Feature，保留阶段和 next_action。输入 ID 与恢复目标冲突、多个候选、Git 证据无法核对时停止，不新建任务。

开始或恢复均检查 Project Gate：DRAFT 输出 `PROJECT PLAN APPROVAL REQUIRED`；DONE 仅在完成证据有效时输出 `PROJECT ALREADY COMPLETE`；只有 ACCEPTED / IN_PROGRESS 且完整计划可实施。核对批准 revision、范围、现有实施授权和 pending_changes；旧批准字段不完整时先核对已有依据，不用项目状态替代批准。

## 2. 选择与调用

按项目状态规范重算 READY。显式 ID 仅可选择 READY 或恢复中的任务；否则依 P0→P1→P2、依赖链解锁价值、稳定 ID 排序。同一时刻只执行一个 Feature。

先把已有明确实施指令保存为 execution.authorization，按状态规范记录对象版本与范围，再运行 `python3 scripts/validate_project_state.py --feature Fxxx`。调用 `.pi/prompts/feature.md`，传入身份、SINGLE / CONTINUOUS 及授权范围、批准记录、已核对恢复信息和权威文档引用。各 Gate 单独返回协调器核验；不使用 Subagent chain 自动跨 Gate。由 Feature 流程负责分支生命周期、阶段执行及检查点更新；本入口不另维护阶段算法或重复创建分支。

## 3. 继续或停止

Feature 返回完成时，核对最终状态提交及状态校验后重新计算依赖；SINGLE 输出该项结果并停止，不因还有 READY 自动扩大范围。CONTINUOUS 在剩余授权范围内继续下一 READY Feature。返回阻塞时保留检查点，输出项目进展、责任者与恢复动作，不选择其他 Feature 绕过当前任务。

没有 READY 时区分待确认、阻塞和真正完成。达到项目完成条件后按 Git Workflow 保存最终状态；提交成功且证据有效才输出 `PROJECT IMPLEMENTATION COMPLETE`。

项目统计和输出遵循项目状态规范，不另维护一份管理状态。此次执行授权覆盖已确认范围内 feature.md 定义的有限修复，不覆盖新的业务或架构决定。
