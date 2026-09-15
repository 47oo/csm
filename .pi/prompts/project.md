---

description: 根据 CSM 完整产品需求生成项目范围、Epic、Feature Backlog、依赖 DAG 和实施计划
argument-hint: "<需求来源或项目规划说明>"
------------------------------

# CSM Project Planning Workflow

对 CSM 项目执行完整项目规划。

CSM 是面向 HPC / AI 运维场景的内部资源管理平台。

用户输入：

$ARGUMENTS

本流程只负责：项目级需求盘点、调用 `project-manager` 产出计划、质量检查、持久化与用户批准。不实现代码，也不自行完成长期架构决策。

规划方法和字段规则遵循 `.pi/agents/project-manager.md`；本 Prompt 只定义编排顺序。

---

# Stage 1 — Discover

读取：

* `AGENTS.md`
* `docs/product/`
* `docs/product/domain-model.md`
* `.pi/skills/resource-domain/SKILL.md`
* `docs/architecture/` 与 `docs/architecture/adr/`
* `docs/database/`
* `docs/api/`
* 当前 `.pi/agents/`
* 当前代码、已有 Handoff 与已有 Test / Review 结果

目标：确认当前项目已经有什么，而不是假设从零开始。

---

# Stage 2 — Requirements Source

确定完整需求来源。优先使用用户在 `$ARGUMENTS` 中明确指定的文件，例如 `docs/product/requirements.md`；如果需求分散在多个已确认的 Product 文档中，则全部纳入。

不得使用旧聊天中的猜测覆盖当前项目文件。

---

# Stage 3 — Project Manager

使用项目级 `project-manager`（`agentScope: project`），基于全部已确认需求建立 Project Plan，输出 Project Goal、Scope、Epic、Feature Inventory、Dependency、Priority、Blocking Decision、Milestone 与 Existing Work Status。

不得在规划阶段开始实现 Feature。

---

# Stage 4 — 质量检查

检查 `project-manager` 的输出是否满足其自身定义的拆分、状态与依赖规则，重点确认：

* Feature 代表产品能力，不是按技术层切分的任务；
* 每个 Feature 有明确完成条件，粒度不过大也不过度碎片化；
* Dependency 有实际原因、无循环，且没有重复规划已有工作；
* 未确认需求没有被自动升级为 Feature 或 CONFIRMED；
* Feature 状态有真实证据支持，不以代码存在推断完成。

发现问题时要求 `project-manager` 修正规划，而不是由协调器改写产品事实。

---

# Stage 5 — Architecture Prerequisites

检查 Backlog 是否依赖尚未完成的长期架构决策（技术栈、认证、权限、删除策略、全局资源标识等）。

已有 Accepted ADR 的不得重复提出；尚未决定但阻塞 Feature 的，记录到 `decisions_required`。

不得在 `/project` 中自行完成长期 Architecture Decision。

---

# Stage 6 — 生成与持久化

创建或更新：

* `docs/project/project-plan.yaml`（机器可读 Source of Truth）
* `docs/project/backlog.md`
* `docs/project/dependency-map.md`
* `docs/project/milestones.md`

Markdown 文件是人类可读视图，不成为机器状态的唯一来源。

重新规划已有项目时保留并核对执行检查点、Git 元数据与真实历史，不重置正在执行的分支信息。

---

# Stage 7 — Approval Gate

生成的 Project Plan 初始 `project.status: DRAFT`。

最终向用户输出：

# Project Plan Summary

## Project Goal

## Epics

## Feature Count

按 P0/P1/P2 汇总。

## Dependency Critical Path

## Ready Features

## Blocked Features

## Decisions Required

## Existing Work

## Suggested First Milestone

## Files Generated

最后输出：

`PROJECT PLAN READY FOR APPROVAL`

不得自动启动 Feature Implementation。

必须等待用户确认 Project Plan；不得自行把 `DRAFT` 改成 `ACCEPTED`。
