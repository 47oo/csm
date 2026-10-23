# F030 Review 跟进收敛：Contract 签核、边界测试与前端交互修正 — Product

- Feature：F030（ENABLER，P2，M21 Review 跟进收敛）
- 状态：READY FOR ARCHITECT
- 需求依据：`docs/product/requirements-v3.md` revision 11 §23.2（CONFIRMED）、§27、§28、§31（T85–T99）、§32、§35.1（revision 11 确认记录）、§35.2（BQ01–BQ17 CONFIRMED；BQ18/BQ19 DESIGN_INPUT）、§35.3（D01–D03 已签核）
- 批准依据：`docs/project/project-plan.yaml` plan_revision 16；`project.approval`（用户，2026-10-23，feature_ids 含 F030）；`execution.authorization`（plan_revision 16 / SINGLE / F030）
- 依赖：F026、F027、F029（均 DONE）
- 上游依据：`docs/features/F029/review-report.md`（APPROVED WITH FOLLOW-UP，RV-01…RV-11、Follow-ups 1–7）、`docs/features/F029/implementation.md`、`docs/features/F029/test-report.md`、`docs/features/F026/product.md`、`docs/features/F027/product.md`、`docs/api/F026.md` v2、`docs/api/F027.md` v1

## 1. 目标与边界

F030 收敛 F029 Review 的非阻塞跟进项与遗留专业设计输入，使 Contract 签核可追溯、边界与并发测试补全、前端授权交互不再产生误导性中间态。

**本 Feature 不改变任何已确认业务行为。** 不新增对象、关系、状态、唯一性、生命周期、权限项、错误码或错误顺序；不改变 §23.2 的授权、范围、可见性与 Audit 语义；不改变已批准端点、参数、Schema 或 Migration；不重开 F026–F029 已交付范围。

**本次未涉及（不等于永久排除）**：批量授予/撤销、每用户授权数量上限、授权到期时间、自定义角色/策略引擎、API Key 级 scope-down、范围缓存或物化。若后续需要，按 `docs/project/change-control.md` 单独裁定。

## 2. 已确认规则（引用，不复制正文）

- 授权粒度、有效权限公式、ADMIN 例外、默认拒绝、读写同受限、未授权对象 404 不泄露：requirements §23.2。
- 授权管理仅 USER_ADMIN；授予/撤销 Audit；撤销保留历史：§23.2 + `docs/api/F026.md` §6/§7。
- 错误顺序 401 → 403 → 422 → 404 → 409；路径对象优先（P-1）；重复授予 409 `already_granted`、撤销已撤销 409 `already_revoked`：`docs/api/F026.md` §1/§4/§5。
- 列表分页/排序/过滤默认值与 `q` 规则：`docs/api/F026.md` §3、D-7/D-8。
- 范围语义与不泄露约束：`docs/api/F027.md` §1–§4。
- 前端不静默成功、候选不含 ADMIN 与已软删 Cluster：`docs/features/F026/product.md` A10/A11；模态确认与加载态守卫：§28。
- 测试必须真实执行、不把预期写成 PASS：§31、§32。

## 3. 不新增规则声明

F030 全部工作属以下四类之一，任何一类都不得顺带改变业务行为：

1. **批准/签核记载**（change-control §2）：批准者、日期、版本、覆盖范围、确认来源。
2. **专业设计输入签核**（requirements §35.2/§35.3）：CHG010-BQ18（Architect/Database）、CHG010-BQ19（Architect/Backend），在既有已签核设计边界内收敛，不提交用户裁定。
3. **测试与测试规范**：断言既有语义，提升回归保护。
4. **文档/注释与前端交互**：说明既有行为，消除误导性中间态。

**边界守卫**：
- 「非唯一完整性错误 → 500 `INTERNAL_ERROR`」只能作为**现状语义记录**写入 Contract；若要改判为 409/422 或调整错误顺序，属已确认错误语义变更，须回 Product/用户按变更控制处理，不得作为文档修正实施。
- 为解决超大授权量而新增端点、查询参数或批量操作，属计划范围扩展，须先经 Product/协调器裁定。
- 前端若采用候选上限，必须显式提示，不得把不完整候选呈现为完整；服务端唯一约束与 409 始终是最终事实且必须如实呈现。

## 4. 范围（对应 plan scope ①–⑦）

| # | 内容 | 层次 |
| --- | --- | --- |
| ① | 补 `docs/api/F026.md` v2 与 F002/F003/F004/F007–F014/F023 域 Contract 追加章节的签核者/日期/版本/覆盖范围记载 | 文档/批准记录 |
| ② | 收敛 CHG010-BQ18（Architect/Database）、BQ19（Architect/Backend）并记录签核依据；仅更新计划 decision 状态与 basis | 专业设计签核 |
| ③ | 补 `q` 边界断言：已知用户 `q=""`/控制字符 → 422；未知用户 + `q=""` → 404（P-1 顺序）；未知用户 + 未声明查询参数 → 422 | 测试 |
| ④ | 补 F026 授予真并发（201 + 409，最终 1 条 ACTIVE、1 条 Audit）与非唯一完整性错误原样抛出的可重复用例 | 测试 |
| ⑤ | 前端候选加载期间门控提交或提示、加载失败显式可重试；超大 ACTIVE 授权量下的排除完整性有明确结论 | 前端交互 |
| ⑥ | 修正 `list_authorizations` 注释（依 P-1 路径对象优先）；`docs/api/F026.md` 记录非唯一完整性错误语义 | 文档/注释 |
| ⑦ | 显式声明集成测试默认 legacy unrestricted、真实 scope 必须使用 `real_scope` marker，并有机制约束 | 测试规范 |

## 5. 验收标准（待执行，不得预设 PASS）

- **P1 Contract 签核完整**：`docs/api/F026.md` 与 12 份域 Contract 追加章节在正文包含签核者、日期、版本/对象路径、覆盖范围与确认来源；正文声明「端点/字段/错误码/权限不变」；版本表与修订记录一致。
- **P2 设计输入收敛**：计划 `decisions_required` 中 CHG010-BQ18、BQ19 状态为 CONFIRMED，basis 引用已签核设计正文路径与版本（DB 设计 v1 DB-D401–D420、F026.md v2、F027.md v1）及签核者/日期；requirements §35.2/§35.3 正文不被改写；未新增任何业务规则。
- **P3 `q` 边界断言**：真实 PostgreSQL 集成测试断言四条边界（已知用户 `q=""` → 422；已知用户含控制字符 → 422；未知用户 `q=""` → 404；未知用户 + 未声明查询参数 → 422），断言校验 HTTP 状态与错误 code；删除 `_validate_q` 或调换校验顺序时至少一条断言失败。
- **P4 并发与完整性错误**：两条独立数据库连接并发授予同一 (user, cluster) → 恰一方 201、另一方 409 `already_granted`；最终 ACTIVE 行数 = 1、Audit 授予记录 = 1；非唯一完整性错误（如 FK 冲突）不被映射为 409 `already_granted`，其行为与 Contract 记录一致（现状：原样抛出 → 500 `INTERNAL_ERROR`）。
- **P5 前端交互**：候选加载期间不存在「已授权 Cluster 被呈现为可选且可提交」的窗口（提交受门控或加载完成后才呈现候选）；加载失败显示明确错误且可重试，不伪装为空列表；超大授权量情形有书面结论，若采用上限则显式提示而非静默截断；`already_granted`/`already_revoked` 仍按 Contract 关闭并刷新/内联呈现，不静默成功。
- **P6 文档/注释一致性**：`list_authorizations` 注释描述与实际规则一致（P-1 路径对象优先），不含与事实相反的结论；`docs/api/F026.md` §5 记录非唯一完整性错误语义，且未改变既有 409/422 映射。
- **P7 测试规范约束**：集成测试默认覆盖口径在 conftest docstring 或测试规范中显式声明；新增真实 scope 模块漏打 `real_scope` 不会被静默当作 legacy 覆盖放行（有机制或断言约束）。
- **P8 无回归**：F026 A1–A33 与 F027 A1–A23 相关行为不变；定向套件通过；全量后端以 F029 基线（721 passed / 6 skipped + 本次新增用例）通过；前端 `tsc --noEmit`、`vite build`、`smoke:client` 通过（F029 基线 322 passed）；无 Schema/Migration、端点、参数、权限项、错误码变更。
- **P9 范围不发生漂移**：变更文件不包含业务规则、授权语义、范围过滤、Audit 或前端功能的新增；`project.acceptance` 仅在 F030 验证通过后由协调器恢复 `COMPLETE`。

## 6. 复用证据

| 对象 | 版本 / 覆盖范围 | 复用结论 |
| --- | --- | --- |
| requirements revision 11 §23.2、§31 T85–T99、§32 | 全部 CONFIRMED | F030 全部产品判定已覆盖，无需新增条款 |
| `docs/features/F026/product.md` A1–A33 | READY FOR ARCHITECT；F026 DONE | 授权管理、Audit、软删/停用/降级、UI 如实呈现可直接引用 |
| `docs/features/F027/product.md` A1–A23 + §3 Q1 | READY FOR ARCHITECT；F027 DONE | 范围执行、404 不泄露、错误顺序、不新增端点可直接引用 |
| `docs/features/F029/review-report.md` | APPROVED WITH FOLLOW-UP，绑定 HEAD `6e8abdb` / Base `4f83a0e` | 本 Feature 输入来源；其「无新增领域规则」结论继续成立 |
| `docs/features/F029/test-report.md` TD-1 / TEST-1、`implementation.md` | 定向 21 passed；全量 721 passed / 6 skipped；前端 322 passed | F030 回归对照基线 |
| `docs/api/F026.md` v2、`docs/api/F027.md` v1 | Architect 签核 | 端点/字段/错误码/权限边界，F030 不得改变 |

## 7. 待决与专业设计输入

**Blocking Questions：None。**

- N1：①⑥ 的记载形态（正文补签核行 vs. 记为「编辑维护」）由 Architect/协调器按 change-control §2 决定；出现内容语义变化即回 Product。
- N2：⑤ 的阈值、提示形态与超大授权量结论由 Architect/Frontend 在既有边界内决定，须满足「不静默截断、409 如实呈现」；需新增端点/参数时回 Product。
- N3：④ 必须使用两条真实连接，顺序调用不构成 F026-RV-03 的关闭证据。
- N4：CHG010-BQ18/BQ19 为 DESIGN_INPUT，签核责任为 Architect/Database 与 Architect/Backend；设计若产生新业务限制，回 Product/用户。
- N5：F029 遗留协调器事项（证据/锚点、approved HEAD、`project.acceptance`）归 MERGE 阶段处理，不在本 Feature 产品范围。

## 8. 交付

- 本文件：`docs/features/F030/product.md`
- 下一责任角色：Architect（ARCHITECTURE Gate），随后 Database / Test Design → Contract

**Status：READY FOR ARCHITECT**
