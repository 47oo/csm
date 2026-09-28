# F005 网段、保留地址与网段历史写入 — 架构方案

> Status: READY FOR IMPLEMENTATION
> Document Type: Feature Architecture
> Feature: F005（Epic E4，P0）
> 依据：`requirements-v2.md` §2.1/§4.4/§4.5/§4.6/§5/§6.5/§8/§9.1、§10 场景 10/11/12/26/27/40/52/53/60/61/62/64/65/82、§11.1 BQ-M/BQ-N/BQ-O/BQ-R/BQ-W/BQ-Z；
>      `domain-model.md` §1/§2/§3/§4/§5/§6；ADR-001…ADR-005；
>      复用 `docs/architecture/F001-cluster-registry.md` §2/§3/§4、`docs/architecture/F013-user-role-management.md` §2.2/§2.3/§4、`docs/database/F001.md` §2.3；
>      `docs/project/project-plan.yaml` F005
> 关联 Contract：`docs/api/F005.md`（唯一字段清单）
> 创建日期：2026-09-25

本文件只记录实现层架构方案。产品/领域事实以 `docs/product/` 为准；技术栈、数据库、API、部署、历史审计载体以 ADR 为准。标记：`CONFIRMED` / `PROPOSED` / `OPEN`。

---

## 1. 方案摘要

F005 在 ADR 既定架构内新增一个受管对象模块「网段（NetworkSegment）及其保留地址」，交付：

1. 一个集群下多个 IPv4 网段的登记、列表、详情、编辑（名称、规范化 CIDR、用途、技术类型、VLAN、网关、自动分配范围）；
2. 保留地址子项的显式增/删（单个地址或起止范围），网关属性的设置与显式清空；
3. 网段身份与唯一性：同集群仍存网段名称唯一（去首尾空格、区分大小写）、规范化 CIDR 唯一；跨集群允许相同 CIDR；同集群重叠仅提示、允许保存；
4. 保留地址（含范围两端）与网关必须落在所属网段 CIDR 内；
5. 网段真实删除前置：逐项删除已分配 IP（F006 引入）、逐条删除保留地址、显式清空网关、解除仍存网卡引用，不级联；
6. 存在已分配 IP 时禁止修改 CIDR（F006 引入分配后生效，F005 提供规则与检查边界）；
7. 「可自动分配数量」「已分配数量」的 §5/§6.5 快照口径计算（F005 交付不含 IP 的可验证子集，已分配数量 = 0，F006 扩展）；
8. 本对象服务端三角色鉴权、操作审计与网段删除/变更资源历史写入（append-only）；
9. 真实删除二次确认（BQ-Z）：须按提示输入网段名称匹配后才可提交；
10. 作为后续 Feature 的网段归属与删除保护目标侧：F005 建立 `network_segments.cluster_id → clusters(id) ON DELETE RESTRICT` 与 `segment_reserved_addresses.segment_id → network_segments(id) ON DELETE RESTRICT`，使 F001 的集群删除保护、及其自身的段删除保护由数据库约束保证。

**复用 F001 / F013 依赖（不复制实现，`CONFIRMED`）**：
- `app.security.principal.get_current_user` → `Principal{user_id, username, role, must_change_password, status}`；
- `app.security.principal.require_roles(*roles)` → 越权 403；
- `app.audit.write(...)`（审计，append-only，`target_type='segment'`）；
- `app.resource_history.write(...)`（**F001 已建表与写入接口**，F005 只写入 `target_type='segment'`，不建表、不提供查询）；
- `app.errors.problem(...)` / problem+json 统一错误体；`app.db.get_db`。

**初始化顺序（`CONFIRMED`）**：F013 `users` → F001 `clusters` + `resource_history` → F005 `network_segments` + `segment_reserved_addresses`。F005 不重复建 `resource_history`/`audit_log`。

---

## 2. 模块边界

### 2.1 后端模块（Python 3.12 + FastAPI，ADR-001）

| 模块 | 职责 | 明确的非职责 |
| --- | --- | --- |
| `app.network_segments`（网段本体） | 网段列表/新增/详情/编辑/真实删除；名称与 CIDR 唯一；重叠检测与提示；保留地址增删；网关设置/清空；自动分配范围；删除前置；写审计与资源历史 | 不实现登录/会话/角色判定（依赖 `security.principal`）；不实现 IP 分配算法与并发（F006）；不实现网卡录入（F002）；不提供资源历史查询（F012） |
| `app.network_segments.addressing`（纯函数小工具，**供 F006 复用**） | `normalize_cidr(raw)->str`；`ipv4_to_int`/`int_to_ipv4`；`cidr_range(cidr)->(int,int)`；`ranges_overlap(a,b)->bool`；`excluded_nums(segment, overlapping_segments)->set[int]`；`auto_assignable_count(...)`；`contains(cidr, ip)->bool` | 不访问数据库、不写业务规则；只做 §5 口径的地址集合运算 |
| `app.network_segments.models` | `NetworkSegment`、`SegmentReservedAddress` ORM 映射（Schema 由 Database 设计） | 不定义其他 Feature 的表 |
| 复用 `app.security.principal` | 操作者解析与三角色鉴权 | 见 §1 |
| 复用 `app.audit` / `app.resource_history` | 操作审计与资源历史写入（append-only） | 不查审计/历史 |
| 复用 `app.errors` / `app.db` | 统一错误体、会话 | — |

模块依赖方向：`network_segments → security.principal`、`network_segments → audit`、`network_segments → resource_history`、`network_segments → clusters(models only, 用于 FK/存在性)`。禁止 `network_segments` 反向依赖 `users`（只依赖 `security.principal`），与 F013 §2.1/F001 §2.1 一致。

### 2.2 与 F001 的关系（`CONFIRMED`）

- F005 引入 `network_segments.cluster_id → clusters(id) ON DELETE RESTRICT`。这样 F001 的集群删除在「仍存网段关联」时由 `SQLSTATE 23503` → `409 CLUSTER_HAS_ASSOCIATIONS` 捕获，满足 §4.1.9、场景 51（网段侧）与 §4.6.2。
- F005 **不修改** F001 代码；仅新增表与 FK，并复用其错误映射约定（见 F001 §2.2）。

### 2.3 与 F002 / F006 的引用保护边界（`CONFIRMED` 规则，`PROPOSED` 机制）

- 需求 §5/§4.4 要求：网段仍有已分配 IP、仍存网卡引用时禁止删除；存在已分配 IP 时禁止修改 CIDR。**F005 定义规则、错误码与检查边界**；具体引用对象由 F002/F006 建立。
- 机制（`PROPOSED`，最小实现，不预建注册框架）：
  - 网卡引用（F002）：`network_interfaces.segment_id → network_segments(id) ON DELETE RESTRICT` → 删除网段时 `23503` → `409 SEGMENT_HAS_INTERFACES`；
  - IP 分配引用（F006）：IP 分配记录对 `network_segments(id)` 建 `ON DELETE RESTRICT` → `409 SEGMENT_HAS_ALLOCATIONS`；
  - 存在已分配 IP 时禁止改 CIDR（F006）：F005 提供 `SegmentUsage.allocated_count(segment_id) -> int` 扩展点，**F005 阶段恒为 0**；F006 接入真实查询后返回 >0 → `409 CIDR_IMMUTABLE`。
- 历史/审计表不得对 `network_segments(id)` 建阻塞 FK；`resource_history`/`audit_log` 用 `target_id text`、无 FK，保证「仅余历史不阻止删除，历史保留」。

### 2.4 前端页面 / 路由 / 状态（Vue 3 + TS + Vite + Element Plus，ADR-001）

| 区域 | 内容 |
| --- | --- |
| 网段页面 `/clusters/:clusterId/segments`（集群内列表） | 列表（分页、`q` 搜索、排序）、新增/编辑对话框、真实删除二次确认（须输入网段名称）、重叠提示、保留地址增删、网关设置/清空、自动分配范围 |
| 网段详情 | §6.5 全字段；保留地址列表；「已分配 IP 及归属」占位页签（数据由 F006 提供，F005 显示空态与后续 Feature 提示）；已分配数量、可自动分配数量快照 |
| Pinia `useClusterStore`（复用 F001） | 当前集群决定网段页面作用域；切换集群刷新列表；**选择只改变查询作用域，不改变角色权限** |
| axios | 复用 F013/F001 拦截：401→登录、403→提示、problem+json 字段级错误、409→冲突/删除前置提示、422→二次确认不一致/字段校验提示 |

前端权限仅用于导航/隐藏，**不作为安全边界**；最终由服务端校验。

---

## 3. 数据影响（Architect 声明的数据行为，Schema 由 Database 设计）

> 本节声明**必须保障的行为与约束**；列类型/索引名/DDL 由 Database 在 `docs/database/F005.md` 设计并交 Backend 实现。F005 `layers.database=true`。

### 3.1 `network_segments`（网段主表，新增）

| 行为 | 说明 | 依据 |
| --- | --- | --- |
| `id` | 稳定主键（`BIGINT`），供 F002 网卡与 F006 IP 分配 `segment_id` 引用 | §4.6.2 |
| `cluster_id` | 所属集群，`NOT NULL`；`FK → clusters(id) ON DELETE RESTRICT` | §4.6.2、§4.1.9、场景 51 |
| `name` | 网段名：**去首尾空格后**存储/比较、**区分大小写**、禁止纯空白；同集群仍存网段内唯一 | §4.6.3、BQ-W、domain §5 |
| `cidr` | 展示值：规范化后的 IPv4 CIDR（如 `192.168.1.0/24`） | §4.6.3、ADR-002 |
| `cidr_key` | 比较键：`ipaddress` 规范化网络地址字符串；同集群（`cluster_id, cidr_key`）唯一；跨集群可重复 | §4.6.3/4、ADR-002 |
| `purpose` | 用途；`NOT NULL`、非空字符串（表示见 §4） | §4.6、§6.5 |
| `technology` | 技术类型；`NOT NULL`、非空字符串（表示见 §4） | §4.6、§6.5 |
| `vlan` | VLAN；`NULL` 表示未填 | §6.5 |
| `gateway` / `gateway_num` | 网关：单个 IPv4 或 `NULL`；`gateway_num` 为数值比较键（或 Database 选定等价表达） | §5、§6.5、BQ-O |
| `auto_alloc_start` / `auto_alloc_end`（+ 数值键） | 自动分配起止；两者同时为 `NULL`（未启用）或同时非空；非空时须在 CIDR 内且起 ≤ 止 | §5、场景 20/21/25/65 |
| `version` | 乐观锁（编辑/删除条件更新） | ADR-003 |
| `created_at` / `updated_at` | `TIMESTAMPTZ`；更新时由 Backend 刷新 | 通用 |
| 无 `status`/`deleted_at` | 网段无停用/逻辑删除状态；真实删除即删行 | §4.6、§5、BQ-C/BQ-M |

**必须由数据库保证的关键完整性（`REQUIRED`，依据 §9.3、ADR-002）**：
1. `UNIQUE (cluster_id, name)`（仍存网段内名称唯一、区分大小写）；真实删除后行即删，名称可复用。
2. `UNIQUE (cluster_id, cidr_key)`（同集群规范化 CIDR 唯一）；不同 `cluster_id` 允许相同 `cidr_key`。
3. CIDR / 地址格式与范围合法性由 Backend 校验（`ipaddress`）并可辅以 CHECK（Database 决定）。
4. `version` 条件更新实现乐观锁。

### 3.2 `segment_reserved_addresses`（保留地址，新增）

| 行为 | 说明 | 依据 |
| --- | --- | --- |
| `id` | 稳定主键 | §5 |
| `segment_id` | 所属网段，`NOT NULL`；`FK → network_segments(id) ON DELETE RESTRICT` | §4.4.2、§5、BQ-O |
| `start_ip` / `end_ip`（+ 数值键） | 保留范围：单个地址 `start == end`；范围两端须落在所属网段 CIDR 内且起 ≤ 止 | §5、场景 53 |
| `created_at` | 创建时间 | 通用 |
| 无 `status` | 保留地址逐条真实删除、无逻辑删除 | §4.4、BQ-O |

**行为**：
- 新增/删除保留地址为**显式独立操作**（ADR-003 显式子项操作）；删网段前须逐条删除；
- 保留地址随时间动态影响「不可分配地址」与「可自动分配数量」（§5、BQ-R），不预占；
- 历史快照中的保留地址/网关不参与任何分配排除（§5、BQ-O）——**排除计算只读现存 `network_segments`/`segment_reserved_addresses` 行，绝不读 `resource_history`**。

### 3.3 网段历史 / 审计写入（跨 Feature 共享载体，F001 已建）

| 载体 | 行为 | 依据 |
| --- | --- | --- |
| `audit_log`（F013 已建，F001 已用） | F005 以 `target_type='segment'` 追加：`action ∈ {segment.create, segment.update, segment.delete, segment.reserved_address.create, segment.reserved_address.delete, segment.gateway.clear}`；append-only；用户删除后仍可读 | §9.1、ADR-005 |
| `resource_history`（F001 已建，F005 只写） | 受管对象删除/变更历史 append-only：至少操作者 + 删除/变更内容；`target_type='segment'`、`target_id=str(segment.id)`、`target_key_snapshot=segment.name`、`action ∈ {update, delete}`；**无对业务表的阻塞 FK**；管理员可查、长期保留、不自动到期（查询 API 由 F012） | §4.4.4/6、BQ-N/BQ-Q/BQ-V、ADR-005 |
| 写入时机 | 网段 `create` 仅写审计；网段 `update`/`delete`、保留地址增删、网关清空写 `resource_history`；删除时**先写历史与审计，再执行 DELETE（同事务）** | §4.4.4、场景 60/61/64 |

### 3.4 Database 设计与 Backend 实现分工

- **Database**（`docs/database/F005.md`）：设计 `network_segments`、`segment_reserved_addresses` 的列/约束/索引；定义对 `clusters(id)`、`network_segments(id)` 的 `ON DELETE RESTRICT` FK；给出初始化建表补充（P0 无迁移工具，ADR-002）。**不写业务实现**。
- **Backend**：ORM 映射；`normalize_cidr`/地址纯函数；创建/编辑/删除事务；唯一与 FK 冲突 → 409 映射；保留地址与网关操作；计数与重叠计算；审计与历史写入；初始化建表脚本增量。**数据库实现由 Backend 承担**。

---

## 4. 字段表示与校验规则（`CONFIRMED` 规则 + `PROPOSED` 表达）

> 以下为 F005 阶段确定的服务端表达与校验。标 `PROPOSED` 的属实现建议，依据标注；如需调整回 Product/Database，可在 Database 设计前修改。

### 4.1 名称 `CONFIRMED`（§4.6.3、BQ-W）
- 去首尾空格后存储与比较；**区分大小写**；禁止纯空白。
- 同集群仍存网段内唯一；跨集群可重复；真实删除后名称可复用。
- `PROPOSED`：长度上限 128（`char_length(trim(name)) between 1 and 128`）；未限制字符类别。**`OPEN`**：是否需要字符集限制（与集群名不同，需求未要求）。

### 4.2 CIDR `CONFIRMED`（§4.6.3/4、§5、场景 11）
- 仅 IPv4；用 Python `ipaddress` 解析，`IPv4Network(raw, strict=False)`；IPv6/非法 → `422 VALIDATION_ERROR`（`errors[].code=CIDR_INVALID`/`CIDR_NOT_IPV4`）。
- `cidr_key = str(network)`（规范化网络地址，如前缀内主机位被归零）。因为 CIDR 的规范化是**全函数**（网络地址 + 前缀唯一确定），`cidr` 展示值即 `cidr_key`；与 F001 `code` 的「展示保留输入形态、比较键单独存储」不同，此处展示与比较键一致（ADR-002 允许比较键单独存储，本处无需）。
- `PROPOSED`：接受带主机位的输入（如 `192.168.1.5/24`）并规范化为 `192.168.1.0/24`；前缀 `/0`–`/32` 均可接受。**`OPEN`**：是否要求用户必须输入网络地址（若 Product 希望严格，改为拒绝主机位）。
- 唯一性：`(cluster_id, cidr_key)` 唯一；跨集群允许相同 CIDR。

### 4.3 用途 `purpose`、技术类型 `technology` `PROPOSED`（§4.6、§6.5）
- 依据 §6.5 展示项与 §4.2.7「技术、用途由所选网段关联展示」：二者为网段属性。
- `PROPOSED`：均 `NOT NULL`、去首尾空格后非空、长度 ≤ 100（purpose 可至 200）；自由文本。
- **`OPEN`**：是否受控枚举（如 technology ∈ {Ethernet, InfiniBand}）及取值集；需求未确认。F005 以自由文本交付，不阻塞；若 Product 后续确认枚举，在 Database 设计前调整（P0 无迁移工具，须在实现前定稿）。

### 4.4 VLAN `PROPOSED`（§6.5）
- `PROPOSED`：`NULL` 或整数 `1–4094`（0/4095 为保留值，802.1Q 常用范围）。非法 → `422 VALIDATION_ERROR`（`errors[].code=VLAN_INVALID`）。
- **`OPEN`**：VLAN 具体范围/是否必填，需求未确认。

### 4.5 网关 `gateway` `CONFIRMED`（§5、BQ-O、场景 27/53）
- 网段属性，`NULL` 表示未设置；真实删除前必须显式清空。
- 单个 IPv4 地址（**`PROPOSED`**：需求 §6.5 以单数「网关」展示、§5 以单值参与排除；若 Product 要求多网关，须先确认）。
- `CONFIRMED`：必须落在所属网段 CIDR 内，否则 `422`（`errors[].code=GATEWAY_OUT_OF_CIDR`，场景 53）。
- `PROPOSED`：不额外禁止网关等于网络/广播地址（需求仅要求「落在 CIDR 内」）；该地址无条件进入分配排除集。
- 设置：`PATCH` 传非空 IPv4；清空：`PATCH` 传 `null` **或** 显式 `DELETE .../gateway`（见 Contract §2.9）。

### 4.6 自动分配范围 `CONFIRMED`（§5、场景 20/21/25/65）
- 两端均须在 CIDR 内且起始 ≤ 结束；未启用时两端为 `NULL`。
- `PROPOSED`：启用/未启用以「两端是否非空」判定；只提供一端 → `422`（`errors[].code=AUTO_RANGE_INVALID`）；提供两端 `null` 即清空。
- `CONFIRMED`：缩小自动分配范围不回收已有分配（仅影响后续选址与计数快照）。
- 地址耗尽不自动切换网段（分配逻辑属 F006）。

### 4.7 保留地址 `CONFIRMED`（§5、场景 53）
- 单个地址（`start_ip == end_ip`）或起止范围；两端须落在所属网段 CIDR 内、起 ≤ 止，否则 `422`（`errors[].code=RESERVED_OUT_OF_CIDR`/`RESERVED_RANGE_INVALID`）。
- 保留地址不绑定网卡；参与同集群分配排除（含跨重叠网段）。
- `PROPOSED`：同一网段内新增保留范围若与已有保留范围**重叠或重复** → `422`（`errors[].code=RESERVED_OVERLAP`）；网关与保留地址重叠允许（二者均仅为排除集元素）。**`OPEN`**：是否允许同一地址重复保留。

### 4.8 网络/广播地址与特殊前缀 `CONFIRMED`（§5）
- 普通网段（前缀 ≤ 30）：网络地址与广播地址不可分配（进入排除集）；`/31` 为点到点、两地址均可用；`/32` 单主机地址可用。
- 这些分配排除规则**在 F005 定义**（作为 §5 口径的一部分，供 F006 使用），其端到端分配验收归 F006（场景 20/21/65）。

---

## 5. 唯一性、重叠与分配排除

### 5.1 唯一性与重叠 `CONFIRMED`（§4.6.3/4/5、场景 12）
- 同集群名称唯一（去首尾空格、区分大小写）→ 冲突 `409 SEGMENT_NAME_TAKEN`。
- 同集群规范化 CIDR 唯一 → 冲突 `409 SEGMENT_CIDR_TAKEN`；跨集群允许相同 CIDR。
- 同集群重叠（两 CIDR 地址区间相交但规范化 CIDR 不等）：**仅提示风险、允许保存**；重叠不豁免名称/CIDR 唯一性与 §5 分配约束。
- 重叠检测（`PROPOSED` 算法）：将 CIDR 转为 `[net_num, bcast_num]` 整数区间，相交即重叠。创建/编辑成功后返回 `overlaps: [{segment_id, name, cidr}]` 与 `has_overlap`；不阻断保存。

### 5.2 分配排除集 `CONFIRMED`（§5、BQ-R、场景 52/65）
对网段 S 的地址可用性（供手动/自动分配与「可自动分配数量」），排除：
1. 同集群已分配 IP 地址（F006；F005 贡献空集）；
2. S 自身登记的保留地址（含范围）与网关；
3. 同集群**其它仍存重叠网段** T（T.cidr 与 S.cidr 相交）的保留地址与网关；
4. 适用网络/广播地址：对每个前缀 ≤ 30 且与 S 重叠的**仍存**网段（含 S 自身），若其网络地址或广播地址落在 S 的自动分配范围内，则排除；`/31`、`/32` 不产生网络/广播排除。
- 已真实删除网段的保留地址/网关仅存在于 `resource_history`，**不参与排除**（§5、BQ-O、场景 62）。
- **`PROPOSED`**：第 4 条「适用网络/广播」解释为「所有仍存重叠网段（含自身）的、落在 S 自动范围内的网络/广播地址」，直接对应 BQ-R 措辞；F005 可完整计算（不依赖 F006）。

---

## 6. 删除前置、CIDR 修改与其它边界

### 6.1 真实删除前置 `CONFIRMED`（§4.4、§5、BQ-N/O/Z、场景 60/82）
删除网段前必须全部满足，任一未满足则拒绝、不级联：
1. **存在已分配 IP** → `409 SEGMENT_HAS_ALLOCATIONS`（F006 引入；F005 阶段无分配，必然为空）；
2. **仍存保留地址未逐条删除** → `409 SEGMENT_HAS_RESERVED_ADDRESSES`（DB `ON DELETE RESTRICT` 或事务内计数）；
3. **网关未显式清空** → `409 SEGMENT_GATEWAY_NOT_CLEARED`（事务内读列）；
4. **仍被网卡引用** → `409 SEGMENT_HAS_INTERFACES`（F002 引入，`ON DELETE RESTRICT`）；
5. **二次确认 `confirm` 不匹配网段名称** → `422 DELETE_CONFIRMATION_MISMATCH`，不删除（BQ-Z）；
6. `version` 不匹配 → `409 VERSION_CONFLICT`。
- 校验顺序（`PROPOSED`）：`401/403` → `404` → `422`（确认不匹配）→ 事务内锁定行后 `409` 保留/网关 → `DELETE ... WHERE id AND version` → `23503` 映射 `SEGMENT_HAS_ALLOCATIONS`/`SEGMENT_HAS_INTERFACES` → rowcount 0 → `404`/`409 VERSION_CONFLICT`。

### 6.2 CIDR 修改边界 `CONFIRMED` 规则 / `PROPOSED` 机制（§5、场景 11）
- 存在已分配 IP 时禁止修改 CIDR → `409 CIDR_IMMUTABLE`（F006 验收；F005 通过 `SegmentUsage.allocated_count` 扩展点提供检查，F005 阶段恒为 0）。
- 无已分配 IP 时可修改 CIDR，但须同时满足：
  - 新 CIDR 规范化后不与同集群其它网段重复（`409 SEGMENT_CIDR_TAKEN`）；
  - 既有网关、自动分配范围必须仍在新 CIDR 内；同一 `PATCH` 中可一并调整，否则 `422`（`GATEWAY_OUT_OF_CIDR`/`AUTO_RANGE_INVALID`）；
  - 既有保留地址若将落在新 CIDR 外 → `422`（`RESERVED_OUT_OF_CIDR`），须先逐条删除相应保留地址再修改 CIDR。
- `PROPOSED`：以上「CIDR 收窄须先处理既有配置」的交互；需求未确认具体 UX。

### 6.3 并发控制 `CONFIRMED`（§9.3、ADR-003）
- 网段 `PATCH`/`DELETE` 使用 `version` 条件更新（ADR-003）。
- **网段 `PATCH`、保留地址新增、网关清空（及删除网段）**在事务内对父网段 `SELECT ... FOR UPDATE` 串行化，避免与 CIDR 修改竞争导致「保留地址落在 CIDR 外」；**不**改变父网段 `version`（`PROPOSED`：`version` 只跟踪可编辑网段属性，见 Contract）。删除单条保留地址不获取父行锁（删除不破坏该不变量）。
- 地址唯一性（IP）由数据库/后端最终保证属 F006。

---

## 7. 计数口径与 F006 扩展点（§5 BQ-R、§6.5）

### 7.1 `auto_assignable_count`（可自动分配数量）— **F005 完整交付**
- 定义：当前查询时，在**已启用的自动分配范围**内满足 §5 全部可自动分配条件的地址数；未启用自动分配范围时为 0；为随记录变化的**快照、非预占**。
- F005 计算式（不含已分配 IP，因 F005 阶段无分配）：
  `count = |{ ip ∈ [auto_alloc_start, auto_alloc_end] : ip ∉ excluded_nums(S, overlaps) }|`
  其中 `excluded_nums` 见 §5.2 第 2/3/4 类（已分配地址集为空）。
- 交付子集可独立验证：场景 10/12/53，及在无 IP 分配前提下对保留/网关/网络广播/`/31`/`/32` 的计数正确性。

### 7.2 `allocated_count`（已分配数量）— **F005 占位，F006 扩展**
- 定义：该网段当前已分配 IP 数量。
- F005 阶段恒为 `0`（无 IP 分配与网卡对象）。
- 扩展方式（F006）：以真实「IP 分配」查询替换 `SegmentUsage.allocated_count` / `allocated_ip_nums`；`excluded_nums` 纳入同集群已分配地址。**F005 不反向依赖 F002/F006**。

### 7.3 「已分配 IP 及归属」展示
- §6.5 要求支持查看已分配 IP 及归属。F005 提供页面占位（空态 + 指向 F006 的说明），**不提供已分配 IP 列表 API**（由 F006 交付）；F005 Contract 声明该子视图 `NOT_REQUIRED`。

---

## 8. 权限与审计

### 8.1 复用 F013 基础（`CONFIRMED`）
- 每个受保护端点依赖 `get_current_user`；角色/状态每请求读库，角色变更即时生效、禁用后立即不可用（F013 §2.2）。
- 角色判定用 `require_roles(*roles)`；越权 → `403 FORBIDDEN`，数据不变。
- 首登未改密拦截由 `get_current_user` 统一处理（`403 PASSWORD_CHANGE_REQUIRED`）。

### 8.2 网段本体鉴权（服务端，`CONFIRMED` §2.1）
| 操作 | 允许角色 | 依赖实现 |
| --- | --- | --- |
| 列表 / 详情 / 保留地址读取 | viewer、maintainer、admin | `get_current_user` |
| 新增 / 编辑（PATCH）/ 保留地址增删 / 网关设置与清空 | maintainer、admin | `require_roles("maintainer","admin")` |
| 真实删除 | maintainer、admin（仍受删除前置约束） | `require_roles("maintainer","admin")` |

- 查看者只读（写入/删除 → `403`）；切换集群不改变角色权限（§2.1、场景 40）。

### 8.3 审计与资源历史（`CONFIRMED` §9.1、ADR-005）
- 审计统一经 `app.audit.write(db, actor, action, "segment", str(segment.id), segment.name, change, "success")`：
  - `segment.create`：`change={name, cidr, purpose, technology, vlan, gateway, auto_alloc_start, auto_alloc_end}`；
  - `segment.update`：`change={仅实际变化字段的 from/to}`（含 `cidr` 变更）；
  - `segment.delete`：`change={name, cidr}`；
  - `segment.reserved_address.create` / `segment.reserved_address.delete`：`change={reserved_id, start_ip, end_ip}`；
  - `segment.gateway.clear`：`change={gateway:{from,to:null}}`。
- `resource_history` 写入 `action ∈ {update, delete}`，含操作者快照与变更/删除内容；删除时先写历史与审计再删行（同事务）。
- 历史查询与「不自动到期」由 F012 统一提供；本 Feature 不提供查询 API。

---

## 9. API Contract（摘要；唯一字段清单见 `docs/api/F005.md`）

Contract 状态 **READY**。Base：`/api/v1`；错误统一 `application/problem+json`。

| # | Method | Path | 说明 | 角色 |
| --- | --- | --- | --- | --- |
| 1 | GET | `/network-segments` | 网段列表（按集群筛选、分页、`q`、排序） | 任意已登录 |
| 2 | POST | `/network-segments` | 新增网段 | maintainer/admin |
| 3 | GET | `/network-segments/{segment_id}` | 网段详情（含保留地址、计数、重叠） | 任意已登录 |
| 4 | PATCH | `/network-segments/{segment_id}` | 编辑属性（乐观锁；CIDR 条件可变） | maintainer/admin |
| 5 | DELETE | `/network-segments/{segment_id}` | 真实删除（二次确认 + 乐观锁） | maintainer/admin |
| 6 | GET | `/network-segments/{segment_id}/reserved-addresses` | 保留地址列表 | 任意已登录 |
| 7 | POST | `/network-segments/{segment_id}/reserved-addresses` | 新增保留地址/范围 | maintainer/admin |
| 8 | DELETE | `/network-segments/{segment_id}/reserved-addresses/{reserved_id}` | 删除单条保留地址 | maintainer/admin |
| 9 | DELETE | `/network-segments/{segment_id}/gateway` | 显式清空网关（幂等） | maintainer/admin |

- 错误码：`400 INVALID_REQUEST`、`422 VALIDATION_ERROR`（`errors[].code` ∈ `CIDR_INVALID`/`CIDR_NOT_IPV4`/`NAME_FORMAT`/`PURPOSE_INVALID`/`TECHNOLOGY_INVALID`/`VLAN_INVALID`/`GATEWAY_OUT_OF_CIDR`/`AUTO_RANGE_INVALID`/`RESERVED_OUT_OF_CIDR`/`RESERVED_RANGE_INVALID`/`RESERVED_OVERLAP`）、`422 DELETE_CONFIRMATION_MISMATCH`、`401 UNAUTHENTICATED`、`403 FORBIDDEN`、`404 SEGMENT_NOT_FOUND`/`CLUSTER_NOT_FOUND`/`RESERVED_ADDRESS_NOT_FOUND`、`409 SEGMENT_NAME_TAKEN`/`SEGMENT_CIDR_TAKEN`/`SEGMENT_HAS_ALLOCATIONS`/`SEGMENT_HAS_RESERVED_ADDRESSES`/`SEGMENT_HAS_INTERFACES`/`SEGMENT_GATEWAY_NOT_CLEARED`/`CIDR_IMMUTABLE`/`VERSION_CONFLICT`。

---

## 10. Frontend / Backend 工作拆分

**Backend**：`app.network_segments`（router/schemas/service/models）+ `app.network_segments.addressing`；`normalize_cidr` 与地址纯函数；创建/编辑/删除事务；保留地址与网关操作；重叠检测；计数计算；唯一与 FK 冲突 → 409 映射；二次确认校验；乐观锁条件更新；审计与资源历史写入；初始化建表增量；pytest + httpx 测试。

**Frontend**：`/clusters/:clusterId/segments` 列表页；新增/编辑对话框；重叠风险提示；保留地址增删控件；网关设置/清空；真实删除二次确认（须输入网段名称）；已分配/可自动分配数量展示；「已分配 IP 及归属」占位页签；axios 错误映射；Vitest 单测。

**Database**：按 §3 设计 `network_segments`、`segment_reserved_addresses`，含对 `clusters(id)`、`network_segments(id)` 的 `ON DELETE RESTRICT` FK、唯一约束、索引；交付初始化建表增量。实现由 Backend 承担。

---

## 11. Test Work

**后端集成（pytest + httpx）**：
- 身份/唯一性：同集群名称去首尾空格、区分大小写唯一、纯空白拒绝；跨集群同名允许；同集群规范化 CIDR 唯一（`192.168.1.0/24` ≡ `192.168.1.5/24`）；跨集群相同 CIDR 允许（场景 10）。
- CIDR 校验：非法/IPv6 拒绝（场景 11 规则侧）；主机位规范化。
- 重叠：同集群部分重叠保存成功并返回 `overlaps`/`has_overlap`（场景 12）；不豁免唯一性。
- 字段校验：保留地址/范围端点、网关超出 CIDR 拒绝且原配置不变（场景 53）；自动范围端点/起止校验；VLAN 范围。
- 删除前置：有保留地址 → `409 SEGMENT_HAS_RESERVED_ADDRESSES`；网关未清 → `409 SEGMENT_GATEWAY_NOT_CLEARED`；清空后无引用可删；`confirm` 不匹配 → `422` 不删除（场景 82）；`version` 冲突。
- 集群保护：为含网段的集群在 F001 侧删除 → `409 CLUSTER_HAS_ASSOCIATIONS`（由 F005 的 RESTRICT FK 触发）。
- 计数：`auto_assignable_count` 在启用/未启用范围、含自身与重叠网段保留/网关、网络/广播、`/31`/`/32` 下的正确性；`allocated_count == 0`。
- 权限：viewer 写/删 403；maintainer/admin 允许；未登录 401。
- 审计/历史：各 action 审计行；`update`/`delete`/保留地址/网关清空资源历史行；删除后仍在；`target_type='segment'`。
- 乐观锁：`PATCH`/`DELETE` 409。

**数据库约束测试**：`UNIQUE(cluster_id, name)`、`UNIQUE(cluster_id, cidr_key)`；`ON DELETE RESTRICT`（clusters、segments）；`resource_history`/`audit_log` append-only。

**前端（Vitest）**：列表/分页/搜索、表单校验、重叠提示、保留地址增删、网关清空、删除二次确认、错误映射、权限隐藏。

**扩展点测试（非 F005 闭环）**：`SEGMENT_HAS_ALLOCATIONS`、`CIDR_IMMUTABLE`、`SEGMENT_HAS_INTERFACES` 由 F006/F002 在引入引用后验收（场景 26/27/52/60/62/65、场景 11 跨集群部分）；管理员历史查询由 F012（场景 61/64）联验。

---

## 12. 技术决策与风险

**已确认（依据）**：栈 ADR-001；PostgreSQL 唯一性 DB 保证、真删 + 独立保留标识、无迁移工具 ADR-002；REST/problem+json/乐观锁 409/offset 分页 ADR-003；HTTP-only/无备份 ADR-004；审计与历史分表、append-only、管理员可查、长期 ADR-005；网段规则 §4.6/§5、BQ-M/N/O/R/W/Z；权限 §2.1；F001/F013 复用基础。

**PROPOSED（不阻塞）**：
1. `purpose`/`technology` 自由文本、必填、长度 ≤ 100/200；非受控枚举；
2. VLAN 范围 `1–4094`；
3. 网关为单个 IPv4，不额外排除网络/广播；
4. CIDR 规范化接受主机位、`/0`–`/32`；
5. 同一网段保留范围不重叠/不重复；
6. 保留地址增删、网关清空不改父网段 `version`，事务内 `SELECT ... FOR UPDATE` 串行化；
7. `SEGMENT_HAS_ALLOCATIONS`/`SEGMENT_HAS_INTERFACES` 用 FK `ON DELETE RESTRICT` + `23503`（按 `constraint_name`/`table_name` 映射）；
8. 计数「适用网络/广播」按「所有仍存重叠网段（含自身）落在 S 自动范围内的网络/广播」解释；
9. 网段名称长度 ≤ 128。

**OPEN / 关注（非阻塞 Database 设计）**：
- `purpose`/`technology` 是否受控枚举及取值集；VLAN 是否必填；网关是否允许多值；网段名称字符集；CIDR 是否要求严格网络地址输入（回 Product 在 Database 设计前确认）。
- CIDR 收窄时对既有保留/网关/自动范围的交互（PROPOSED，需产品确认 UX）。
- `resource_history` 为 F001 首次引入的共享载体；F005 只写、F012 查询口径须一致。
- IP 相关删除/immutable 检查依赖 F002/F006 建 RESTRICT FK 与分配查询；F005 STAGE 无法端到端验收。

---

## 13. Implementation Layers

| Layer | 需要 | 说明 |
| --- | --- | --- |
| database | **true** | `network_segments`、`segment_reserved_addresses` + 唯一约束/索引 + RESTRICT FK + 初始化建表增量；Database 设计、Backend 实现 |
| backend | **true** | 网段模块、地址纯函数、鉴权复用、保留地址/网关、计数与重叠、审计/历史写入、错误映射 |
| frontend | **true** | 网段列表/新增/编辑/删除二次确认、保留地址增删、网关清空、重叠提示、计数展示、错误映射 |

结论：**READY FOR IMPLEMENTATION**（实现仍须通过独立 Database Design 与 Contract Gate）。