# Repository Structure

本文档说明 CSM 项目主要目录职责。

> **2026-09-24 起：CSM 处于 V2 重构。**
> V1 的应用代码（`backend/`、`frontend/`、`tests/`、`deploy/`）与 V1 设计文档（`docs/architecture/`、`docs/database/`、
> `docs/api/`、`docs/deployment/`、`docs/product/` 的 V1 内容、`docs/reviews/`、`docs/test-reports/`）已从 `v2` 分支移除；
> 它们完整保存在 `release/v1` 分支与 tag `v1.0.0-demo`。下文标注「V2 待建立」的目录将在 V2 需求与架构确认后重新建立。

## `docs/product/`

用于保存：

* 产品需求；
* 功能规格；
* 验收标准；
* 已确认的业务决策；
* 权威领域模型。

当前仅有 `requirements-v2.md`（Status: DRAFT — AWAITING CONTENT）。V1 的 `requirements.md`、`domain-model.md`、
`domain-model.yaml`、`handoffs/` 已移除（见 `release/v1`）。V2 的权威领域模型在 V2 需求确认后建立。

## `docs/architecture/` — V2 待建立

用于保存：

* 架构决策；
* 系统边界；
* 组件设计；
* 重要技术取舍。

V1 的 ADR 与 Handoff 已移除（见 `release/v1`）。

## `docs/database/` — V2 待建立

用于保存：

* 数据模型说明；
* 数据库设计；
* Schema 设计决策；
* 数据库迁移相关说明。

## `docs/api/` — V2 待建立

用于保存：

* API 契约；
* 请求和响应结构；
* API 设计规范。

## `docs/deployment/` — V2 待建立

用于保存生产内网部署的运维文档（前置条件、部署步骤、初始化、验证、升级与运行约束）。
同一份部署详细信息只在此维护一个权威来源，`README.md` 仅保留开发流程并指向此处。

## `docs/project/`

用于保存：

* 项目计划（Source of Truth：`project-plan.yaml`）；
* Backlog；
* 依赖关系；
* Milestone；
* 项目流程说明。

子目录：

* `v1/`：CSM V1 的冻结计划快照（对应 tag `v1.0.0-demo`），不再维护。
* `v2/`：CSM V2 的规划入口与前提（`planning-intake.md`）。

## 应用代码目录 — V2 待建立

* `backend/`：后端应用代码。
* `frontend/`：前端应用代码。
* `tests/`：项目级自动化测试和测试相关资源。
* `deploy/`：生产部署配置与模板（nginx 配置、环境变量模板等）。

V1 的对应内容见 `release/v1`；V2 的目录形态与编排入口由 V2 架构决策确定。

## `.pi/agents/`

用于保存不同专业角色的 Agent 定义。

Agent 定义只描述角色职责、输入输出和工作边界，不复制完整领域模型。

## `.pi/skills/`

用于保存可复用的：

* 领域知识；
* 工程方法；
* 项目专用能力。

## `.pi/prompts/`

用于保存用户可以直接调用的工作流程入口 Prompt。

## `.pi/extensions/`

用于保存 Pi Extension 以及后续的 Agent 编排能力。