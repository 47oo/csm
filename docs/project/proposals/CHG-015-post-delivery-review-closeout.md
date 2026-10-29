# CHG-015 交付后外部检查（R01–R10）处置与候选计划 revision 25（新增 F037–F045）

- **状态**：**待批准（PROPOSED / PENDING APPROVAL，不是 APPLIED）**。日期 2026-10-29。本文与 `docs/project/proposals/CHG-015-candidate-plan.yaml`、`docs/project/proposals/CHG-015-r04-requirements-revision-16-draft.md` 均为待批提案；用户批准并给出 AQ-1–AQ-7 裁定前，`docs/project/project-plan.yaml`（revision 24，`project.status=DONE`）保持为唯一执行基线，不改变任何 DONE 证据与执行授权。
- **候选计划**：`docs/project/proposals/CHG-015-candidate-plan.yaml`，`project.plan_revision=25`、`project.status=DRAFT`、`approval` 各字段为 null / `feature_ids=[]`；`project.acceptance.status` 由 COMPLETE 改为 **PENDING**（evidence 列表原样保留，另加 `basis` 说明其只覆盖 plan revision 24 范围）。
- **需求候选文本**：`docs/project/proposals/CHG-015-r04-requirements-revision-16-draft.md`（§28.1 + T127–T129 的 PROPOSED 草案，未写回需求正文；仅当 AQ-1=A/B 并经用户确认后落稿为 revision 16）。
- **来源**：`/tmp/csm-review-2026-10-29.md`（外部检查，基线 `main` HEAD `bcd6b32`，检查前后仓库 clean；R01–R10），以及 Architect 对本次候选范围的评估结论。
- **性质**：以「已确认契约符合性缺陷修复」+「非功能改进候选」+「流程 / 工具修正」为主。**不新增业务规则**，需求 revision 保持 15（AQ-1=A/B 时须由用户确认落稿 revision 16，见 §4 与草案文件）。

## 0. 推荐裁定组合（待用户一次确认）

| 决策 | 推荐 | 说明 |
| --- | --- | --- |
| AQ-1 | **A** | 仅 VM 表单 Host 选择 + Resource 创建页 Cluster 选择两处控件，并新增候选完整性验收（§28.1 + T127–T129，需求 revision 16） |
| AQ-2 | **A** | 仅实现侧有界解析，零可观察差异（同字节输入逐字一致） |
| AQ-3 | **A（已由既有契约确定）** | 解析阶段失败归入既有 422 `IMPORT_INVALID_FILE{reason:"unreadable"}`；`kind: DERIVED_FROM_CONFIRMED`，需用户在批准时确认该推导 |
| AQ-4 | **B** | 组件 / 逻辑级可重复入口，不引入浏览器二进制 |
| AQ-5 | **A** | 纳入 R10（F039）；R07（F040）机制见 AQ-6；R06（F042）转 backlog 不启动 |
| AQ-6 | **(i) 收敛依赖** | 仅把 `antd` / `tailwindcss` / `@tailwindcss/vite` 收敛为 `~` 并同步 lockfile，不改架构策略文档 |
| AQ-7 | **待用户裁定** | 模型配置策略（A/B/C）。不影响本期计划批准，仅影响 8 份 `.pi/agents/*.md` frontmatter |

## 1. 影响对象

| 对象 | 影响 |
| --- | --- |
| `docs/product/requirements-v3.md` | **本提案不修改（保持 revision 15）**。AQ-1=A/B 时另行落稿 revision 16（草案见 `CHG-015-r04-requirements-revision-16-draft.md`）。 |
| `docs/project/project-plan.yaml` | 候选 revision **24 → 25**：新增 F037–F045（9 项，ID 连续）、`decisions_required` 修订为 AQ-1–AQ-7；`features` 中 F001–F036 逐字保留（含 `git` / `evidence` / `scope` / `implementation`），DONE 历史不改写；`project.acceptance` 改 PENDING 且证据保留。 |
| `docs/api/F014.md` / `docs/api/F023.md` | 正文版本**不改**。F037 交付时在 §1.2 各加一条**不升版编辑性澄清附注**（先例 F035-RV-05），仅澄清解析阶段异常归入既有 `unreadable`。 |
| `docs/architecture/frontend-ui-stack.md` | **不改**。R07 是让 `frontend/package.json` 与该已批准策略对齐（AQ-6=(i)）；放宽为 `^` 属重大架构变更（AQ-6=(ii)），需用户批准。 |
| `docs/project/git-workflow.md` | R01：协调器直接维护（命令统一引用已确认交付线 `v3.4`）。**不建 Feature**。 |
| `docs/project/change-control.md` | R03：协调器直接维护（把一次性「本次用户授权」改为条件规则 + 带日期 / 对象版本的历史记录）。**不建 Feature**。 |
| `.pi/skills/frontend-ui/SKILL.md` | R08 的「验证命令去重」部分：协调器直接维护（同一类型检查不重复执行）。**不建 Feature**（已从 F043 范围移除）。 |
| `.pi/agents/*.md` | R09：受 AQ-7 约束；裁定后由协调器一行式维护 frontmatter，不建 Feature（F044 已 CANCELLED）。 |
| Schema / Migration / 权限矩阵 / 模板 | **不改**（见 §2）。 |

新增 / 变更 Feature（以候选计划条目为准）：

| ID | 标题 | kind | 优先级 | Milestone | depends_on | 状态 | api_required |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F037 | 导入解析异常统一收敛为 422 `IMPORT_INVALID_FILE`（R02） | FEATURE | P0 | M28 导入契约修复 | F014, F023, F034, F035 | DRAFT | **true**（§1.2 编辑性澄清附注） |
| F038 | 导入解压 / 解析内存边界加固（R05） | FEATURE | P1 | M29 导入解析加固 | F014, F023, F037 | DRAFT | false |
| F039 | Dashboard 容量查询批量化与查询计数基准（R10） | FEATURE | P2 | **M30 非功能改进** | F010, F013, F027 | DRAFT | false |
| F040 | 前端依赖版本范围与架构升级策略对齐（R07） | ENABLER | P1 | **M30 非功能改进** | — | DRAFT | false |
| F041 | 对象选择控件候选完整性（R04） | FEATURE | P1 | **M30 非功能改进** | F003, F004, F006 | DRAFT | false |
| F042 | 前端按页面边界懒加载（R06） | FEATURE | P2 | **M30 非功能改进** | F033 | DRAFT | false |
| F043 | 前端交互回归可重复入口（R08） | ENABLER | P2 | **M30 非功能改进** | — | DRAFT | false（`layers.frontend=false`，先例 F016） |
| F044 | Agent 模型配置与角色职责解耦（R09） | ENABLER | P2 | M30 非功能改进 | — | **CANCELLED** | false |
| F045 | CHG-015 变更集整体回归与部署等价验收 | FEATURE | P0 | M31 变更集整体回归与验收 | F037, F038, F039, F041, F043（AQ-6=(i) 时再补 F040） | DRAFT | false |

里程碑 `M30 前端与性能改进` 更名为 **`M30 非功能改进`**（F039–F044 全部同步）；M28 / M29 / M31 名称不变。

## 2. 不变项清单（本提案的显式边界）

1. **错误码与 `reason` 集合**：不新增 / 删除 / 重命名错误码；`IMPORT_INVALID_FILE.details.reason` 仍为 `unreadable` / `unsupported_format` / `header_missing` / `missing_columns` / `unknown_columns` / `column_order` / `empty_file`。
2. **上限数值**：5 MiB 字节上限、5000 数据行上限、错误预览 1000 行、`errors_truncated` 语义均不变；不新增「解压后字节数 / 列数」等可观察上限（AQ-2=A；B 情形须另立需求变更 + 契约升版）。
3. **权限矩阵与端点**：不新增权限项、角色、端点或查询参数；`IMPORT`、`DELETE_OBJECT`、`VIEW_DELETED`、`USER_ADMIN` 等口径不变。
4. **§20 容量公式**：可分配集合 / 可分配总量 / 已占用量 / 剩余可用量与 AUTO 池交集的算法、gateway 与 RESERVED 去重口径、负 `remaining` 语义均不变；F039 只改查询组织方式并保留 `ip_capacity.py` 的公式单点。
5. **模板**：F023 §6 冻结 26 列与 F014 的 BM 14 / VM 10 列模板不移、不改、不重排。
6. **CSV 解析行为**：不启用严格 CSV 引号规则（T114 等价性口径不变）、不调整 `csv.field_size_limit`、不新增字段边界错误判定。
7. **列表匹配语义**：各域列表 `q` 继续沿用既有 ILIKE 子串语义（F013 §1.4 / §6 冻结），不引入 pg_trgm；共享 `Select` 组件既有全局语义不变（新行为由候选控件或 opt-in props 承载）。
8. **Schema / Migration**：本变更集无新表、新列、新索引、新约束、新迁移；R02 / R05 为服务层实现，R10 若需索引另行 DATABASE Gate 签核。
9. **§23.2 集群范围过滤**：范围可见性、404 / 403 语义、导入行级归因、Dashboard 按范围重算、候选不泄露未授权集群规模等口径不变。
10. **F001–F036 的 DONE 判定、范围与证据**：不重写、不回填、不「当时已满足新要求」式改写；命中既有契约的偏差以新 Feature 承接（`change-control.md` §5）。
11. **执行基线**：`project-plan.yaml` 在批准前不被本提案覆盖；`execution.authorization` 不因候选计划产生新的实施授权。

## 3. R01–R10 处置

| ID | 分类 | 处置 | 承载 | 执行方式 |
| --- | --- | --- | --- | --- |
| R01（High） | PROCESS_OR_TOOLING | `docs/project/git-workflow.md` 的创建 / Review / Merge 命令统一引用已确认交付线 `v3.4`，Review 基线改用同一权威字段；新增「工作流文档与计划基线一致性检查」只读命令；不机械改写历史 SHA。**执行中另发现**：本地 `v3`、`v3.4` 同时存在同名**标签与分支**，`git rev-parse v3.4` 报 `ambiguous`，故比较类命令统一改为 `refs/heads/$DELIVERY_BRANCH` | — | **协调器直接维护**（不建 Feature） |
| R02（Medium） | IMPLEMENTATION_DEFECT | 四端点解析异常统一返回 422 `IMPORT_INVALID_FILE{reason:"unreadable"}`；补两条导入路径回归；F014 §1.2 / F023 v2 §1.2 加不升版编辑性澄清附注 | F037 | 按 Feature（PRODUCT → … → MERGE） |
| R03（Medium） | PROCESS_OR_TOOLING | `change-control.md` 的一次性授权改为条件规则，历史授权移入带日期与对象版本的记录，保留「已有明确授权不重复询问」 | — | **协调器直接维护**（不建 Feature） |
| R04 | REQUIREMENT_CHANGE | 待裁定 AQ-1；推荐 A（两处控件 + §28.1 / T127–T129）。裁定 A/B 需需求 revision 16 落稿后实施，C 转 backlog | F041 | 按 Feature；需求 revision 16 落稿由用户在批准时确认 |
| R05 | NON_FUNCTIONAL_IMPROVEMENT | 待裁定 AQ-2；推荐 A（仅实现侧有界解析，验收收敛为「内存峰值有界 + 同字节输入逐字一致 + 基准证据」） | F038 | 按 Feature |
| R06 | NON_FUNCTIONAL_IMPROVEMENT | AQ-5 推荐 A 时转 backlog，不启动（Feature 条目保留，不删除） | F042 | 按 Feature（本期不启动） |
| R07 | NFR + 架构符合性偏差 | 待裁定 AQ-6；推荐 (i)：仅收敛 `antd` / `tailwindcss` / `@tailwindcss/vite` 为 `~` 并同步 lockfile，不改架构策略文档 | F040 | 按 Feature |
| R08 | PROCESS_OR_TOOLING | 待裁定 AQ-4；推荐 B（组件 / 逻辑级可重复入口，不引入浏览器依赖）。**其中 Skill 命令去重不建 Feature** | F043（回归入口部分） | 两部分：回归入口按 Feature；Skill 命令去重 **协调器直接维护** |
| R09 | PROCESS_OR_TOOLING | 不构成 Feature：属用户模型配置意图（AQ-7）与协调器一行式 frontmatter 维护；扩展已实现「未声明 model 即继承协调器」 | F044（**CANCELLED**，条目与 ID 保留） | AQ-7 裁定后 **协调器直接维护** `.pi/agents/*.md` |
| R10 | NON_FUNCTIONAL_IMPROVEMENT | 本期待办（AQ-5=A）：先补查询计数与代表性规模基准，再批量加载保留池与占用统计，保留 `ip_capacity.py` 公式单点 | F039 | 按 Feature |
| G4 | BASELINE_ERRATA | 基线勘误：`docs/product/domain-model.md` revision 14 → **15**（当前需求基线的正确值；获批 revision 16 后再同步为 16）与「F001–F028」→「F001–F036」；`AGENTS.md` §1.1 与 requirements §36 的 F001–F028 → F001–F036、§36「T01–T99」→「T01–T126」；清理 `docs/project/project-plan.yaml` 末尾遗留的顶层键 `plan_revision: 22` | — | **协调器直接维护**（不建 Feature；属事实记录勘误，不改业务规则） |
| — | 变更集整体验收 | 各 Feature DONE 不等于变更集整体验收：跨功能回归 + 真实部署等价验证，并通过后恢复 `project.acceptance=COMPLETE` | F045 | 按 Feature |

## 4. 待裁定项（`decisions_required`）

| ID | 状态 | 关联 | 选项 | 推荐与理由 |
| --- | --- | --- | --- | --- |
| AQ-1 | PROPOSED | R04 / F041 | A=仅 VM Host + Resource Cluster 两控件并新增候选完整性验收；B=覆盖全部对象选择控件；C=不纳入本期（backlog） | **A**：现有截断提示与 F006 记录表明不是静默违约；范围收在创建路径最痛的两处，改动面与验收面可控 |
| AQ-2 | PROPOSED | R05 / F038 | A=仅实现侧有界解析；B=新增可观察上限（触发需求 revision 16 + 契约升版）；C=仅补基准与检查方法 | **A**：报告未测得真实内存崩溃；B 会新增业务可见规则并升版需求，与「不新增未确认规则」冲突 |
| AQ-3 | **CONFIRMED**（`DERIVED_FROM_CONFIRMED`） | R02 / F037 | A=文件级 `IMPORT_INVALID_FILE{reason:"unreadable"}`；B=行级字段长度错误（须另立变更） | **A**：由 `docs/api/F014.md` §1.2/§2/§7、`docs/api/F023.md` v2 §1.2 与 requirements revision 15 §24.5 + T114 追认必然确定，不新增业务规则；待用户在批准时确认该推导 |
| AQ-4 | PROPOSED | R08 / F043 | A=引入仓库内浏览器 E2E 依赖；B=组件 / 逻辑级可重复入口；C=仅 smoke 拆分 | **B**：可重复执行且不新增依赖与 CI 负担 |
| AQ-5 | PROPOSED | R06/R07/R10 | A=纳入 R10（F039）与 R07（F040，机制见 AQ-6），R06（F042）转 backlog；B=同时纳入 R06；C=均不纳入 | **A**：R07 是已批准架构策略的符合性偏差，R10 属可验证查询开销；R06 收益不确定 |
| AQ-6 | PROPOSED（`DESIGN_INPUT`） | R07 / F040 | (i) 收敛依赖声明范围；(ii) 修改架构策略放宽为 `^`（重大架构变更，需批准）；(iii) 记录例外并登记技术债（须写复审触发条件） | **(i)**：与既有策略一致、零架构变更、回归面最小 |
| AQ-7 | OPEN | R09 | A=保持 8 份文件固定模型（现状）；B=删除 `model:` 改为继承协调器（扩展零改动）；C=增加环境变量覆盖（需扩展改动 + 新测试） | 未给推荐：属用户模型配置意图，不阻塞本期计划批准 |

需求 revision 16 草案（仅在 AQ-1=A/B 且用户确认后落稿）：`docs/project/proposals/CHG-015-r04-requirements-revision-16-draft.md`（§28.1 + T127–T129 + §35.1 确认行 + §32 追加句 + 索引同步清单；AQ-1=C 时整体废弃，需求零 diff）。

## 5. dispatch 依据与历史保护

- 本次是**外部检查报告触发的交付后修复 / 改进**，不是重开一期范围：需求 revision 15 →（若 AQ-1=A）16；plan revision 24 → 25；F001–F036 全部 DONE 的证据、`git` 字段、`scope` / `acceptance` 逐字不改写。
- 已 DONE 的 F014 / F023 / F034 / F035 **不受影响**（不回退、不重开、不改证据）；其交付行为中与冻结契约不符的解析异常逃逸由 **F037** 承接修正，内存边界加固由 **F038** 承接。
- `project.acceptance`：`status` 改为 `PENDING`，原 `evidence` 列表**原样保留**，新增 `basis` 说明「上述证据覆盖 plan revision 24（F001–F036）范围；新增 F037–F045 交付后需由 F045 整体回归补充，方可恢复 COMPLETE」（不伪造路径、不删除既有锚点）。
- 候选计划中的 F037–F045 为 DRAFT、F044 为 CANCELLED（含 `cancellation_basis`）；所有 DRAFT 条目的 `implementation` 为 PENDING，`git` 全为 null，`evidence` 为空——不声称任何实施结果。

## 6. 待批准清单（用户需一次给出）

1. **是否批准 plan revision 25** 及其中 Feature 范围（F037–F043、F045 纳入；F044 CANCELLED；里程碑 M30 更名）。
2. **AQ-1 / AQ-2 / AQ-4 / AQ-5 / AQ-6** 各选项（推荐：A / A / B / A / (i)）。
3. **是否确认 AQ-3 的既有契约推导**（422 `IMPORT_INVALID_FILE{reason:"unreadable"}`，`kind: DERIVED_FROM_CONFIRMED`）。
4. **是否批准需求 revision 16 落稿**（仅当 AQ-1=A 或 B；草案见 `CHG-015-r04-requirements-revision-16-draft.md`）。
5. **AQ-7 模型配置策略**（A/B/C；可延后，不阻塞批准，仅影响 8 份 agent 文件）。

## 7. 角色输入与后续步骤

1. **协调器（先行、只读核对后直接维护文档）**：§3 表中「协调器直接维护」各项（R01、R03、Skill 命令去重、G4 基线勘误、`project-plan.yaml` 末尾遗留 `plan_revision: 22` 顶层键清理）；将 CHG-015 登记到 `pending_changes`（`affects: ALL`）并暂停受影响调度；运行 `python3 scripts/validate_project_state.py --plan docs/project/proposals/CHG-015-candidate-plan.yaml --root .`、`python3 scripts/render_project_views.py --write` 与 `python3 scripts/validate_project_state.py` 复核（派生视图与 `planning_status` 由脚本重算，本提案中的统计为临时值）。
2. **Architect（轻量、非 Feature 设计）**：AQ-6=(i) 的依赖范围核对（仅三个依赖，antd 6.6.x / Tailwind 4.3.x 内）与 F037 编辑性澄清附注的范围确认；F037 / F038 / F039 / F041 / F043 的正式设计仍在各自 ARCHITECTURE / CONTRACT Gate 完成。
3. **Database（必要时）**：确认 R02 / R05 无 DDL；若 R10 需新索引，按 DATABASE Gate 单独签核。
4. **用户**：按 §6 一次给出批准与裁定。批准后由协调器同步计划、需求（如需升版）、派生视图，并重新验证受影响 Gate；执行授权必须另行明确，不能从计划批准推导。
5. **若裁定为 backlog 的项**：由协调器将对应 Feature 置 CANCELLED 或以 `change-control.md` 记录不纳入依据，不删除条目、不改写 DONE 证据。

## 8. 明确声明

- 本提案与候选计划、需求草案**均未获批**，**不改变执行基线**：`project-plan.yaml`（revision 24 / `DONE`）、`execution.authorization`、F001–F036 的提交 / 测试 / Review 证据保持原样。
- 报告中的「推荐」为规划建议，**不是已确认决策**；AQ-1 / AQ-2 / AQ-4 / AQ-5 / AQ-6 为 `PROPOSED`，AQ-7 为 `OPEN`，不得据推荐项直接实施。唯一例外是 AQ-3：其结论由既有 CONFIRMED 契约与需求条款推导（`DERIVED_FROM_CONFIRMED`），仍待用户在批准时确认该推导。
- 本提案不声称 R01–R10 中任何一项已完成修复：除已在 §3 明确写出「协调器直接维护」的流程 / 工具 / 勘误项外（由协调器执行并在执行后记录），其余结论仍是待实施状态。
- `project.acceptance` 改为 `PENDING` 不是验收失败回溯，而是如实反映「新增范围尚未并入整体验收证据链」；F001–F036 的既有验收结论与证据不变。

## 9. 协调器已执行（2026-10-29，未提交）

以下为本次在本工作区完成、**尚未提交**的可审阅修改（提交范围与时点待用户批准后按 Git Workflow 处理）：

| 文件 | 改动 | 对应项 |
| --- | --- | --- |
| `docs/project/git-workflow.md` | 交付分支解析为 `$DELIVERY_BRANCH`（当前 `v3.4`）；创建 / Review / Merge / 中断恢复 / 提案分支全部改引用该变量；比较类命令使用 `refs/heads/$DELIVERY_BRANCH`（同名 tag 导致 ambiguous）；新增 §4 一致性检查命令与判定规则 | R01 |
| `docs/project/change-control.md` | §3 一次性「本次用户授权」改为条件规则（当前指令或可定位授权，不跨任务继承），历史授权移入带日期的记录表 | R03 |
| `.pi/skills/frontend-ui/SKILL.md` | 验证段按影响选择 `typecheck` / `build` / `smoke:client`（不再默认重复类型检查），并要求交互回归有可重复入口、浏览器专项如实标记未入库 | R08（命令去重部分） |
| `docs/product/domain-model.md` | 依据 revision 14 → 15（当前基线）；「F001–F028 已交付」→「F001–F036」（plan revision 24） | G4 |
| `AGENTS.md` §1.1 | 当前状态改为 F001–F036 / `v3.4` / `main` / 需求 revision 15 / plan revision 24 | G4 |
| `docs/product/requirements-v3.md` §36 | 「F001–F028 已交付并合入 `v3.2`」→「F001–F036 已交付并合入 `v3.4`」；「T01–T99」→「T01–T126」。仅状态记录段，§1–§35 业务规则零改动 | G4 |
| `docs/project/project-plan.yaml` | 清理末尾遗留顶层键 `plan_revision: 22`（与 `project.plan_revision: 24` 冲突的陈旧重复）；登记 `pending_changes: [{id: CHG-015, proposal: …, affects: ALL}]` | G4 + §4.2 暂停登记 |

验证（实际执行，本工作区）：

```text
python3 scripts/validate_project_state.py                                    -> PROJECT STATE VALID
python3 scripts/render_project_views.py                                      -> PROJECT VIEWS VALID (无统计变化)
python3 scripts/validate_project_state.py --previous /tmp/csm-plan-before.yaml -> PROJECT STATE VALID
python3 scripts/validate_project_state.py --plan docs/project/proposals/CHG-015-candidate-plan.yaml --root . -> PROJECT STATE VALID
```

未验证：未运行后端 pytest、前端 typecheck / build / smoke（本次无代码改动）；未提交、未切分支、未 push；未执行 R01–R10 的实质修复（除上表流程 / 文档 / 勘误项）。
