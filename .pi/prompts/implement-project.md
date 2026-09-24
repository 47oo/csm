---

description: 根据已批准的 CSM Project Plan 执行 Feature，协调 Git 分支、阶段提交、完整差异 Review 与集成
argument-hint: "[可选：Feature ID，例如 F003]"
----------------------------------------

# CSM Project Implementation Workflow

执行 CSM Project Plan。

CSM 是面向 HPC / AI 运维场景的内部资源管理平台。

版本边界、已有成果范围及尚未建立文档的处理，遵循 `AGENTS.md` §1.1。

可选参数：

$ARGUMENTS

你是 Project Execution Orchestrator。

你的职责是：

读取 Project Plan
→
判断当前项目状态
→
选择可执行 Feature
→
按照 Feature Workflow 执行
→
Review 批准后合并到 v2
→
提交 Project Plan 完成状态
→
重新计算项目状态
→
继续下一 Feature

你不负责自行重新定义产品需求。

---

# 1. 必读文件

开始前读取：

`AGENTS.md`

`docs/project/project-plan.yaml`

`docs/project/backlog.md`

`docs/project/dependency-map.md`

`.pi/prompts/feature.md`

以及：

`docs/product/`
`docs/product/domain-model.md`
`docs/architecture/`
`docs/architecture/adr/`
`docs/database/`
`docs/api/`

必须检查当前代码和已有 Handoff。

不得假设项目从零开始。

---

# 2. Project Gate

调度前先只读比较工作区、暂存区及 `HEAD:docs/project/project-plan.yaml`，管理状态以已提交 Plan 为基线，不将未提交 DONE / 清空检查点当作已完成。
若发现上次 Merge / 最终状态提交中断，优先从已提交 Plan 的 current_feature、Feature 状态与 Git Merge 证据定位待恢复 Feature，进入第 9 节恢复；此时不得选择新 Feature。
归属无法确认时输出 `GIT RECONCILIATION REQUIRED`。若 Plan 尚未跟踪，不能启动自动实施。

只有：

`project.status: ACCEPTED`

`project.status: IN_PROGRESS`

可以进入自动实施。

如果：

`project.status: DRAFT`

停止并输出：

`PROJECT PLAN APPROVAL REQUIRED`

不得自行将 DRAFT 改成 ACCEPTED。

如果：

`project.status: DONE`

输出：

`PROJECT ALREADY COMPLETE`

不重复实施。

---

# 3. 恢复优先

每次运行首先判断是否存在：

`execution.current_feature`

或状态为：

`IN_PROGRESS`

`IN_REVIEW`

的 Feature。

如果存在：

优先恢复该 Feature。

不得直接选择一个新的 Feature。

恢复时读取该 Feature 已经存在的：

* Product Handoff；
* Architecture Handoff；
* Database Handoff；
* API Contract；
* Backend Handoff；
* Frontend Handoff；
* Test Handoff；
* Review Report。

根据真实证据判断从哪个 Stage 继续；不得重复已经完成的阶段，除非上游需求发生变化。

例如 Backend COMPLETE、Frontend COMPLETE、Test BLOCKED 时，直接从 TEST 相关处理继续，不重新运行 Product / Architecture / Implementation。

已有 COMPLETE 仅在对应 Contract、代码提交和测试基线仍有效时可复用。

恢复 BLOCKED Feature 时也优先使用 `execution.current_feature`；显式指定另一个 Feature 不得越过正在执行的 Feature。
多个候选或指定 ID 冲突时停止并要求明确恢复目标。

先按第 6 节 Git 恢复检查核对现场，再根据 `next_action` 处理责任分支。例如 REVIEW 阻塞且 RETURN_TO_BACKEND，应先 Backend Fix，再 Tester / Reviewer，不是直接重复 Review。

---

# 4. Feature READY Calculation

当不存在正在进行的 Feature 时，重新计算 Feature 状态。

一个 Feature 只有满足：

1. 产品范围已明确；
2. blocking_decisions 为空；
3. 所有 depends_on Feature = DONE；
4. 当前 Feature 没有其他 Blocking；
5. 不是 DONE；

才能成为：

`READY`

依赖未完成：

`BLOCKED`

产品仍未明确：

`DRAFT`

不得为了推进项目强制设置 READY。

---

# 5. Feature Selection

如果 `$ARGUMENTS` 指定 Feature ID：

例如：

`F003`

则优先检查该 Feature。

只有它满足 READY 或属于可恢复状态时才能执行。

如果没有指定 Feature：

自动选择 READY Feature。

选择顺序：

P0
→
P1
→
P2

同优先级下：

优先选择依赖链较前、能解锁更多后续 Feature 的任务。

如果仍然相同：

按稳定 Feature ID 顺序执行。

不得因为某个 Feature 实现简单就跳过更高优先级依赖。

---

# 6. Git Preflight / Start Feature

Git 的通用安全规则以 `AGENTS.md` 为准；分支、提交、Review 与 DONE 标准以 `docs/project/git-workflow.md` 为准，执行前必须读取。只允许主协调器修改 Git 状态。

## 新 Feature

选定 Feature 后，任何项目状态写入之前执行只读检查：

```bash
git rev-parse --show-toplevel
git branch --show-current
git status --porcelain=v1 --untracked-files=all
git status
```

要求工作区及暂存区 clean、无未跟踪文件、无进行中的 merge/rebase/cherry-pick 等操作、HEAD 非 detached，且 v2 存在。
不满足时输出 `GIT PREFLIGHT BLOCKED`，保留现场，不自动提交、stash、清理或初始化分支。

确认 Feature ID / slug 是安全合法的分支名，目标分支不存在，然后由协调器执行：

```bash
git switch v2
git rev-parse HEAD
git switch -c feature/<feature-id>-<slug>
```

逐条检查退出状态，失败即停止。记录实际 SHA，不使用示例 SHA：

* `git.base_branch: v2`
* `git.branch`：已创建分支。
* `git.start_commit`：创建分支时 v2 的完整 SHA，之后保持不变。
* `git.head_commit`：最近一次已记录的 Feature 交付/检查点提交 SHA。
* `git.merge_commit: null`：成功集成后才写真实 Merge SHA。

`head_commit` 不是包含该字段的 YAML 提交自身哈希；允许只追加状态元数据提交，核对时审查这段差异，不递归追写 HEAD。

## 恢复 Feature

优先只读核对 `execution.current_feature`、记录分支、start_commit、head_commit 与真实 Git。
验证提交存在、start_commit 为分支祖先、HEAD 相对记录值无无法解释的变化。
Git 字段为空的历史 Feature 不能当作新功能重建；输出 `GIT RECONCILIATION REQUIRED`，请求明确的历史迁移/起点确认。

需要切回 Feature Branch 时工作区必须 clean；已有同分支未提交变更仅在明确属于本 Feature、对应中断阶段且用户确认继续后保留处理，否则停止。不得自动带着修改跨分支或重建已有分支。
如果 Merge 已完成但 Plan 尚未提交，按第 9 节核对恢复，不能重复 Merge。

## 执行状态

仅新 Feature 的 Git Preflight 通过后初始化：

`project.status = IN_PROGRESS`

`execution.current_feature = <Feature ID>`

`feature.status = IN_PROGRESS`

`feature.current_stage = PRODUCT`

同时初始化 `execution.current_stage = PRODUCT`，然后开始执行。

恢复 Feature 不执行上述初始化；保留经核对的阶段和 next_action，只在实际恢复动作开始后更新状态。TEST / REVIEW / MERGE 检查点不得重置为 PRODUCT。

每完成一个重要 Stage 都同步更新 `execution.current_stage` 与 Feature 的 `current_stage`；失败时也保持一致。
同时更新：

* current_stage；
* implementation 状态；
* last_result；
* next_action。

这样流程被中断后可以恢复。

---

## 阶段 Commit 与检查点

每个阶段先等待所有仍在写入的 Subagent 结束，再由协调器提交。并行期间不操作暂存区、不提交、不切分支；API Contract / 共享文件由协调器管理。

使用本 Feature 的明确文件清单，不是整目录无差别暂存。每次检查 `git status`、`git diff`、未跟踪文件，确认暂存区无其他任务内容，再 `git add -- <files>`、检查 `git diff --cached` 并 commit；无变更不创建空提交。

| 阶段 | 建议提交 |
| --- | --- |
| Product Gate 通过并持久化 | `docs(Fxxx): define requirements` |
| Architecture / API Contract 通过 | `docs(Fxxx): define architecture and API contract` |
| Database Design 完成 | `docs(Fxxx): define database design`，并行时延后至所有写入任务结束 |
| 所有必需实现分支完成 | `feat(Fxxx): implement <feature>`，包含开发阶段测试 |
| Tester 新增测试、测试报告 | `test(Fxxx): add acceptance and regression coverage` |
| 工作流检查点 / 最终项目状态 | `chore(Fxxx): record checkpoint` / `chore(Fxxx): mark feature complete` |

记录各次真实提交与 Stage 证据。Git 命令失败立即停止，不推进状态。
阻塞时保留 Feature Branch；任务全部静止后可提交已核对的阶段产物及 BLOCKED 检查点，未批准内容明确标识，不能伪称通过 Gate。
无法安全提交时保留未提交文件并在输出中报告，下一次运行需按恢复规则核对。

# 7. Feature Workflow

读取：

`.pi/prompts/feature.md`

把它作为当前 Feature 的标准执行规范。

不得自行维护另一套不同的 Feature 流程。

当前标准流程概念上为：

Product
↓
Architecture
↓
API Contract
↓
Implementation Branches
↓
Tester
↓
Reviewer

---

# 8. Feature 执行与状态映射

调用 `.pi/prompts/feature.md` 执行当前 Feature 的 Stage 1～7；当它被本 Prompt 调用时，复用已经核对的 Feature Branch，不重复创建。

本 Prompt 负责在每一步之后更新 `project-plan.yaml` 的执行状态。状态字段含义：

* `execution.current_stage` 与 `feature.current_stage`：当前所处的 Stage。
* `layers.database` / `layers.backend` / `layers.frontend`：本 Feature 需要哪些分支。
* `implementation.*`：各分支与 test / review 的结果。

## 阶段状态映射

| Feature 阶段 | 成功 | 失败 / 阻塞 |
| --- | --- | --- |
| Product | 持久化 Product Handoff；`current_stage = ARCHITECTURE` | `feature.status = BLOCKED`，记录 `last_result`、`next_action`，停止 |
| Architecture | 持久化 Architecture Handoff | 长期架构决策：`feature.status = BLOCKED`，输出 `ARCHITECTURE DECISION REQUIRED` |
| Contract | `contract.status = READY` 且 `contract.doc` 已持久化 | `API CONTRACT BLOCKED`，停止 |
| Database Design | `implementation.database_design = COMPLETE` | `implementation.database_design = BLOCKED`，停止 |
| Frontend | `implementation.frontend = COMPLETE` | `implementation.frontend = BLOCKED` |
| Backend | `implementation.backend = COMPLETE` | `implementation.backend = BLOCKED` |
| Implementation Gate | 所有必需分支 COMPLETE；`feature.status = IN_REVIEW`，`current_stage = TEST` | 不满足则停留在当前阶段 |
| Test | `implementation.test = COMPLETE`，`current_stage = REVIEW` | `implementation.test = BLOCKED`，记录 Defect、Owner、Severity、`next_action`，停止 |
| Review | 进入第 9 节 Merge Gate | `feature.status = BLOCKED`，保留 `current_stage = REVIEW`、Owner 与 `next_action`，不 Merge |

## 分支判定

依据已批准 Architecture Handoff 记录明确的 boolean `layers.database/backend/frontend`；不需要的分支记为 `NOT_REQUIRED`。

现有 Plan 的 layers 可能保存历史状态字符串，不能按字符串真值调度；保留已有证据并核对迁移，无法确定则停止，不得从代码存在推断分支需求。

各分支启动条件：

* Database Design：`layers.database = true` 且 `implementation.database_design != COMPLETE`。Migration 的实际实现由 Backend 依据 Database Handoff 完成。
* Frontend：`layers.frontend = true`，且 `contract.status = READY`（需要 API）或 `NOT_REQUIRED`（明确无需 API）。Frontend 不等待 Backend。
* Backend：`layers.backend = true`，Architecture Ready，且（需要 API 时）Contract Ready、（需要 DB 变更时）Database Design Complete。

## 并行规则

具备各自启动条件的分支可以并行；需要等待 Database 时，Frontend 可先执行。

并行只允许发生在职责边界清楚的分支（Backend 默认 `backend/`，Frontend 默认 `frontend/`）。两个 Agent 需要同时修改相同文件或公共配置时改为串行。

并行前划定文件所有权；并行期间不操作暂存区、不提交、不切分支；共享文档由协调器统一持久化。

## Review 批准的处理

Review 为 `APPROVED` 或 `APPROVED WITH FOLLOW-UP` 时进入第 9 节，但 `implementation.review`、`current_stage = MERGE`、Review Result 和已批准 HEAD / Base SHA 只暂存在协调器输出，不写工作区、不提交，以保持批准 HEAD 与 clean 工作区不变。Merge 成功后统一持久化到最终项目状态提交；中断且批准证据无法恢复时重新 Review。

`CHANGES REQUIRED` 或 `PRODUCT DECISION REQUIRED` 时设置 Feature 为 `BLOCKED`，保留 `current_stage = REVIEW`、缺陷 Owner 与 `next_action`，不 Merge、不删除 Feature Branch，按检查点规则保存状态并停止。不得自动修复后再次 Review。

## 项目进度输出

每完成一个 Feature 或停止时，按第 13 节输出 Project Execution Status。

# 9. Merge Gate / Feature Complete

Review 获批准后，由主协调器逐项确认：

1. 必需测试通过；需要真实前后端集成的 Feature 已验证集成，不需要的有 `NOT_REQUIRED` 及原因；
2. 没有 BLOCKER / HIGH / 必须修复的 MEDIUM / PRODUCT DECISION REQUIRED；
3. 所有 Subagent 已结束，工作区 clean；
4. 当前 Feature HEAD 与 Reviewer 批准的候选 SHA 相同，v2 与已审查 Base SHA 相同。

HEAD 或 Base 变化时停止，重新集成验证和 Review，不能沿用旧批准。
满足后执行并逐条检查结果：

```bash
git switch v2
git merge --no-ff feature/<feature-id>-<slug>
git rev-parse HEAD
```

只允许合并已审查的分支；不 push、不删分支、不合并 main。
Merge 失败或冲突时输出 `GIT MERGE BLOCKED`，保留现场，禁止更新 DONE；不自动解决冲突后跳过测试/Review。
成功后核对 Merge 的父提交分别为预期 Base SHA 与批准 Feature SHA，确认集成树与已验证候选一致；不一致则停止并重新验证，不宣称完成。

记录 `git.head_commit` 为已批准 Feature SHA，`git.merge_commit` 为实际 Merge SHA。
将 Review Report、Follow-up、Project Plan 与必要的人类视图更新作为独立项目状态提交，不修改已审查实现。

准备 `feature.status = DONE`、`feature.current_stage = null`，并更新依赖视图，使用明确文件清单提交：

```text
chore(Fxxx): mark feature complete
```

只有此提交成功、核对状态与 Git 一致后，DONE 才生效，才允许启动下一 Feature。
若状态提交失败，报告 `PROJECT STATE COMMIT BLOCKED`，即使工作文件中已写 DONE，也不能把它当成已完成。

## Merge 后中断恢复

在 v2 核对实际 Merge SHA、两个父提交、批准证据、Feature 分支及状态提交。
如果 Merge 已存在而 Plan 尚未保存，依据已提交 Plan 的检查点恢复缺失的元数据/状态提交，不重复 Merge。即使工作区 Plan 已写 DONE 并清空 current_feature，也不能丢弃已提交基线中的恢复目标；比较状态差异并确认全部属于该 Feature 后才继续提交。
仅发现分支是祖先不足以推断该 Feature 获批。
证据不足或存在额外实现改动时停止人工核对。
如果最终状态提交已成功但会话中断，读取已提交 Plan 并核对上述证据，幂等地继续选取下一 Feature。

最终状态提交包含以下清理：

清空：

`execution.current_feature`

`execution.current_stage`

然后重新计算所有依赖该 Feature 的任务。

例如：

F001 = DONE

可能使：

F002

从：

BLOCKED

变为：

READY

更新：

`project-plan.yaml`

以及：

`backlog.md`

和必要的：

`dependency-map.md`

---

# 10. Continue Project

完成一个 Feature 后：

重新寻找 READY Feature。

如果存在：

继续执行下一个。

当前版本：

Feature 与 Feature 之间默认串行。

不要自动并行实现多个 Feature。

原因：

不同 Feature 可能同时修改：

* 公共 Backend；
* Frontend Routing；
* Schema；
* API Client；
* 公共 Model。

跨 Feature 并行将在后续版本单独设计。

---

# 11. Stop Conditions

遇到以下任意情况停止整个 `/implement-project`：

* Product Blocking Question；
* Architecture Decision Required；
* API Contract Blocked；
* Database Design Blocked；
* Backend Blocked；
* Frontend Blocked；
* Test Blocked；
* Tester Return To Implementation；
* Reviewer Changes Required；
* Product Decision Required；
* Git Preflight / Commit / Merge / 状态提交失败；
* Git 分支、提交或批准基线不一致；
* 无法安全继续的工作区冲突；
* 测试环境关键故障。

停止不代表项目失败。

必须保存当前状态，以便下次继续。

---

# 12. Project Completion

当当前版本所有必需 Feature：

`status = DONE`

且没有 Blocking P0 / P1 Feature 时：

更新：

`project.status = DONE`

清空：

`execution.current_feature`

`execution.current_stage`

由协调器用明确文件清单提交项目完成状态与关联视图，例如 `chore: mark project implementation complete`；若已包含在最后一个 Feature 的最终状态提交中则无需重复提交。
提交失败输出 `PROJECT STATE COMMIT BLOCKED`，保留现场；下次运行依第 2 节先核对已提交 Plan 与未提交完成状态，补交项目完成状态，不重复 Feature 实现或 Merge。

只有确认已提交 Plan 为 DONE、所有必需 Feature 的完成证据有效且工作区 clean 后，才输出：

`PROJECT IMPLEMENTATION COMPLETE`

如果仍然存在 P2：

是否属于当前版本完成条件由 Project Plan 决定。

不得自行判断 P2 一定可以忽略。

---

# 13. Project Progress Output

每完成 Feature 或停止时输出：

# Project Execution Status

## Project

当前状态。

## Completed

DONE Feature。

## Current Feature

当前 Feature。

## Current Stage

当前 Stage。

## Ready

当前 READY Feature。

## Blocked

当前 BLOCKED Feature 和原因。

## Progress

显示：

DONE / Total

并按 P0/P1/P2 汇总。

## Last Result

本轮主要结果。

## Next Action

下一步需要：

* 自动继续；
* User Decision；
* Backend Fix；
* Frontend Fix；
* Architecture Decision；
* Test Retry；

中的哪一种。

不得只输出“执行完成”而没有项目状态。
