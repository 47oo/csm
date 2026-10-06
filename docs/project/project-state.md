# 项目状态规范

`docs/project/project-plan.yaml` 是 CSM V3 一期计划与执行状态的唯一机器可读来源。Backlog / Dependency Map / Milestones 由 `scripts/render_project_views.py` 自动生成；不手工维护。空计划也可生成明确标注“尚未规划”的视图。Git 操作以 `git-workflow.md` 为准，批准以 `change-control.md` 为准。

## 1. Plan 结构

| 字段 | 含义 |
| --- | --- |
| `project.name / version` | 项目名称、V3 一期标识 |
| `project.requirements` | 当前 V3 需求路径及 revision |
| `project.plan_revision` | 计划内容版本；批准记录必须匹配 |
| `project.status` | DRAFT / ACCEPTED / IN_PROGRESS / DONE |
| `project.approval` | plan_revision、feature_ids、approved_by、approved_on、basis；未批准时字段为 null，feature_ids 为 [] |
| `project.acceptance` | 一期整体验收的 status（PENDING / BLOCKED / COMPLETE）及 evidence（仓库相对文件路径列表）；COMPLETE 需有实际跨功能验收依据 |
| `features` | 稳定 Feature ID 的条目列表，初始允许空列表但不可执行 |
| `decisions_required` | 决策 ID、来源、问题、状态、影响范围/Feature 与责任者；引用需求 §35，避免复制问题正文 |
| `pending_changes` | 未完成提案的 id、proposal、affects（ALL 或非空 Feature ID 列表） |
| `execution` | 执行授权与中断检查点，不替代 Feature 历史证据 |
| `planning_status` | 从项目与 Feature 重算的完整性、计数和列表 |

完整计划的每个 Feature 至少有 `id, title, kind, priority, milestone, scope, acceptance, requirements, depends_on, blocking_decisions, status`。id 使用 F 加数字；kind 使用 FEATURE / ENABLER；priority 使用 P0 / P1 / P2。requirements 为非空仓库相对文件路径列表，可加锚点；scope / acceptance 写范围与可观察完成条件。不按数据库/API/页面重复拆三个 Feature。

实施信息包括：

* `layers.database/backend/frontend`：boolean，Architecture 确定；未知不能用 false 代替。
* `api_required`：boolean，Architecture 确定是否需要 API Contract；database=true 时 backend 必须为 true，以承接 Migration 实现。
* `implementation.product/architecture/database/test_design/contract/backend/frontend/test/review`：PENDING / COMPLETE / BLOCKED / NOT_REQUIRED；database 表示设计阶段，实际 Migration 由 backend 承接。architecture=COMPLETE 表示 READY FOR DESIGN，最终设计签核仍在 CONTRACT 阶段核验。
* `not_required`：按 gate 名保存不适用理由；只允许 layers 中明确为 false 的 database/backend/frontend，以及 api_required=false 的 contract。Product、Architecture、Test Design、Test、Review 不能用 NOT_REQUIRED 绕过。
* `current_stage`：PRODUCT / ARCHITECTURE / DATABASE / TEST_DESIGN / CONTRACT / IMPLEMENTATION / TEST / REVIEW / MERGE；未开始、CANCELLED 及 DONE 为 YAML null。
* `last_result, next_action`：最近结果和可执行后续动作；DONE 的 next_action 为 null。
* `git.base_branch/branch/start_commit/head_commit/merge_commit`：语义完全遵循 Git Workflow，不虚构 SHA。
* `evidence`：按 gate 名保存非空仓库相对文件路径列表。每个 COMPLETE 都需对应 evidence，可加锚点；版本、批准者和覆盖范围写在被引用报告中，不能仅靠文件存在证明通过。DONE 的 Git 合并证据另记 git 字段。
* `cancellation_basis`：CANCELLED 的明确取消依据；不删除旧 Feature 条目。

例如 `evidence: {test_design: [docs/features/F001/test-report.md#test-design]}`。这是格式示例，不代表该文件已存在。CLI 检查实际文件存在且位于仓库内；纯内存 `validate()` 的文件检查由 root 参数启用。新增字段缺失时返回核对现有证据，不能自动补写批准或 COMPLETE。

Contract 的 READY / BLOCKED / NOT_REQUIRED 是专业交接状态，对应 implementation.contract 的 COMPLETE / BLOCKED / NOT_REQUIRED。其它角色完成词映射见 §3；不能把任意字符串直接写入 implementation。

## 2. 项目与 Feature 状态

项目：DRAFT 表示未批准；完整计划及有效批准后 ACCEPTED；开始已授权 Feature 后 IN_PROGRESS；全部范围交付、整体验收 COMPLETE 并保存真实最终状态提交后 DONE。已完成项目获批新 revision 和新增范围后回到 ACCEPTED。计划批准不自动触发执行。

| Feature 状态 | 使用条件 |
| --- | --- |
| DRAFT | 尚待定义或尚未纳入有效批准范围 |
| BLOCKED | 依赖未 DONE、阻塞决策、环境/Git/提案暂停或阶段失败；记录原因、责任者及 next_action |
| READY | 范围/验收齐备且获批，无阻塞决策/暂停，全部依赖已提交 DONE，尚未启动 |
| IN_PROGRESS | Preflight 后启动或合法恢复，保存当前阶段和执行目标 |
| IN_REVIEW | 测试放行且候选交付已提交，正式 Review 中 |
| DONE | 全部必要 Gate 通过、获批候选合并、最终状态提交成功；Review 批准本身不够 |
| CANCELLED | 有明确取消依据；不等于 DONE，不解锁依赖 |

未启动项在 DRAFT / BLOCKED / READY 间按事实重算；READY 启动后 IN_PROGRESS；测试放行进入 IN_REVIEW；缺陷退回 IN_PROGRESS 或按原因 BLOCKED；合法恢复保留检查点。DONE 不因新需求回退，以新 Feature 承接。

## 3. 阶段 Gate 与证据

| 阶段 | 放行证据 |
| --- | --- |
| PRODUCT | READY FOR ARCHITECT，需求已确认且无影响本 Feature 的 Blocking Questions |
| ARCHITECTURE | READY FOR DESIGN，架构方案/API 草案、layers、api_required 与验证策略明确；尚不放行编码 |
| DATABASE | 需要时 READY FOR DATABASE IMPLEMENTATION + Schema / Migration 设计版本；无需时 NOT_REQUIRED |
| TEST_DESIGN | TEST DESIGN READY，验收映射、边界/并发场景、环境与可验证性明确；不代表执行通过 |
| CONTRACT | Architect 核对 Database / Test Design 后 READY FOR IMPLEMENTATION；有 API 时 Contract READY，无需 API 时 NOT_REQUIRED + 理由，仍记录最终设计签核 |
| IMPLEMENTATION | 必需 Backend / Frontend COMPLETE，包含必要 Migration 实现与本地验证 |
| TEST | READY FOR REVIEW，独立测试实际执行、验收映射完整 |
| REVIEW | APPROVED 或 APPROVED WITH FOLLOW-UP，候选 HEAD / Base 固定、无必须修复项 |
| MERGE | Git Workflow 的 Merge Gate、真实 Merge SHA、最终状态提交成功 |

顺序为 PRODUCT → ARCHITECTURE → DATABASE / TEST_DESIGN → CONTRACT → IMPLEMENTATION → TEST → REVIEW → MERGE。DATABASE 与 TEST_DESIGN 可并行，其间 current_stage 记录当前协调关注阶段，分支结果分别记录于 implementation。二者完成后才能进入 CONTRACT；涉及已完成数据库设计变化时，Tester 重新核对测试设计。

Product / Architecture / Database / Test Design 复用及最多两轮修复只按 feature Prompt；复用记录同样需要证据和版本核验。缺陷修复或输入变化后把失效的下游结果标回 PENDING / BLOCKED，不能保留无效 COMPLETE。BLOCKED 检查点可以保留失败阶段和未完成输入，恢复前重新校验阶段前置条件。

## 4. 执行检查点

`execution` 至少包含 `mode, authorization, current_feature, current_stage, last_result, next_action, repair_rounds`。mode 为 SINGLE / CONTINUOUS 或尚未执行时 null。authorization 未授权为 null；存在时必须有 `plan_revision, feature_ids, authorized_by, authorized_on, basis`，记录真实用户指令，不能从计划批准推导。活动任务、阻塞中的执行检查点和显式 --feature 调度需要匹配当前 revision 的授权；SINGLE 只能有一个授权 Feature，CONTINUOUS 也使用明确 ID 列表。

repair_rounds 为 0..2 的整数。相同活动任务不得降低计数；用户明确恢复产生新的授权来源记录后才可重置，不能仅为重置预算改写文字。feature Prompt 的“同一必须修复问题仍存在”停止条件由缺陷记录人工核验。

最多一个 IN_PROGRESS / IN_REVIEW Feature。存在 current_feature 时，它必须是 IN_PROGRESS / IN_REVIEW / BLOCKED，execution.current_stage 与 Feature 一致。current_feature=null 时 current_stage 也为 null。允许唯一活动 Feature 缺失检查点作为恢复候选，但需核验后补齐，不能据此新建并行 Feature。

完成后清空当前目标/阶段与下一动作，保留历史证据；中断时保留失败阶段、进行中分支、实际结果和恢复动作。Merge 成功但状态提交失败，按 Git Workflow 恢复，不能调度下一项。

## 5. 统计、完整性与校验

`planning_status.status` 必须等于 project.status；`counts` 按全部七种 Feature 状态重算；`ready_features` 为 READY ID；`blocked_draft_features.BLOCKED / DRAFT` 与对应状态完全一致。

`plan_completeness` 为 incomplete / complete。complete 要求一期范围均有 Feature / 验收映射、真实无环依赖、明确未决项及其影响，并已生成一致的派生视图；不等于已批准。空骨架始终 incomplete，不可调度或 DONE。

协调器修改状态前保存本次 V3 Plan 快照到临时路径（如 `/tmp/csm-plan-before.yaml`），每次合法转换后用 `--previous` 比较，再将通过的结果作为下一次基线。不从旧版本分支读取输入。转换检查禁止跳过 READY→IN_PROGRESS→IN_REVIEW→DONE；BLOCKED/MERGE 的中断恢复可在证据核验后到 DONE；禁止重写 DONE 的范围、验收和交付证据。阶段回退按受影响 Gate 重新验证。

先生成派生结果，再校验（只有协调器执行写操作）：

```bash
python3 scripts/render_project_views.py --write
python3 scripts/validate_project_state.py --previous /tmp/csm-plan-before.yaml
```

生成器只更新 planning_status 的统计/列表和三个视图，不改 Feature 状态、完整性、批准或执行授权；重写 YAML 时可能规范化排版和注释。无 --write 时只检查陈旧结果，失败不写文件。首次尚无快照时记录原因，使用基础校验，不能假称验证过转换。

提交前及提交后核对：

```bash
python3 scripts/validate_project_state.py
python3 scripts/render_project_views.py
```

修改校验器/生成器时运行 `python3 -m unittest discover -s scripts -p 'test_*.py'`。调度指定 Feature 时另执行 `python3 scripts/validate_project_state.py --feature Fxxx`。依赖见 `scripts/requirements.txt`。脚本检查结构、Gate 前置条件、已记录结果与文件存在、授权元数据、统计及可选的快照转换；不会证明批准来源、Git SHA、报告内容或测试结果真实。协调器仍核对覆盖范围、专业签核与 Git / Test / Review。批准 HEAD 冻结期间只做只读检查，不生成/修改视图。
