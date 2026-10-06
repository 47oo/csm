---
description: 执行单个已登记 Feature，按需复用设计并完成实现、验证、Review 与合并
argument-hint: "[任务或 Feature ID]"
---

# Feature Workflow

输入：$ARGUMENTS（已登记 Feature ID 或调度器提供的恢复任务）

主协调器负责分工、共享文档持久化、Gate、状态和 Git；专业角色按 `.pi/agents/` 执行。所有 Subagent 调用使用 `agentScope: project`。

每个 Gate 由协调器检查角色结果及证据后单独放行。禁止用 Subagent `chain` 跨越 Product、设计定稿、Test、Review 等 Gate：扩展仅按进程错误停止，进程成功不代表业务 READY。并行只用于同一已放行阶段内、所有权明确的任务。

读取 `AGENTS.md`、`docs/project/project-state.md`、`docs/project/git-workflow.md`、`docs/project/handoff.md`，再加载当前 Feature 及明确依赖。无需为每项任务遍历所有文档。

批准权限和需求修订按 `docs/project/change-control.md`。独立调用仅执行本 Feature；不自动转到其它 Feature，也不在 proposal 分支实施。

V3 一期的产品入口为 `docs/product/requirements-v3.md`，领域关系先查 `docs/product/domain-model.md`。每个 Gate 核对当前条款版本及 §35 的确认记录/剩余问题，不从旧版本补齐输入；已经确认的枚举、恢复范围和技术栈直接引用，尚未确定的业务行为不能由实现自行裁定。

## 1. 入口与阶段复用

独立调用也要求项目已批准、Feature READY 或合法恢复目标；从 implement-project 调用时复用其恢复信息。按 Git Workflow 执行 Preflight / 创建或恢复分支；新任务在 Preflight 成功后设置 project=IN_PROGRESS、Feature=IN_PROGRESS、execution.current_feature，并将两个 current_stage 设为 PRODUCT；恢复任务从 next_action 继续，不重置已完成阶段。每个重要阶段按状态规范更新结果与证据，并按 Git Workflow 保存检查点。

新建或恢复前先记录或核验 execution.authorization 中已有明确实施指令，再运行 `python3 scripts/validate_project_state.py --feature Fxxx`，核对批准版本和 pending_changes。状态转换保存前一份 V3 快照，按 project-state.md 的 --previous 检查；只读角色不执行此写入。已有检查点不能绕过需求变更暂停；中断 Merge/状态提交先按 Git Workflow 恢复现场，再校验。不从旧报告臆补缺失批准。

Product / Architecture / Database / Test Design 已有成果满足以下全部条件时，协调器可以记录复用结果而不再次调用该角色：

* 有可读取的确认/批准证据，明确覆盖本 Feature 的范围、验收与适用设计。
* 依据、实现基线和依赖没有使结论失效的变化。
* 必需输入齐备，无未决业务、架构、完整性或 Contract 问题。

记录来源、版本、覆盖范围与核对结论。无法判断时交原角色核对，不由协调器补做专业决策；不能仅因功能简单跳过 Gate。实现修复后的 Test / Review 不能靠复用旧报告放行。

## 2. 需求、设计与契约定稿

Product 缺失或失效时调用 product-manager，只有 `READY FOR ARCHITECT` 且无 Blocking Questions 才继续。协调器将确认规则保存到产品文档，报告引用。

Architecture 缺失或失效时调用 architect 的设计模式，要求 `READY FOR DESIGN`，明确 layers、api_required、方案与 API 草案、数据库影响和验证策略。此时 architecture=COMPLETE 仅表示方案足以启动设计检查，不放行编码。重大未决技术问题返回相应决策者。

然后按需调用 Database Design，并调用 tester 的 TEST_DESIGN 模式。二者可并行评估同一方案；若数据库结论改变测试预期，定稿前由 Tester 核对更新。Database 需完成本 Feature 的 Schema / Migration 设计，尚不要求 Migration 实现；不涉及数据设计时记录 NOT_REQUIRED 和理由。Test Design 需给出验收映射、边界/并发场景、环境和可验证性检查，结果为 `TEST DESIGN READY`；这不是测试执行通过。

Architect 核对需求、数据库设计、测试设计与 API 草案的一致性后，签核最终设计并返回 `READY FOR IMPLEMENTATION`。需要 API 时 Contract 必须 READY，字段按 architect.md 清单；无需 API 时 contract=NOT_REQUIRED 并有理由，仍须完成最终设计核对。发现差异先由对应角色修正，再定稿，不由协调器替专业角色裁定。

缺少输入、数据库设计或测试设计仍有阻塞、Contract 未签核时不启动实现。普通设计专业签核按 Change Control，无需用户逐份批准。

## 3. 按需实施

| 分支 | 启动依据 | 完成结果 |
| --- | --- | --- |
| Backend | layers.backend=true，全部适用设计 Gate 通过 | BACKEND COMPLETE |
| Frontend | layers.frontend=true，全部适用设计 Gate 通过 | FRONTEND COMPLETE |

无需的分支记录 NOT_REQUIRED 并说明理由。Schema 变更必须由 Backend 承接实际 Migration，设计完成不代表实现完成。契约定稿后 Frontend 不等待 Migration 或 Backend 实现；Backend 与 Frontend 可在文件所有权清晰时并行。

Database READY 必须附设计版本及上游依据，由协调器核验接收后放行 Backend；不能仅凭一个状态词视为已批准设计。

协调器持久化只读角色产物；所有写入停止后按 Git Workflow 提交检查点。阻塞时记录已完成和仍在运行的分支，不能假称取消或静止；先停止/等待受影响写入，再做 Git 操作。

API Contract 冲突时停止受影响实现，返回 Architect / Product；重新批准后通知双方并重新验证受影响成果。原 COMPLETE 不直接沿用。

## 4. Test 与 Review

全部必需实现分支完成（包括数据库实际实现）后调用 tester 的 TEST 模式。输入已核对的 Test Design、当前验收、设计、Contract、实现报告，要求独立实际验证。只有 `READY FOR REVIEW` 可进入正式 Review；TEST DESIGN READY / PARTIAL / BLOCKED 不能通过。

验证依据和公共要求见 `docs/project/implementation-rules.md`；数据完整性检查使用 `.pi/skills/data-integrity/SKILL.md`。报告逐项映射本 Feature 验收，无关项说明不适用，不在此重复维护业务用例。

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

需求修订超出当前批准范围时转 Project Planning / Change Control，暂停受影响任务；已 DONE 的交付以新变更 Feature 承接，不改写原完成历史。

## 6. 合并、状态与输出

按 Git Workflow 的 Merge Gate 合并，保存报告与最终状态并提交；只有最终状态提交成功才返回 `FEATURE COMPLETE` 或 `FEATURE COMPLETE WITH FOLLOW-UP`。输出 Feature 分支、批准 HEAD、Merge SHA、状态提交 SHA 与证据链接。

未完成时输出 `Feature Workflow Stopped`，列出阶段、问题、责任角色、已完成/进行中分支、修复轮数和下一步。按项目状态规范更新检查点，不能声称已合并或 DONE。
