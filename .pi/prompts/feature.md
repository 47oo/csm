---
description: 执行单个已登记 Feature，按需复用设计并完成实现、验证、Review 与合并
argument-hint: "[任务或 Feature ID]"
---

# Feature Workflow

输入：$ARGUMENTS（已登记 Feature ID 或调度器提供的恢复任务）

主协调器负责分工、共享文档持久化、Gate、状态和 Git；专业角色按 `.pi/agents/` 执行。所有 Subagent 调用使用 `agentScope: project`。

读取 `AGENTS.md`、`docs/project/project-state.md`、`docs/project/git-workflow.md`、`docs/project/handoff.md`，再加载当前 Feature 及明确依赖。无需为每项任务遍历所有文档。

## 1. 入口与阶段复用

独立调用也要求项目已批准、Feature READY 或合法恢复目标；从 implement-project 调用时复用其恢复信息。按 Git Workflow 执行 Preflight / 创建或恢复分支；新任务在 Preflight 成功后设置 project=IN_PROGRESS、Feature=IN_PROGRESS、execution.current_feature，并将两个 current_stage 设为 PRODUCT；恢复任务从 next_action 继续，不重置已完成阶段。每个重要阶段按状态规范更新结果与证据，并按 Git Workflow 保存检查点。

Product / Architecture / Database 已有成果满足以下全部条件时，协调器可以记录复用结果而不再次调用该角色：

* 有可读取的确认/批准证据，明确覆盖本 Feature 的范围、验收与适用设计。
* 依据、实现基线和依赖没有使结论失效的变化。
* 必需输入齐备，无未决业务、架构、完整性或 Contract 问题。

记录来源、版本、覆盖范围与核对结论。无法判断时交原角色核对，不由协调器补做专业决策；不能仅因功能简单跳过 Gate。实现修复后的 Test / Review 不能靠复用旧报告放行。

## 2. Product 与 Architecture

Product 缺失或失效时调用 product-manager，只有 `READY FOR ARCHITECT` 且无 Blocking Questions 才继续。协调器将确认规则保存到产品文档，报告引用。

Architecture 缺失或失效时调用 architect，要求 `READY FOR IMPLEMENTATION`、明确 layers、必要设计与验证策略。重大未决技术问题暂停等待决策，不让开发者代为裁定。

随后检查 Contract：需要 API 时必须 READY、有权威文档与批准依据，字段完整性按 architect.md 的唯一清单核对；无需 API 为 NOT_REQUIRED 且有理由。缺失、未批准或 BLOCKED 不放行。

## 3. 按需实施

| 分支 | 启动依据 | 完成结果 |
| --- | --- | --- |
| Database Design | layers.database=true，Product / Architecture 完成 | READY FOR DATABASE IMPLEMENTATION |
| Backend | layers.backend=true，Contract Gate 通过，必要 Database Design 完成 | BACKEND COMPLETE |
| Frontend | layers.frontend=true，Contract Gate 通过 | FRONTEND COMPLETE |

无需的分支记录 NOT_REQUIRED。Schema 变更必须明确实现责任，默认由 Backend 实现，设计完成不代表实现完成。Frontend 不等待 Database / Backend；Backend 与 Frontend 可在文件所有权清晰时并行。

协调器持久化只读角色产物；所有写入停止后按 Git Workflow 提交检查点。阻塞时记录已完成和仍在运行的分支，不能假称取消或静止；先停止/等待受影响写入，再做 Git 操作。

API Contract 冲突时停止受影响实现，返回 Architect / Product；重新批准后通知双方并重新验证受影响成果。原 COMPLETE 不直接沿用。

## 4. Test 与 Review

只有全部必需分支完成（包括数据库实际实现）才调用 tester。输入当前验收、设计、Contract、实现报告，要求独立实际验证。只有 `READY FOR REVIEW` 可进入正式 Review；PARTIAL / BLOCKED 不能通过。

按 Git Workflow 提交全部候选交付物、确保 clean，并提供候选 HEAD / Base 与测试证据，调用 reviewer。结果仅 APPROVED / APPROVED WITH FOLLOW-UP 可进入 Merge Gate；其他结果按原因返回或阻塞。

## 5. 有限修复循环

已确认范围内、不需要修改产品、架构或 Contract 决策的实现/测试缺陷，可以自动返回对应 Backend / Frontend / Tester。每轮修复后重跑受影响测试及必要回归，再执行独立 Review；旧批准失效。

每次显式执行（包括用户明确恢复）最多自动修复 2 轮。一个修复轮次包括派发缺陷、修复、重新 Test / Review；并行修多个缺陷仍算一轮。内部递归调用不能重置计数，历史问题 ID 与结果保留。

出现下列情况立即暂停，保存 BLOCKED、失败阶段与 next_action：

* 同一必须修复问题在一轮修复验证后仍存在，或达到两轮仍有必须修复问题。
* 新业务规则、架构或 Contract 决策、破坏性数据操作需要确认。
* Git 异常、基线不一致、文件归属冲突、环境阻塞或无法可靠验证。
* 责任角色不能在授权范围内修复。

需求/设计变化应重新走受影响上游 Gate；不能借修复循环扩展范围。用户明确继续后可以开始新的两轮预算，但不能清除历史缺陷或省略重新验证。

## 6. 合并、状态与输出

按 Git Workflow 的 Merge Gate 合并，保存报告与最终状态并提交；只有最终状态提交成功才返回 `FEATURE COMPLETE` 或 `FEATURE COMPLETE WITH FOLLOW-UP`。输出 Feature 分支、批准 HEAD、Merge SHA、状态提交 SHA 与证据链接。

未完成时输出 `Feature Workflow Stopped`，列出阶段、问题、责任角色、已完成/进行中分支、修复轮数和下一步。按项目状态规范更新检查点，不能声称已合并或 DONE。
