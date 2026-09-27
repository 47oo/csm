# F002 计算资源登记、无 IP 网卡与一次原子提交基础 — 架构方案

> Status: READY FOR IMPLEMENTATION
> Document Type: Feature Architecture
> Feature: F002（Epic E2，P0）
> 依据：`requirements-v2.md` §2.1/§2.2/§4.1.2–4.1.10/§4.2.4/§4.2.5/§4.3/§4.4/§4.5/§6.3/§6.4/§7.1–§7.4/§9.1、§10 场景 2/5/6/28/29/30/34/42/46/47/48/50 与 §11.1 BQ-AA/BQ-AB/BQ-W/BQ-Z、§11.2；
>      `domain-model.md` §1/§2/§3/§4/§5/§6；ADR-001…ADR-005；
>      复用 `docs/architecture/F001-cluster-registry.md` §2/§3/§4、`docs/architecture/F005-network-segments.md` §2/§3/§4/§5/§6、`docs/architecture/F013-user-role-management.md` §2.2/§2.3/§4、`docs/database/F001.md` §2.3、`docs/database/F005.md` §2.1；
>      `docs/project/project-plan.yaml` F002
> 关联 Contract：`docs/api/F002.md`（唯一字段清单）
> 创建日期：2026-09-25

本文件只记录实现层架构方案。产品/领域事实以 `docs/product/` 为准；技术栈、数据库、API、部署、历史审计载体以 ADR 为准。标记：`CONFIRMED` / `PROPOSED` / `OPEN`。

---

## 1. 方案摘要

F002 在 ADR 既定架构内新增一个受管对象模块「计算资源（Resource）及其无 IP 网卡」，交付：

1. 计算资源公共信息（所属集群、资源名称、资源类型、状态）的登记、编辑、供表单加载的详情与真实删除；
2. 网卡子项：同一资源下 0..N 张网卡，接口名 + 可关联本集群仍存网段（0..1），**本阶段不分配 IP**（IP 与管理 IP 归 F006）；
3. 一次提交公共信息 + 全部网卡，**整单原子**（单事务）：任一校验或写入失败，整单不生效；编辑显式区分「删除网卡 / 未修改 / 新增或修改网卡」；
4. 身份与唯一性：同集群仍存资源名称在裸金属与 VM 之间统一唯一（去首尾空格、区分大小写）；同一资源下接口名唯一；`resource_type` 与所属集群创建后只读；改名不改归属（网卡以 `resource_id` 关联）；
5. 同名新增显式处理：新增发现同集群同名仍存资源时服务端拒绝创建并返回既有资源标识，供前端提示用户进入该资源编辑，不创建第二条、不覆盖、不合并；
6. 真实删除前置：删除资源前须逐项先删其仍存网卡（`409 RESOURCE_HAS_INTERFACES`），不级联；无恢复入口；二次确认（BQ-Z：输入资源名称）；乐观锁；
7. 本对象服务端三角色鉴权（查看者只读、资源维护者读写、平台管理员管理）与操作审计、删除/变更资源历史写入（append-only）；
8. 复用 F001/F005 建立的集群/网段归属与删除保护目标侧：本 Feature 新引入 `resources.cluster_id → clusters(id) ON DELETE RESTRICT` 与 `network_interfaces.segment_id → network_segments(id) ON DELETE RESTRICT`，使集群、网段删除保护由数据库约束保证，并复用 F005 的 `409 SEGMENT_HAS_INTERFACES` 语义。

**复用 F013 / F001 / F005 依赖（不复制实现，`CONFIRMED`）**：
- `app.security.principal.get_current_user` → `Principal{user_id, username, role, must_change_password, status}`；
- `app.security.principal.require_roles(*roles)` → 越权 403；
- `app.audit.write(...)`（审计，append-only，`target_type='resource'`）；
- `app.resource_history.write(...)`（**F001 已建表与写入接口**，F002 只写入 `target_type='resource'`，不建表、不提供查询）；
- `app.errors.problem(...)` / problem+json 统一错误体；`app.db.get_db`；
- `app.network_segments` 的存在性/归属读取（用于「网段须存在且与本资源同集群仍存」校验），不复制网段规则。

**初始化顺序（`CONFIRMED`）**：F013 `users` → F001 `clusters` + `resource_history` → F005 `network_segments` + `segment_reserved_addresses` → F002 `resources` + `network_interfaces`。F002 不重复建 `resource_history`/`audit_log`/`clusters`/`network_segments`。

---

## 2. 模块边界

### 2.1 后端模块（Python 3.12 + FastAPI，ADR-001）

| 模块 | 职责 | 明确的非职责 |
| --- | --- | --- |
| `app.resources`（计算资源本体） | 资源新增/编辑/供表单加载详情/真实删除；公共信息校验；`resource_type` 与 `cluster_id` 只读；同名处理；网卡子项的显式增/改/删；整单原子事务；唯一与 FK 冲突 → 409 映射；审计与资源历史写入 | 不实现登录/会话/角色判定（依赖 `security.principal`）；不实现 IP/管理 IP 分配（F006）；不实现类型专有详情与宿主关系（F004）；不实现列表/筛选/分页/搜索（F003）；不提供资源历史查询（F012） |
| `app.resources.models` | `Resource`、`NetworkInterface` ORM 映射（Schema 由 Database 设计） | 不定义其他 Feature 的表 |
| `app.resources.service`（内部实现） | 名称规范化（`btrim`）、payload 接口名去重、网段归属校验、整单事务、乐观锁条件更新、`23503`/`23505` 冲突映射 | 不承载 HTTP 层；不实现网段算法（复用 F005） |
| 复用 `app.security.principal` | 操作者解析与三角色鉴权 | 见 §1 |
| 复用 `app.audit` / `app.resource_history` | 操作审计与资源历史写入（append-only） | 不查审计/历史 |
| 复用 `app.errors` / `app.db` | 统一错误体、会话 | — |
| 复用 `app.network_segments`（models/存在性读取） | 校验 `segment_id` 存在、属于本资源同集群、仍存 | 不复制网段业务规则；不反向依赖 F002 |

模块依赖方向：`resources → security.principal`、`resources → audit`、`resources → resource_history`、`resources → clusters(models only, FK/存在性)`、`resources → network_segments(models only, FK/归属校验)`。禁止 `resources` 反向依赖 `users`（只依赖 `security.principal`），与 F013 §2.1/F001 §2.1/F005 §2.1 一致。

### 2.2 与 F001 / F005 的关系（`CONFIRMED`）

- F002 引入 `resources.cluster_id → clusters(id) ON DELETE RESTRICT`。集群仍存计算资源时，F001 删除集群由 `SQLSTATE 23503` → `409 CLUSTER_HAS_ASSOCIATIONS` 捕获（满足 §4.1.9、场景 51 的计算资源侧）。F002 **不修改** F001 代码，仅新增表与 FK。
- F002 引入 `network_interfaces.segment_id → network_segments(id) ON DELETE RESTRICT`。网段仍被网卡引用时，F005 删除网段由 `23503` → `409 SEGMENT_HAS_INTERFACES` 捕获（F005 §2.3 已声明该扩展点）。F002 为 F005 的「网段被引用」保护提供行为侧。
- F002 引入 `network_interfaces.resource_id → resources(id) ON DELETE RESTRICT`，使资源删除时不级联网卡（§4.4.2）。
- F002 **为 F006 预留**：IP 记录将挂在 `network_interfaces`/`resources` 之下；F006 将扩展「网段存在已分配 IP 时禁止删 CIDR/删网段」及资源/IP 子项删除保护。F002 不实现 IP，不用 IP 字段。

### 2.3 与 F003 / F004 / F006 的边界（`CONFIRMED`，避免重叠）

| Feature | 边界 |
| --- | --- |
| F003 | 统一资源列表、筛选、分页、搜索与公共详情展示页；F002 只交付「供表单加载」的单资源详情与全部写入端点。F003 可在同一详情资源上扩展展示字段，不改 F002 写契约。 |
| F004 | 类型专有详情（SN/CPU/内存/GPU/vCPU）、VM 必填宿主、列表/详情类型摘要、删宿主前逐项真删 VM；F002 只交付「类型字段容器」与公共信息 + 网卡，不实现类型字段校验与宿主要求。 |
| F006 | IP 与管理 IP 的分配/删除/展示、含 IP 的整单原子、网段分配排除与并发唯一；F002 的网卡与网段关联保持「无 IP」，管理 IP 字段不在本 Contract。 |

### 2.4 前端页面 / 路由 / 状态（Vue 3 + TS + Vite + Element Plus，ADR-001）

| 区域 | 内容 |
| --- | --- |
| 资源表单路由 `/clusters/:clusterId/resources/new`、`/clusters/:clusterId/resources/:resourceId/edit` | 新增/编辑共用表单：集群（只读回显）、资源名称、资源类型（创建时可改、编辑只读）、状态、网卡卡片列表；一次提交公共信息 + 全部网卡 |
| 网卡卡片 | 增/删网卡；接口名；网段选择（0..1，仅本集群仍存网段）；选定后由 F005 网段数据只读带出技术、用途、前缀、网关（§4.2.7、场景 28）；**不单独录入 technology/purpose**（场景 29） |
| 同名处理 | 提交创建收到 `409 RESOURCE_NAME_EXISTS` 时，用返回的 `existing_resource_id` 提示「该集群已存在同名资源，是否进入编辑？」；用户确认后跳转编辑路由，加载既有网卡（§4.1.10、场景 2/45） |
| 真实删除 | 删除确认对话框须输入资源名称（BQ-Z）；成功后离开列表/详情 |
| 冲突保留输入 | 收到 `409 VERSION_CONFLICT` 保留当前表单内容并提示刷新确认后重提（§4.5、场景 47） |
| 字段/记录级错误 | 解析 problem+json `errors[]`，将错误定位到具体字段与网卡卡片（如「第 2 张网卡」），保留已填内容（§7.3） |
| Pinia `useClusterStore`（复用 F001） | 决定表单集群作用域；编辑时集群只读；**选择只改变查询作用域，不改变角色权限** |
| axios | 复用 F013/F001 拦截：401→登录、403→提示、problem+json 字段级错误、409→同名/冲突/删除前置提示、422→二次确认不一致/字段校验 |

前端权限仅用于导航/隐藏，**不作为安全边界**；最终由服务端校验。

---

## 3. 数据影响（Architect 声明的数据行为，Schema 由 Database 设计）

> 本节声明**必须保障的行为与约束**；列类型/索引名/DDL 由 Database 在 `docs/database/F002.md` 设计并交 Backend 实现。F002 `layers.database=true`。

### 3.1 `resources`（计算资源主表，新增）

| 行为 | 说明 | 依据 |
| --- | --- | --- |
| `id` | 稳定主键（`BIGINT`），供网卡 `resource_id` 与后续服务/类型详情引用 | §4.1.2、§4.1.4 |
| `cluster_id` | 所属集群，`NOT NULL`；`FK → clusters(id) ON DELETE RESTRICT`；创建后不可改 | §4.1.1/8、§4.1.9、场景 50 |
| `name` | 资源名：**去首尾空格后存储/比较、区分大小写、禁止纯空白**；`UNIQUE (cluster_id, name)` 覆盖裸金属与 VM 的统一判重 | §4.1.2/3、BQ-W、domain §5 |
| `resource_type` | `bare_metal` \| `virtual_machine`；`NOT NULL`；创建后不可改（无更新路径） | §1.3、§4.1.5、场景 34 |
| `status` | `IDLE`/`ALLOC`/`DOWN`/`UNKNOWN`；`NOT NULL DEFAULT 'ALLOC'` | §4.3、BQ-A |
| `status_updated_by` | 状态来源操作者；`NULL` 或 `FK → users(id) ON DELETE SET NULL`（**不记录外部来源系统**） | §4.3、BQ-AA |
| `status_updated_at` | 状态更新时间；`NOT NULL DEFAULT now()`；仅状态变更时刷新 | §4.3、BQ-AA |
| `version` | 乐观锁（编辑/删除条件更新） | §4.5、ADR-003 |
| `created_at` / `updated_at` | `TIMESTAMPTZ`；`updated_at` 由 Backend 在任何 UPDATE 时刷新（跨受管表统一约定，不承担状态语义） | 通用 |
| 无 `status`（停用）/`deleted_at` | 无逻辑删除/停用；真实删除即删行 | §4.2.10、§4.4、BQ-M |

**必须由数据库保证的关键完整性（`REQUIRED`，依据 §5、§9.3、ADR-002）**：
1. `UNIQUE (cluster_id, name)`（同集群仍存资源名称在裸金属与 VM 间统一唯一、区分大小写）；真实删除后行即删，名称可复用。
2. `NAME` 非空且 `name = btrim(name)` 由 CHECK 保证。
3. `resource_type`/`status` 取值由 CHECK 约束。
4. `version ≥ 1` + 条件 UPDATE/DELETE 实现乐观锁。
5. `cluster_id` 的 RESTRICT FK 保证集群删除保护。

### 3.2 `network_interfaces`（无 IP 网卡子表，新增）

| 行为 | 说明 | 依据 |
| --- | --- | --- |
| `id` | 稳定主键；供 F006 IP 记录引用 | §4.2.2 |
| `resource_id` | 所属资源，`NOT NULL`；`FK → resources(id) ON DELETE RESTRICT` | §4.1.4、§4.4.2 |
| `name` | 接口名：**去首尾空格后存储/比较、区分大小写、禁止纯空白**；`UNIQUE (resource_id, name)` | §4.2.5、BQ-W |
| `segment_id` | 可选网段（0..1），`NULL` 或 `FK → network_segments(id) ON DELETE RESTRICT`；须属于与本资源**同集群**的**仍存**网段 | §4.2.6、§4.6.9/10、§7.1 |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | 通用 |
| 无 IP 字段 | 本 Feature 网卡不含 IP；IP/管理 IP 属 F006 | F002 scope、F006 |

**必须由数据库保证的关键完整性（`REQUIRED`）**：
1. `UNIQUE (resource_id, name)`（同一资源下接口名唯一、区分大小写）。
2. `resource_id`、`segment_id` 的 RESTRICT FK（不级联；删除保护）。
3. 「网段与本资源同集群」：应用层必须校验；数据库侧建议以**复合 FK**（如 `network_interfaces` 冗余 `resource_cluster_id`，并建 `(resource_id, resource_cluster_id) → resources(id, cluster_id)` 与 `(segment_id, resource_cluster_id) → network_segments(id, cluster_id)`）落实（`PROPOSED`，由 Database 决定；若不采用复合 FK，则该归属为应用保证并在测试覆盖）。

### 3.3 资源历史 / 审计写入（跨 Feature 共享载体，F001 已建）

| 载体 | 行为 | 依据 |
| --- | --- | --- |
| `audit_log`（F013 已建，F001/F005 已用） | F002 以 `target_type='resource'` 追加：`action ∈ {resource.create, resource.update, resource.delete}`；append-only；用户删除后仍可读 | §9.1、ADR-005 |
| `resource_history`（F001 已建，F002 只写） | `target_type='resource'`、`target_id=str(resource.id)`、`target_key_snapshot=resource.name`、`action ∈ {update, delete}`；至少操作者 + 变更/删除内容（`change` JSONB）；**无对业务表的阻塞 FK**；管理员可查、长期保留、不自动到期（查询 API 由 F012） | §4.4.4/6、BQ-N/BQ-Q/BQ-V、BQ-AB、ADR-005 |
| 写入时机 | 资源 `create` 仅写审计；资源 `update`（含网卡增/改/删）写 `resource_history(update)`；资源 `delete` 先写历史与审计再执行 DELETE（同事务） | §4.4.4、场景 47/48 |
| 网卡变更的历史表达 | 网卡显式增/改/删作为资源 `update` 的 `change` 内容承载（`target_type='resource'`）。是否再细化到网卡级记录由 Database 在 F002 设计阶段按 BQ-AB 确定（`PROPOSED`） | BQ-AB、ADR-005 |
| 历史不阻塞删除 | `resource_history`/`audit_log` 不得对 `resources(id)` 建阻塞 FK | §4.4.2、ADR-005 |

### 3.4 Database 设计与 Backend 实现分工

- **Database**（`docs/database/F002.md`）：设计 `resources`、`network_interfaces` 的列/约束/索引；定义对 `clusters(id)`、`network_segments(id)`、`resources(id)` 的 `ON DELETE RESTRICT` FK；确定「网段同集群」的 DB 表达（复合 FK 或应用保证）；给出初始化建表补充（P0 无迁移工具，ADR-002）。**不写业务实现**。
- **Backend**：ORM 映射；名称规范化、payload 接口名去重；创建/编辑/删除事务；网卡显式增/改/删；同名处理；唯一与 FK 冲突 → 409 映射；乐观锁条件更新；审计与历史写入；初始化建表脚本增量。**数据库实现由 Backend 承担**。

---

## 4. 字段表示与校验规则（`CONFIRMED` 规则 + `PROPOSED` 表达）

> 以下为 F002 阶段确定的服务端表达与校验。标 `PROPOSED` 属实现建议，依据标注；如需调整回 Product/Database，可在 Database 设计前修改。

### 4.1 资源名称 `name` `CONFIRMED`（§4.1.2/3、BQ-W）
- 去首尾空格后存储与比较；**区分大小写**；禁止纯空白；同集群仍存资源（裸金属 + VM）统一唯一；真实删除后名称可复用。
- `PROPOSED`：长度上限 128（`char_length(btrim(name)) between 1 and 128`）；未限制字符类别（与集群名不同，需求未要求字符集）。**`OPEN`**：是否需要资源名字符集限制（回 Product，非阻塞）。

### 4.2 资源类型 `resource_type` `CONFIRMED`（§1.3、§4.1.5、场景 34）
- 取值 `bare_metal` / `virtual_machine`。
- 创建时必填；编辑请求若携带与当前不同的值 → `400 INVALID_REQUEST`（`errors[].code=RESOURCE_TYPE_IMMUTABLE`）；携带相同值视为无变化（`PROPOSED`，便于表单回传）。
- 无更新 `resource_type` 的写入路径。

### 4.3 所属集群 `cluster_id` `CONFIRMED`（§4.1.8、场景 50）
- 创建时必填，集群须存在（否则 `404 CLUSTER_NOT_FOUND`，与 F005 一致）。
- 创建后不可改；编辑请求若携带与当前不同的值 → `400 INVALID_REQUEST`（`errors[].code=RESOURCE_CLUSTER_IMMUTABLE`）；相同值视为无变化（`PROPOSED`）。
- 网卡与后续对象以 `resource_id` 关联，改名/改状态不改变归属。

### 4.4 状态 `status` `CONFIRMED`（§4.3、BQ-A、BQ-AA）
- 取值 `IDLE`/`ALLOC`/`DOWN`/`UNKNOWN`；未提供默认 `ALLOC`。
- 状态由资源维护者/管理员更新；状态变更时刷新 `status_updated_by`（操作者）与 `status_updated_at`（仅状态时间）。
- **BQ-AA 表达**：状态来源**仅记录操作者**、不记录外部来源系统；状态相关时间**只有一个** `status_updated_at`，不引入第二个状态时间域；所有受管表通用的 `updated_at` 不承担状态语义。
- `PROPOSED`：创建时（无论是否显式给出状态）`status_updated_by=当前操作者`、`status_updated_at=now()`；非状态字段编辑不改动这两列。

### 4.5 网卡 `network_interfaces` `CONFIRMED`（§4.2.2/4/5/6/7、§4.6.9/10、场景 28/29/30）
- 同一资源下 0..N 张网卡；接口名去首尾空格、区分大小写、禁止纯空白、`UNIQUE (resource_id, name)`。
- 每张网卡可关联 0..1 个网段；**本阶段不分配 IP**；网段可暂不选（§4.6.10），分配 IP 前必须补选（由 F006 验收，场景 30）。
- 网卡请求**不携带** technology/purpose/前缀/VLAN/网关；这些由所选网段只读带出（§4.2.7、场景 28/29）。
- `PROPOSED`：接口名长度上限 128。

### 4.6 网段归属校验 `CONFIRMED`（§4.2.6/7、§4.6.2/6、场景 11 规则侧）
- 网卡所选 `segment_id` 必须：① 存在且仍存（否则 `422 VALIDATION_ERROR`，`errors[].code=INTERFACE_SEGMENT_INVALID`）；② 属于与本资源相同的集群（否则 `422`，`errors[].code=INTERFACE_SEGMENT_CLUSTER_MISMATCH`）。
- 资源编辑时 `cluster_id` 不可变，故网段归属以创建时集群为基准。

---

## 5. 唯一性、同名处理与整单原子

### 5.1 唯一性 `CONFIRMED`（§4.1.2、§4.2.5、§5）
- 同集群仍存资源 `name` 在裸金属与 VM 之间统一唯一（`UNIQUE (cluster_id, name)`）；跨集群允许重复。
- 同一资源下接口名唯一（`UNIQUE (resource_id, name)`）。
- 同一请求 payload 内不得出现重复接口名；服务端在事务内再次校验（前端 §7.2 只做基础校验）。冲突 → `409 RESOURCE_NAME_EXISTS` / `409 INTERFACE_NAME_TAKEN`（payload 内重复 → `422`，`errors[].code=INTERFACE_NAME_DUPLICATE_IN_PAYLOAD`）。
- 数据库唯一约束为最终保证（§9.3、ADR-002）。

### 5.2 同名新增处理 `CONFIRMED`（§4.1.10、场景 2/45）
- `POST /resources` 命中同集群同名仍存资源 → **拒绝创建**，返回 `409 RESOURCE_NAME_EXISTS`，并在 problem+json 扩展成员中返回 `existing_resource_id`（及 `existing_resource_type`），供前端提示进入既有资源编辑。
- 不得创建第二条、不得覆盖或合并；只有用户确认进入编辑后按既有稳定 ID 更新。

### 5.3 整单原子与显式网卡操作 `CONFIRMED`（§4.5、ADR-003）
- 一次提交公共信息 + 全部网卡，作为**一次完整操作**（单事务）：任一校验或写入失败，整单不生效，不出现「资源已创建但第二张网卡失败」等半完成状态。
- 网卡子项采用**嵌套显式操作**（`interfaces[]` 内每项带 `op ∈ {create, update, delete}`），编辑时：
  - `delete`：显式删除指定网卡；
  - `update`：显式修改指定网卡（可改名/改网段）；
  - `create`：新增网卡；
  - **未出现在 `interfaces[]` 中的既有网卡视为未修改**（不删除、不覆盖）。
- `interfaces` 缺省或 `[]` 表示本次不改动网卡；要删除全部网卡须显式给出各 `delete` 项。该表达满足 §4.5「区分删除网卡 / 未修改」与 §4.4「逐项显式先删」，且不引入破坏整单原子的独立网卡端点。

### 5.4 并发控制 `CONFIRMED`（§4.5、§9.3、ADR-003）
- 资源 `PATCH`/`DELETE` 使用 `version` 条件更新（资源级乐观锁覆盖整张表单，含网卡变更）。
- 两人基于同一旧版本编辑同一资源：后提交者 `409 VERSION_CONFLICT`，**保留输入**，刷新确认后重提，不静默覆盖或自动合并（场景 47）。
- 并发新增同名网卡由 `UNIQUE (resource_id, name)` 兜底映射 `409 INTERFACE_NAME_TAKEN`；并发新增同名资源由 `UNIQUE (cluster_id, name)` 兜底映射 `409 RESOURCE_NAME_EXISTS`。

---

## 6. 身份只读、删除前置与二次确认

### 6.1 身份只读 `CONFIRMED`（§4.1.5/8、场景 34/50）
- `resource_type`、`cluster_id` 创建后只读（编辑传不同值拒绝，见 §4.2/§4.3）；改名/改状态不改变归属（网卡以 `resource_id` 关联，场景 5）。

### 6.2 真实删除前置 `CONFIRMED`（§4.4.2/3、BQ-M/BQ-Z、场景 6/46/48）
删除资源前必须全部满足，任一未满足则拒绝、不级联：
1. **仍存网卡未逐项删除** → `409 RESOURCE_HAS_INTERFACES`（DB `ON DELETE RESTRICT` 或事务内计数）；
2. **二次确认 `confirm` 去首尾空格后须等于资源名称（区分大小写）** → 不匹配 `422 DELETE_CONFIRMATION_MISMATCH`，不删除；
3. `version` 不匹配 → `409 VERSION_CONFLICT`。
- 校验顺序（`PROPOSED`）：`401/403` → `404` → `422`（确认不匹配）→ 事务内锁定行后 `409 RESOURCE_HAS_INTERFACES` → `DELETE ... WHERE id AND version` → `23503` 映射 → rowcount 0 → `404`/`409 VERSION_CONFLICT`。
- 无恢复入口；删除/变更资源历史与审计保留（场景 48）。
- **F006 预留**：IP 记录引入后，删除网卡/IP 的逐项前置由 F006 扩展；「删除整个资源不要求先手工清空管理 IP」由 F006 验收。

---

## 7. 权限与审计

### 7.1 复用 F013 基础（`CONFIRMED`）
- 每个受保护端点依赖 `get_current_user`；角色与状态每请求读库，角色变更即时生效、禁用后立即不可用（F013 §2.2）。
- 角色判定使用 `require_roles(*roles)`；越权 → `403 FORBIDDEN`，数据不变。
- 首登未改密拦截由 `get_current_user` 统一处理（`403 PASSWORD_CHANGE_REQUIRED`）。

### 7.2 资源本体鉴权规则（服务端，`CONFIRMED` §2.1）
| 操作 | 允许角色 | 依赖实现 |
| --- | --- | --- |
| 详情（供表单加载） | viewer、maintainer、admin | `get_current_user` |
| 新增（POST）/ 编辑（PATCH） | maintainer、admin | `require_roles("maintainer","admin")` |
| 真实删除（DELETE） | maintainer、admin（仍受删除前置约束） | `require_roles("maintainer","admin")` |

- 查看者只读（写入/删除 → `403`）；切换集群不改变角色权限（§2.1、场景 40）。

### 7.3 审计与资源历史（`CONFIRMED` §9.1、ADR-005）
- 审计统一经 `app.audit.write(db, actor, action, "resource", str(resource.id), resource.name, change, "success")`：
  - `resource.create`：`change={cluster_id, name, resource_type, status, interfaces:[{name, segment_id}]}`；
  - `resource.update`：`change={仅实际变化字段的 from/to; interfaces:{created:[...], updated:[...], deleted:[...]}}`；
  - `resource.delete`：`change={cluster_id, name, resource_type, status}`。
- `resource_history` 写入 `action ∈ {update, delete}`，含操作者快照与变更/删除内容；删除时**先写历史与审计，再执行 DELETE（同事务）**。
- 历史查询与「不自动到期」由 F012 统一提供；本 Feature 不提供查询 API。

---

## 8. API Contract（摘要；唯一字段清单见 `docs/api/F002.md`）

Contract 状态 **READY**。Base：`/api/v1`；错误统一 `application/problem+json`。

| # | Method | Path | 说明 | 角色 |
| --- | --- | --- | --- | --- |
| 1 | POST | `/resources` | 新增资源（公共信息 + 全部网卡，整单原子） | maintainer/admin |
| 2 | GET | `/resources/{resource_id}` | 供表单加载的单资源详情（公共信息 + 网卡 + version） | 任意已登录 |
| 3 | PATCH | `/resources/{resource_id}` | 编辑公共信息 + 网卡显式增/改/删（乐观锁） | maintainer/admin |
| 4 | DELETE | `/resources/{resource_id}` | 真实删除（二次确认 + 乐观锁，存在网卡则拒绝） | maintainer/admin |

- 资源列表/筛选/分页/搜索为 F003；类型详情为 F004；IP/管理 IP 为 F006（均 `out_of_scope`）。
- 错误码：`400 INVALID_REQUEST`（`errors[].code ∈ RESOURCE_TYPE_IMMUTABLE`/`RESOURCE_CLUSTER_IMMUTABLE`/`NO_FIELDS`/`INVALID_INTERFACE_OP`）、`422 VALIDATION_ERROR`（`errors[].code ∈ NAME_FORMAT`/`RESOURCE_TYPE_INVALID`/`STATUS_INVALID`/`INTERFACE_NAME_FORMAT`/`INTERFACE_NAME_DUPLICATE_IN_PAYLOAD`/`INTERFACE_NOT_FOUND`/`INTERFACE_SEGMENT_INVALID`/`INTERFACE_SEGMENT_CLUSTER_MISMATCH`）、`422 DELETE_CONFIRMATION_MISMATCH`、`401 UNAUTHENTICATED`、`403 FORBIDDEN`、`404 RESOURCE_NOT_FOUND`/`CLUSTER_NOT_FOUND`、`409 RESOURCE_NAME_EXISTS`（附 `existing_resource_id`）、`409 INTERFACE_NAME_TAKEN`、`409 RESOURCE_HAS_INTERFACES`、`409 VERSION_CONFLICT`。

---

## 9. Frontend / Backend 工作拆分

**Backend**：`app.resources`（router/schemas/service/models）；名称规范化与 payload 去重；创建/编辑/删除事务；网卡显式增/改/删；网段归属校验；同名处理与 `existing_resource_id`；唯一与 FK 冲突 → 409 映射；乐观锁条件更新；二次确认校验；审计与资源历史写入；初始化建表增量；pytest + httpx 测试。

**Frontend**：资源表单页（新增/编辑）；网卡卡片增删；网段选择（本集群仍存，0..1）；选定网段只读带出技术/用途/前缀/网关；同名提示进入编辑；真实删除二次确认（须输入资源名称）；冲突保留输入；problem+json 字段/记录级错误定位；`useClusterStore` 复用；Vitest 单测。

**Database**：按 §3 设计 `resources`、`network_interfaces`，含对 `clusters(id)`、`network_segments(id)`、`resources(id)` 的 `ON DELETE RESTRICT` FK、唯一约束、索引（及网段同集群的 DB 表达）；交付初始化建表增量。实现由 Backend 承担。

---

## 10. Test Work

**后端集成（pytest + httpx）**：
- 身份/唯一性：同集群资源名去首尾空格、区分大小写唯一、纯空白拒绝；裸金属与 VM 合并判重（场景 2）；跨集群同名允许；同资源下接口名唯一；payload 内重复接口名拒绝；跨集群相同 IP/名称不冲突（IP 部分 F006）。
- 同名新增：`409 RESOURCE_NAME_EXISTS` 且返回 `existing_resource_id`，不创建第二条、不覆盖、不合并（场景 2/45）。
- 只读字段：编辑传不同 `resource_type` → `400 RESOURCE_TYPE_IMMUTABLE`；传不同 `cluster_id` → `400 RESOURCE_CLUSTER_IMMUTABLE`；相同值容忍（场景 34/50）。
- 网卡：新增/编辑/删除网卡；`interfaces` 省略/空数组=未修改；显式 `delete` 删除；改名/改网段；网段存在性/同集群校验（`INTERFACE_SEGMENT_INVALID`/`INTERFACE_SEGMENT_CLUSTER_MISMATCH`）；网段只读属性不由网卡请求携带（场景 28/29）。
- 整单原子：一次提交中第二张网卡失败 → 资源与首张网卡均不残留（场景 43 规则侧、§4.5）。
- 删除前置：存在网卡 → `409 RESOURCE_HAS_INTERFACES`，不级联；删除全部网卡后可删资源；`confirm` 不匹配 → `422` 不删除（BQ-Z）；`version` 冲突（场景 6/46/48）。
- 并发：同旧 version 编辑 → 后提交 `409 VERSION_CONFLICT`，输入保留由前端联验（场景 47）。
- 权限：viewer 写/删 403；maintainer/admin 允许；未登录 401；集群切换不改变权限（场景 40 规则侧）。
- 审计/历史：`resource.create/update/delete` 审计行；`update`/`delete` 资源历史行；删除后仍在；`target_type='resource'`。
- 网段删除保护行为侧：为含网卡的网段在 F005 侧删除 → `409 SEGMENT_HAS_INTERFACES`（由 F002 的 RESTRICT FK 触发）。
- 集群删除保护行为侧：为含计算资源的集群在 F001 侧删除 → `409 CLUSTER_HAS_ASSOCIATIONS`。

**数据库约束测试**：`UNIQUE(cluster_id, name)`、`UNIQUE(resource_id, name)`、`chk` 名称/枚举/version、`ON DELETE RESTRICT`（clusters/network_segments/resources）。

**前端（Vitest）**：表单结构、网卡卡片增删、网段选择与只读带出、同名提示进入编辑、冲突保留输入、删除二次确认、字段/记录级错误映射、权限隐藏。

**联验（非本 Feature 闭环）**：IP 与管理 IP（F006，场景 1/3/4/9/30/43/44、场景 46 的管理 IP 部分）；类型详情与宿主（F004，场景 1/2/13/14/15/33）；服务/VM 关联删除拒绝（F007，场景 6/46/51）；列表/详情展示（F003，场景 8/32）；管理员历史查询（F012，场景 48/61/64）；跨对象权限一致性（F009，场景 40）、全平台终局（F011，场景 57）。

---

## 11. 技术决策与风险

**已确认（依据）**：栈 ADR-001；PostgreSQL 唯一性 DB 保证、真删 + 无软删、无迁移工具 ADR-002；REST/problem+json/乐观锁 409/offset 分页/显式子项操作 ADR-003；HTTP-only/无备份 ADR-004；审计与历史分表、append-only、管理员可查、长期 ADR-005；资源登记/网卡/原子/删除规则 §4.1–§4.5、§6.4、§7.2/§7.3；名称口径 BQ-W；删除二次确认 BQ-Z；状态来源与时间 BQ-AA；网卡/IP 单独真删历史表达委派 BQ-AB；权限 §2.1；F001/F005/F013 复用基础。

**PROPOSED（不阻塞）**：
1. 资源名、接口名长度上限 128；无字符集限制（仅 §4.1 的空白/大小写口径）；
2. 编辑传相同 `resource_type`/`cluster_id` 视为无变化，不报错；
3. 网卡子项用嵌套显式 `op ∈ {create,update,delete}`；缺省=未修改；
4. 网段同集群归属优先以复合 FK 落实，否则应用保证并测试覆盖；
5. `RESOURCE_HAS_INTERFACES` 用 `ON DELETE RESTRICT` + `23503`（按 `constraint_name` 映射）；
6. 创建/状态变更时刷新 `status_updated_by`/`status_updated_at`；非状态编辑不刷新；
7. 网卡变更在 `resource_history(update)` 的 `change` 内结构化承载；是否细化到网卡级记录由 Database 按 BQ-AB 决定；
8. 接口列表默认按 `name` 稳定排序（前端卡片顺序由前端维护）。

**OPEN / 关注（非阻塞 Database 设计）**：
- 资源名/接口名是否需字符集或长度上限（回 Product 在 Database 设计前确认）；
- `resource_history` 网卡级历史表达（BQ-AB 委派）；F012 查询口径须一致；
- 「网段同集群」DB 表达（复合 FK 与否）由 Database 决定；
- IP/管理 IP 与含 IP 整单原子由 F006 引入后验收；F002 不以 IP 字段预留。

---

## 12. Implementation Layers

| Layer | 需要 | 说明 |
| --- | --- | --- |
| database | **true** | `resources`、`network_interfaces` + 唯一约束/索引 + 对 `clusters(id)`、`network_segments(id)`、`resources(id)` 的 RESTRICT FK + 初始化建表增量；Database 设计、Backend 实现 |
| backend | **true** | 资源模块、名称规范化、网卡显式增/改/删、同名处理、整单事务、鉴权复用、审计/历史写入、错误映射 |
| frontend | **true** | 资源表单、网卡卡片、网段选择、同名进入编辑、删除二次确认、冲突保留输入、错误映射 |

结论：**READY FOR IMPLEMENTATION**（实现仍须通过独立 Database Design 与 Contract Gate）。