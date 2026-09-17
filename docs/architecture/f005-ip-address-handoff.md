# Architecture Handoff — F005 IPAddress 管理

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Feature: F005（E02，P1，`depends_on: [F004]` = DONE）
> 配套契约：`docs/api/f005-ip-address.md`（新建，`READY`）
> Product Source: `docs/product/handoffs/f005-ip-address.md`（`READY FOR ARCHITECT`，无 Blocking，AC-01 ~ AC-42，NQ-1 ~ NQ-10）

---

## Feature

IPAddress 管理（F005）— IP 地址的登记、查询、字面值修正、逻辑删除，**IPAddress → NetworkInterface 必选绑定**落地，**Cluster 内 IP 唯一性**的保存前阻止，**`cluster_id` 受控推导与漂移归零**，以及 **F014 父删子拦**在 NetworkInterface 上的端到端。

## Status

`READY FOR IMPLEMENTATION`（无 Blocking；API Contract = `READY`）。

## Context — 现状核实（只读检查结论）

| 项 | 现状 |
|---|---|
| 应用工厂 | `/api` → health + clusters + cluster_views + bare_metals + virtual_machines + network_interfaces + auth；F013 `AuthMiddleware` fail-closed 覆盖全部 `/api/*`（仅登录豁免）；**无白名单机制** |
| 统一错误基座 | `common/errors.py`、`common/error_handlers.py`（`RequestValidationError` → 400 + `details[].field`）、`common/sqlstate.py`（23502/23514→400、**23505/23503→409**，单一映射表） |
| 分页 / 事务 / 活跃过滤 | `common/pagination.py`（默认 50 / 上限 200）、`api/deps.py` 请求级事务、`db/active.py`（`active_filter` / `select_active` 唯一活跃谓词来源） |
| 统一软删 | `app/deletion/service.py::soft_delete()`（**系统内唯一**写 `deleted_at` 的路径）+ `deletion/checks.ActiveChildCheck` + allow-list guard |
| F014 接线现状 | `CLUSTER_ACTIVE_CHILD_CHECKS = (has_active_bare_metals,)`；`BARE_METAL_ACTIVE_CHILD_CHECKS = (has_active_virtual_machines, has_active_network_interfaces)`；**`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS = ()`（显式空元组，注释标注「F005 追加位置」）**；`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS = ()` |
| NIC 模块（直接父） | `app/network_interfaces/**`；`service._lock_active_host` 用 `select_active(BareMetal).with_for_update(read=True)`；`delete_network_interface` 已 `soft_delete(..., active_children=NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS)` |
| BareMetal 模块 | `app/models/bare_metal.py` 含 `cluster_id`（`NOT NULL` FK，`PATCH` 不可变）；`BareMetalRead` 暴露 `cluster_id` |
| Database | head = `0005_f004_network_interfaces`。**`ip_addresses` 表不存在**；`MIGRATION_HEAD = "0005_f004_network_interfaces"` |
| Frontend | `api/http.ts`（`ApiError{status,code,details[]}`）、`useResourceDelete`、NIC 页面与表单、`App.vue` 视图切换（无 vue-router）。**无 IP UI** |
| 须演进 guard | `tests/database/{helpers.MIGRATION_HEAD, test_schema.EXPECTED_TABLES, test_migrations}`；`test_structure_guard`；`test_auth_guards.EXPECTED_GET_ROUTES`（只增）；**`test_cluster_views_guards.BOUNDARY_TOKENS`（当前含 `ip-address` / `ip_address` 且全局扫描，F005 注册后必然失效）**；**`test_network_interfaces_guards` 的 G-7（断言两个 `ip` token 必须在集合中）与 G-9（断言 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS == ()` 且源码含 `"= ()"`）** |

**结论**：F005 是非空基座上的增量交付：新增一张表 + 一次增量 migration + 一个新模块，并履行两项已确认义务（NIC 父删子拦；`cluster_id` 受控推导 + 漂移归零）。其余机制全部复用。

---

## Architecture Summary

- 新增 `backend/app/models/ip_address.py` + `backend/app/ip_addresses/**`（schemas / repository / derivation / deletion / service / router）。
- 新增 migration `0006_f005_ip_addresses`（`down_revision = "0005_f004_network_interfaces"`；不改 `0001`–`0005`；无数据迁移）。
- **改** `app/network_interfaces/deletion.py`：`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 由**显式空元组**演进为 `(has_active_ip_addresses,)`（**追加**；不动 `BARE_METAL` / `CLUSTER` 检查）。
- 新增前端 IP API 客户端 + 列表 / 详情 / 登记 / 修正 / 删除入口。
- 演进而非删除既有 guard；新增 IP guard 与**漂移检测回归 + 反例 + 唯一性漏洞证明**三件套。

**要点**：一次 `CREATE TABLE` 建齐 7 列 + 2 个 `RESTRICT` FK；`cluster_id` 反规范化列**仅由单一领域服务从 NIC→BareMetal 推导写入**（无触发器 / 无复合 FK / 无 CHECK）；`ux_ip_addresses_cluster_ip_active (cluster_id, ip_address) WHERE deleted_at IS NULL` 为唯一性最终权威；`ip_address TEXT` 字面存取且**不声明 COLLATE / 无 `lower()` 索引 / 无格式 CHECK**；无 `status` / 无 VRF / 无 IP 池 / 无 DHCP / 无 DNS / 无自动发现；IP 是叶子资源，其自身活跃子检查显式为空。

---

## Domain Impact

**使用**已有领域对象：`NetworkInterface`（直接父，N:1 mandatory，用户 2026-09-15 裁定）、`BareMetal`（推导链中间节点）、`Cluster`（唯一性边界，仅被读取）。

**新增领域对象：无。** IPAddress 实体、其唯一字段、IP→NIC 关系、Cluster 内唯一性规则与软删语义均已由 CONFIRMED 产品文档确定。本 Feature 只落地为表 / 模型 / API / 领域服务。

- 状态：**无**。唯一性：`(cluster_id, ip_address)` 活跃范围内唯一，字面精确、大小写敏感、跨 Cluster 可重复、软删释放。
- 关系：`IPAddress → NetworkInterface` N:1 mandatory；`cluster_id` 为**受控推导的反规范化值**，不是调用方输入。
- 生命周期：软删 / 不级联 / 无子资源 / 父 NIC 有活跃 IP 时不得删除。
- **不裁定**：NQ-1（格式 / 归一化）、NQ-2（父绑定可变性）、NQ-3（字面值可变性之否定选项）、NQ-5（跨 Cluster 迁移重推导）、NQ-8（`by-name`）——均为「不实现、不承诺、不预留」。

---

## Decisions

### 决策 1 — `ip_addresses` Schema 与增量 migration

**Revision**：`0006_f005_ip_addresses`，`down_revision = "0005_f004_network_interfaces"`。一次 `CREATE TABLE` + 3 个索引：

```sql
CREATE TABLE ip_addresses (
  id                   BIGINT GENERATED ALWAYS AS IDENTITY,
  network_interface_id BIGINT      NOT NULL,   -- 直接父（N:1 mandatory；用户 2026-09-15 裁定）
  cluster_id           BIGINT      NOT NULL,   -- 反规范化：唯一性边界（ADR-0002）
  ip_address           TEXT        NOT NULL,   -- 字面值；无长度 / trim / 格式 / 归一化约束
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at           TIMESTAMPTZ NULL,
  CONSTRAINT pk_ip_addresses PRIMARY KEY (id),
  CONSTRAINT fk_ip_addresses_network_interface FOREIGN KEY (network_interface_id)
    REFERENCES network_interfaces (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_ip_addresses_cluster FOREIGN KEY (cluster_id)
    REFERENCES clusters (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE UNIQUE INDEX ux_ip_addresses_cluster_ip_active
  ON ip_addresses (cluster_id, ip_address) WHERE deleted_at IS NULL;

CREATE INDEX ix_ip_addresses_cluster_id        ON ip_addresses (cluster_id);
CREATE INDEX ix_ip_addresses_network_interface_id
  ON ip_addresses (network_interface_id);
```

`downgrade`（**严格逆序**）：`drop_index ix_ip_addresses_network_interface_id` → `drop_index ix_ip_addresses_cluster_id` → `drop_index ux_ip_addresses_cluster_ip_active` → `drop_table ip_addresses`。破坏性，生产禁止。

**REQUIRED 规格（不得偏离）**

- 列集合**恰为 7 列**：`{id, network_interface_id, cluster_id, ip_address, created_at, updated_at, deleted_at}`。
- **CHECK 约束集合为空**（无格式 / 长度 / 空白 / `lower()` / collation 类 CHECK）。
- FK 恰为 `{fk_ip_addresses_network_interface, fk_ip_addresses_cluster}`，均 `confdeltype='r'` / `confupdtype='r'`；**禁止 CASCADE**。
- 索引恰为 `{ux_ip_addresses_cluster_ip_active, ix_ip_addresses_cluster_id, ix_ip_addresses_network_interface_id}`；`ux_` 的列顺序为 `(cluster_id, ip_address)`、predicate 恰为 `deleted_at IS NULL`。
- `ip_address TEXT NOT NULL`：**不声明列级 collation、不写 `COLLATE`、不建 `lower(ip_address)` 表达式索引**（ADR-0002 + §22 + `case_sensitive: true`）。
- **无 `status` 列**；**无 VRF / 租户 / 命名空间列**；**无 IP 池 / 网段 / DHCP / DNS / 自动发现 / 外部平台列**；**无载体多态列 / 载体类型选择器**。
- `sa.Identity(always=True)`；时间列 `server_default=sa.text("now()")`；遵循既有 `NAMING_CONVENTION`。
- **不改 `0001`–`0005`**；**无数据迁移**；无触发器；无新 extension。

**文档同步（Database / 协调器落盘）**

1. `docs/database/csm-v1-schema-design.md`：`ip_addresses` 段补**实际 migration 版本号 `0006_f005_ip_addresses`**；索引 / 约束表述对齐实现。
2. 同文件**关键设计决策 #3 的归属对齐**：现文写「受控写入路径（必须由 **F014** 领域服务强制）」，而该表不存在于 F014 且 F014 已把义务移交 F005。改为「由 **F005** 的领域服务 `app/ip_addresses/derivation.py::derive_cluster_id` 强制；唯一写入点为 `IpAddressRepository.create`；由漂移检测回归保证」。**不改规则，只改归属与文件级落点。**
3. 新建 `docs/database/f005-ip-address-migration.md`（镜像 `f004-network-interface-migration.md` 结构）。

**被拒绝**：加 `status`；加 VRF / 命名空间 / IP 池 / DHCP / DNS / 自动发现列；加格式 `CHECK` 或 `lower()` 唯一索引或 `COLLATE`；把 `cluster_id` 做成复合外键逐级传递；触发器；`ON DELETE CASCADE`；改既有基线 migration。

### 决策 2 — 端点集合与资源表示封闭性（含 NQ-4 裁定）

端点恰为 5 个，路径前缀 `/api/ip-addresses`：`POST`（201）、`GET`（200，分页，可选 `network_interface_id`）、`GET /{ip_address_id}`（200）、`PATCH /{ip_address_id}`（200）、`DELETE /{ip_address_id}`（204）。

**NQ-4 裁定：响应不暴露 `cluster_id`。** 资源表示字段集合**恰为 5 字段** `{id, network_interface_id, ip_address, created_at, updated_at}`。

理由：
1. `cluster_id` 是**内部一致性关键的反规范化推导值**，其正确性由「唯一受控写入路径 + 漂移检测 0 行」保证，**不是**产品登记事实；产品为 IPAddress 确认的字段只有 `ip_address`。放进对外表示会把它升格为一级属性，诱发调用方读取 / 回填（与 AC-07 冲突）。
2. **与先例一致**：F004 / F006 的资源表示均不暴露 Cluster 归属。F002 暴露 `bare_metals.cluster_id` 是因为那是该资源的**登记字段**（R-BM-001）；F005 的 Cluster 归属是**推导值**，性质不同。
3. **可观测性不受损**：AC-33~AC-36 本来就必须**绕过应用层直接对数据库断言**（ADR-0002 §3 明确要求），API 暴露与否不影响任何 AC 的可判定性。
4. **Client 可达性不受损**：Cluster 归属可由既有端点沿链取得。
5. **可逆成本低**：未来若需暴露，属**加性**只读字段变更；反之先暴露再收回是破坏性变更。

**请求侧永不接受 `cluster_id`**：`IpAddressCreate` / `IpAddressUpdate` 均 `extra="forbid"`，字段集合分别恰为 `{network_interface_id, ip_address}` 与 `{ip_address}`（AC-07）。

`PATCH` 可变字段封闭集合 = `{ip_address}`；**父绑定不可变**（NQ-2 未确认 → 默认不提供）。不提供 `by-name`、restore / 批量 / `include_deleted`。

### 决策 3 — NQ-6 裁定：按 NIC 限定读取的路由形态与归属

**结论**：F005 提供 **`GET /api/ip-addresses?network_interface_id={id}`** 作为 canonical 父限定读取能力（集合端点的**可选 query parameter，不新增端点**）；R-QUERY-003 的关联查询视图仍归 **F010**，F010 **必须复用**。

语义：`network_interface_id` 非整数 → `400`；父 NIC 不存在 / 已删 → **`404 NOT_FOUND`**；父 NIC 存在但无活跃 IP → **`200` + `items == []`**；未提供 → 全部活跃 IP。

理由：与 F002 `?cluster_id=`、F004 / F006 `?bare_metal_id=` **完全对称**（项目内已三次确立）；不新增端点 / 领域字段；Empty-vs-NotFound 判定落在唯一一处。

**被拒绝**：嵌套路径（跨模块注册、与先例不对称）；完全归 F010（重复实现过滤与 R-QUERY-004）；仅无过滤列表（违反 AC-18）。

**不做**：不提供 `?cluster_id=` / `?vrf=` / `?status=` / `?ip_prefix=` 等任何第二维度过滤。

### 决策 4 — NQ-7 裁定：响应码

| 情形 | HTTP | `error.code` | `details[]` |
|---|---|---|---|
| `POST` / `?network_interface_id=` 引用不存在或已软删 NIC（或上游链不活跃） | **`404`** | `NOT_FOUND` | `[]` |
| 同 Cluster 内活跃重复字面值（应用层预检命中） | **`409`** | `CONFLICT` | `[{"field": "ip_address", "code": "DUPLICATE"}]` |
| 绕过预检直写重复（DB `ux_..._active` 命中，`23505`） | **`409`** | `CONFLICT` | `[{"code": "DUPLICATE"}]`（`field` 非契约） |
| 缺字段 / 非整数 / 未识别字段 / 空 PATCH / `null` | `400` | `VALIDATION_ERROR` | `details[].field` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |

与 F002 / F004 / F006 完全一致。**永不 500**（`23505` / `23503` 均由既有单一映射处理）。

### 决策 5 — `cluster_id` 受控推导：唯一写入点与可失败 guard（本 Feature 最关键设计）

**唯一领域写入点**：新增 `app/ip_addresses/derivation.py::derive_cluster_id(session, network_interface_id) -> int`，以**单条语句**沿 `network_interface_id → network_interfaces.bare_metal_id → bare_metals.cluster_id` 推导，并在同一语句内对**父 NIC 行**取共享锁、同时确认父 NIC 与其宿主 BareMetal 均活跃：

```python
stmt = (
    select(BareMetal.cluster_id)
    .join(NetworkInterface, NetworkInterface.bare_metal_id == BareMetal.id)
    .where(
        NetworkInterface.id == network_interface_id,
        active_filter(NetworkInterface),
        active_filter(BareMetal),
    )
    .with_for_update(read=True, of=NetworkInterface)   # FOR SHARE OF network_interfaces
)
cluster_id = session.scalars(stmt).one_or_none()
if cluster_id is None:
    raise NotFoundError()      # 不存在 / 已软删 / 上游链不活跃 → 404
return cluster_id
```

**写入路径封闭（AC-37）**：

- `create_ip_address` 是 `derive_cluster_id` 的**唯一调用方**，并把结果作为 `cluster_id` 传给 `IpAddressRepository.create`；
- `IpAddressRepository.create` 是**唯一**向 `IpAddress` 实例 / `ip_addresses` 表写 `cluster_id` 的位置；
- `update_ip_address` **不触碰** `cluster_id`（父绑定不可变 ⇒ 推导结果不可能变化）；
- `IpAddressCreate` / `IpAddressUpdate` / `IpAddressRead` / `router.py` / 前端 `api/ipAddresses.ts` **不含** `cluster_id` token。

**可失败 guard（静态源码扫描 / AST，G-9）**：扫描 `backend/app/**/*.py`，断言
1. 向 `IpAddress` 实例或 `ip_addresses` 写 `cluster_id` 的位置集合**恰为** `{app/ip_addresses/repository.py::IpAddressRepository.create}`；
2. 从 `BareMetal.cluster_id` / NIC→BareMetal 链路读取用作推导的函数集合**恰为** `{app/ip_addresses/derivation.py::derive_cluster_id}`；
3. `derive_cluster_id` 的调用点集合**恰为** `{app/ip_addresses/service.py::create_ip_address}`；
4. `ip_addresses` 的 schemas / router / 前端客户端中**不存在** `cluster_id` 字样。

**明确禁止**（ADR-0002 已裁定，不得重开）：数据库触发器；逐级复合外键；任何把「`cluster_id` 与链路一致」写成 Schema 约束（CHECK / FK 组合 / 生成列）的做法。一致性由**受控写入 + 漂移检测（0 行）回归**保证——这是 ADR-0002 §3 的**已知取舍**，必须如实记录而非绕过。

### 决策 6 — 漂移检测的持续回归与证明用例（不得降级）

漂移查询**逐字采用** AC-34 的 SQL（**不加 `deleted_at` 过滤**，检查全部行）：

```sql
SELECT ip.id, ip.cluster_id AS stored_cluster, bm.cluster_id AS derived_cluster
FROM ip_addresses ip
JOIN network_interfaces nic ON nic.id = ip.network_interface_id
JOIN bare_metals        bm  ON bm.id  = nic.bare_metal_id
WHERE ip.cluster_id <> bm.cluster_id;   -- 期望 0 行
```

**落点**：新增 `tests/ip_address_drift_helpers.py`，把该 SQL 固化为**单一常量** `DRIFT_QUERY` + `find_drift(conn)`（**只存在于测试侧**；不为此新增产品端点、不在生产代码里放未被调用的死代码）。三个测试共用它：

| 测试 | 内容 | AC |
|---|---|---|
| **T-34** | 全部数据仅经产品路径创建后 `DRIFT_QUERY` 返回 **0 行**；并在软删 IP、软删 NIC、跨 Cluster 重复字面值等操作后重复断言仍为 0 行 | AC-34 |
| **T-35** | **反例证明**：绕过领域服务，直接对数据层插入一条 `cluster_id != bm.cluster_id` 的 IP 行（数据库**不会**拒绝）→ `DRIFT_QUERY` **必须返回 1 行** | AC-35 |
| **T-36** | **漂移即唯一性静默漏洞的证明**：Cluster A 已有活跃 `10.0.0.10`；再直接写入一条真实属于 A、但 `cluster_id = B` 的 `10.0.0.10` 行 → `ux_ip_addresses_cluster_ip_active` **不会**阻止 → `DRIFT_QUERY` 必须发现它（1 行），证明 F005-R7 是 R-IP-001 的**必需**保障 | AC-36 |

**不得降级**：三个测试必须同时存在；T-34 不得弱化为「仅检查 AC-33 的抽样行」；T-35 / T-36 必须以真实 DB 写入构造反例（不得 mock），且若有人移除漂移查询或唯一索引谓词，二者必须失败。T-34 同时是**并发测试（T-31）**结束后的断言之一。

**此外记录（不实现、不预留）**：若未来确认 BareMetal 跨 Cluster 迁移，必须**在同一事务内**重推导受影响 IP 的 `cluster_id` 并对目标 Cluster 重校验唯一性，否则漂移查询将 > 0 行、R-IP-001 静默失效。

### 决策 7 — 创建路径的父链存在性 / 活跃性与并发协议

1. **共享锁对象 = 父 NIC 行（仅此一行）**：`derive_cluster_id` 在创建事务内 `FOR SHARE OF network_interfaces`。锁序与 F004 / F006 / F014 一致（「写子资源 → 先锁父行 `FOR SHARE`」）。
2. **不需要一并锁 BareMetal / Cluster，且不锁。** 理由：
   - 推导所依赖的 `network_interfaces.bare_metal_id` 与 `bare_metals.cluster_id` 在 V1 **均不可变**（F004 / F002 的 `PATCH` 均不含），因此持有父 NIC 行 `FOR SHARE` 后推导结果在事务内**不可能被并发改变**；
   - 「活跃 NIC ⇒ 活跃宿主」由 F014 机制保证（`BARE_METAL_ACTIVE_CHILD_CHECKS` 含活跃 NIC 检查），不可能出现「宿主已删 + 父 NIC 活跃」；
   - 额外加锁**不带来任何额外保证**，只增加锁 footprint 与跨表锁序审计成本；
   - 对宿主活跃性以**同一语句的 `WHERE bm.deleted_at IS NULL`** 完成（防御性断言，未命中即 `404`），不额外加锁。
   - **记录**：若未来允许 `bare_metals.cluster_id` 或 `network_interfaces.bare_metal_id` 可变，本决策必须重开。
3. **交错分析（两种交错都不产生孤立记录）**：
   - IP 建先持 NIC `FOR SHARE` ⇒ 并发「删除父 NIC」在其 `FOR UPDATE` 上阻塞；IP 提交后 NIC 删除的活跃子检查（`has_active_ip_addresses`）命中 → `409`（无部分写入）；
   - NIC 删先持 `FOR UPDATE` 并置 `deleted_at` ⇒ IP 建阻塞；NIC 删提交后 IP 建在 `READ COMMITTED` 下重新求值未命中活跃 NIC → `404`。
   - **死锁**：本 Feature 只新增「NIC 行 `FOR SHARE` →（同一语句内）读 BareMetal」，而 NIC 删除为「NIC 行 `FOR UPDATE` → 读 IP 行（无锁）」、宿主删除为「BareMetal 行 `FOR UPDATE` → 读 NIC 行（无锁）」。**新增路径不引入任何反向持锁**，故不新增死锁序。
4. **不变式**：并发结束后孤立记录查询 **0 行**（AC-31）且 `DRIFT_QUERY` **0 行**。
5. **唯一性与最终权威**：应用层预检 `IpAddressRepository.active_ip_exists(cluster_id, ip_address)` 仅返回友好 `409`，是体验优化；`ux_ip_addresses_cluster_ip_active` 是**最终权威**（§21）。预检与插入之间为 `READ COMMITTED`，并发窗口由唯一索引兜底（`23505` → `409`，永不 500）。
6. **FK 违规映射**：正常路径由 `FOR SHARE` + 活跃确认给出 `404`；若绕过预检，经既有通用 `sqlstate.py` 返回 `409 CONFLICT` + `details[].code = "REFERENCE"`，仍非 5xx；**不为本资源另立映射**，该路径在产品路径下不可达。

### 决策 8 — F014 义务落点（父删子拦）与既有 guard 演进

- 新增 `app/ip_addresses/deletion.py`：
  - `has_active_ip_addresses(session, network_interface_id) -> bool`（`EXISTS` 活跃 IP，复用 `active_filter`；`LIMIT 1`）；
  - `IP_ADDRESS_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()` —— **IPAddress 是 V1 叶子资源**；显式声明空元组是保持 F014 §5 约定的一致性，**不是**为未确认能力预留，且由 `== ()` 的 guard 固定（防止「顺手」发明子资源）。
- **改** `app/network_interfaces/deletion.py`：`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS = (has_active_ip_addresses,)`，**追加**，保留 `has_active_network_interfaces`；`BARE_METAL_ACTIVE_CHILD_CHECKS`（VM + NIC）与 `CLUSTER_ACTIVE_CHILD_CHECKS` **不得**改动。
- `delete_network_interface` 已传入 `active_children=NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`，**无需改删除路径逻辑**；NIC 删除端点的 `409 + ACTIVE_CHILDREN_EXIST` 分支由 F004 契约存在于本 Feature 变为**可达**（F005 **不修改** F004 契约正文）。
- 无循环导入：`network_interfaces.deletion → ip_addresses.deletion → models.ip_address`；`app.ip_addresses.*` **不得**导入 `app.network_interfaces.*`（仅 `app.models.network_interface`）——由 G-15 的导入方向断言固定。
- **既有 guard 演进（演进而非删除）**：
  - `tests/database/helpers.py::MIGRATION_HEAD` → `"0006_f005_ip_addresses"`；
  - `tests/database/test_schema.py::EXPECTED_TABLES` → 加 `ip_addresses`；
  - `tests/database/test_migrations.py` → head / 表集合 / 可重建加 `ip_addresses` / `0006`；新增「downgrade 到 `0005_f004_network_interfaces` 后 `ip_addresses` 被删、既有表完好、再次 `upgrade head` 可重建」；
  - `tests/test_structure_guard.py::test_only_expected_tables_registered` → 加 `ip_addresses`；
  - `tests/test_auth_guards.py::EXPECTED_GET_ROUTES` → 追加 `/api/ip-addresses`、`/api/ip-addresses/{ip_address_id}`（只增不删）；
  - `tests/test_cluster_views_guards.py::BOUNDARY_TOKENS` → **移除** `ip-address` / `ip_address`（已成为合法资源，与 F006 移除 `virtual-machine`、F004 移除 `network-interface` 同一处置）；**保留** `container` / `service`；**保持对全部 OpenAPI path 的全局扫描**；
  - `tests/test_network_interfaces_guards.py`：`test_g7_boundary_tokens_narrowed_but_global` 由「断言两个 `ip` token 必须在集合中」演进为「断言二者**不在**集合中，`container` / `service` 仍在，且扫描仍为全局」；`test_g9_nic_active_child_checks_explicitly_declared` 由 `== ()` / 源码 `"= ()"` 演进为「为 tuple 且**非空**、且包含 `has_active_ip_addresses`」，并**保留** `test_g9_nic_delete_path_passes_active_child_checks` 的 AST 消费断言；
  - 新增 `tests/database/test_ip_addresses_schema_guard.py`、`tests/test_ip_addresses_api.py`、`tests/test_ip_addresses_guards.py`、`tests/test_ip_addresses_concurrency.py`、`tests/test_ip_addresses_consistency.py`、`tests/ip_address_drift_helpers.py`。

### 决策 9 — 「不实现」的结构性 guard

| Guard | 断言 |
|---|---|
| 无格式校验 / 无归一化 | `app/ip_addresses/**` 不含 `ipaddress` / `inet_` / `inet_pton` / `ip_network` / `normalize` / `strip(` / `split(` / `lower(` / `upper(` / `re.` 等对 `ip_address` 的处理；schema 无 `min_length` / `max_length` / `pattern` / `strip_whitespace` / `to_lower` / `to_upper`，无 `field_validator` / `model_validator`；表无 CHECK；行为断言：空串 / 含首尾空白 / 超长 / `not-an-ip` 均原样往返 |
| 无状态 | 列 / ORM / schema / OpenAPI 参数 / 端点中无 `status` |
| 无 VRF / 命名空间 | 无 `vrf` / `vrf_id` / `rd` / `tenant` / `namespace` / `netns` / `vni` 列、字段、参数、过滤或端点 |
| 无 IP 池 / 网段 / DHCP / DNS / 自动发现 | 无 `pool` / `pool_id` / `subnet` / `segment` / `gateway` / `vlan` / `dhcp` / `dns` / `discovered` / `external_id` / `last_seen` / `sync` / `credential` |
| 无多态父载体 | 无 `carrier_type` / `owner_type` / `parent_type` / `bare_metal_id` / `virtual_machine_id` / `container_id` 可写参数或列；`IpAddressCreate` 字段集合**恰为** `{network_interface_id, ip_address}` |
| 无未确认字段 | 无 `purpose` / `note` / `remark` / `owner` / `assigned_at` / `reclaimed_at` / `state` / `description` |
| `cluster_id` 不可写 / 不暴露 | 3 处 schema / router / 前端客户端均无 `cluster_id`；请求携带 → `400` |
| 无未确认能力预留 | 不存在为 VRF / IP 状态 / IP 池 / 多态父载体 / `cluster_id` 可写 / 格式归一化 / Excel 导入预留的字段、参数、分支、常量或占位（含 `# TODO` 与不可达 `if`） |
| 交付面封闭 | 路由恰为 5 个端点；无 `by-name`；无 restore / undelete / purge / batch / `include_deleted` / trash；无 Cluster 视角 / 聚合 / 计数的 IP 端点 |

### 决策 10 — 交付层

```text
database: true      # 新增 ip_addresses 表 + migration 0006 + schema 文档同步（实现由 Backend 负责）
backend:  true      # models/ip_address.py + app/ip_addresses/** + network_interfaces/deletion 追加 + guard 演进 + 全部测试
frontend: true      # api/ipAddresses.ts + 列表/详情/登记/修正/删除 + App.vue 视图接线
```

`database: true` 理由：引入新表与新 partial unique index（R-IP-001 唯一性最终权威），且 schema 文档存在已确认漂移（关键决策 #3 归属）必须同步；无数据迁移。

### 决策 11 — 契约

**新建** `docs/api/f005-ip-address.md`（`READY`）。**不修改**任何既有契约正文。F004 契约中「NIC 的 `409 ACTIVE_CHILDREN_EXIST` 当前不可达、F005 落地时追加活跃 IPAddress 检查」的表述**已被本 Feature 履行且无需改字**。

### 决策 12 — 计划落盘

```yaml
layers: { database: true, backend: true, frontend: true }
contract: { status: READY, doc: docs/api/f005-ip-address.md }
implementation: { database_design: PENDING, backend: PENDING, frontend: PENDING, test: PENDING, review: PENDING }
open_questions:
  NQ-4: { resolved_by: architecture, summary: "不暴露 cluster_id；请求侧永不接受。" }
  NQ-6: { resolved_by: architecture, summary: "GET /api/ip-addresses?network_interface_id=；F010 必须复用。" }
  NQ-7: { resolved_by: architecture, summary: "父不存在/已删 → 404；唯一性 → 409 + DUPLICATE。" }
```

### 决策 13 — 前端接线

见 Frontend Work。三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code` 分支，**不解析 `message`**；不重复实现任何业务守卫；不引入新依赖、不引入 vue-router。

---

## Database Work

**Revision**：`0006_f005_ip_addresses`，`down_revision = "0005_f004_network_interfaces"`。**不改 `0001`–`0005`**；**无数据迁移**。

- `upgrade`：`CREATE TABLE ip_addresses`（7 列 + PK + 2 FK `RESTRICT`/`RESTRICT`，**0 个 CHECK**）→ `create_index ux_ip_addresses_cluster_ip_active`（`unique=True`, `postgresql_where=sa.text("deleted_at IS NULL")`）→ `create_index ix_ip_addresses_cluster_id` → `create_index ix_ip_addresses_network_interface_id`。
- `downgrade`（严格逆序，见决策 1）。
- 无 `COLLATE`；无 `lower()` 表达式索引；无触发器；无 CASCADE。
- **列集合恰为 7 列；CHECK 集合为空；FK 恰为 2 条；索引恰为 3 条（其中唯一索引恰 1 条）。**

数据层职责：
1. **保存唯一性边界本身**：`(cluster_id, ip_address)` 活跃范围内唯一必须由数据库强制，且 predicate 与常规查询过滤完全一致。
2. **必选父子关系的物理表达**：`network_interface_id NOT NULL` + FK `RESTRICT`。
3. **承载推导值**：`cluster_id NOT NULL` + FK `RESTRICT`（只保证被引用 Cluster 物理存在；**不**保证与链路一致 —— ADR-0002 已知取舍）。
4. **读取与 FK 检查索引**：`ix_ip_addresses_network_interface_id`、`ix_ip_addresses_cluster_id`。
5. **格式 / 归一化 / 状态 / VRF 一律不表达**。

**文档同步**：`docs/database/csm-v1-schema-design.md`（IP 段补版本号；关键设计决策 #3 归属 F014 → F005 对齐）；新建 `docs/database/f005-ip-address-migration.md`。

---

## Backend Work

1. **ORM 模型** `app/models/ip_address.py`：`IpAddress(IdMixin, TimestampMixin, SoftDeleteMixin, Base)`，`__tablename__ = "ip_addresses"`；列 `network_interface_id` / `cluster_id` / `ip_address`（均按决策 1）；**无** `status` / VRF / 池 / DHCP / DNS / 载体列。`__table_args__` 恰为两条显式命名 `ForeignKeyConstraint`（`RESTRICT`/`RESTRICT`）、`Index("ux_ip_addresses_cluster_ip_active", "cluster_id", "ip_address", unique=True, postgresql_where=sa.text("deleted_at IS NULL"))`、`Index("ix_ip_addresses_cluster_id", "cluster_id")`、`Index("ix_ip_addresses_network_interface_id", "network_interface_id")`；**无 `CheckConstraint`**。注册到 `app/models/__init__.py`。
2. **schema** `app/ip_addresses/schemas.py`：`IpAddressRead` 恰 5 字段（无 `cluster_id` / `deleted_at` / `status`）；`IpAddressCreate` 恰 2 字段（`extra="forbid"`，**不加任何字段约束**）；`IpAddressUpdate` 恰 1 字段（`ip_address: str | None`，`extra="forbid"`）；`MUTABLE_FIELDS = ("ip_address",)`。
3. **推导** `app/ip_addresses/derivation.py`：`derive_cluster_id(session, network_interface_id) -> int`（决策 5 的语句；未命中 → `NotFoundError`）。本模块是**唯一**从 NIC→BareMetal 读取 `cluster_id` 的位置。
4. **repository** `app/ip_addresses/repository.py`：读取一律经 `active_filter` / `select_active`；`get_active`、`list_active(params, *, network_interface_id=None)`；`active_ip_exists(cluster_id, ip_address, *, exclude_id=None)`；`create(*, network_interface_id, cluster_id, ip_address)`（**唯一**写 `cluster_id` 的位置，`flush()` + `refresh()`）；`update(...)`。**不存在**写 `deleted_at` 的方法；**不存在**任何格式校验 / 归一化方法。
5. **service** `app/ip_addresses/service.py`：
   - `create_ip_address`：`cluster_id = derive_cluster_id(...)`（未命中 → `404`）→ `active_ip_exists` 命中 → `409` + `details[{"field": "ip_address", "code": "DUPLICATE"}]` → `create`；
   - `list_ip_addresses`：给出 `network_interface_id` 时先 `select_active(NetworkInterface)` 确认父活跃（未命中 `404`），再返回该父的活跃子集；未给出 → 全部活跃；
   - `get_ip_address_by_id`：未命中 → `404`；
   - `update_ip_address`：加载活跃目标（`404`）→ `model_fields_set` 为空 → `400`；`ip_address` 为 `None` → `400` + `field == "ip_address"`；`active_ip_exists(目标行 cluster_id, 新字面值, exclude_id=目标)` 命中 → `409 DUPLICATE`；**不写 `cluster_id`、不写 `network_interface_id`**；
   - `delete_ip_address`：`soft_delete(session, IpAddress, ip_address_id, active_children=IP_ADDRESS_ACTIVE_CHILD_CHECKS)`（显式传入）。
6. **router** `app/ip_addresses/router.py`（`prefix="/ip-addresses"`）：**恰 5 个端点**；`GET ""` 的 query 参数恰为 `{page, page_size, network_interface_id}`；在 `app/main.py` 以 `prefix="/api"` 挂载；无 `by-name`、无 restore / 批量 / `include_deleted`、无 Cluster 维度端点。
7. **F014 接线**：`app/ip_addresses/deletion.py`（`IP_ADDRESS_ACTIVE_CHILD_CHECKS = ()` + `has_active_ip_addresses`）；**改** `app/network_interfaces/deletion.py` 的 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS = (has_active_ip_addresses,)`。
8. **migration** `backend/migrations/versions/0006_f005_ip_addresses.py`（决策 1 / Database Work 规格）。
9. **Guard 演进 + 新增**：见决策 8 与 Test Work（**演进而非删除**）。

---

## Frontend Work

1. **`frontend/src/api/ipAddresses.ts`**：`IpAddressRead`（恰 5 字段；**无 `cluster_id`**）；`IpAddressCreateBody{network_interface_id, ip_address}`；`IpAddressUpdateBody{ip_address?}`；`listIpAddresses({page?, page_size?, networkInterfaceId?})`、`getIpAddress(id)`、`createIpAddress(body)`、`updateIpAddress(id, body)`、`deleteIpAddress(id)`。**不提供**任何 IP 格式校验 / 归一化 / trim / 唯一性预检辅助函数（注释明确：合法性由服务端裁决，§21）。
2. **`pages/IpAddressListPage.vue`**：`GET /api/ip-addresses`（可选 `network_interface_id` 限定，来自 NIC 详情入口，供 F010 复用同一过滤）；三态互不相同；**Empty 与 Not Found 可区分**；错误按 `error.code` 分支；行级详情 / 删除（二次确认）+ 登记入口；提交中 Loading 防重复；**无状态列 / 无状态筛选 / 无 Cluster 列**。
3. **`pages/IpAddressDetailPage.vue`**：5 字段展示（时间不透明字符串）；`404` → **独立 Not Found 态**；`ip_address` 可修正（`PATCH`，仅此一个字段可编辑）；`network_interface_id` **只读**；删除入口。
4. **`components/IpAddressFormDialog.vue`**：create = 网络接口选择（复用 `GET /api/network-interfaces`；若从 NIC 详情进入则预选）+ `ip_address` 文本输入；edit = 仅 `ip_address`；**不对 `ip_address` 做长度 / 空白 / 空串 / 格式 / 正则校验，也不做任何归一化**；失败按 `error.code` + `details[].field`（`VALIDATION_ERROR` → 字段级提示；`NOT_FOUND` → 「请检查所选网络接口」；`CONFLICT` + `details[].code === 'DUPLICATE'` → 「该 IP 在所属 Cluster 内已被占用」）。
5. **`composables/useIpAddressDelete.ts`**：复用 `useResourceDelete`；**不假定**「IP 永远无子资源」。
6. **`App.vue`**：新增 `ip-address-list`（可选 `networkInterfaceId` + 返回上下文）与 `ip-address-detail` 视图；头部导航新增「IP 地址」；从 `NetworkInterfaceDetailPage` 进入「查看 IP 地址」（携带 `network_interface_id`），返回时恢复 NIC 详情上下文。
7. **禁止重复实现业务守卫**（§21）：同 Cluster IP 唯一、父 NIC 存在性 / 活跃性、NIC 删除守卫**一律由后端裁决**，前端不回填 `cluster_id`、不预判、不禁用入口。
8. **不做**：Cluster 视角 / 关联聚合 / 计数、Excel 导入、审计 / 恢复 / 回收站 / 批量 / 导出 / 高级筛选、VRF / IP 状态 / IP 池 / DHCP / DNS / 自动发现 UI、任何 IP 格式校验 UI。

---

## Contract

```text
READY
```

唯一权威正文：`docs/api/f005-ip-address.md`（新建）。**不修改**任何既有契约。

---

## Test Work

### API + DB 行为

| # | 测试 | 层次 | AC |
|---|---|---|---|
| T-01 | `POST`（活跃 NIC + `ip_address`）→ `201`；响应字段集合**恰 5 字段**；无 `deleted_at` / `status` / `cluster_id` / `vrf` / 池 / 备注 | API | AC-01 |
| T-02 | `POST` 缺 `ip_address` / 非字符串（含 `{}`）→ `400` + `field == "ip_address"`，无写入 | API + DB | AC-02 |
| T-03 | `POST` 缺 `network_interface_id` / 非整数 → `400` + `details[].field` | API | AC-03 |
| T-04 | `POST` 引用不存在 / 已软删 NIC → `404`（`details == []`），无写入、非 5xx；`?network_interface_id=` 同语义 | API + DB | AC-04 |
| T-05 | schema 封闭（多父 / 载体选择器 / `cluster_id` → `400`）；父列 `NOT NULL` + FK `RESTRICT` | API + Schema | AC-05 |
| T-06 | 同一 NIC 连续登记 2 个不同字面值 → 均 `201` | API + DB | AC-06 |
| T-07 | 请求体携带 `cluster_id` / `vrf` / `status` / `pool_id` → `400`，不产生记录 | API | AC-07 / AC-42 |
| T-08 | Cluster A 内已活跃 `10.0.0.10`（**另一台 BM 的另一张 NIC**）再登记 → `409` + `field == "ip_address"` + `code == "DUPLICATE"`；不产生第二条活跃记录、非 5xx | API + DB | AC-08 |
| T-09 | Cluster A 与 B 各自登记 `10.0.0.10` → 均 `201` | API + DB | AC-09 |
| T-10 | 字面精确：同 Cluster 内字面相同 → 冲突；`2001:DB8::1` 与 `2001:db8::1` → 均 `201`；DB 层无 `lower()` 索引、列 `collation_name IS NULL` | API + DB | AC-10 |
| T-11 | 绕过应用层直插同 Cluster 重复活跃字面值 → `23505`；经应用路径 → `409`（**永不 500**）；predicate 恰为 `deleted_at IS NULL` | DB + API | AC-11 |
| T-12 | `not-an-ip` / 空串 / 含首尾空白 / 超长字面值**不被拒绝**，按字面值原样往返 | API + DB | AC-12 |
| T-13 | 请求 / 响应 / 表 / 端点 / 参数中**无** `status` | API + Schema | AC-13 |
| T-14 | 无 `vrf` / `tenant` / `namespace` / `netns` 列、字段、参数、过滤、端点 | API + Schema | AC-14 |
| T-15 | 无用途 / 备注 / 负责人 / 分配对象 / 回收状态 / DHCP / DNS / 自动发现 / 外部平台 id / 凭据 | API + Schema | AC-15 / AC-39 |
| T-16 | `GET /api/ip-addresses` → `200` + 空信封，不得 404；分页 / 非法参数 `400` | API | AC-16 |
| T-17 | `GET /{id}` 不存在 / 已软删 → `404`；重复 `DELETE` 已删 → `404` | API | AC-17 |
| T-18 | `?network_interface_id=`：NIC 不存在 / 已删 → `404`；存在但无活跃 IP → `200` + `items == []` | API + DB | AC-18 |
| T-19 | 绕过应用层预置 `deleted_at` → 不出现在 `items` / `total`；按 `id` → `404` | API + DB | AC-19 |
| T-20 | `PATCH` 新 `ip_address` → `200` 新值；再次读取一致；`network_interface_id` / `created_at` 不变；响应无 `cluster_id` | API + DB | AC-20 |
| T-21 | `PATCH` 为目标 Cluster 已占用活跃字面值 → `409` + `DUPLICATE`，无部分写入；为另一 Cluster 已有但目标未占用 → `200` | API + DB | AC-21 |
| T-22 | `PATCH` 含未识别 / 不可变字段 → `400`；空 body → `400`；`{"ip_address": null}` → `400`；父绑定不可变 | API | AC-22 |
| T-23 | `DELETE`（活跃）→ `204` 无响应体；行仍物理存在且 `deleted_at` 非空 | API + DB | AC-23 |
| T-24 | 软删 Cluster A 内 `10.0.0.10` 后可在同 Cluster 重新登记 → `201`；旧行 `deleted_at` 未被改写 | API + DB | AC-24 |
| T-25 | 删除 IP 后父 NIC 的 `deleted_at` / `updated_at` / `name` / `technology_type` / `purpose` / `bare_metal_id` **逐字段不变**；上游 BareMetal / Cluster 不变 | API + DB | AC-25 |
| T-26 | 无 restore / undelete / purge / 批量 / `include_deleted` / 回收站 | API | AC-26 |
| T-27 | NIC 有活跃 IP → `DELETE /api/network-interfaces/{id}` → `409` + `code == "ACTIVE_CHILDREN_EXIST"`；NIC `deleted_at` **仍为 NULL** | API + DB | AC-27 |
| T-28 | 先软删该 NIC 全部活跃 IP（及其它活跃子资源）再 `DELETE` → `204`；可证明 IP 是阻断来源 | API + DB | AC-28 |
| T-29 | NIC 有活跃 IP 时其宿主 BareMetal 亦不可删 → `409`；`Cluster → BareMetal → NIC → IP` 链条闭合 | API + DB | AC-29 |
| T-30 | `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 非空、含 `has_active_ip_addresses`、由 NIC 删除路径真实消费（AST）；`BARE_METAL_ACTIVE_CHILD_CHECKS` 仍含 VM + NIC；`IP_ADDRESS_ACTIVE_CHILD_CHECKS == ()` | 静态 + API | AC-30 |
| T-31 | 并发「创建 IP vs 删除父 NIC」两种交错：孤立记录不变式 = **0 行**；且 `DRIFT_QUERY` = 0 行 | 并发（真实 PG） | AC-31 |
| T-32 | 创建 IP 对父 NIC 行 `FOR SHARE` + 同事务确认活跃（持锁期间另一连接 `FOR UPDATE NOWAIT` 失败；父删先提交则创建被拒 `404`）；锁序不引入新死锁 | 并发（真实 PG） | AC-32 |
| T-33 | 经产品路径创建 IP → 直读 DB 断言 `cluster_id == 宿主 BareMetal 的 cluster_id`（**不是**请求提供的值） | API + DB | AC-33 |
| T-34 | **漂移检测回归**：仅经产品路径产生的数据 `DRIFT_QUERY` 恒为 **0 行**（含跨 Cluster 重复字面值、软删 IP / NIC 后） | DB（回归） | AC-34 |
| T-35 | **反例证明**：绕过领域服务直插不一致行 → `DRIFT_QUERY` 必须返回 **1 行** | DB | AC-35 |
| T-36 | **唯一性漏洞证明**：Cluster A 已有 `10.0.0.10`；直插真实属于 A 但 `cluster_id = B` 的 `10.0.0.10`（唯一索引不阻止）→ `DRIFT_QUERY` 必须发现它 | DB | AC-36 |
| T-37 | `cluster_id` 写入路径唯一：静态 guard（G-9）+ `PATCH` 前后 `cluster_id` 逐字节不变 | 静态 + API + DB | AC-37 |
| T-38 | 不注册 Cluster 视角 / 关联聚合 / 计数端点；无 Excel 导入端点；无第二维度过滤 | API | AC-38 |
| T-39 | 结构性 guard：无格式校验 / 归一化；无 DHCP / DNS / 自动发现 / 外部同步字段或端点 | 静态 | AC-39 |
| T-40 | 未认证访问 5 端点 → `401` 且不改数据；已认证用户即可增改删 | API | AC-40 |
| T-41 | 前端：三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code`；`DUPLICATE` 字段级提示；不实现业务守卫 | 前端组件 | AC-41 |
| T-42 | schema / 契约 / 前端均无为 VRF、IP 状态、IP 池、多态父载体、`cluster_id` 可写、格式归一化、Excel 导入预留的字段 / 参数 / 分支 / 占位 | 静态 + OpenAPI | AC-42 |

### 结构 / 静态 guard

| # | guard | 关联 |
|---|---|---|
| G-1 | ORM 与 DB 列集合**恰为** 7 列；无 `status` / VRF / 池 / DHCP / DNS / 载体 / 备注类列 | AC-01/13/14/15/42 |
| G-2 | **CHECK 约束集合为空**；`ip_address` 为 `TEXT` 且 `character_maximum_length IS NULL` | AC-02/12/39 |
| G-3 | PK 恰为 `pk_ip_addresses`；FK 恰为 2 条，`confdeltype='r'` / `confupdtype='r'` | AC-05 |
| G-4 | 唯一索引集合**恰为** `{ux_ip_addresses_cluster_ip_active}`，列序 `(cluster_id, ip_address)`、`WHERE (deleted_at IS NULL)`，且**不含 `COLLATE` / `lower(`**；另两个普通索引存在 | AC-10/11 |
| G-5 | 表集合 guard 演进（`EXPECTED_TABLES` 加 `ip_addresses`；`MIGRATION_HEAD = 0006_f005_ip_addresses`），**增表演进不得删测试** | 约束 |
| G-6 | `EXPECTED_GET_ROUTES` 追加两条 IP GET（只增不删） | 约束 |
| G-7 | `BOUNDARY_TOKENS` 收窄为 `{container, service}`（移除两个 `ip` token）、**保持全局扫描**；`test_network_interfaces_guards.test_g7` 同步演进 | AC-38 |
| G-8 | `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 为 tuple 且**非空**、含 `has_active_ip_addresses`，NIC 删除路径经 AST 真实传入；`BARE_METAL_ACTIVE_CHILD_CHECKS` 仍含 VM + NIC；`CLUSTER_ACTIVE_CHILD_CHECKS` 未变；`IP_ADDRESS_ACTIVE_CHILD_CHECKS == ()` 且 IP 删除路径显式传入 | AC-27/28/30 |
| G-9 | `cluster_id` 单一写入路径（决策 5 的 4 条断言）；3 处 schema / router / 前端客户端无 `cluster_id` | AC-07/37 |
| G-10 | 「不实现格式 / 归一化」：源码无相关符号；schema 无约束元数据与 validator；DB 无 CHECK；空串 / 首尾空白 / 非 IP 字面值原样往返 | AC-12/39 |
| G-11 | 无 `status` / VRF / 命名空间 / IP 池 / DHCP / DNS / 自动发现 / 同步 / 外部 id / 凭据 / 多态父载体：列 / schema / OpenAPI 参数 / 端点 token 全量扫描为空 | AC-13/14/15/42 |
| G-12 | 全库无 `confdeltype='c'`；`ip_addresses` 所有列 `collation_name IS NULL`；无触发器 | R-DELETE-005 / ADR-0002 |
| G-13 | 无通用 `resources` 表 / EAV / STI / 多态 mapper / JSON(B)；`Base.metadata.tables` 集合恰为预期 7 张 | §24 |
| G-14 | 唯一软删写入路径 allow-list 保持 `{backend/app/deletion/service.py}`；`app/ip_addresses/**` 写入 `deleted_at` 的位置为 0 | AC-23/26 |
| G-15 | 交付面封闭：IP 路由恰 5 个端点；无 `by-name` / restore / 批量 / `include_deleted`；`GET ""` 的 query 参数恰为 `{page, page_size, network_interface_id}`；`app.ip_addresses.*` 不导入 `app.network_interfaces.*`（仅 `app.models.network_interface`） | AC-16/18/26/38 |
| G-16 | migration：head = `0006_f005_ip_addresses`；可应用 / 可重复 / 可从空库重建 / `alembic check` 无漂移；`downgrade 0005` 后 `ip_addresses` 被删且既有表完好；既有表列集合未变 | 约束 |
| G-17 | 前端：`api/ipAddresses.ts` 字段封闭（无 `cluster_id`）；无格式校验 / 归一化 / 唯一性预检辅助；无新依赖；无 vue-router | AC-41/42 |

### 必须同步演进的既有测试

`tests/database/{helpers,test_schema,test_migrations}`、`tests/test_structure_guard.py`、`tests/test_auth_guards.py`、**`tests/test_cluster_views_guards.py`（BOUNDARY_TOKENS）**、**`tests/test_network_interfaces_guards.py`（G-7 / G-9）**。

**原样保留**：`tests/test_deletion_guards.py`、`tests/database/test_deletion_schema_guard.py`、`tests/database/test_g2_schema_guard.py`、`tests/database/test_constraints.py`、`tests/test_bare_metals_guards.py`、`tests/test_virtual_machines_guards.py`、`tests/test_clusters_guards.py`。

---

## REQUIRED

1. `ip_addresses` 唯一性由 **partial unique index** 强制（predicate 恰为 `deleted_at IS NULL`）；比较**字面精确、大小写敏感**；**禁止 `lower()` / `COLLATE` / 大小写折叠 / trim / 归一化**。
2. `ip_address` 列**必须**为 `TEXT` 且**无任何 CHECK / 长度 / `<> ''` / 正则**约束；应用层**不得**做格式校验、trim、归一化、空串拒绝。
3. `network_interface_id NOT NULL` + FK `RESTRICT`；`cluster_id NOT NULL` + FK `RESTRICT`；**禁止 CASCADE**；**禁止**复合外键 / 触发器 / 一致性 CHECK。
4. `cluster_id` **只能**由 `derive_cluster_id` 推导并经 `IpAddressRepository.create` 写入；**不存在**第二条写入路径；`PATCH` **不得**触碰 `cluster_id` 与 `network_interface_id`；请求 / 响应 schema **不得**出现 `cluster_id`。
5. 创建路径**必须在同一事务内**对父 NIC 行取 `FOR SHARE` 并在同一语句内确认父 NIC 与其宿主 BareMetal 均活跃；未命中 → `404`；**不得**额外锁定 BareMetal / Cluster 行；**不得**引入新的反向持锁。
6. 唯一性冲突：应用层预检 → `409 CONFLICT` + `field == "ip_address"` + `code == "DUPLICATE"`；DB `23505` 为**最终权威**，经既有单一映射 → `409`，**永不 500**；**不得**另立 SQLSTATE 映射。
7. `deleted_at` 写入路径**恰好 1 条**；IP 删除**必须**委托 `soft_delete(..., active_children=IP_ADDRESS_ACTIVE_CHILD_CHECKS)`；`IP_ADDRESS_ACTIVE_CHILD_CHECKS` **显式为空元组**。
8. `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` **必须被追加**为含 `has_active_ip_addresses` 的非空元组；`BARE_METAL_ACTIVE_CHILD_CHECKS`（VM + NIC）与 `CLUSTER_ACTIVE_CHILD_CHECKS` **不得**被削弱或替换；NIC 删除路径**必须**真实消费该常量。
9. **漂移检测三件套（T-34 / T-35 / T-36）为必需项，不得省略、不得降级、不得 mock**；`DRIFT_QUERY` 必须与 AC-34 的 SQL 语义一致，且 `T-35` / `T-36` 必须真正绕过应用层写入反例。
10. 请求 / 响应 schema **封闭**（`extra="forbid"`）；`IpAddressCreate` 恰 `{network_interface_id, ip_address}`；`IpAddressUpdate` 恰 `{ip_address}`；空 body → `400`；`ip_address` 为 `null` → `400`。
11. **无 `status`**；**无 VRF / 命名空间**；**无 IP 池 / 网段 / DHCP / DNS / 自动发现 / 外部平台同步**；**无多态父载体 / 载体类型选择器**；**无除 `ip_address` 与父标识外的未确认字段**。
12. **不得为** NQ-1 / NQ-2 / NQ-3 / NQ-5 / NQ-8 预留任何字段、参数、分支、常量或占位（含 `# TODO` 与不可达 `if`）。
13. 不新增任何 CASCADE / 触发器 / `COLLATE`；**不改 `0001`–`0005`**；现有基线 migration 保持字节不变。
14. 既有 guard **必须演进而非删除**；`BOUNDARY_TOKENS` 与 `test_network_interfaces_guards` 的 G-7 / G-9 **必须**同步，否则 F005 会因 F004 / F009 guard 失败。
15. 失败必须由**后端**裁决（§21）；前端**不得**重复实现唯一性 / 父存在性 / 删除守卫。
16. 所有端点位于 `/api` 前缀下，由 F013 中间件**自动覆盖**，**不新增白名单**；错误信封 / 状态码 / 分页 / 事务 / 活跃过滤**复用**既有机制。
17. F011 的 IP 行导入（未来）**必须复用**本 Feature 的领域校验与推导服务，不得绕过 IP 冲突（NQ-9 / R-IMPORT-002）——本 Feature 记录该义务，**不实现导入**。

---

## Constraints

1. 不得修改或新增 `clusters` / `users` / `sessions` / `bare_metals` / `virtual_machines` / `network_interfaces` 的列与约束；只新增 `0006`。
2. 不得新增领域对象、字段、关系、状态或唯一性规则；`ip_address` 是唯一登记字段。
3. 不得实现第二条 `deleted_at` 写入路径；不得实现 restore / undelete / purge / 批量删除 / 已删资源查看。
4. 不得偏离 `api-conventions.md` 的信封、状态码、分页与 Empty / Not Found 语义；不得修改既有契约正文。
5. 不得引入新框架 / 新中间件 / 新依赖 / vue-router；不得引入 EAV / 通用表 / STI / 多态 / JSONB。
6. 不得引入触发器、复合外键、`COLLATE`、`lower()` 表达式索引、`CASCADE`。
7. 不得注册 Cluster 视角 / 关联聚合 / 计数 / Excel 导入端点；不得注册 `by-name`。
8. 不得把 `ip_address` 的格式 / 归一化规则写进任何位置（含注释中的强制性断言）。
9. 不得为 VRF、IP 状态、IP 池、多态父载体、`cluster_id` 可写、格式归一化预留字段 / 参数 / 分支。
10. 不得让前端成为业务守卫的裁决点（§21）。

---

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 注册 `/api/ip-addresses` 使 `BOUNDARY_TOKENS`（含两个 `ip` token，全局扫描）与 `test_network_interfaces_guards.test_g7` 失败；处置不当会「删测试 / 收窄扫描范围」 | REQUIRED #14；G-7 |
| R2 | `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS == ()` 与 `"= ()"` 断言必然失效；若被删除则父删子拦 fail-open | REQUIRED #8；G-8；T-27 ~ T-31 |
| R3 | 表集合 / 路由 / migration head guard 被删除而非演进 | REQUIRED #14；G-5 / G-6 / G-16 |
| R4 | **漂移检测被弱化**（只测抽样行、用 mock 代替真实反例、或把查询只放在一次性脚本里）导致 R-IP-001 的静默漏洞不可发现 | REQUIRED #9；决策 6；T-34 / T-35 / T-36 三件套必须同时存在 |
| R5 | 有人「顺手」加上 `lower(ip_address)` 唯一索引 / `COLLATE` / 格式 CHECK / trim，静默修改已确认的比较语义 | REQUIRED #1/#2；G-2 / G-4 / G-10；T-10 / T-12 |
| R6 | 出现第二条 `cluster_id` 写入路径，或 `cluster_id` 泄漏到请求 / 响应 | REQUIRED #4；G-9；T-07 / T-37 |
| R7 | 唯一性 / FK 冲突返回 500 | REQUIRED #6；T-08 / T-11 |
| R8 | 锁范围扩大（一并锁 BareMetal / Cluster）引入新锁序与死锁面；或漏锁父 NIC 产生孤立记录 | 决策 7；REQUIRED #5；T-31 / T-32 |
| R9 | `23503` 在产品路径不可达时的 `409 REFERENCE` 与契约期望的 `404` 被误认为缺陷 | 决策 7.6；契约 §4.3 显式记录该路径不可达 |
| R10 | 文档漂移残留（关键设计决策 #3 仍写 F014 归属）导致后续 Feature 找错落点 | 决策 1 文档同步 #2 |
| R11 | 前端把「同 Cluster IP 唯一」或 IP 格式做成前端校验 / 输入限制，形成第二裁决点 | REQUIRED #15；G-17；T-41 |
| R12 | F011 未来重新实现一套 IP 校验，绕过冲突检查 | REQUIRED #17；契约 §1 / §10 显式声明 |

---

## Open Questions

### Blocking

**无。** 本轮 NQ-4 / NQ-6 / NQ-7 已由 Architecture 裁定（决策 2 / 3 / 4）。

### Non-blocking

1. **NQ-1（`ip_address` 格式 / 归一化）**：**不实现、不承诺**（G-10 / T-12）。若未来确认格式校验，会在保存路径引入**拒绝**；若确认归一化，会改变唯一性语义并需数据迁移 —— 必须作为**新增产品规则**单独确认。
2. **NQ-2（父绑定可变性）**：**默认不可变**（`PATCH` 不含该字段，T-22）。
3. **NQ-3（`ip_address` 字面值可变性）**：**默认可变**（PATCH + 重校验，T-20 / T-21）。
4. **NQ-4（响应是否暴露 `cluster_id`）**：**已裁定为不暴露**；请求侧永不接受。
5. **NQ-5（BareMetal 跨 Cluster 迁移的连带重推导）**：属未来 Feature；V1 不存在改属产品路径，触发条件不可达。**记录**：若该能力落地，必须同事务重推导并对目标 Cluster 重校验唯一性，否则 `DRIFT_QUERY` 将 > 0 行。
6. **NQ-8（IP 的 `by-name` 别名）**：**不提供**。
7. **NQ-9（F011 复用校验）**：F011 的 IP 行导入必须复用本 Feature 的领域校验与推导服务（REQUIRED #17）。
8. **NQ-10（文档 / 计划元数据漂移）**：见决策 1 / 12。
9. **实现注意（非产品问题）**：`ux_ip_addresses_cluster_ip_active` 经 `23505` 触发时，`sqlstate.py` 的字段回退可能解析出非契约的 `field`；契约已声明该 `field` 在 DB 兜底路径上**不构成契约**。

---

## Implementation Layers

```text
database: true
backend:  true
frontend: true
```

**文件所有权**：Backend = `backend/**` + `tests/**`；Frontend = `frontend/**`；共享 `docs/**` 由协调器统一落盘。

---

## Verification Strategy

1. **契约层**：5 字段封闭表示；`cluster_id` 不在响应 / 请求；必填 `400`；父存在性 / 活跃性 `404`；列表 Empty 与详情 Not Found 可区分；`?network_interface_id=` 的 Empty-vs-NotFound；负向路由 / 参数。
2. **唯一性**：同 Cluster 冲突（跨 BM / 跨 NIC）`409 DUPLICATE`；跨 Cluster 允许；IPv6 大小写不同可共存；软删释放；**绕过应用层直插被 `23505` 拒绝**；无 `lower()` / `COLLATE`。
3. **推导与漂移（重点）**：T-33 / T-34 / **T-35** / **T-36**；G-9 单一写入路径。
4. **并发与关系写入**：`FOR SHARE` 父 NIC 锁、两种交错、孤立记录不变式 0 行、漂移仍为 0 行、无新增锁序；`23505` / `23503` 均非 5xx。
5. **F014 端到端**：NIC 有活跃 IP → `409 ACTIVE_CHILDREN_EXIST` 无部分写入；软删后可删；BareMetal 级联阻断经 NIC 检查成立；检查点常量演进且被真实消费；`IP_ADDRESS_ACTIVE_CHILD_CHECKS == ()`。
6. **维护与删除**：PATCH 部分更新与封闭性、修正后重校验、软删、不级联逐字段比对、无恢复 / 批量 / `include_deleted`。
7. **无状态 / 无 VRF / 无未确认字段 / 无未确认能力预留**（G-2 / G-10 / G-11 / T-12 ~ T-15 / T-42）。
8. **数据层结构（G-1 ~ G-4 / G-12 / G-13 / G-16）**：列 / CHECK / FK / 索引 / collation / 触发器 / CASCADE / 表集合 / migration 可重复与可重建 / downgrade 精确逆序 / 既有表结构不变。
9. **认证面**：`/api/ip-addresses*` 由 F013 自动覆盖，无白名单；未认证 401 且不改数据。
10. **前端（AC-41）**：三态、Empty vs Not Found、`error.code` 分支（含 `DUPLICATE`）、无客户端业务守卫、无新依赖 / 无 vue-router。
11. **工程门禁**：lint 通过；既有测试全绿；**所有 guard 完成演进而非删除**；`alembic check` 无漂移。

---

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

**放行依据**：Product Handoff 为 `READY FOR ARCHITECT` 且无 Blocking；13 项待决技术问题已逐条裁定；`database: true`；API Contract = `READY`。**需用户确认的长期技术决策：无。**

GIT: NONE
