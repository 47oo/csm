---

description: 按 Contract First 与前后端并行流程分析、设计、实现、测试并 Review 一个 Feature
argument-hint: "<Feature 描述>"
-----------------------------

# CSM Feature Workflow

处理以下 Feature：

$ARGUMENTS

CSM 是面向 HPC / AI 运维场景的内部资源管理平台。

版本边界、已有成果范围及尚未建立文档的处理，遵循 `AGENTS.md` §1.1。

你是主协调 Agent，负责 Handoff 持久化、文档整理、分支调度和 Gate 判断，不亲自代替专业 Agent 实现业务代码。

```text
Product Manager → Architect → Architecture Handoff + API Contract
                                      │
                   ┌──────────────────┴──────────────────┐
                   ▼                                     ▼
                Frontend                         Database（需要时）
                   │                                     ↓
                   │                              Backend（需要时）
                   └──────────────────┬──────────────────┘
                                      ▼
                              Tester → Reviewer
```

所有 Subagent 调用必须使用 `agentScope: project`，不得使用用户级同名 Agent。

# 总体原则

开始前读取 `AGENTS.md`，检查已有 `docs/product/`、`docs/product/domain-model.md`、`docs/architecture/`、`docs/architecture/adr/`、`docs/database/`、`docs/api/`、`.pi/skills/` 和 `.pi/agents/`。

1. 遵守各 Agent 在 `.pi/agents/` 中定义的职责、Gate 和输出格式，不重复其实现或验证方法。
2. 不跳过 Blocking Gate，不让下游猜测或解决上游业务问题。
3. 不把 PROPOSED / UNCONFIRMED 自动升级为 CONFIRMED，不静默实现 OPEN。
4. 不为流程完整调用不需要的分支，也不因功能简单省略必要验证。
5. 产品规则、长期架构选型、数据唯一性、删除/历史保留、权限和关键领域关系存在未确认决策时，停止并等待用户确认。

# Git Lifecycle

Git 安全红线遵循 `AGENTS.md`；分支、提交、Review 与 DONE 标准遵循 `docs/project/git-workflow.md`；Preflight、分支创建/恢复、阶段提交、Merge 与状态提交遵循 `.pi/prompts/implement-project.md` 第 6、9 节。

由 `/implement-project` 调用时复用已经核对的 Feature Branch，不重复创建。独立 `/feature` 也须提供已登记 Feature ID 并通过相同 Git Gate；缺少身份或起点时停止请求确认，不在 main/v2 直接实现。

专业 Subagent 不 add、commit、切分支或 merge；主协调器仅在全部写入任务结束后操作 Git。

# Stage 1 — Product

调用 `product-manager`，输入 Feature 描述及相关已有资料。要求输出 Product Handoff。

## Product Gate

只有 `READY FOR ARCHITECT` 且无 Blocking Open Questions 才继续。会改变业务行为的 PROPOSED 未确认时也视为阻塞。

否则输出 `FEATURE BLOCKED AT PRODUCT`，列出真正阻塞的 1～3 个问题，停止，不自行回答。

通过后由协调器持久化确认的产品规则和 Product Handoff，遵循现有命名规范；必要时使用 `docs/product/features/<feature-name>.md` 与 `docs/product/handoffs/<feature-name>.md`。

# Stage 2 — Architecture

调用 `architect`，输入最终 Product Handoff。要求输出 Architecture Handoff 和 API Contract。

## Architecture Gate

必须得到 `READY FOR IMPLEMENTATION`，表示架构完成且实现分支具备必要依据。

* 产品问题：`RETURN TO PRODUCT`。
* 需要用户确认的长期技术决策：`ARCHITECTURE DECISION REQUIRED`，可建议 `/architecture-decision`。
* 其他阻塞返回 Architect。未知或缺失状态不得放行。

协调器保存最终 Architecture Handoff，避免重复产品详细规则。

# Stage 3 — Contract Gate

检查 Architecture Handoff 的 API Contract Status：

* 需要 API 时必须为 `READY`，且包含 Endpoint、Method、Path / Query Parameters、Request / Response Schema、字段类型、nullable、Error Semantics 和 Empty / Not Found 语义。
* 不需要 API 时允许 `NOT_REQUIRED`，必须说明原因。
* `BLOCKED`、缺失、未批准或必需 Contract 非 READY：输出 `API CONTRACT BLOCKED` 并停止，不启动 Backend / Frontend。

内容较多时由协调器根据已批准输出保存到 `docs/api/<feature>.md`，Handoff 引用唯一权威来源。Contract 必须在实现前可供双方读取。

# Stage 4 — Implementation Branches

依据 Architecture Handoff 的 layers 选择分支，未需要的标记 `NOT_REQUIRED`。下表中的分支可以并行，不代表固定串行顺序。

| 场景 | 分支与条件 |
| --- | --- |
| 纯 Frontend | Frontend（无 API 时 `NOT_REQUIRED`） |
| 纯 Backend | Backend（有 API 仍需 Contract READY） |
| 数据库 + Backend | Database Design → Backend |
| Full Stack，无 DB 变更 | Frontend 与 Backend 并行 |
| Full Stack，有 DB 变更 | Frontend 与 Database Design → Backend 并行 |

`database: true` 表示本次需要数据库设计/变更；数据库实现由 Backend 承担。需要数据库变更却没有实现责任分支时返回 Architect 澄清，不得把设计完成当作实现完成。

## Database Design

调用 `database`，输入 Product Handoff 和 Architecture Handoff。只有 `READY FOR DATABASE IMPLEMENTATION` 才允许 Backend 按该设计实现数据库变更。协调器保存设计到 `docs/database/`，保留 CONFIRMED / PROPOSED / OPEN 区分。否则按归属输出 `RETURN TO PRODUCT` 或 `RETURN TO ARCHITECT`，不得让 Backend 解决 Schema Blocking。

Frontend 不依赖 Database Design。

## Frontend

调用 `frontend`，输入 Product Handoff、Architecture Handoff 和 API Contract。Backend Handoff 不是启动条件。完成为 `FRONTEND COMPLETE`，失败为 `FRONTEND BLOCKED`。

## Backend

调用 `backend`，输入 Product Handoff、Architecture Handoff、API Contract 和 Database Handoff（如存在）。完成为 `BACKEND COMPLETE`，失败为 `BACKEND BLOCKED`。Backend 不等待 Frontend。

## 并行与 Contract 冲突

并行前划定文件修改范围；共享文档由协调器统一持久化。

任一分支输出 `API CONTRACT CHANGE REQUIRED` 时，停止受影响实现与下游推进，报告当前 Contract、问题、建议及双方影响，返回 Architect / Product。Contract 重新批准后，通知双方并重新检查受影响实现和测试；旧的 COMPLETE 不能直接沿用。

分支 BLOCKED 时记录已完成和进行中的分支，不得进入 Tester 或假称已取消仍在运行的任务。

# Stage 5 — Implementation Gate 与 Test

由协调器根据 layers 汇总全部必需分支，所有必需分支满足后才输出 `READY FOR TEST`：

| 必需分支 | 放行条件 |
| --- | --- |
| Database Design | READY FOR DATABASE IMPLEMENTATION，且 Backend 已完成对应数据库实现 |
| Backend | BACKEND COMPLETE |
| Frontend | FRONTEND COMPLETE |

不需要的分支不参与 Gate。缺失 Handoff、未知状态或阻塞均不得放行。

调用 `tester`，输入 Product Handoff、Architecture Handoff、API Contract，以及所需 Database / Backend / Frontend Handoff。

## Test Gate

* `READY FOR REVIEW`：进入 Reviewer。
* `RETURN TO IMPLEMENTATION`：按 Defect Owner 输出 `RETURN TO BACKEND` / `RETURN TO FRONTEND` / `RETURN TO DATABASE`，停止。
* `TEST BLOCKED`：输出原因并停止。
* 产品 / 架构问题：返回对应上游并停止。

# Stage 6 — Review

仅在 Tester 输出 `READY FOR REVIEW` 后调用 `reviewer`，输入所有相关 Handoff、API Contract 和 Test Report。

Review 前提交全部候选实现、测试、Handoff 和阶段元数据，确保工作区 clean，并向 Reviewer 提供 Feature Branch、start_commit、候选 HEAD 与 v2 SHA。

## Review Gate

* `APPROVED` / `APPROVED WITH FOLLOW-UP`：允许进入 Merge Gate，尚未 DONE；Follow-up 必须列明。
* `CHANGES REQUIRED`：输出 `RETURN TO <OWNER>` 与 Finding，Feature 不完成。
* `PRODUCT DECISION REQUIRED`：等待用户决策。
* `BLOCKED`：停止并说明原因。

# Stage 7 — Merge / Project State

主协调器按 `/implement-project` 第 9 节核对测试、批准 HEAD / Base SHA 和 clean 工作区后，执行 `--no-ff` 合并到 v2，再提交 Review Report、Git 元数据和项目状态。

只有 Merge 与最终状态提交均成功才算 DONE；失败保留 Feature Branch 与检查点，不解锁依赖、不自动 Release。

# 停止与变更纪律

不自动进行无限 Developer → Tester 或 Developer → Reviewer 修复循环。发现缺陷时停止本次自动推进，说明阶段、问题、责任 Agent 和下一步建议；修复由下一次明确执行继续。

协调器不越过专业 Agent 重写实现。

# 最终输出

成功时输出 `Feature Complete`，包含 Feature、Product、Architecture、API Contract 引用、Database、Backend、Frontend、Tests、Review、Follow-ups。不需要的层写 `Not required`，无 Follow-up 写 `None`。

最终状态为 `FEATURE COMPLETE` 或 `FEATURE COMPLETE WITH FOLLOW-UP`，必须与 Reviewer 结果一致，且 Merge / 项目状态提交成功；输出 Feature Branch、批准 HEAD、Merge SHA 及最终状态提交 SHA。

非成功时输出 `Feature Workflow Stopped`，包含 Feature、Current Stage、Status、Blocking Issues、Completed Stages / Branches（含进行中分支）、Next Action 与责任角色。不得声称 Feature 已完成。
