# F026 集群范围授权基座与 ADMIN 授权管理 — Product

- Feature：F026（FEATURE，P0，M17）
- 状态：READY FOR ARCHITECT
- 需求依据：`docs/product/requirements-v3.md` revision 11 §3、§5、§21、§22、§23、§23.1、§23.2、§24、§25、§27、§28、§31（T85–T99）、§32、§35.1
- 批准依据：`docs/project/proposals/CHG-010-cluster-access.md`；`docs/project/project-plan.yaml` plan_revision 14；用户 2026-10-21「批准并实施」
- 依赖：F002、F003、F015、F017（均 DONE）

## 1. 目标与边界

F026 建立「用户 × Cluster」授权事实与仅 ADMIN 的授权管理，供 F027 强制执行复用：

1. 授权持久化结构（字段/索引/约束由 Database 签核）；
2. Alembic 迁移与既有非 ADMIN × 既有 Cluster（含软删 Cluster）回填；
3. 授权查询/授予/撤销 API（仅 ADMIN）；
4. System 页授权管理 UI（仅 ADMIN）；
5. 授予/撤销 Audit 与撤销历史；
6. 统一 `AccessScope` 类型与逐请求解析入口。

**明确不做**：对既有业务域端点施加范围过滤、搜索/Dashboard/导入收敛（F027）；端到端 404/total/计数/行级拒绝（F027/F028）；新角色/权限项；资源实例级授权；组织/租户/审批流；API Key scope-down；物理删除授权历史；修改 F001–F025 已交付行为与证据。

F026 交付后、F027 合并前，非 ADMIN 的实际数据可见范围仍等于现状；这是计划承认的交付时间窗，不得宣称范围已生效。

## 2. 业务规则（§23.2 CONFIRMED）

- 授权主体为人类账号；API Key 继承绑定账号范围，不构成独立主体。
- 粒度：账号 × Cluster；不按资源类型、单对象或操作类型分别授权。
- 有效权限 = 角色矩阵允许的操作 ∩ 对象所属 Cluster 在授权集合内；范围只收紧，不放宽既有完整性/唯一性/软删/状态/关系约束。
- 同一账号 × Cluster 任意时刻至多一条有效授权；并发重复授予由数据库唯一约束兜底。
- 授权记录的目标账号与 Cluster 不可修改；变更 = 撤销旧记录 + 新建授予记录。
- ADMIN 不受范围限制；不为 ADMIN 建立授权行（授予拒绝、回填跳过、UI 不作为候选）。
- 非 ADMIN 无授权 = 空集合，默认拒绝，不得回退为全部可见。
- 撤销为状态变更：保留 `revoked_at` + 撤销操作者，不物理删除；重新授予产生新记录，不复用已撤销记录。
- Cluster INACTIVE 不改变授权；软删期间授权不生效；恢复后原授权自动恢复；新建 Cluster 不自动授予非 ADMIN。
- 授予目标 Cluster 只允许未删除；INACTIVE 允许；已软删 Cluster 拒绝（T96）。
- ADMIN 降级后立即按既有授权解析（可能为空），不隐式补偿；升级为 ADMIN 后不受限，既有授权行保留但不参与解析。
- 账号停用不删除/修改授权；停用期间无法认证；重新启用后按既有授权解析（A-1，推导口径）。
- 回填：既有非 ADMIN 账号 × 既有 Cluster（含软删），幂等；ADMIN 无行；不改变角色/状态/业务对象。
- 授权管理仅 ADMIN，复用 `USER_ADMIN`；VIEWER/EDITOR 403。
- 授予/撤销各写一条 Audit，与业务写入同事务；含目标账号、Cluster、动作、操作者、时间；无敏感内容；回填不写业务 Audit（A-3，PROPOSED）。
- `AccessScope`：ADMIN = unrestricted；非 ADMIN = 有效授权 ∩ Cluster 未软删；逐请求解析、同请求内稳定、不跨请求缓存；API Key 同口径。
- F026 不将 `AccessScope` 用于既有业务端点过滤。

## 3. 端点与错误语义（交由 Contract 定稿）

建议形态：用户管理子资源，仅 ADMIN。

- `GET /api/v1/users/{user_id}/cluster-authorizations`：分页查询，含有效/已撤销状态；
- `POST /api/v1/users/{user_id}/cluster-authorizations`：逐条授予；
- `POST /api/v1/cluster-authorizations/{id}/revoke`：撤销（或等价子资源 DELETE，Contract 定稿）。

错误顺序：401 → 403（角色）→ 422（请求体/参数）→ 404（路径对象不存在）→ 409（冲突）。

- 401：未认证；失效 API Key。
- 403：非 ADMIN 访问授权管理；CSRF。
- 422：`user_id`/`cluster_id` 非法；目标账号不存在或为 ADMIN；目标 Cluster 不存在或已软删；分页/排序非法。
- 404：路径中的授权/用户不存在。
- 409：重复授予 `already_granted`；撤销已撤销 `already_revoked`。
- 空结果 200 `{items:[], total:0}`；并发重复授予后到者 409，不静默成功。

## 4. 验收标准（待执行，不得预设 PASS）

映射 T90 / T92 / T96 / T99，以及 T85 / T93 / T95 / T91 的基座部分。

- A1 授予后可查到有效授权及授予时间/操作者；解析集合包含该 Cluster。
- A2 重复授予 409，有效记录仍为 1；并发重复授予后有效记录 ≤1。
- A3 给 ADMIN 授予 422，不产生 ADMIN 授权行；ADMIN 解析恒为不受限。
- A4 撤销后不再有效，保留撤销时间/操作者，历史可查，无物理删除。
- A5 重新授予产生新有效记录，已撤销记录不改写；1 有效 + N 已撤销合法。
- A6 仅 ADMIN 可查询/授予/撤销；非 ADMIN 403；未认证 401 先于 403。
- A7 授权查询返回账号/角色/状态、Cluster、授权/撤销状态，分页排序过滤；空集合 200；非法参数 422。
- A8 撤销不存在 404；撤销已撤销 409 且状态不变、不新增 Audit。
- A9 System 页授权区域仅 ADMIN 可见可操作；非 ADMIN 构造请求仍被服务端拒绝。
- A10 UI 如实呈现授予/撤销成功与失败，不静默成功。
- A11 授予候选不含 ADMIN 与已软删 Cluster；INACTIVE 可选。
- A12 ACTIVE ⇄ INACTIVE 不改变授权行与解析集合。
- A13 软删 Cluster 授权行保留但不生效；恢复后自动生效；期间撤销的恢复后也不生效。
- A14/A15 授予已软删/不存在 Cluster 422，无悬空授权。
- A16 新建 Cluster 不自动产生非 ADMIN 授权。
- A17 ADMIN 降级后按既有授权解析；升级后不受限且授权行保留。
- A18 停用账号无法认证，授权记录不变；启用后按既有授权解析。
- A19 非 ADMIN 解析 = 有效授权 ∩ 未软删 Cluster；仅 A/B 时精确为 {A,B}。
- A20 无授权 = 空集合，不回退全部可见。
- A21 ADMIN = unrestricted。
- A22 同请求内解析稳定可复用，不跨请求缓存。
- A23 授予/撤销/角色变更后下一请求即时反映（含 API Key）。
- A24 F026 不改变既有端点可见范围，T01–T84 无回归。
- A25 真实 PostgreSQL Alembic up/down/up 通过。
- A26 回填后每个既有非 ADMIN × 既有 Cluster（含软删）恰好一条有效授权；ADMIN 0 行；计数一致。
- A27 回填幂等。
- A28 回填不改变角色/状态/业务对象；升级后无全量失权、无额外越权。
- A29 迁移在已有业务数据与软删 Cluster 上可执行；恢复软删 Cluster 时授权生效。
- A30 成功授予仅一条 Audit，与授权写入同事务；失败无残留。
- A31 成功撤销仅一条 Audit，可追溯。
- A32 ADMIN 可通过既有 `GET /api/v1/audit` 查询；非 ADMIN 仍 403。
- A33 Audit 无敏感内容；撤销不以 DELETE 语义记录。

不在 F026 验收：T85 端到端 404、T87/T88 列表/搜索/Dashboard 收敛、T89 导入行级拒绝、T91/T94/T95 端到端、T97/T98 全量回归、T85–T99 真实 Compose 集成 → F027/F028。

## 5. 待决与专业设计输入

Blocking Questions：None。

- CHG010-BQ18（Architect/Database）：授权表/列/索引/有效行唯一/FK/迁移回填/查询实现/并发保护。
- CHG010-BQ19（Architect/Backend）：授权列表分页排序过滤与 System UI 展示口径。
- A-1（Product/用户，CONTRACT 前确认）：停用账号保留授权、启用后恢复、允许为停用账号授予、回填含 DISABLED。
- A-2（Product/Architect）：非 ADMIN 升级为 ADMIN 后既有授权行保留，降级时按既有行解析。
- A-3（Product/用户/Database）：回填不写业务 Audit，以迁移计数与 T99 为证据。
- D-1–D-6：端点形态、冲突 reason、Audit object_type/action、AccessScope 位置、撤销交互、回填实现，交 Architect/Database 定稿。

## 6. 交付

- 建议保存：`docs/features/F026/product.md`（本文件）。
- 下一责任角色：Architect（ARCHITECTURE Gate），随后 Database / Test Design / Contract。

**Status：READY FOR ARCHITECT**