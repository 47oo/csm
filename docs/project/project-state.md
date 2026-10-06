# 项目状态规范

`docs/project/project-plan.yaml` 是机器状态唯一来源。Markdown Backlog、依赖图和 Milestone 是派生视图。状态生效与 Git 证据规则见 `docs/project/git-workflow.md`。

## 项目与 Feature

规划前提、范围与需求覆盖仍必须以已确认产品文档为准；本规范仅定义管理状态，不自行生成产品能力。

项目状态：`DRAFT`（待确认）、`ACCEPTED`（用户批准）、`IN_PROGRESS`（执行中）、`DONE`（完成证据已提交）。只有 ACCEPTED / IN_PROGRESS 可自动实施。空计划或 incomplete 计划不能因零个未完成 Feature 被判为 DONE。

状态不替代批准。计划批准、实施授权与设计签核按 `docs/project/change-control.md` 核验；恢复任务同样适用，不因存在检查点而跳过当前批准范围和暂停标记。

| Feature 状态 | 条件 |
| --- | --- |
| DRAFT | 范围或验收标准尚未明确 |
| BLOCKED | 范围已明确，但存在决策、依赖、环境或执行阻塞 |
| READY | 范围及验收明确，无阻塞决策，depends_on 全部 DONE，具备执行前提 |
| IN_PROGRESS | 正在准备或实现，包括缺陷修复 |
| IN_REVIEW | 必需实现完成，正在 TEST / REVIEW / MERGE |
| DONE | 通过 Git Workflow 的完成条件，且最终状态提交成功 |
| CANCELLED | 用户明确取消，记录原因；不得默认为满足依赖 |

执行优先恢复 `execution.current_feature`。没有检查点时，IN_PROGRESS / IN_REVIEW 是恢复候选；多个候选或身份不一致时停止核对，不猜测。DONE 不因重新计算 READY 被覆盖。

## 字段约定

* Feature 至少记录稳定 id、目标、范围、验收依据、priority、depends_on、blocking_decisions、status。
* `execution.current_feature`：当前 Feature ID 或 null。
* `execution.current_stage` 与 Feature 的 `current_stage`：同值，取 PRODUCT / ARCHITECTURE / CONTRACT / DATABASE / IMPLEMENTATION / TEST / REVIEW / MERGE；结束并完成状态提交后为 null。
* `layers.database/backend/frontend`：boolean；不使用状态字符串。database 表示需要数据库设计/变更，数据库实现由 Backend 承担。
* `implementation.database_design/backend/frontend/test/review`：PENDING / COMPLETE / BLOCKED / NOT_REQUIRED。NOT_REQUIRED 必须有范围理由，Test / Review 的必要验证不能据此省略。
* `contract.status`：READY / BLOCKED / NOT_REQUIRED；需要 API 且 READY 时必须有 `contract.doc` 和批准依据。
* `last_result`、`next_action`：阶段结果、责任角色与恢复动作；无后续恢复动作时 `next_action: null`。说明放 `last_result` / `note`，不得写成字符串 `null（说明）`。
* `evidence`：阶段报告、权威文档版本、测试基线、Review 与 Git 证据的引用；复用阶段记录复用来源、适用范围及核对结果。
* `repair`：本次执行的自动修复轮数、问题 ID、责任角色、每轮结果；轮次策略由 `feature.md` 定义。
* Feature 的 `git` 字段含义由 Git Workflow 定义。

计划尚未生成 Feature 时保持空数组，不为符合字段规范创建虚构任务。未来旧格式或缺失元数据须核对证据后显式迁移，不能按字符串真值调度。

### 批准与变更字段

* `project.approval`：当前有效计划批准，包含 `plan_revision`、`feature_ids`（批准覆盖的明确 ID 列表）、`approved_by`、`approved_on`、`basis`（可定位确认来源及批准范围）。`plan_revision` 必须与当前计划一致；部分批准不放行未列出的 Feature。
* `pending_changes`：默认为空列表。每项包含 `id`、`proposal`（提案路径）、`affects`（Feature ID 列表或 `ALL`）。仅保存尚未解除的暂停标记；批准并落地或用户取消后移除，处理历史保存在提案。命中标记的 Feature 不得开始、恢复或合并。
* 本次实施授权由协调器在交接/执行输出中记录来源、SINGLE / CONTINUOUS 模式和范围，不以 `project.approval` 代替。恢复时沿用仍有效的授权；无法取得依据时再请求缺失的授权。

旧的 `approved_by/approved_on/approval_basis` 等记录可保留历史，但只有核对明确版本、范围和确认来源后才能迁移到 `project.approval`。流程维护不能替用户补签旧计划。候选修订的批准记录在提案中保存，不能覆盖当前有效批准。

### 一致性校验

协调器在调度前、恢复现场核对后、状态提交前及提交后运行：

```bash
python3 scripts/validate_project_state.py
```

选择开始或恢复的 Feature 后另运行 `python3 scripts/validate_project_state.py --feature Fxxx`，检查当前计划批准覆盖与暂停标记。脚本依赖 Python 3 和 PyYAML（工具依赖见 `scripts/requirements.txt`）；不要求安装应用运行环境。

检查包括 ID/依赖无环、合法状态与字段类型、READY 的依赖/决策、统计和派生列表、执行检查点与 Feature 阶段一致、DONE 的阶段清空与证据字段、禁止伪 null。`DONE` 的 git/evidence 非空仅是结构要求，实际提交、测试、Review 证据仍按 Git Workflow 人工核验。

失败输出 `PROJECT STATE INVALID`，停止调度或状态提交，先按证据修复；不能自动清空冲突检查点。Git 中断恢复需要先定位实际现场，再校正状态，不能因校验失败而丢弃未提交产物。批准缺失输出 `PROJECT APPROVAL RECONCILIATION REQUIRED`；应先查已有证据，不能自动认定用户从未授权。

## 阶段结果映射

| 结果 | 记录与下一步 |
| --- | --- |
| Product READY FOR ARCHITECT 或符合复用条件 | 记录证据，进入 ARCHITECTURE |
| Architect READY FOR IMPLEMENTATION 或符合复用条件 | 记录方案，进入 CONTRACT 检查；该状态不代替 Database Design 完成 |
| Contract READY / 合法 NOT_REQUIRED | 启动必要实施分支 |
| Database READY FOR DATABASE IMPLEMENTATION | database_design = COMPLETE，放行 Backend |
| Backend / Frontend COMPLETE | 对应 implementation = COMPLETE |
| 所有必需实现完成 | Feature = IN_REVIEW，stage = TEST |
| Test READY FOR REVIEW | test = COMPLETE，stage = REVIEW |
| Test / Review 发现可修复实现缺陷 | 按 feature.md 返回对应角色，Feature = IN_PROGRESS；重置受影响实现、测试、Review 结果，保留旧证据但标明失效 |
| 阻塞或达到修复停止条件 | Feature = BLOCKED，保留失败阶段、问题和 next_action |
| Review 获批准 | MERGE 候选仅暂存协调器输出，按 Git Workflow 保持批准 HEAD 不变 |
| Merge 与最终状态提交成功 | DONE，清空执行检查点，重算依赖 |

并行时 current_stage 表示协调器正在等待的阶段，分支进度以 implementation 字段为准。API、方案或代码变化时重新检查影响范围，旧 COMPLETE 不自动沿用。

## 完成与输出

只有已批准范围内所有必需 Feature 完成、无阻塞完成目标的未决事项，才能准备项目 DONE；P2 是否必需由已批准计划决定。取消任务涉及范围变化时需用户确认。

每次结束输出项目状态、完成数/总数、当前 Feature/阶段、READY/阻塞项、最近结果、下一步和证据链接。不得将工作区尚未提交的 DONE 作为真实完成。
