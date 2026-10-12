# F015 Audit 查询、已删除对象管理与系统功能 — PRODUCT 阶段报告

- **Feature**：F015 Audit 查询、已删除对象管理与系统功能（FEATURE，P1，M6 检索、导入与系统功能；deps F002–F012）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`
- **依据**：`docs/product/requirements-v3.md` revision 3 CONFIRMED（§21、§22、§23、§25、§28、§31 T24/T25/T26/T36/T41、§35.1/§35.2）；`docs/project/project-plan.yaml` plan_revision 4 F015 条目（用户 2026-10-06 批准）；已完成 Feature 产品/契约 `docs/features/F00x/product.md`、`docs/api/F003.md`/`F004.md`/`F007.md`/`F008.md`/`F009.md`/`F010.md`/`F011.md`/`F012.md`（各域删除/恢复/Activity/Audit 现状）；`docs/api/F002.md` v1（认证、权限 capability、错误码、操作者、无注册声明）；`docs/database/f002-auth.md` v1、`docs/database/f003-cluster.md`（`users`/`audit_logs` Schema、append-only、operator 快照）；`docs/api/F013.md`（只读约定参考）；`docs/product/domain-model.md`；`.pi/skills/resource-domain/SKILL.md`。

> 说明：本报告只定义 F015 的产品行为；各对象删除/恢复/Audit 写入/Activity 语义已随 F003–F012 落地，F015 **引用不重定义、不修改**。报告区分 `CONFIRMED` 与 `PROPOSED`/`OPEN`。

## 1. 范围与排除项

### 1.1 目标
在已完成各资源域之上，提供三项面向管理员/运维的系统能力（§21–§23/§28）：
1. **完整 Audit 查询**（§22/§25）：跨对象查询 `audit_logs`，限 ADMIN（`AUDIT_READ`）。
2. **已删除对象统一查看与恢复入口**（§21）：ADMIN 在一个入口中跨 8 类对象查看已软删对象并按各域规则恢复。
3. **用户与账号管理 + System 页面**（§23/§28）：ADMIN 创建账号、分配角色、停用/启用账号；不开放自行注册；System 页面承载 §28 的 System。

本 Feature 是跨对象查询与系统管理入口，不引入新业务资源实体、字段或状态，不改变任何已 DONE Feature 的行为语义。

### 1.2 本次范围（除标注 PROPOSED/OPEN 外为 CONFIRMED）
- **完整 Audit 查询**（§22/§23）：`GET /api/v1/audit`（§25 已确认 `/api/v1/audit` 路径），仅 ADMIN；字段、过滤、分页见 §3。
- **资源 Activity**（§22/§23）：全基础角色（VIEWER/EDITOR/ADMIN）可查看资源变更记录；已随各域 Feature 作为 `GET /api/v1/{object}/{id}/activity` 提供；F015 只做跨对象完整查询，**不重定义 Activity，不提升其可见范围**。
- **已删除对象统一查看与恢复**（§21）：覆盖 Cluster、Resource、Interface、Network、IPPool、IPAddress、Service、ServiceEndpoint；仅 ADMIN（`VIEW_DELETED`/`RESTORE`）。恢复只恢复当前对象、重检唯一性与依赖有效性、失败不覆盖新对象；每类对象恢复规则引用其自身 Feature。
- **用户与账号管理**（§23）：ADMIN 创建账号、分配角色、停用账号；停用后不可登录但历史审计保留操作者身份；停用/启用写审计；不开放自行注册。
- **System 页面**（§28）：承载账号管理与（PROPOSED）已删除对象管理入口。
- **Audit 持续保留、无修改/删除/清空入口**（§22）：含 ADMIN；不提供批量清空、不设置到期自动清理。

### 1.3 使用者
- ADMIN：完整 Audit 查询、已删除对象恢复、账号与角色管理、System 页面（§23 表格）。
- VIEWER/EDITOR：可查看资源 Activity（§23）；**不可**使用完整 Audit 查询、已删除对象管理与用户管理。

### 1.4 明确排除（CONFIRMED）
- **不做归档/清理任务**：一期 Audit 持续保留、不自动过期、无归档系统或清理任务；后续容量压力作为独立变更确认（§22/§35.2 Q07-A）。
- **不做自行注册**：无 `POST /api/v1/auth/register`、`/signup` 或匿名建号端点（§23；F002 §5）。
- **不做 Cluster 级复杂 RBAC**：仅基础角色 VIEWER/EDITOR/ADMIN（§23）。
- **不做各域业务规则重定义**：各对象删除/恢复/唯一性/依赖规则不变（§21；F003–F012）。
- **不做监控/导入/全局搜索/Dashboard**：属 F013/F014（§3/§17/§20/§24）。
- **不做一期集成验收**：属 F016（§31/§32）。
- **不在本 Feature 改变 Activity 与完整 Audit 的权限边界**（§22/§23）。

## 2. 领域影响分析

| 对象/视图 | 关系 | 作用域 | 生命周期 | 依据及状态 | 未决/影响 |
| --- | --- | --- | --- | --- | --- |
| 完整 Audit 查询（`audit_logs` 派生视图，非新实体） | 跨所有 object_type 只读 | 全局（ADMIN） | 无（只读） | §22 CONFIRMED | 参数/响应形态 OPEN（O-4） |
| 资源 Activity（既有，各域提供） | `(object_type,object_id)` 只读 | 每对象 | 无 | §22/§23 CONFIRMED | 无 |
| 已删除对象统一列表（派生视图，跨 8 类） | 聚合各域 `deleted_at IS NOT NULL` | 全局（ADMIN） | 无（只读） | §21 CONFIRMED | 展示字段落点 OPEN（O-2/O-7） |
| 恢复动作 | 复用各域 restore，不级联 | 每对象 | 恢复当前对象 | §21/T24/T41 CONFIRMED | 统一 API 形态 OPEN（O-3） |
| 用户账号（`users` 既有实体） | user_sessions（1:N） | 全局 | 创建→停用/启用（不物理删除） | §21/§23 CONFIRMED | 初始密码/改密 OPEN（O-5） |
| 账号事件 Audit | `audit_logs` object_type=`user` | 全局 | append-only | §22/§23 CONFIRMED（写入义务） | object_type 值登记 OPEN（O-6） |

数据完整性对应表（引用 `.pi/skills/data-integrity/SKILL.md`；F015 无新 Schema 语义，仅消费既有约束）：

| 规则依据及版本 | 作用域 | 记录/不变量 | 验证方向 |
| --- | --- | --- | --- |
| §22 / f003 DB-D28 | `audit_logs` | append-only；无 UPDATE/DELETE 路径 | DB 触发器 + API/UI 无入口 |
| §22 / f003 DB-D27 | `audit_logs.operator_*` | operator 快照 + FK RESTRICT | 停用后审计仍可解析 |
| §21 / 各域契约 | 各对象 restore | 唯一/依赖重检；失败不覆盖 | 逐类恢复失败用例 |
| §21 | 用户账号 | 停用而非删除，保留历史身份 | 停用后旧审计不变 |
| §23 | 权限 | 服务端强制；401 先于 403 | 三角色 × 端点矩阵 |

## 3. 必须遵守的已确认约束

- **§21**：8 类对象 `deleted_at` 软删、默认隐藏；删除后 hostname/IP 可重用，Network/Pool/Service/Interface 名称按 §4.1 复用，Cluster code 不重用；ADMIN 可查看并恢复；删除/恢复规则（引用检查、无级联、只恢复当前对象、重检唯一/依赖、失败不覆盖）；用户账号停用保留身份。
- **§22**：Audit 字段 `operator, action, object_type, object_id, before_data, after_data, created_at`，action 至少 CREATE/UPDATE/DELETE/RESTORE；资源 Activity 全基础角色可见，完整 Audit 限 ADMIN；不展示/记录密码、令牌；持续保留、不自动清理、无修改/删除/清空入口（含 ADMIN）；备份须含 Audit（F016 验证）。
- **§23**：权限矩阵逐行；完整审计查询与用户/角色/系统设置 = ADMIN（`AUDIT_READ`/`USER_ADMIN`）；查看已删与恢复 = ADMIN（`VIEW_DELETED`/`RESTORE`）；查看变更记录 = 全角色（`VIEW_ACTIVITY`）；本地账号、部署初始化首个 ADMIN、不开放注册；服务端执行鉴权。
- **§25**：REST 前缀 `/api/v1/`；`/api/v1/audit` 已列；用户管理须有契约；分页/排序/错误由契约明确。
- **§28**：主要页面含 Audit、System；列表页至少分页、排序、过滤、模糊搜索。
- **§31**：T24/T25/T26/T36/T41 映射见 §4。
- **§35.2**：Q07-A（Audit 持续保留/无清理/备份）、Q10-B（名称复用与恢复）已关闭，不重开。
- **F002 Contract**：权限 capability、401/403/409 语义、操作者取自 `request.state.operator`、无注册声明、`users` 表约束（`version` 乐观锁、status ACTIVE/DISABLED）。
- **F003 Database**：`audit_logs` append-only 触发器、operator 快照、object_type 无枚举 CHECK（varchar(64)）、无 `deleted_at`、无 `version`。

## 4. 可观察验收标准

> 覆盖 plan F015 acceptance 的 T24/T25/T26/T36/T41；每条给出可观察条件。`ActivityItem`/`AuditRow` 字段沿用各域已有形状（§22）。

### 4.1 完整 Audit 查询（§22/T25/T26）
| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | `GET /api/v1/audit` 仅 ADMIN 可访问：ADMIN 200；VIEWER/EDITOR 403 `FORBIDDEN{reason:"permission"}`；未认证 401 `AUTH_REQUIRED`（401 先于 403） | §22/§23/T25 |
| A2 | 完整 Audit 响应每条含 `operator`（含 `operator_user_id`+`operator_username`）、`action`、`object_type`、`object_id`、`before_data`、`after_data`、`created_at` | §22 |
| A3 | 支持按操作者（`operator`）、`object_type`、`object_id`、`action`、时间范围（`created_at` from/to）过滤，条件按 AND 组合；不合法取值 422 | §22/§25 |
| A4 | 支持分页（沿用既有基线 `page=1`/`page_size=20`，1..100；越界/非法 422）；空结果 200 `{items:[],total:0}` | §25/§28 |
| A5 | 查询为只读：不改任何对象、不写新 Audit、幂等 | §22 |
| A6 | 资源 Activity（各域 `.../activity`）对 VIEWER/EDITOR/ADMIN 均 200；仅由 `VIEW_ACTIVITY` 控制；F015 未改变其可见性 | §22/§23/T25 |
| A7 | 已有 Audit 行内容不因查询、业务对象删除/恢复、名称复用或账号停用而变化（写入后只读不变） | §21/§22/T26/T36 |

### 4.2 Audit 保留与不可变更（§22/T26/T36）
| # | 验收标准 | 映射 |
| --- | --- | --- |
| A8 | 无任何修改、删除、批量清空 Audit 的 API 或前端入口，ADMIN 亦无；对候选路径/方法返回 404/405 | §22/T36 |
| A9 | Audit 不按时间自动过期：不存在 TTL/清理任务；旧行在长时间跨度后仍返回 | §22/T36 |
| A10 | Audit 不记录、不回显密码/令牌等敏感认证内容；用户相关审计仅含白名单字段 | §22/T26 |
| A11 | 账号停用/启用不改变其既有 Audit 行；停用账号的历史审计仍展示原 `operator_username` 并可解析 `operator_user_id` | §21/§22/T26 |

### 4.3 已删除对象统一查看与恢复（§21/T24/T41）
| # | 验收标准 | 映射 |
| --- | --- | --- |
| A12 | ADMIN 在统一入口可查看 8 类已删对象：Cluster、Resource、Interface、Network、IPPool、IPAddress、Service、ServiceEndpoint；默认查询隐藏已删，仅在 `deleted=only/include`（ADMIN）下出现 | §21/T24 |
| A13 | 统一已删列表支持过滤（至少 `object_type`）与分页；返回稳定 ID 与可跳转标识 | §21/§25/§28 |
| A14 | ADMIN 可从统一入口对上述任一对象触发恢复；恢复成功后该对象在默认查询可见（`deleted_at=null`），并写 RESTORE Audit | §21/§22/T24 |
| A15 | 恢复**只恢复当前对象、不级联**：恢复 Service 不恢复其 ServiceEndpoint；恢复 Interface 不恢复其 Resource；恢复 Network 不恢复其 IPPool/IPAddress；恢复 Resource 不恢复其 Interface | §21/T24 |
| A16 | 标识被重用（Network/Pool/Service/Interface 名称、Resource hostname）或依赖仍被删除时恢复失败：分别返回 `409 CONFLICT{unique_conflict}` / `409 CONFLICT{dependency_deleted}`，**新对象不被覆盖**，原对象仍为已删 | §21/T24/T41 |
| A17 | **T41 恢复侧**：Network/Pool/Service 名称删除后被新对象复用 → 旧对象恢复失败且新对象保持不变；Cluster code 不重用，无同类冲突路径 | §4.1/§5/§21/T41 |
| A18 | 恢复后写 RESTORE Audit（object_type 为对应对象），同事务；恢复失败/回滚不留 Audit 残留 | §22 |
| A19 | 每类对象的恢复具体规则（唯一性、依赖、归属、地址边界、监听唯一等）沿用其自身 Feature；F015 不新增/不改变这些语义，统一入口仅按 object_type 路由到既有恢复 | §21/F003–F012 |

### 4.4 用户与账号管理（§23/T26）
| # | 验收标准 | 映射 |
| --- | --- | --- |
| A20 | ADMIN 可创建账号（`username`、初始凭据、`role`）；创建后该账号可登录并按角色进入 `permissions` | §23 |
| A21 | ADMIN 可分配/变更角色（VIEWER/EDITOR/ADMIN）；变更后新会话/后续请求按新角色鉴权 | §23 |
| A22 | ADMIN 可停用账号；停用后该账号登录返回 401 `AUTH_INVALID_CREDENTIALS`（与未知用户/错误密码响应一致，不泄露存在性），且其现有会话失效（401 `AUTH_REQUIRED`） | §23/F002 |
| A23 | ADMIN 可启用已停用账号；启用后恢复登录能力 | §23 |
| A24 | 创建/角色变更/停用/启用均记录 Audit（同事务）；停用/启用记 `UPDATE`，含 before/after | §22 |
| A25 | 不开放自行注册：无 `POST /api/v1/auth/register|/signup` 或匿名建号端点；未定义路径 404 | §23/F002 §5 |
| A26 | 账号管理仅 ADMIN（`USER_ADMIN`）：VIEWER/EDITOR 403，未认证 401；服务端强制 | §23 |

### 4.5 System 页面（§28）
| # | 验收标准 | 映射 |
| --- | --- | --- |
| A27 | System 页面存在，承载账号管理（创建/角色/停用/启用）与完整 Audit 查询入口；ADMIN 可访问，非 ADMIN 不显示且后端拒绝 | §28/§23 |
| A28 | System 页面列表至少分页、排序、过滤（§28 列表基线）；前端隐藏不替代服务端鉴权 | §28/§23 |

### 4.6 权限与边界
| # | 验收标准 | 映射 |
| --- | --- | --- |
| A29 | 权限矩阵在服务端执行：完整 Audit/用户管理/查看已删/恢复 = 仅 ADMIN；Activity = 全角色；可复现 | §23/T25 |
| A30 | 前端不提供修改/删除/清空 Audit 入口；即使构造请求也无对应端点 | §22/T36 |
| A31 | 本 Feature 不改变已 DONE Feature 的行为语义（各域删除/恢复/Activity/唯一性） | §21/plan F015 |

## 5. 不变量（I-1…）

- **I-1 Audit append-only**：`audit_logs` 仅追加；无 UPDATE/DELETE/TRUNCATE/清空路径（含 ADMIN、含 UI）；DB 触发器 `trg_audit_logs_append_only` 兜底（§22/f003 DB-D28）。
- **I-2 Audit 脱敏**：不记录、不展示密码/令牌等敏感认证内容；用户审计仅白名单字段（§22）。
- **I-3 Audit 持续保留**：无 TTL、无自动过期、无清理/归档任务；备份须含 Audit（F016 验证）（§22/T36）。
- **I-4 历史操作者身份保留**：账号停用/角色变更不改写既有审计；`operator_user_id` 可空 + `operator_username` 快照保证停用后仍可解析（§21/§22）。
- **I-5 恢复原子性**：恢复在单事务内完成唯一/依赖重检与写入；失败整体回滚，不部分生效、不留 Audit 残留（§21/§22）。
- **I-6 恢复不覆盖**：标识被重用或依赖失效时恢复失败并保持新对象与原对象状态不变（§21/T24/T41）。
- **I-7 恢复不级联**：仅恢复请求对象自身，不恢复其父/子/关联对象（§21/T24）。
- **I-8 软删默认隐藏**：已删除对象默认不出现在常规查询；仅 `deleted=only/include` 且具 `VIEW_DELETED`（ADMIN）可见（§21）。
- **I-9 账号不删除**：用户账号以停用代替删除；不提供物理删除用户路径；`audit_logs.operator_user_id` FK RESTRICT 保证持审计用户不可物理删除（§21/§23/f003 DB-D27）。
- **I-10 无自行注册**：不存在匿名建号/注册端点（§23/F002 §5）。
- **I-11 服务端强制鉴权**：权限仅由服务端判定，前端隐藏不替代；401 先于 403（§23/F002）。
- **I-12 读写边界**：Audit 查询、已删列表查询、Activity 为只读；写操作（恢复、账号管理）为 ADMIN 且写 Audit 同事务（§22/§23）。
- **I-13 分页有界**：完整 Audit 与已删列表分页且有结果集上限，越界/非法 422（§25/§28）。
- **I-14 稳定 ID**：查询结果与恢复目标使用稳定 UUID，不用 name/hostname/code 拼接（§4）。
- **I-15 不改既有语义**：F015 不改变 F003–F012 已交付的删除/恢复/Activity/唯一性行为（plan F015）。

## 6. 引用（不重定义）

| 对象类型（`object_type`） | 删除/恢复权威 | Activity 权威 |
| --- | --- | --- |
| `cluster` | `docs/api/F003.md` §6.5/§6.6 | F003 §6.7 |
| `resource` | `docs/api/F004.md` | F004 |
| `interface` | `docs/api/F007.md` §6.5/§6.6 | F007 §6.7 |
| `network` | `docs/api/F008.md` §6.5/§6.6 | F008 §6.7 |
| `ip_pool` | `docs/api/F009.md` | F009 |
| `ip_address` | `docs/api/F010.md` | F010 |
| `service` | `docs/api/F011.md` §6.5/§6.6 | F011 §6.7 |
| `service_endpoint` | `docs/api/F012.md` §6.5/§6.6 | F012 §6.7 |

统一入口按 `object_type` 路由到上述既有恢复语义；F015 不复制其规则。

## 7. 依赖与未决问题

依赖（CONFIRMED，均已 DONE）：F002（认证/权限/operator/无注册）、F003–F012（各对象软删/恢复/Activity/Audit 写入与 `audit_logs` Schema）；F001（真实 PG 测试基线）；F013/F014 无直接依赖。D02 相关设计（认证机制、审计一致性、错误语义）已在 F002 契约签核。

BLOCKING：无。

`CONFIRMED`：§21 全部；§22 全部；§23 全部；§25 前缀与 `/api/v1/audit`；§28 Audit/System 页与列表基线；§31 T24/T25/T26/T36/T41；§35.2 Q07-A/Q10-B。

`PROPOSED`/`OPEN`（非阻塞，均给可实施默认，交 Architect/CONTRACT 或 Product 确认，不自行设为永久规则）：

- **O-1（OPEN，产品/设计，非阻塞）— System 页面内容**：§28 仅列页面名，未定义「系统设置」具体项。**PROPOSED**：System 页承载账号管理与已删除对象管理入口；不新增未确认的系统设置项；完整 Audit 查询置于 §28 的 Audit 页。Owner：Product/Architect。
- **O-2（OPEN，产品/设计，非阻塞）— 已删除对象管理落点**：§28 未列独立「已删除」页。**PROPOSED**：作为 System 页的一个区域/Tab，或 System 页内入口跳转统一列表。Owner：Product/Architect。
- **O-3（OPEN，设计，非阻塞）— 统一恢复 API 形态**：**PROPOSED**：不新增跨对象统一恢复端点，前端统一入口按 `object_type` 调用各域既有 `POST /api/v1/{object}/{id}/restore`（避免重复语义、保持 I-15）；统一已删查询可用 `GET /api/v1/deleted`（PROPOSED 路径）只读聚合。Owner：Architect → CONTRACT。
- **O-4（OPEN，设计，非阻塞）— Audit 查询参数/响应形态**：**PROPOSED**：`operator` 支持按 `operator_username` 匹配并回传 `operator_user_id`；`object_id` 建议与 `object_type` 组合；时间范围 `from`/`to` 含边界、UTC；默认排序 `created_at` 降序、同刻 `id` 升序；响应 `{items:[AuditRow],page,page_size,total}`，`AuditRow` 形状与各域 `ActivityItem` 一致。Owner：Architect → CONTRACT。
- **O-5（OPEN，产品/设计，非阻塞）— 账号初始凭据与改密/重置**：§23 未定义创建账号的初始密码与改密流程。**PROPOSED**：ADMIN 创建账号时设置初始密码；改密/重置与「首次登录强制改密」为一期未确认，暂不实现，后续按变更控制。Owner：Product/用户。
- **O-6（OPEN，设计/数据库，非阻塞）— 账号事件 `object_type` 登记**：**PROPOSED**：用户创建/角色变更/停用/启用写 Audit，`object_type="user"`，action `CREATE`/`UPDATE`（停用/启用为 `UPDATE status`，before/after 含 role/status，不含密码）；不经 RESTORE。`audit_logs.object_type` 现为无枚举 CHECK 的 varchar(64)，登记该值无需 Schema 变更，具体交由 Database 签核。Owner：Architect/Database。
- **O-7（OPEN，设计，非阻塞）— 已删列表展示字段**：**PROPOSED**：至少 `object_type`、`object_id`、`label`（如 hostname/name/code）、`cluster`（适用时）、`deleted_at`；「删除操作者」非对象字段，若展示需从 Audit 派生，记为 OPEN。Owner：Architect。
- **O-8（OPEN，计划字段）**：`project-plan.yaml` F015 未填 `layers`/`api_required`，由 ARCHITECTURE 补齐（预期 `api_required=true`，`layers` 含 backend/frontend；database 取决于 O-6 是否需迁移/注册表记录）。

## 8. 交 Architect 的输入

1. **API**：`GET /api/v1/audit`（§25 已确认）；PROPOSED 只读 `GET /api/v1/deleted`（O-3）；用户与账号管理端点（O-6，如 `/api/v1/users`）；恢复复用各域既有端点（O-3）。契约含权限（`AUDIT_READ`/`USER_ADMIN`/`VIEW_DELETED`/`RESTORE`）、401/403/404/409/422 语义、分页/排序/过滤基线（O-4）。
2. **Audit 查询**：字段映射至 `audit_logs`（operator 快照、before/after JSONB、created_at）；过滤与分页；只读、不写 Audit；不改变逐对象 Activity（§22）。
3. **已删除对象统一入口**：跨 8 类 `deleted_at IS NOT NULL` 聚合；展示字段（O-7）；恢复路由到各域既有 restore，保持 I-5/I-6/I-7/I-15。
4. **用户与账号管理**：创建/角色/停用/启用；停用即时失效会话；不开放注册；写 `object_type="user"` Audit（O-6）；初始凭据处理（O-5）。
5. **System 页面**：承载账号管理 + 已删对象管理（O-1/O-2）+ Audit 查询入口；§28 列表基线。
6. **不变量**：I-1…I-15 由 DB（append-only 触发器、FK RESTRICT）与业务层（服务端鉴权、同事务）共同保证。
7. **待裁定**：O-1–O-8。
8. **边界**：不改各域 Schema 语义；不新增业务对象；不实现归档/清理/自行注册/复杂 RBAC。

## 9. 结论与下一步

无 Blocking Questions，无待用户裁定事项。**READY FOR ARCHITECT**。下一步 ARCHITECTURE：定义 `/api/v1/audit`、统一已删查询与用户管理端点，裁定 O-1–O-8 的 API 形态与落点；确认 object_type 值登记（O-6）是否需 Database 参与；前端承接 System 页面、Audit 页与已删除对象管理入口。