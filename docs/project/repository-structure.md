# Repository Structure

本文档说明 CSM 项目主要目录职责。

## `docs/product/`

用于保存：

* 产品需求；
* 功能规格；
* 验收标准；
* 已确认的业务决策；
* 权威领域模型。

其中 `docs/product/domain-model.md` 是资源领域模型的权威来源。

## `docs/architecture/`

用于保存：

* 架构决策；
* 系统边界；
* 组件设计；
* 重要技术取舍。

## `docs/database/`

用于保存：

* 数据模型说明；
* 数据库设计；
* Schema 设计决策；
* 数据库迁移相关说明。

## `docs/api/`

用于保存：

* API 契约；
* 请求和响应结构；
* API 设计规范。

## `docs/project/`

用于保存：

* 项目计划；
* Backlog；
* 依赖关系；
* Milestone；
* 项目流程说明。

## `backend/`

用于保存后端应用代码。

## `frontend/`

用于保存前端应用代码。

## `tests/`

用于保存项目级自动化测试和测试相关资源。

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
