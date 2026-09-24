# CSM

面向 HPC / AI 运维场景的内部资源管理平台。目标是替代分散维护的 Excel，提供统一的资源登记、查询、维护、关联、状态查看与资源使用情况查看。

> **当前状态：CSM V2 重构中。**
> - CSM V1 已冻结为演示版本 `v1.0.0-demo`（tag → `563eda3`，冻结分支 `release/v1`）。版本边界见 `docs/project/releases.md`。
> - V2 是对 V1 的大跨度重构（资源领域与产品范围均变化），其**应用代码与 V1 设计文档已从 `v2` 分支重置**，需求与架构重新进行。
> - **V1 全部内容（代码、需求、架构、API、数据库、Review / Test 文档）未丢失**，完整保存在 `release/v1` 分支与 `v1.0.0-demo` tag 中，可随时参考。

## 目录

| 路径 | 说明 |
|---|---|
| `docs/product/requirements-v2.md` | V2 产品需求（Status: DRAFT — AWAITING CONTENT，待填写）。 |
| `docs/project/project-plan.yaml` | V2 项目计划（当前为 incomplete / DRAFT 骨架）。 |
| `docs/project/v1/` | V1 冻结计划快照。 |
| `docs/project/v2/planning-intake.md` | V2 规划前提、待澄清输入与重置记录。 |
| `docs/project/git-workflow.md` | 分支与提交流程。 |
| `.pi/` | Agent 定义、Skill、工作流 Prompt。 |

V2 的 `docs/architecture/`、`docs/database/`、`docs/api/`、`docs/deployment/` 以及 `backend/`、`frontend/`、`tests/`、`deploy/` 将在 V2 需求与架构确认后建立（见 `docs/project/repository-structure.md`）。

## 流程入口

* 规划 V2：`.pi/prompts/project.md`
* 实现 Feature：`.pi/prompts/implement-project.md`
* 规划前提与归档记录：`docs/project/v2/planning-intake.md`

## 说明

V2 的技术栈、部署形态与详细数据模型尚未确认，以 `docs/product/requirements-v2.md` 与后续架构决策为准。在 V2 需求与架构批准前，本仓库不包含应用代码。