# F006 IPv4 分配与同一表单 IP 集成 — 架构方案

> Status: READY FOR IMPLEMENTATION
> Document Type: Feature Architecture
> Feature: F006（Epic E4，P0，M1）
> 依据：`requirements-v2.md` §2.1/§4.2.1–4.2.3/§4.2.6–4.2.11/§4.4/§4.5/§5/§6.4/§7.1/§7.3/§7.4/§9.1/§9.3、§10 场景 3/4/9/11/19–21/24–27/30/31/43/44/45/46/52/60/62/65、§11.1 BQ-AB/BQ-AC/BQ-H/BQ-N/BQ-O/BQ-R/BQ-W/BQ-Z；
>      `domain-model.md` §1/§2/§3/§4/§5/§6；ADR-001…ADR-005；
>      复用 `docs/architecture/F002-resource-registration.md` §2/§3/§4/§5/§6、`docs/architecture/F005-network-segments.md` §2/§3/§5/§6/§7、`docs/architecture/F013-user-role-management.md`（角色/操作者解析与会话）、`docs/architecture/F001-cluster-registry.md`（`resource_history`/`audit_log` 载体）；
>      `docs/api/F002.md`、`docs/api/F005.md`；`docs/database/F001.md` §2.3、`docs/database/F002.md` §2.1/§2.2/§9、`docs/database/F005.md` §2.1/§2.2/§7；
>      `docs/project/project-plan.yaml` F006
> 关联 Contract：`docs/api/F006.md`（唯一字段清单；扩展 `docs/api/F002.md`）
> 创建日期：2026-09-25

本文件只记录实现层架构方案。产品/领域事实以 `docs/product/` 为准；技术栈、数据库、API、部署、历史审计载体以 ADR 为准。标记：`CONFIRMED` / `PROPOSED` / `OPEN`。

---

## 1. 方案摘要

F006 在 ADR 既定架构与 F002/F005 已交付基础上，把 IPv4 分配集成进同一资源表单，交付：

1. IPv4 分配记录（`ip_addresses`）：挂 `network_interfaces.id`，冗余 `cluster_id`/`resource_id`/`segment_id`；**同集群有效 IP 全局唯一由数据库唯一约束保证**（§4.2.1、§9.3）；
2. 手动分配（网段内任意可用，含自动范围外）与自动分配（启用范围内按数值从小到大取第一个可用），**排除规则与 `/31`、`/32` 特例复用 F005 `addressing` 纯函数**（§5、场景 19/20/21/25/31）；
3. 资源管理 IP：`resources` 新增 nullable 引用 `management_ip_id`，指向本资源某个网卡的 IP；编辑时删除管理 IP 或其网卡须**同次显式清空/重选**，否则整单拒绝（§4.2.9/§4.2.11、场景 46 自身子项侧）；
4. 整单原子：扩展 F002 表单 payload，`interfaces[].ips[]` 用**嵌套显式操作**（`op ∈ {create, delete}`，IP 不可改地址只能删除重分配）；一次提交公共信息 + 全部网卡 + 全部 IP，单事务（§4.5、场景 43）；
5. IP 逐项真实删除释放占用、无恢复；再次分配重检；删除上级不隐式释放（§4.4.3、§5、场景 24）；
6. 网段侧保护生效：仍被网卡引用 `/` 仍有已分配 IP 时禁止删除网段（`SEGMENT_HAS_INTERFACES`/`SEGMENT_HAS_ALLOCATIONS`），存在已分配 IP 时禁止修改 CIDR（`CIDR_IMMUTABLE`）；新增保留地址/修改网关的冲突检查覆盖既有分配（§5、场景 26/27/52/60/62）；
7. 并发不重复由**数据库唯一约束最终保证**，资源表单用既有乐观锁串行化本资源写入；方案不引入服务端自动重试（§9.3、场景 22/23，端到端复核归 F011）；
8. IP 创建/删除/管理 IP 变更历史复用 `resource_history(target_type='resource', action='update')` 的 `change` 结构化承载（BQ-AB 委派）；append-only、删除后保留；查询归 F012；
9. 本对象服务端三角色鉴权复用 F013、操作审计 `target_type='resource'`（IP 变更并入 `resource.update`）；
10. F005 扩展点落地：以真实查询实现 `SegmentUsage.allocated_count`/`allocated_ip_nums`，供 F005 删除保护、CIDR 不可修改、保留/网关冲突检查与「可自动分配数量」使用；F005 页面「已分配 IP 及归属」由 F006 交付只读端点。

**复用 F002 / F005 / F001 / F013 依赖（不复制实现，`CONFIRMED`）**：
- `app.security.principal.get_current_user` → `Principal{user_id, username, role, must_change_password, status}`；
- `app.security.principal.require_roles(*roles)` → 越权 403；
- `app.audit.write(...)`（审计，append-only，`target_type='resource'`）；
- `app.resource_history.write(...)`（F001 已建表与写入接口，F006 只写入 `target_type='resource'`，不建表、不提供查询）；
- `app.errors.problem(...)` / problem+json 统一错误体；`app.db.get_db`；
- `app.resources`（F002）：资源主体、网卡显式增/改/删、整单事务、乐观锁、名称规范化、同名处理；F006 在其事务与 payload 内**扩展 IP 子项**，不新增独立资源写端点；
- `app.network_segments`（F005）：网段存在性/归属读取、保留地址与网关、`addressing` 纯函数、`SegmentUsage` 扩展点。

**初始化顺序（`CONFIRMED`）**：F013 `users` → F001 `clusters` + `resource_history` → F005 `network_segments` + `segment_reserved_addresses` → F002 `resources` + `network_interfaces` → F006 `ip_addresses` + `resources.management_ip_id`。F006 不重复建 `resource_history`/`audit_log`/`clusters`/`network_segments`/`resources`/`network_interfaces`。

---

## 2. 模块边界

### 2.1 后端模块（Python 3.12 + FastAPI，ADR-001）

| 模块 | 职责 | 明确的非职责 |
| --- | --- | --- |
| `app.ip_allocation`（IP 分配主体，新增） | IP 记录模型与查询；手动/自动选址；可用性排除；`excluded_nums` 接入分配集合；管理 IP 解析与校验；IP 子项在资源事务内的应用；`SegmentUsage` 真实实现（被 F005 扩展点使用）；IP 删除/释放 | 不实现登录/会话/角色判定（依赖 `security.principal`）；不实现资源/网卡本体事务（扩展 F002）；不实现网段属性/保留/网关（F005）；不提供资源历史查询（F012） |
| `app.ip_allocation.addressing`（复用 F005 纯函数） | 复用 `normalize_cidr`/`ipv4_to_int`/`int_to_ipv4`/`cidr_range`/`ranges_overlap`/`contains`/`excluded_nums`；新增 `allocated_nums(cluster_id)`、`first_available(start,end,excluded)`、`validate_manual(segment, address, excluded)` | 不访问数据库（由调用方传入已查询集合）；不写业务规则，只做 §5 口径集合运算 |
| `app.network_segments.usage`（F005 预留扩展点，F006 填充实现） | `SegmentUsage.allocated_count(segment_id) -> int`、`SegmentUsage.allocated_ip_nums(cluster_id) -> set[int]`；供 F005 删除/CIDR/保留/网关路径与计数使用 | 不反向依赖 `app.resources`；只读 `ip_addresses`（与 `network_segments`），不写 |
| `app.resources`（F002，F006 扩展） | 资源表单事务内应用 IP 子项与管理 IP；payload 校验扩展；错误定位扩展 | 不实现字段级 IP 分配算法（在 `app.ip_allocation`） |
| 复用 `app.security.principal` / `app.audit` / `app.resource_history` / `app.errors` / `app.db` | 见 §1 | — |

模块依赖方向：`resources → ip_allocation`（表单事务调用 IP 应用）；`ip_allocation → network_segments`（网段/纯函数/模型读取）；`network_segments.usage → ip_addresses`（扩展点只读查询）。`ip_allocation → security.principal/audit/resource_history`。禁止对 `users` 反向依赖（只依赖 `security.principal`）。

**`SegmentUsage` 扩展点接入方式（`CONFIRMED` 需求 / `PROPOSED` 机制，需 Backend 实现前确认）**：
- F005 架构 §7.2 已声明「F005 提供 `SegmentUsage.allocated_count` 扩展点，F005 阶段恒为 0；F006 接入真实查询」。
- 推荐实现（保持依赖方向）：F006 在 `app.ip_allocation` 提供 allocated 查询 provider，由应用启动时注册/注入到 `app.network_segments.usage`；F005 写入路径仅调用扩展点接口。
- 备选（最简、F005 已预留）：F006 就地填充 `app.network_segments.usage` 的函数体，使其读取 `ip_addresses`。此方式在同一 `network_segments` 包内引入对 F006 模型的引用，属实现层机制、非产品规则；Backend 应将其隔离在单一函数内并加测试。Database 不承担该决策。
- 不采用「F005 反向依赖 F002/F006 业务模块」的写法。

### 2.2 与 F002 的关系（`CONFIRMED`）

- IP 只能经资源表单事务增/删（与 F002 网卡一致）：F006 **不新增独立 IP 写端点**，从而保证整单原子（§4.5）与「逐项显式、无恢复」。
- F002 的 `interfaces[]` 显式 `op` 扩展出 `ips[]`；F002 的乐观锁 `version` 覆盖含 IP 的整张表单（场景 47 的后端保证仍由 F002 提供）。
- F002 既有 `DELETE /resources` 前置（无仍存网卡）不变；引入 IP 后新增「网卡仍含 IP 时不能删网卡」（`INTERFACE_HAS_IPS`）。
- F002 `resources` 表新增 nullable `management_ip_id`（见 §3.2）；F006 不改 F002 既有列语义。

### 2.3 与 F005 的关系（`CONFIRMED` 规则 / `PROPOSED` 机制）

- F006 建立 `ip_addresses.segment_id → network_segments(id) ON DELETE RESTRICT`，使 F005 删除仍含已分配 IP 的网段时 `SQLSTATE 23503` → `409 SEGMENT_HAS_ALLOCATIONS`（F005 §7 已声明该扩展点）。
- 存在已分配 IP 时禁止改 CIDR：F005 `PATCH /network-segments/{id}` 通过 `SegmentUsage.allocated_count(segment_id) > 0` → `409 CIDR_IMMUTABLE`。
- 新增保留地址/修改网关的冲突检查：F005 `POST .../reserved-addresses` 与 `PATCH /network-segments/{id}`（网关非空）在同一事务内调用 `SegmentUsage.allocated_ip_nums(cluster_id)`，与新增保留范围/新网关取交集，非空则 `409 RESERVED_ADDRESS_CONFLICTS_ALLOCATION` / `409 GATEWAY_CONFLICTS_ALLOCATION`（`PROPOSED` 错误码命名，见 Contract §4；需同步修订 `docs/api/F005.md`）。
- 「可自动分配数量」`auto_assignable_count` 在 F005 已扣保留/网关/网络广播；F006 接入后**同时扣同集群已分配 IP**（§5 BQ-R、场景 65）。
- 重叠网段跨段排除：F006 查询 allocated 集合时按 **cluster_id**（而非单个 segment_id）取全集，与 F005 `excluded_nums` 的跨重叠语义一致；已真实删除网段的保留/网关仍不参与（只读现存行）。

### 2.4 前端页面 / 状态（Vue 3 + TS + Vite + Element Plus，ADR-001）

| 区域 | 内容 |
| --- | --- |
| 资源表单 `/clusters/:clusterId/resources/new`、`/edit`（复用 F002） | 网卡卡片内新增 IP 区：手动输入 / 自动分配按钮；未选网段时禁用分配并提示先选网段；选定网段后只读带出技术/用途/前缀/网关（F005）；整单提交 |
| 管理 IP 选择 | 资源级下拉/单选，候选为本表单将保存的 IP（`interface_index` + `address` 或 `ip_id`）；删除管理 IP 或其网卡时强制显式清空/重选，否则前端阻断并提示 |
| 已分配 IP 侧栏/页签 | 网段详情「已分配 IP 及归属」由 F006 只读端点提供（替换 F005 占位空态） |
| 错误定位 | 解析 problem+json `errors[]`，定位「第 N 张网卡 · 具体 IP」；`IP_ALREADY_IN_USE` 展示冲突对象（本集群资源/网卡）；`NO_AVAILABLE_ADDRESS` 明确提示不切换网段 |
| 冲突保留输入 | `409 VERSION_CONFLICT`/IP 并发冲突保留表单内容，提示刷新确认后重提（§7.3） |
| Pinia `useClusterStore`（复用 F001/F002） | 决策查询作用域；前端权限仅导航/隐藏，不作安全边界 |

---

## 3. 数据影响（Architect 声明的数据行为，Schema 由 Database 设计）

> 本节声明**必须保障的行为与约束**；列类型/索引名/DDL 由 Database 在 `docs/database/F006.md` 设计并交 Backend 实现。F006 `layers.database=true`。

### 3.1 `ip_addresses`（IP 分配记录，新增）

| 行为 | 说明 | 依据 |
| --- | --- | --- |
| `id` | 稳定主键（`BIGINT`），供管理 IP 引用与 F012 查询 | §4.2.1 |
| `interface_id` | 所属网卡，`NOT NULL`；`FK → network_interfaces(id) ON DELETE RESTRICT` | §4.2.2/3、§4.4.3 |
| `resource_id` | 所属资源（冗余，源自网卡）；用于管理 IP 归属复合 FK 与查询 | §4.2.9、场景 46 |
| `cluster_id` | 所属集群（冗余，源自资源）；用于「同集群有效 IP 全局唯一」唯一约束 | §4.2.1、§5、§9.3 |
| `segment_id` | 分配时所选网段，`NOT NULL`；`FK → network_segments(id) ON DELETE RESTRICT` | §4.6.6/7、§5、§4.4.2 |
| `ip` | 规范化点分十进制 IPv4；仅 IPv4 | §4.2.8、§5 |
| `ip_key` | 比较键（`PROPOSED`：生成列，规范化后等于 `ip`；或数值键） | ADR-002 |
| `created_at` | 创建时间（IP 行不可改地址，无 `updated_at`） | §5「IP 不可改、只能删除重分配」 |
| 无 `status`/`deleted_at` | 无逻辑删除/停用；真实删除即删行、释放占用 | §4.2.10、§4.4、BQ-M |

**必须由数据库保证的关键完整性（`REQUIRED`，依据 §4.2.1、§5、§9.3、ADR-002）**：
1. `UNIQUE (cluster_id, ip_key)`：同集群仍存有效 IP 全局唯一，跨集群允许重复；真实删除后行即删、地址可复用（场景 3/24、§10.22/23）。
2. `segment_id` 的 `ON DELETE RESTRICT`：仍有已分配 IP 时禁止删除网段（→ `409 SEGMENT_HAS_ALLOCATIONS`）。
3. `interface_id` 的 `ON DELETE RESTRICT`：仍有 IP 时禁止删除网卡（→ `409 INTERFACE_HAS_IPS`）。
4. `CHECK` IPv4 格式护栏；不存在 IPv6 列/路径。

**`PROPOSED`（不阻塞）**：
- IP 属于网卡所选网段：`ip_addresses.segment_id` 应与 `network_interfaces.segment_id` 一致（新增 `UNIQUE (network_interfaces.id, segment_id)` 作复合 FK 目标，或应用保证并测试覆盖）。采用哪种由 Database 决定，遵循 F002 §2.3 的复合 FK 先例。
- `ip_key` 用生成列 `GENERATED ALWAYS AS (ip) STORED`（与 F005 `cidr_key` 一致）；`UNIQUE (cluster_id, ip_key)` 或退化为 `UNIQUE (cluster_id, ip)`。
- 唯一约束设为 `DEFERRABLE INITIALLY IMMEDIATE` 以支持同一事务内「先删后建同地址」（亦可通过「先应用 delete 再应用 create」保证顺序）。

### 3.2 `resources.management_ip_id`（F002 表上的附加列，新增）

| 行为 | 说明 | 依据 |
| --- | --- | --- |
| `management_ip_id` | `NULL` 或指向 `ip_addresses(id)`；管理 IP 为本资源某个网卡 IP 的引用，`nullable` | §4.2.9 |
| 归属约束 | 被引用 IP 必须属于本资源（`PROPOSED`：`ip_addresses` 冗余 `resource_id` + `UNIQUE(resource_id,id)`，`resources (id, management_ip_id) → ip_addresses(resource_id,id)`；或应用保证并测试） | §4.2.9、场景 46 |
| 引用删除 | `FK → ip_addresses(id) ON DELETE RESTRICT`：删除管理 IP 前必须先在同次提交清空/重选；不得 `SET NULL` 静默清空 | §4.2.11、场景 46 |
| 访问/展示 | 资源详情/列表展示「管理 IP」；不新增独立 IP 记录 | §4.2.9、§6.2 |

**迁移纪律（AGENTS §6）**：`resources` 已由 F002 交付；本列为**可空、附加、向前兼容**变更，由 F006 的 Database 设计记录，Backend 以增量/幂等方式落地（P0 无迁移工具，ADR-002）；不得删除或改写既有数据。F002 新增时 `management_ip_id` 缺省 `NULL`。

### 3.3 网卡表附加约束（F002 表上，新增，`PROPOSED`）

若采用复合 FK 落实 §3.1/§3.2 归属，需在 `network_interfaces` 上附加 `UNIQUE (id, cluster_id)`、`UNIQUE (id, segment_id)` 作 FK 目标；均为附加、无列/语义/既有数据变化。若 Database 选择「应用保证 + 测试覆盖」，则不新增这些约束，但须在 `docs/database/F006.md` 明确并测试。

### 3.4 `SegmentUsage` 真实实现（F005 扩展点填充）

| 行为 | 说明 | 依据 |
| --- | --- | --- |
| `allocated_count(segment_id)` | 该网段已分配 IP 数（真实查询 `ip_addresses`） | F005 §7.2、场景 60 |
| `allocated_ip_nums(cluster_id)` | 该集群全部已分配 IP 数值集合（含所有网段） | §5、场景 52/65 |
| 接入点 | F005 删除网段前置 `SEGMENT_HAS_ALLOCATIONS`；F005 `PATCH` CIDR `CIDR_IMMUTABLE`；F005 保留/网关冲突检查；F005 `auto_assignable_count` 扣除 | §5、场景 26/27/52/65 |

### 3.5 历史 / 审计写入（跨 Feature 共享载体，F001/F013 已建）

| 载体 | 行为 | 依据 |
| --- | --- | --- |
| `audit_log`（F013 已建） | F006 以 `target_type='resource'` 追加；IP 增/删与管理 IP 变更并入 `action='resource.update'`，`change` 内结构化含 `interfaces[].ips`/`management_ip`；append-only、用户删除后仍可读 | §9.1、ADR-005 |
| `resource_history`（F001 已建，F006 只写） | `target_type='resource'`、`target_id=str(resource.id)`、`target_key_snapshot=resource.name`、`action ∈ {update, delete}`；`change` 结构化承载 IP 创建/删除与管理 IP 变更；**无对业务表的阻塞 FK**；管理员可查、长期保留、不自动到期（查询 API 由 F012） | §4.4.4/6、BQ-AB/BQ-N/BQ-Q/BQ-V、ADR-005 |
| 写入时机 | 资源 `create` 仅写审计（含初始接口/IP）；资源 `update`（含网卡/IP/管理 IP 变更）写 `resource_history(update)`；资源 `delete` 先写历史与审计再删行（同事务） | §4.4.4、场景 48 |
| IP 历史表达 | **不新增 IP 级历史表**；IP 创建/删除以父资源 `update` 的 `change` 结构化承载（`target_type='resource'`） | BQ-AB、与 F002 网卡一致 |
| 历史不阻塞删除 | `resource_history`/`audit_log` 不得对 `resources(id)`/`ip_addresses(id)` 建阻塞 FK | §4.4.2、ADR-005 |

> `resource_history.action` 的 CHECK 目前仅允许 `('update','delete')`（`docs/database/F001.md` §2.3）。故 IP 创建不能落成 `action='create'`；F006 将其并入父资源 `update`。若 F012 后续需要按 IP 地址/动作检索，再按 AGENTS §6 增量扩展（非阻塞）；本 Feature 不改 F001 表约束。

### 3.6 Database 设计与 Backend 实现分工

- **Database**（`docs/database/F006.md`）：设计 `ip_addresses` 列/约束/索引；设计 `resources.management_ip_id`（含 FK 表达与迁移记录）；确定「IP 属于网卡所选网段」「管理 IP 属于本资源」的 DB 表达（复合 FK 或应用保证）；确定 `ip_key` 表达与唯一约束可延迟性；交付初始化/增量建表补充（P0 无迁移工具，ADR-002）。**不写业务实现**。
- **Backend**：ORM 映射；手动/自动选址与排除；`SegmentUsage` 真实实现与 F005 接入；资源事务内 IP 子项与管理 IP 应用；`23503`/`23505` 冲突 → 409 映射；审计与历史写入；初始化建表增量。**数据库实现由 Backend 承担**。

---

## 4. 分配规则与算法（`CONFIRMED` 规则，复用 F005）

### 4.1 分配模式 `CONFIRMED`（§5、场景 19/25）
- **手动**：先选定集群与网段（网卡 `segment_id`）再填写 IPv4；允许使用自动分配范围以外、但仍在网段 CIDR 内的可用地址（场景 19）。
- **自动**：在网段**已启用的自动分配范围**内，按地址数值从小到大选择第一个可用地址；未启用自动分配范围的网段只能手动分配（场景 25 → `AUTO_RANGE_NOT_ENABLED`）。
- 地址耗尽时返回 `NO_AVAILABLE_ADDRESS`，**不自动切换到其它网段**（§5、场景 23）。
- 前端预览候选不构成占用；以最终提交结果为准（§5）。

### 4.2 可用性排除集 `CONFIRMED`（§5、BQ-R/BQ-O、场景 20/21/52/65）
对网段 S 内地址，排除：
1. 同集群已分配 IP 地址（`SegmentUsage.allocated_ip_nums(cluster_id)`，覆盖所有网段，含重叠）；
2. S 自身登记的保留地址（含范围）与网关；
3. 同集群**其它仍存重叠网段** T（T.cidr 与 S.cidr 相交）的保留地址与网关；
4. 适用网络/广播地址：对每个前缀 ≤ 30 且与 S 重叠的**仍存**网段（含 S 自身），其网络/广播地址若落在 S 的分配范围则排除；`/31`、`/32` 不产生网络/广播排除。
- 已真实删除网段的保留/网关仅存在于 `resource_history`，**不参与排除**（场景 62）；排除计算只读现存行。
- 未变更的既有 IP 保持原归属，不因已由自身占用而在编辑时被当作新分配冲突（§5、场景 44）。
- 可用性判断**仅以平台记录为依据**，不做网络扫描/实时探测（§5）。

### 4.3 校验错误映射（`PROPOSED` 命名/状态，依据 §5、场景 20/31）
| 情况 | 错误 |
| --- | --- |
| 未选网段即分配 IP | `422 SEGMENT_NOT_SELECTED`（场景 30/31） |
| 地址不在网卡所选网段 CIDR 内 | `422 IP_OUT_OF_SEGMENT`（场景 11/20） |
| 同集群已被占用（含并发） | `409 IP_ALREADY_IN_USE`，附冲突对象（场景 3/4/20/44） |
| 命中仍存网段保留地址 | `422 IP_RESERVED`（场景 20/52） |
| 命中仍存网段网关 | `422 IP_GATEWAY`（场景 20/52） |
| 普通网段网络地址 | `422 IP_NETWORK_ADDRESS`（场景 20） |
| 普通网段广播地址 | `422 IP_BROADCAST_ADDRESS`（场景 20） |
| 自动范围未启用却请求自动 | `422 AUTO_RANGE_NOT_ENABLED`（场景 25） |
| 自动范围耗尽 | `409 NO_AVAILABLE_ADDRESS`，不切换（场景 23） |

### 4.4 `/31`、`/32` `CONFIRMED`（§5）
- `/31`：点到点网段，两个地址均可用，无网络/广播排除。
- `/32`：按单主机地址处理，该地址可用（自动范围须落在该地址）。
- 由 F005 `addressing.excluded_nums` 的既有分支处理；F006 不重复实现。

### 4.5 复用 F005 `addressing`（`CONFIRMED`）
- 复用 `normalize_cidr`/`ipv4_to_int`/`int_to_ipv4`/`cidr_range`/`ranges_overlap`/`contains`/`excluded_nums`。
- F006 新增纯函数：`allocated_nums(cluster_id)`（由调用方查询后转为数值集）、`first_available(start,end,excluded)`、`validate_manual(segment, address, excluded)`。
- `auto_assignable_count`（F005 §7.1）在 F006 接入后扣除同集群已分配集合；计数仍为快照、不预占（场景 65）。

---

## 5. 整单原子与 IP op 语义

### 5.1 表单 payload 扩展 `CONFIRMED`（§4.5、§6.4、ADR-003）
- `interfaces[]` 每项的 `ips[]` 采用嵌套显式操作：
  - `op:"create"`：新增 IP，`mode ∈ {manual, auto}`；`manual` 必填 `address`，`auto` 省略 `address`；
  - `op:"delete"`：显式删除 `id` 指定的既有 IP；
  - **IP 不可改地址**：不提供 `update` 改写地址；改址＝删除后重新分配（建议，依据 §5「再次分配须重新检查」）。
- 未出现在某网卡 `ips[]` 中的既有 IP 视为**未修改**（不删除、不覆盖），与 F002 网卡语义一致。
- 单事务：任一校验/写入失败整单回滚，不残留半条数据（场景 43）。事务内应用顺序（`PROPOSED`）：锁定资源行 → 应用 interface `delete`（含其 IP 显式删除）→ 应用 interface `update`（含 IP 增/删、网段变更）→ 应用 interface `create`（含 IP）→ 解析并设置管理 IP → 写审计/历史。同一事务内如需「先删后建同地址」，先应用 delete 再 create，且唯一约束可延迟（`PROPOSED`）。

### 5.2 网段变更与删除前置 `CONFIRMED`（§4.4、§7.4、场景 30）
- 分配 IP 前网卡必须已选网段，否则 `422 SEGMENT_NOT_SELECTED`。
- 已有 IP 的网卡不能只改网段后保留旧地址（§7.4）：`op:"update"` 携带不同 `segment_id` 且该网卡在本请求应用后仍有任何 IP → `422 INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE`；须在同次提交显式 `delete` 旧 IP 后在新网段 `create`。
- 删除网卡前须逐项删除其 IP（§4.4.3）：interface `delete` 可在同一项内携带显式 `ips` `delete` 项；应用后该网卡仍有 IP → `409 INTERFACE_HAS_IPS`，不级联。

### 5.3 管理 IP `CONFIRMED`（§4.2.9/§4.2.11、场景 46）
- 管理 IP 为资源引用，`nullable`；被引用 IP 必须属于本资源。
- 创建时 IP 尚无 ID：请求用 `management_ip = { interface_index, address }` 指定（`PROPOSED` 表达；`interface_index` 为 `interfaces[]` 的 0 基下标，与 problem+json 错误字段下标一致）。
- 编辑时：
  - 省略 `management_ip` = 不修改；
  - `management_ip = null` = 显式清空；
  - `management_ip = { ip_id }` = 重选既有 IP；
  - `management_ip = { interface_index, address }` = 重选本请求内的 IP（可用于本请求新建的 IP）。
- 若本请求删除了当前管理 IP 或其所隶属网卡，而 `management_ip` 未显式给出 → `422 MANAGEMENT_IP_REQUIRED`，整单拒绝（不静默清空/改指）。
- `management_ip` 解析后不属于本资源的有效 IP → `422 MANAGEMENT_IP_INVALID`。
- 删除整个资源不要求单独清空管理 IP 字段；但因 `management_ip_id` 为 RESTRICT 引用，删除管理 IP 的网卡/IP 的既有 PATCH 已要求同次清空/重选（§4.2.11）。

### 5.4 重复提交 `CONFIRMED`（BQ-AC）
- 重复提交未改变任何字段的编辑仍按一次变更处理（`version` 递增并写变更历史），**不做幂等短路**；适用于含 IP 的资源表单。

---

## 6. 删除 / 释放与网段保护

### 6.1 IP 逐项真实删除 `CONFIRMED`（§4.4.3、§5、场景 24）
- IP 经资源表单 `op:"delete"` 真实删行、释放占用、无恢复。
- 释放后该地址可再次分配，须重新通过 §4.2 全部检查。
- 删除上级（网卡/资源/网段）**不隐式释放**其仍存 IP；由 RESTRICT 保护（`INTERFACE_HAS_IPS`/`RESOURCE_HAS_INTERFACES`/`SEGMENT_HAS_ALLOCATIONS`）。
- 二次确认按 BQ-Z 为**资源级**；IP 删除无独立二次确认（随表单提交）。

### 6.2 网段侧保护生效 `CONFIRMED`（§5、F005 §6、场景 26/60）
- `DELETE /network-segments/{id}`：仍有已分配 IP → `409 SEGMENT_HAS_ALLOCATIONS`；仍被网卡引用 → `409 SEGMENT_HAS_INTERFACES`（F002）。
- `PATCH /network-segments/{id}` 修改 CIDR：`SegmentUsage.allocated_count > 0` → `409 CIDR_IMMUTABLE`。
- 新增保留地址/修改网关与既有分配冲突 → `409 RESERVED_ADDRESS_CONFLICTS_ALLOCATION` / `409 GATEWAY_CONFLICTS_ALLOCATION`（`PROPOSED`），原配置不变。

### 6.3 资源删除前置追加 `CONFIRMED`（§4.4.3）
- 删除资源前须已逐项删除全部网卡（F002 `RESOURCE_HAS_INTERFACES`）；而每张网卡须先删除其 IP（`INTERFACE_HAS_IPS`）。F006 不新增资源级前置码。

---

## 7. 并发与唯一性

- **最终保证**：`UNIQUE (cluster_id, ip_key)` 由数据库保证，两并发请求不能写同一同集群地址（§9.3、场景 22）。
- **同资源写入**：资源表单继续使用 F002 乐观锁 `version` 条件更新 + 事务内锁定资源行，串行化同一资源的并发编辑（场景 47）。
- **跨资源/跨网段并发**：依赖唯一约束兜底；触达 `23505` 时回滚整单并映射 `409 IP_ALREADY_IN_USE`（手动）或 `409 NO_AVAILABLE_ADDRESS`（自动候选被并发占用）。
- **重试策略（`PROPOSED`）**：本阶段**不引入服务端自动重试**，保持“一次提交失败即整单失败、前端保留输入重提”的简单语义；这与 BQ-AC「不错峰短路」不冲突（重试是客户端新提交，非幂等短路）。可选增强（非 P0 必需）：自动模式下对唯一冲突做有界重试，但不改变整单原子语义。
- 不采用跨多网段行锁/串行化隔离级别；唯一约束已足够，符合 AGENTS §2.6 简洁原则。

---

## 8. 历史与审计

- 审计：`target_type='resource'`；IP 增/删与管理 IP 变更并入 `resource.update`，`change` 结构化示例：
  `{ interfaces: { created:[{name, segment_id, ips:[{address, mode}]}], updated:[{id, ips:{created:[{address}], deleted:[{ip_id, address}]}}], deleted:[{id, ips:[...]}] }, management_ip: {from, to} }`（`PROPOSED` 结构）。
- 资源历史：`resource_history(target_type='resource', action='update')`，`change` 含 IP 创建/删除与管理 IP 变更；删除时先写历史/审计再删行（同事务）；append-only、删除后保留。
- 不新增 IP 级历史表（BQ-AB；与 F002 BQ-AB 决策一致）；不修改 F001 `resource_history`/`audit_log` 结构；查询归 F012。
- 历史不参与任何分配排除或删除保护判定（只读现存业务行）。

---

## 9. 权限

- 复用 F013 `get_current_user`/`require_roles`，逐请求读库、角色变更即时生效、禁用立即失效、首登未改密拦截。
- IP 与管理 IP 的读写发生在 `/resources` 端点内，沿用 F002 鉴权：详情任意已登录；`POST`/`PATCH`/`DELETE` 为 `maintainer`/`admin`；查看者写操作 `403`，数据不变（§2.1、场景 40）。
- 新增只读端点 `GET /network-segments/{id}/allocated-ips`：任意已登录（查看者可见）。
- F005 端点上新增的保留/网关分配冲突检查沿用 F005 已有写权限（`maintainer`/`admin`）。
- 集群选择只改变查询作用域，不改变角色权限。

---

## 10. API Contract（摘要；唯一字段清单见 `docs/api/F006.md`）

Contract 状态 **READY**（扩展 `docs/api/F002.md`）。Base：`/api/v1`；错误统一 `application/problem+json`。

| # | Method | Path | 说明 | 角色 |
| --- | --- | --- | --- | --- |
| 1 | POST | `/resources` | 新增资源：公共信息 + 全部网卡 + 全部 IP + 管理 IP，整单原子 | maintainer/admin |
| 2 | GET | `/resources/{resource_id}` | 表单详情：含 `interfaces[].ips[]` 与 `management_ip` | 任意已登录 |
| 3 | PATCH | `/resources/{resource_id}` | 编辑：网卡/IP 显式增/删 + 管理 IP 清空/重选（乐观锁） | maintainer/admin |
| 4 | DELETE | `/resources/{resource_id}` | 真实删除（沿用 F002；须先删完网卡/IP） | maintainer/admin |
| 5 | GET | `/network-segments/{segment_id}/allocated-ips` | 网段已分配 IP 及归属（F005 页面页签数据源） | 任意已登录 |

- F005 端点（`POST .../reserved-addresses`、`PATCH /network-segments/{id}` 网关）新增分配冲突检查错误码（见 Contract §4），F006 提供检查、需同步修订 `docs/api/F005.md`。
- 新增/扩展错误码：`IP_ALREADY_IN_USE`、`IP_OUT_OF_SEGMENT`、`IP_RESERVED`、`IP_GATEWAY`、`IP_NETWORK_ADDRESS`、`IP_BROADCAST_ADDRESS`、`NO_AVAILABLE_ADDRESS`、`AUTO_RANGE_NOT_ENABLED`、`SEGMENT_NOT_SELECTED`、`INTERFACE_HAS_IPS`、`INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE`、`MANAGEMENT_IP_INVALID`、`MANAGEMENT_IP_REQUIRED`、`IP_NOT_FOUND`，以及 F005 侧 `CIDR_IMMUTABLE`/`SEGMENT_HAS_ALLOCATIONS`/`RESERVED_ADDRESS_CONFLICTS_ALLOCATION`/`GATEWAY_CONFLICTS_ALLOCATION`、`VERSION_CONFLICT`（详见 Contract）。

---

## 11. Frontend / Backend / Database 工作拆分

**Backend**：`app.ip_allocation`（models/router 只读端点/schemas/service）+ `addressing` 纯函数扩展；`SegmentUsage` 真实实现与 F005 接入（删除保护/CIDR/保留/网关/计数）；资源事务内 IP 子项与管理 IP 应用；错误映射；审计与历史写入；初始化/增量建表；pytest + httpx 测试。

**Frontend**：资源表单 IP 区（手动/自动分配、未选网段禁用、整单提交）；管理 IP 选择与删除时强制清空/重选；网段详情「已分配 IP 及归属」页签；problem+json 错误定位到「第 N 张网卡 / 具体 IP」；冲突保留输入；Vitest 单测。

**Database**：按 §3 设计 `ip_addresses`、`resources.management_ip_id`，以及（若采用）`network_interfaces` 附加唯一约束；交付初始化/增量建表补充与迁移记录。实现由 Backend 承担。

---

## 12. Test Work

**后端集成（pytest + httpx）**：
- 唯一性/并发：同集群重复 IPv4 拒绝、跨集群允许（场景 3）；一请求内第二个 IP 冲突整单不残留（场景 4）；并发请求不重复（场景 22，端到端回归归 F011）；耗尽整单失败不残留（场景 23）。
- 手动/自动：自动范围外网段内可手动（场景 19）；越界/已占用/保留/网关/网络/广播拒绝（场景 20）；`192.168.1.20–30` 中 `.20` 已分配、`.21` 已保留 → 下次自动得 `.22`（场景 21）；未启用自动只能手动（场景 25）。
- 释放复用：删除后重新分配（场景 24）。
- 网段保护：有已分配 IP 禁止删网段/CIDR 修改（场景 26/60）；仍存重叠网段保留/网关跨段排除与新增保留/改网关覆盖既有分配（场景 27/52）；删网段历史保留/网关不影响其它重叠网段分配（场景 62）。
- 网卡/管理 IP：未选网段拒绝分配（场景 30/31）；改网段须释放旧 IP、删网卡须先删 IP；删管理 IP/其网卡未显式清空/重选整单拒绝、显式处理后成功（场景 46 自身侧）。
- 整单原子：第二张网卡/第二个 IP 失败资源与既有网卡/IP 保持原状（场景 43）；未修改既有 IP 不当作冲突（场景 44）。
- 只读端点：`allocated-ips` 返回归属、分页、空态（F005 页签）。
- 权限：viewer 写/删 403；maintainer/admin 允许；未登录 401；allocated-ips viewer 可读。
- 审计/历史：IP 增/删与管理 IP 变更写入 `resource_history(update)`/审计；删除后仍在；`target_type='resource'`。
- 计数：`allocated_count`/`auto_assignable_count` 扣同集群已分配后的正确性（场景 65）。

**数据库约束测试**：`UNIQUE(cluster_id, ip_key)`；`segment_id`/`interface_id` RESTRICT FK（`SEGMENT_HAS_ALLOCATIONS`/`INTERFACE_HAS_IPS`）；`management_ip_id` 归属与 RESTRICT；名称/格式 CHECK；构建「IP 属于网卡所选网段」归属（若采用复合 FK）。

**前端（Vitest）**：手动/自动 UI、未选网段禁用、管理 IP 强制清空/重选、错误定位、冲突保留、allocated-ips 页签。

**联验（非本 Feature 闭环）**：并发唯一与耗尽的千节点端到端复核（F011，场景 22/23）；IP 历史管理员查询（F012，场景 48/61/64）；类型详情/宿主与 VM/服务关联（F004/F007，场景 45/46/1/13/14）；网段页保留/网关与分配交互（F005）。

---

## 13. 技术决策与风险

**已确认（依据）**：栈 ADR-001；PostgreSQL 唯一性 DB 保证、真删、无迁移工具 ADR-002；REST/problem+json/乐观锁 409/显式子项操作 ADR-003；HTTP-only/无备份 ADR-004；历史审计分表、append-only、管理员可查、长期 ADR-005；IPv4 分配规则 §5、§4.2/§4.4/§4.5/§6.4、§7.1/§7.3/§7.4；名称/接口口径 BQ-W；真删二次确认 BQ-Z；重复提交按一次变更 BQ-AC；网卡/IP 单独真删历史表达 BQ-AB；权限 §2.1；F001/F002/F005/F013 复用基础。

**PROPOSED（不阻塞）**：
1. `ip_addresses` 冗余 `resource_id`/`segment_id` + 复合 FK 落实「IP 属于网卡所选网段」「管理 IP 属于本资源」，或应用保证并测试；
2. `ip_key` 生成列 `= ip`；唯一约束 `DEFERRABLE INITIALLY IMMEDIATE`；
3. 管理 IP 请求表达：`{interface_index, address}`（创建/重选新 IP）+ `{ip_id}`（重选既有）；
4. IP op 仅 `create`/`delete`，不支持改址；
5. 错误码命名与状态分配（§4.3、§6.2）；
6. `SegmentUsage` 接入方式（注册 provider 或就地填充扩展点）；
7. 事务内应用顺序（delete → update → create）与无服务端自动重试；
8. 历史 `change` 结构（`interfaces[].ips` + `management_ip`），不新增 IP 级历史表。

**OPEN / 关注（非阻塞 Database 设计 / 实现）**：
- F005 合约需同步修订以纳入 `RESERVED_ADDRESS_CONFLICTS_ALLOCATION`/`GATEWAY_CONFLICTS_ALLOCATION`（协调器执行；F005 已 READY，改动为附加错误码，不改既有语义）；
- `resources.management_ip_id` 属 F002 已交付表上的附加可空列，需按 AGENTS §6 记录迁移与已有数据处理（P0 绿地、向前兼容，非阻塞）；
- F012 若需按 IP 地址/动作检索历史，可能需扩展 `resource_history` 表达或新增 IP 级视图（后续增量，非阻塞）；
- `SegmentUsage` 反向依赖边界由 Backend 在实现前确认（推荐注册/provider 方式）。

---

## 14. Implementation Layers

| Layer | 需要 | 说明 |
| --- | --- | --- |
| database | **true** | `ip_addresses` + 唯一/CHECK/RESTRICT FK；`resources.management_ip_id`；可选 `network_interfaces` 附加唯一约束；初始化/增量建表；Database 设计、Backend 实现 |
| backend | **true** | IP 分配模块、`SegmentUsage` 真实实现与 F005 接入、资源事务 IP 子项与管理 IP、错误映射、审计/历史写入 |
| frontend | **true** | 资源表单 IP 区、管理 IP 选择、allocated-ips 页签、错误定位、冲突保留 |

结论：**READY FOR IMPLEMENTATION**（实现仍须通过独立 Database Design 与 Contract Gate）。