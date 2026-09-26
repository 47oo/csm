# CSM

面向 HPC / AI 运维场景的内部资源管理平台。目标是替代分散维护的 Excel，提供统一的资源登记、查询、维护、关联、状态查看与资源使用情况查看。

当前状态：CSM V2 独立建设，产品需求待确认，尚未开始应用实现。版本边界与文档建立规则见 `AGENTS.md` §1.1。

## 目录

| 路径 | 说明 |
|---|---|
| `docs/product/requirements-v2.md` | V2 产品需求，当前为 DRAFT，等待需求正文。 |
| `docs/project/project-plan.yaml` | V2 项目计划，当前为 incomplete / DRAFT 骨架。 |
| `docs/project/git-workflow.md` | 以 v2 为集成分支的 Git 流程。 |
| `docs/project/project-state.md` | 项目字段与状态转换。 |
| `docs/project/handoff.md` | 公共交接与缺陷规范。 |
| `docs/project/implementation-rules.md` | 前后端公共实现规则。 |
| `.pi/` | Agent 定义、领域分析 Skill、工作流 Prompt 与通用调度扩展。 |

领域模型、架构、数据库、API、部署文档及应用代码，在对应需求与设计确认后建立。

## 流程入口

* 规划 V2：`.pi/prompts/project.md`
* 调度项目：`.pi/prompts/implement-project.md`
* 执行单个 Feature：`.pi/prompts/feature.md`

技术栈、部署形态与详细数据模型尚未确认，以 V2 已确认产品文档与后续批准的架构决策为准。
