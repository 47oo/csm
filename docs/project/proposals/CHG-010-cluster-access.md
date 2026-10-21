# CHG-010 按用户控制可访问集群（需求变更提案）

| 项 | 值 |
| --- | --- |
| Change ID | CHG-010 |
| 状态 | **PROPOSED / 待用户裁定与批准**（未批准，未生效） |
| 来源 | 用户本次指令：「访问权限控制功能新增，可以控制用户访问的集群（比如只能访问 a 集群，b 集群，其他禁止访问这样）」 |
| 基线 | `docs/product/requirements-v3.md` revision 10；`docs/project/project-plan.yaml` plan_revision 13（DONE，F001–F025 全 DONE，acceptance COMPLETE） |
| 候选 | 需求 revision 11；计划 revision 14；新增 F026–F028；`pending_changes: [CHG-010]`，`affects: ALL` |
| 处理依据 | `docs/project/change-control.md` §1–§4、`docs/project/git-workflow.md` §7 |
| 候选计划 | `docs/project/proposals/CHG-010-candidate-plan-delta.yaml`（增量）、`docs/project/proposals/CHG-010-candidate-plan-full.yaml`（合并预览，仅供审阅，不是已批准计划） |

> 本提案中的业务规则、验收编号、Feature 范围和推荐选项全部为 **PROPOSED**，除非明确标注 CONFIRMED。
> 用户一句话需求本身是 CONFIRMED 的输入事实；其业务含义、默认值、读写范围和排除边界尚需裁定。
> 未批准前不得改写需求正文、计划基线、DONE Feature 证据，也不得启动实现。

---

## 1. 需求理解

### 1.1 目标

在既有系统级角色（VIEWER / EDITOR / ADMIN）之上，增加**按账号限定可访问 Cluster 集合**的能力：例如只允许 user01 访问 cluster-a、cluster-b，其余集群禁止查询与操作。

### 1.2 与既有权限矩阵的关系（PROPOSED）

- 角色维度（§23，CONFIRMED）不变：决定“能做什么操作”。
- 新增集群范围维度：决定“能对哪些集群的对象做”。
- **有效权限 = 角色允许的操作 ∩ 对象所属 Cluster 在账号授权集合内**。
- 不新增角色类型、不按资源实例授权、不做组织 / 租户 / 审批流。
- API Key 不新增独立范围语义，继承绑定账号的范围（与 §23.1 “不产生新的权限语义”一致）。

### 1.3 性质裁定（需用户确认）

本需求应定性为「在既有基础角色上新增**集群范围限制**」，而不是重新引入 §3 排除的「复杂 RBAC」。因此需要收窄 §3 / §23 / §23.1 的排除表述，而不是撤回整个权限范围：

- 保留排除：自定义角色、资源实例级 ACL、层级权限继承、策略引擎、组织 / 租户、审批流。
- 新增允许：Cluster 级、按用户显式授予的访问范围（可读可写，默认拒绝）。

若用户认为这仍属于“复杂 RBAC”并维持原排除项，则本提案不能成立，应输出 `PROJECT PLAN BLOCKED`。

---

## 2. 需求正文差异（全部 PROPOSED）

### 2.1 §3 一期范围

| 位置 | 现文（revision 10） | 建议 |
| --- | --- | --- |
| 包含项 | 「基础用户权限」 | 改为「基础用户权限（系统级角色 + 集群范围授权）」 |
| 排除项 | 「复杂 RBAC」 | 收窄为「复杂 RBAC（自定义角色、资源实例级 ACL、层级权限继承、策略引擎、组织 / 租户）」 |

### 2.2 §23 用户与权限

| 位置 | 现文 | 建议 |
| --- | --- | --- |
| 首段 | 「一期仅基础角色，不实现 Cluster 级复杂 RBAC」 | 「一期使用基础角色 + 集群范围授权；不实现资源实例级及按操作类型的自定义 RBAC」 |
| 矩阵表 | 三角色操作矩阵 | **保持不变**；表后增加「有效权限 = 角色矩阵 ∩ 集群范围（§23.2）」 |
| 既有解释 | 删除 / 释放 / 恢复仅 ADMIN | 保持不变；ADMIN 不受集群范围限制 |

### 2.3 §23.1 API Key

| 位置 | 现文 | 建议 |
| --- | --- | --- |
| 明确排除 | 「Cluster 级或资源实例级复杂 RBAC」 | 改为「资源实例级复杂 RBAC」；保留“API Key 不产生新的权限语义” |
| 权限继承 | 等于绑定账号的角色权限 | 补充「并继承绑定账号的集群范围；逐请求解析，不缓存、不做 Key 级 scope-down」 |

### 2.4 新增 §23.2 集群范围授权（候选正文）

> 以下为候选文本；每一项都受第 6 节决策约束，未裁定项不得当作已确认。

- **主体**：授权主体为人类账号（VIEWER / EDITOR / ADMIN）；API Key 通过绑定账号继承同一范围，不构成独立主体。
- **粒度**：Cluster 级；不按资源类型、不按单对象、不按操作类型分别授权。
- **有效权限**：角色矩阵允许的操作 ∩ 对象所属 Cluster 在授权集合内；范围只收紧、不放宽任何既有完整性约束。
- **ADMIN**：ADMIN 不受集群范围限制；默认不为 ADMIN 建立授权行，避免第二事实来源。
- **默认拒绝**：非 ADMIN 未获任何授权时，可见集合为空；列表为空集合，详情与写操作被拒绝。不得回退为“全部可见”。
- **读写一致**：查询、搜索、详情、Dashboard、Activity、导入预校验与写入、新增、修改、删除、释放、恢复均受范围约束。
- **不可见性**：未授权集群完全不可见；列表 `total`、Dashboard 计数、搜索结果和错误信息不得泄露其存在或规模。
- **管理权限**：仅 ADMIN 可授予、查看、撤销授权；复用 §23「用户、角色、系统设置」权限项，不新增权限项。
- **审计**：授予与撤销写入 Audit，含目标账号、目标 Cluster、动作、操作者；与业务写入同事务；不记录敏感凭据。
- **撤销与历史**：撤销保留授权历史（建议 `revoked_at` + 撤销操作者），不物理删除关系记录；重新授予产生新的有效记录。
- **Cluster 状态**：INACTIVE 不回收授权，也不自动放开；Cluster 软删期间授权不生效，恢复后的生效口径由决策确定。
- **迁移**：对既有非 ADMIN 账号按裁定口径回填既有 Cluster 授权（推荐全量回填，避免升级即失权）。
- **错误语义**：未授权对象按 404 处理（不泄露存在性）；提交体显式引用未授权或不可选 Cluster 复用既有 422 `VALIDATION_ERROR`；401 → 403（角色）→ 422 → 404 → 409 的相对顺序不变。
- **明确排除**：自定义角色、资源实例级 ACL、层级继承、策略引擎、组织 / 租户、审批流、Key 级 scope-down。

### 2.5 §31 验收

在 T01–T84 之后新增 **T85–T99（PROPOSED）**，见第 7 节。

### 2.6 §32 上线验收

补充：未授权集群的读 / 写拒绝、列表 / 搜索 / Dashboard / 导入过滤、ADMIN 授权管理、授权变更 Audit、撤销即时生效、API Key 继承、迁移无失权、既有角色矩阵与完整性规则无回归。

### 2.7 §35 / §36 / domain-model

- §35.1：新增 revision 11 确认记录（**待用户裁定后填写真实来源**，不得预填）。
- §35.2：登记 CHG010-BQ01–BQ19；在全部裁定前，删除“当前无登记中的 OPEN 业务问题”的绝对表述。
- §36：需求基线改为 revision 11，记录对 §3 / §23 / §23.1 的收窄关系。
- `docs/product/domain-model.md`：新增「集群范围授权：§23、§23.2」索引行；正文仍只在需求文件维护。

---

## 3. 影响评估

### 3.1 领域与数据影响（PROPOSED，评估级）

新增「用户 × Cluster」授权关系，建议独立关系表（表名 / 字段 / 索引 / 迁移由 Database 在 Feature DATABASE Gate 签核）：

- 同一用户对同一 Cluster 最多一条**有效**授权；并发重复授予由数据库唯一约束兜底。
- 撤销建议保留历史（`revoked_at`、`revoked_by`），不建议物理删除；Audit 与关系历史互为佐证。
- Cluster 软删不删除授权行，但授权在软删期间不生效；是否回填软删 Cluster、恢复后是否自动生效需裁定。
- 用户停用不删除授权；重新启用后授权恢复（与既有账号生命周期一致）。
- 回填建议：既有非 ADMIN 账号 × 既有 Cluster 全量授权，保证升级不造成全量失权；迁移需幂等并提供真实 PostgreSQL `up/down/up` 验证。
- 所有业务对象均可唯一归入一个 Cluster：Resource / Network 直接持有 Cluster；IPPool 经 Network；Interface / Service 经 Resource；Endpoint 经 Service 且与 IP 同 Cluster；未绑定 IP 仍有 `cluster_id`。因此范围判定无归属歧义。

### 3.2 执行与接口影响（PROPOSED，评估级）

- 现有鉴权集中在 `get_current_operator` / `require_permission`，读服务多数不接收 operator；不能逐端点手写，需集中到统一 `AccessScope` 与查询谓词 helper。
- 读路径：各域列表与详情、Activity、全局搜索（4 类候选 + 关联行 + total）、Dashboard（counts + networks）、已删除对象（仅 ADMIN）、导入预校验。
- 写路径：各域创建 / 修改 / 删除 / 释放 / 恢复、IP 分配 / 绑定 / 解绑、跨对象父级派生、导入写入、API Key 管理（ADMIN 不受限）。
- `total` 必须与列表使用同一范围谓词，避免“空页但 total>0”及规模泄露。
- 导入：范围外行按既有行错误口径返回（行号 + 字段 + 原因），保持整批原子回滚，不产生部分成功或残留 Audit。
- 授权管理端点建议作为用户管理子资源（`/api/v1/users/{id}/cluster-grants`），仅 ADMIN；逐条授予 / 撤销，便于逐条 Audit 与并发安全。
- 新增错误 reason（如 `already_granted`）需登记到 F002 共享错误注册表；范围不可见对象统一 404，不新增泄露性错误码。

### 3.3 前端影响（PROPOSED）

- 列表 / 详情 / 搜索 / Dashboard / 下拉候选自动收敛；前端不作为唯一强制点。
- 非 ADMIN 且无授权集群时，明确空态「暂无已授权集群」，不伪装为加载失败或普通“暂无数据”。
- ADMIN 在 System 页面新增集群授权管理（逐条授予 / 撤销、结果呈现、撤销复用 `ConfirmDialog` 二次确认）。
- 不新增“我的范围”端点：候选下拉复用已过滤的 `GET /api/v1/clusters`。

### 3.4 既有 Feature 影响

| Feature | 影响 | 处理 |
| --- | --- | --- |
| F002 | 有效权限模型与 404 语义扩展 | 新 Feature 承接，F002 证据不改写 |
| F003 / F004–F012 | 列表 / 详情 / 写路径加范围过滤 | 新 Feature 承接 |
| F013 / F018 | 搜索候选、关联行、Dashboard 计数语义收窄 | 新 Feature 承接，需契约 errata |
| F014 / F023 | 预校验与写入增加范围行级归因 | 新 Feature 承接，模板与原子性不变 |
| F015 / F017 | 授权管理、Audit、API Key 继承 | 新 Feature 承接 |
| F019 / F021 / F022 | 复用既有端点自动收敛 | 回归验证 |
| F016 | 整体验收证据保留，但覆盖不了新范围 | 新增 F028 承接候选整体验收 |
| F024 / F025 | 离线脚本不变；`--push` 同口径受范围约束 | 文档说明 + 回归 |

已 DONE Feature 的范围、验收、Git / Test / Review 证据保持原样，不回写为“当时已满足新规则”。

---

## 4. 候选计划

### 4.1 Feature 拆分（PROPOSED）

| ID | 标题 | 优先级 | 里程碑 | 依赖 | layers / API |
| --- | --- | --- | --- | --- | --- |
| F026 | 集群范围授权基座与 ADMIN 授权管理 | P0 | M17 | F002, F003, F015, F017 | DB/BE/FE=true；api=true |
| F027 | 服务端访问范围强制执行 | P0 | M18 | F026 | DB=false；BE=true；FE=false；api=true |
| F028 | 范围变更集成验收与回归 | P0 | M19 | F026, F027 | 全 false；api=false |

- **F026**：授权数据模型与迁移回填、授权查询 / 授予 / 撤销 API、ADMIN 授权管理 UI、Audit、统一 `AccessScope` 与逐请求解析。不改变既有端点可见范围，可独立验收。
- **F027**：一次接入全部读 / 写 / 聚合 / 搜索 / 导入路径；**必须整体合并**，不得形成部分端点受限的安全中间态。内部可分批实现，但合并与验收以整体为准。
- **F028**：真实 Compose 上执行 T85–T99 与 T01–T84 关键回归，更新候选 revision 14 的整体验收证据。

依赖为单链 F026 → F027 → F028，无环。三项均为 P0，不能因优先级移出一期必需范围。

### 4.2 验收承接

- F026：迁移 / 回填 / 授权管理 / Audit / AccessScope。
- F027：全部读写路径、搜索、Dashboard、导入、未绑定 IP、跨对象派生、不可见性。
- F028：跨角色、多授权组合、撤销即时生效、迁移演练、既有矩阵与完整性无回归、Compose 部署。
- 各 Feature DONE 不自动代替候选 revision 14 的一期整体验收，也不自动授权发布。

---

## 5. 影响文件（获批后）

- `docs/product/requirements-v3.md`：§3、§23、§23.1、新增 §23.2、§31 T85–T99、§32、§35.1、§35.2、§36。
- `docs/product/domain-model.md`：新增编排索引行。
- `docs/project/project-plan.yaml`：revision 14、F026–F028、decisions_required、pending_changes、approval、acceptance。
- `docs/project/{backlog.md,dependency-map.md,milestones.md}`：由脚本生成。
- 后续 Feature 正文：`docs/features/F026–F028/`、`docs/api/F026.md`（范围附录）、`docs/database/f026-*.md`。

---

## 6. 决策登记（全部 OPEN，等待用户裁定）

推荐组合 = 下列“推荐”列。用户可以回复「按推荐执行」，或逐项调整。

| ID | 问题 | 推荐 | 备选 / 影响 |
| --- | --- | --- | --- |
| CHG010-BQ01 | ADMIN 是否受集群范围限制 | 不受限，且不为其建授权行 | 若受限需第二类管理员，易与 §21/§22 冲突 |
| CHG010-BQ02 | 非 ADMIN 无授权时默认 | 拒绝，可见集合为空 | 默认允许会使功能失效 |
| CHG010-BQ03 | 限制读还是读写 | 读写同时限制 | 只限写仍会泄露查询 / 搜索 / Dashboard |
| CHG010-BQ04 | API Key 是否继承 | 继承绑定账号范围，不做 Key 级 scope-down | 不继承会形成越权通道 |
| CHG010-BQ05 | 授权授予 / 撤销是否写 Audit | 写入，逐条记录 | 不记录无法追溯谁放开访问 |
| CHG010-BQ06 | 非 ADMIN 是否可见已删对象 | 永不可见；ADMIN 按 §21 | 与既有 VIEW_DELETED 一致 |
| CHG010-BQ07 | 未授权集群是否完全不可见 | 是，不泄露名称 / 计数 / 存在性 | 可见名称会泄露集群清单 |
| CHG010-BQ08 | 迁移回填范围 | 既有非 ADMIN × 既有 Cluster 全量授权 | 不回填会导致升级即全量失权 |
| CHG010-BQ09 | 谁管理授权 | 仅 ADMIN，复用“用户、角色、系统设置” | 新增权限项会扩大 §23 矩阵 |
| CHG010-BQ10 | 新建 Cluster 默认授权 | 不自动授予非 ADMIN，由 ADMIN 显式授予 | 自动授予全部用户会削弱默认拒绝 |
| CHG010-BQ11 | ADMIN 降级时范围 | 立即按既有授权解析（可能为空），不隐式补偿 | 可要求降级前校验，但会增加操作约束 |
| CHG010-BQ12 | 撤销是否保留历史 | 保留 `revoked_at` + 撤销操作者 | 硬删仅靠 Audit，历史更脆弱 |
| CHG010-BQ13 | 越权对象错误语义 | 非 ADMIN 统一 404，不泄露存在性 | 403 更直白但泄露存在性 |
| CHG010-BQ14 | 零授权 Dashboard / 搜索 | 显式空态（计数 0、空结果、提示无授权集群） | 不报错、不回退全局 |
| CHG010-BQ15 | 回填是否含软删 Cluster | 包含，恢复后行为与升级前一致 | 排除则恢复后需重新授权 |
| CHG010-BQ16 | 导入 / 批量绑定 / 脚本推送 | 与普通 API 同口径，行级拒绝 | 特例会形成绕过通道 |
| CHG010-BQ17 | 是否允许给 ADMIN 建授权行 | 不允许，ADMIN 走不受限 | 允许会产生第二事实来源 |
| CHG010-BQ18 | 表 / 索引 / 迁移 / 查询实现 | 专业设计签核，不提交用户 | Architect / Database |
| CHG010-BQ19 | 授权列表分页 / UI 展示口径 | 沿用既有列表契约，不改变排序 / 分页 | Architect / Backend |

> 其中 BQ01–BQ17 必须由用户裁定；BQ18–BQ19 在已裁定边界内由专业角色签核。
> 最小裁定集（决定能否进入 Feature 设计）：BQ01、BQ02、BQ03、BQ07、BQ08、BQ12、BQ13。

---

## 7. 建议验收标准（T85–T99，PROPOSED）

| ID | 验收标准 |
| --- | --- |
| T85 | 仅授权 A、B 的账号按 ID 读取 C 集群任一业务对象被拒绝（404，不泄露存在性/业务字段） |
| T86 | 同一账号对 C 集群对象的新增、修改、删除、释放、恢复均被拒绝；A、B 集群按角色矩阵正常 |
| T87 | 各域列表与 `total` 仅覆盖可见集群；分页不出现“空页但 total>0” |
| T88 | 全局搜索（含 §17.1 关联行）与 Dashboard 计数仅覆盖可见集群；未授权对象不出现、不泄露规模 |
| T89 | 导入（§24 / §24.1 / §24.3 推送）含未授权集群行时整批失败，返回行号 + 权限原因，无部分成功与残留 |
| T90 | 仅 ADMIN 可查看 / 授予 / 撤销授权；非 ADMIN 被拒绝；不新增权限项 |
| T91 | 撤销授权后即时生效，无需重新登录 |
| T92 | 授予与撤销各写 Audit，可被 ADMIN 查询，含目标账号 / Cluster / 操作者，无敏感内容 |
| T93 | 无任何授权的非 ADMIN：列表空集合、详情 / 写操作拒绝，不回退为全局可见 |
| T94 | API Key 继承绑定账号范围；401 先于 403、失效 Key 不泄露存在性等既有行为不回归 |
| T95 | Cluster INACTIVE 不改变授权；切换状态不改变可见集合 |
| T96 | 对不存在 / 已软删 Cluster 授权被拒绝，不产生悬空授权 |
| T97 | 既有角色矩阵不回归（T25 / T43 等）；范围不放宽任何完整性约束（T01–T41 关键抽样） |
| T98 | 非 ADMIN 在任何范围下不可见已删对象，`include` / `only` 仍 403；ADMIN 行为符合裁定 |
| T99 | 迁移回填与裁定一致、幂等；升级后不出现全量失权或越权；真实 PostgreSQL `up/down/up` 通过 |

执行要求：服务端强制（不仅是前端隐藏入口）、真实 PostgreSQL 验证授权唯一性、真实 Compose 验证跨功能；未执行不得写成 PASS。

---

## 8. 风险与未决

| ID | 风险 | 缓解 |
| --- | --- | --- |
| R-01 | 与 §3 / §23 / §23.1 已确认排除项冲突 | 本提案按变更控制处理，未批准不实现 |
| R-02 | 任一读路径遗漏范围过滤 = 安全缺口 | F027 整体合并，端点 × 域双向核对，F028 覆盖 |
| R-03 | 回填口径错误导致上线全量失权 | 回填口径写入验收并核对计数，F028 演练 |
| R-04 | total / Dashboard / 错误信息泄露存在性 | 把“不泄露”写成可观察验收项 |
| R-05 | 缓存 / 会话导致撤销不即时 | 逐请求解析，不跨请求缓存；F028 验证 |
| R-06 | 旧用例语义变化造成假通过 | F028 明确关键回归子集与预期调整依据 |
| R-07 | 17 项业务决策未裁定导致长期阻塞 | 先裁定最小集，专业项并行签核 |

未决（不阻塞本提案审阅，但影响正文落稿细节）：

- 是否需要独立的“授权变更历史”视图，还是仅依赖 Audit。
- 是否需要按用户 / 按集群双向授权查看。
- 新集群是否通知 ADMIN 或提示“未授权用户清单”。
- 未来组织 / 租户模型是否以当前授权表为扩展基座（本期不预建）。

---

## 9. 批准与 Git 处理

### 9.1 当前状态

- 本提案与候选计划仅为审阅材料；`docs/project/project-plan.yaml` 基线未被修改。
- 候选计划已做结构校验（`validate_project_state.py --plan docs/project/proposals/CHG-010-candidate-plan-full.yaml` 通过），但**不代表批准或可执行**。
- 当前工作区不 clean：分支 `v3.2` 存在一处与本变更无关的已跟踪文件删除（`_bmad-output/implementation-artifacts/spec-modernize-all-frontend-pages-with-ant-design-and-tailwind.md`）。
- 因此**未创建 proposal 分支**，避免携带未知改动切换分支。

### 9.2 批准后步骤（协调器执行）

1. 先处理或确认工作区未知删除，确保 Preflight clean；从 `v3` 创建 `proposal/CHG-010-cluster-access` 并记录基线 SHA。
2. 在基线 `pending_changes` 登记 CHG-010（`affects: ALL`），暂停 F026–F028 调度。
3. 按用户批准的 BQ 结果写入需求 revision 11、domain-model、计划 revision 14、派生视图。
4. 保存真实批准记录（`approved_by`、`approved_on`、`basis`、feature_ids F001–F028）与确认来源；`project.status` 由 DONE → ACCEPTED；`acceptance` 置 PENDING 并保留 F016 证据。
5. 运行 `render_project_views.py --write` 与 `validate_project_state.py --previous <snapshot>`；失败不宣称生效。
6. 合入 `v3` 的提案变更不产生 Feature DONE，也不自动启动实现；实施需另行执行授权。

---

## 10. 审阅结论

- 本提案已覆盖需求差异、影响评估、候选计划、验收与风险。
- 尚需用户裁定 CHG010-BQ01–BQ17（最小集 BQ01/BQ02/BQ03/BQ07/BQ08/BQ12/BQ13），并批准候选计划 revision 14。
- 在上述裁定与批准前，状态为 **PROJECT PLAN READY FOR APPROVAL（待裁定项未关闭）**，不得进入 Feature 设计或实现。