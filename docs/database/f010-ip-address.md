# F010 IP 地址分配与容量 — DATABASE 设计

- **签核**：Database；设计版本 v1（2026-10-09）
- **上游依据**：requirements-v3.md revision 3（§4、§4.1、§11、§11.1、§12、§12.1、§13/§13.1/§13.2/§13.3、§14、§16、§20、§21、§22、§23、§26、§27、§31 T04–T07/T10/T16/T17/T18/T22/T23/T24/T25/T26/T30/T31/T32/T34/T35、§35.2 Q04-A/Q04-B/Q10-A/Q10-B、§35.3 D01/D02）；`docs/features/F010/product.md`（A1–A26、I-1–I-10）；`docs/features/F010/architecture.md`（DR-118–DR-139）；`docs/api/F010.md` 草案 v0；`docs/database/f001-baseline.md` v1（DB-D2/DB-D4/DB-D7）、`f007-interface.md` v1、`f008-network.md` v1（DB-D88/DB-D90/DB-D93）、`f009-ip-pool.md` v1（DB-D104/DB-D105/DB-D106/DB-D107）；`backend/alembic/versions/0008_networks.py`、`0009_ip_pools.py`
- **覆盖**：`ip_addresses` 表、字段/类型/必填/默认、约束/索引/FK 命名、同 Cluster 部分唯一（I-1/DR-119）、CIDR 包含/集群一致性/绑定 Interface 集群一致性三个触发 backstop（DR-120/DR-119/DR-121）、`ip_pool_id` 来源历史 FK（DR-122）、索引集合与 `IpAddressOccupancyProvider` 查询支撑、`_lock_network` 复用与 T07/T35 并发方案（I-8/DR-134）、迁移 `0010_ip_addresses`、真 PG 验证项（V-DB-95–V-DB-111）、已有数据影响。不覆盖 `docs/api/F010.md` 定稿、D01 v9 §5.9 签核、TEST 执行与实现。

## 1. 设计决策汇总（DB-D111–DB-D127）

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D111 | `ip_addresses` 独立对象表，`id` UUID PK `pk_ip_addresses` 默认 `gen_random_uuid()`；软删/恢复/Activity/乐观锁 | CONFIRMED（§13/§21/§27/DR-118）+DESIGN |
| DB-D112 | `network_id` UUID NOT NULL FK `fk_ip_addresses_network_id_networks`→`networks(id)` ON DELETE RESTRICT + `ix_ip_addresses_network_id`；引用须存在、未软删（应用 422）；创建后不可改（应用 422，DR-120） | CONFIRMED（§13/§14/§21/DR-118）+DESIGN |
| DB-D113 | `cluster_id` UUID NOT NULL **冗余** FK `fk_ip_addresses_cluster_id_clusters`→`clusters(id)` ON DELETE RESTRICT + 全量 `ix_ip_addresses_cluster_id`；创建时取自锁定 Network；一致性由触发 backstop（DB-D121） | PROPOSED→DATABASE（I-1/DR-119）+DESIGN |
| DB-D114 | `address` PG 原生 `inet` NOT NULL，`ck_ip_addresses_address_host`（`family=4 AND masklen=32`）+ `ck_ip_addresses_address_not_disabled`（§11.1 五段禁用，纯 SQL backstop）；创建必填、创建后不可改（应用 422，DR-120） | PROPOSED→DATABASE（DR-120/I-4）+DESIGN |
| DB-D115 | `interface_id` UUID NULL FK `fk_ip_addresses_interface_id_interfaces`→`interfaces(id)` ON DELETE RESTRICT + `ix_ip_addresses_interface_id`；非空时绑定 Cluster 一致性由触发 backstop（DB-D122）；可 PATCH 绑定/解绑/转移（DR-121/DR-136） | CONFIRMED（§13/§14/DR-121）+DESIGN |
| DB-D116 | `ip_pool_id` UUID NULL FK `fk_ip_addresses_ip_pool_id_ip_pools`→`ip_pools(id)` ON DELETE RESTRICT + `ix_ip_addresses_ip_pool_id`；分配来源历史，Pool 删除/缩小不回收、不删除（§12/§21 例外） | PROPOSED→DATABASE（DR-122/I-6）+DESIGN |
| DB-D117 | `description` text NULL（无上限，同 F003/F004/F007/F008/F009）；**不落** `metadata`/`name`/`status`（DR-123/I-3） | DESIGN（D01 §5.9 拟） |
| DB-D118 | `version` integer NOT NULL DEFAULT 1 CHECK ≥1；`created_at`/`updated_at` timestamptz NOT NULL `now()`（`updated_at` 应用维护无触发器）；`deleted_at` timestamptz NULL 软删 | DESIGN |
| DB-D119 | 同 Cluster 未删地址唯一：部分唯一 `uq_ip_addresses_cluster_id_address UNIQUE(cluster_id,address) WHERE deleted_at IS NULL`（I-1/DR-119 落地） | PROPOSED→DATABASE（I-1/DR-119）+DESIGN |
| DB-D120 | `address` 属 Network CIDR + 非网络/广播 backstop：`fn/trg_ip_addresses_cidr_contains`（BEFORE INSERT/UPDATE，`FOR KEY SHARE` networks；含网络地址/广播地址排除与 /31、/32 例外） | PROPOSED→DATABASE（DR-120）+DESIGN |
| DB-D121 | `cluster_id` 一致性 backstop：`fn/trg_ip_addresses_cluster_consistent`（BEFORE INSERT/UPDATE，`FOR KEY SHARE` networks，`NEW.cluster_id = networks.cluster_id`，模式同 F009 `trg_ip_pools_cidr_contains`） | PROPOSED→DATABASE（I-1/DR-119）+DESIGN |
| DB-D122 | 绑定 Interface 的 Cluster 一致性 backstop：`fn/trg_ip_addresses_interface_cluster`（BEFORE INSERT/UPDATE，`interface_id` 非空时经 `interfaces→resources` 校验 `resources.cluster_id = NEW.cluster_id`；不检查软删，软删交应用引用检查/422） | CONFIRMED（§14/DR-121）+DESIGN |
| DB-D123 | **不建** `network_id`/`address`/`cluster_id`/`ip_pool_id` 不可变触发器；不可改为 CONTRACT 层规则，应用 422。沿用 F008 DB-D93、F009 §3.5 先例 | DESIGN（DR-120/I-4 裁定） |
| DB-D124 | 索引集合：`uq_ip_addresses_cluster_id_address`（部分唯一）+ `ix_ip_addresses_network_id/_cluster_id/_interface_id/_ip_pool_id/_deleted_at`；不建 pg_trgm/GIN、不建 address 单列 B-tree、不建额外复合索引（F013 交叉引用：F013 已评估 IP 精确/前缀索引并**延期**，`0013` 不建 IP 索引；触发条件见 docs/database/f013-search-index.md §4） | DESIGN |
| DB-D125 | 并发/锁：手动/自动分配与恢复事务内复用 `_lock_network`（networks 行 FOR UPDATE，F008 DB-D90/DB-D93）；触发 backstop 对 networks 行 `FOR KEY SHARE` 串行；部分唯一跨 Network/Cluster 兜底；`IpAddressOccupancyProvider` 由部分唯一 `(cluster_id,address)` 与 `ix_ip_addresses_network_id` 支撑；关闭 D02 相应部分 | PROPOSED→DATABASE（I-2/I-8/DR-126/DR-134）+DESIGN |
| DB-D126 | 迁移 `0010_ip_addresses`，`down_revision=0009_ip_pools`；**不重复启用** btree_gist/pg_trgm（0008/0001 已启用）；单一 head、全表新建无回填、对称可逆 | DESIGN（DR-132） |
| DB-D127 | 100% 新建对象，无已有数据迁移；downgrade 丢弃 `ip_addresses` 数据不可逆，生产回滚用 F001 全库备份 | DESIGN |

## 2. `ip_addresses` 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK `pk_ip_addresses` |
| network_id | UUID | NOT NULL | — | FK `fk_ip_addresses_network_id_networks`→`networks(id)` ON DELETE RESTRICT；`ix_ip_addresses_network_id` |
| cluster_id | UUID | NOT NULL | — | 冗余；FK `fk_ip_addresses_cluster_id_clusters`→`clusters(id)` ON DELETE RESTRICT；`ix_ip_addresses_cluster_id` |
| address | inet | NOT NULL | — | `ck_ip_addresses_address_host`；`ck_ip_addresses_address_not_disabled`；部分唯一 `uq_ip_addresses_cluster_id_address` |
| interface_id | UUID | NULL | — | FK `fk_ip_addresses_interface_id_interfaces`→`interfaces(id)` ON DELETE RESTRICT；`ix_ip_addresses_interface_id` |
| ip_pool_id | UUID | NULL | — | FK `fk_ip_addresses_ip_pool_id_ip_pools`→`ip_pools(id)` ON DELETE RESTRICT；`ix_ip_addresses_ip_pool_id` |
| description | text | NULL | — | — |
| version | integer | NOT NULL | 1 | `ck_ip_addresses_version`：≥1 |
| created_at/updated_at | timestamptz | NOT NULL | now() | UTC；`updated_at` 应用维护 |
| deleted_at | timestamptz | NULL | — | 软删（释放） |

CHECK 形态（`ck_` 由 naming convention 展开为 `ck_ip_addresses_<name>`）：

| 约束名 | 表达式 |
| --- | --- |
| ck_ip_addresses_address_host | `family(address) = 4 AND masklen(address) = 32` |
| ck_ip_addresses_address_not_disabled | `NOT (address << '0.0.0.0/8'::inet OR address << '127.0.0.0/8'::inet OR address << '169.254.0.0/16'::inet OR address << '224.0.0.0/4'::inet OR address << '240.0.0.0/4'::inet)` |
| ck_ip_addresses_version | `version >= 1` |

DDL（关键片段，供迁移使用）：

```sql
CREATE TABLE ip_addresses (
    id           uuid        NOT NULL DEFAULT gen_random_uuid(),
    network_id   uuid        NOT NULL,
    cluster_id   uuid        NOT NULL,
    address      inet        NOT NULL,
    interface_id uuid,
    ip_pool_id   uuid,
    description  text,
    version      integer     NOT NULL DEFAULT 1,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    deleted_at   timestamptz,
    CONSTRAINT pk_ip_addresses PRIMARY KEY (id),
    CONSTRAINT fk_ip_addresses_network_id_networks
        FOREIGN KEY (network_id) REFERENCES networks(id) ON DELETE RESTRICT,
    CONSTRAINT fk_ip_addresses_cluster_id_clusters
        FOREIGN KEY (cluster_id) REFERENCES clusters(id) ON DELETE RESTRICT,
    CONSTRAINT fk_ip_addresses_interface_id_interfaces
        FOREIGN KEY (interface_id) REFERENCES interfaces(id) ON DELETE RESTRICT,
    CONSTRAINT fk_ip_addresses_ip_pool_id_ip_pools
        FOREIGN KEY (ip_pool_id) REFERENCES ip_pools(id) ON DELETE RESTRICT,
    CONSTRAINT ck_ip_addresses_address_host
        CHECK (family(address) = 4 AND masklen(address) = 32),
    CONSTRAINT ck_ip_addresses_address_not_disabled
        CHECK (NOT (
            address << '0.0.0.0/8'::inet OR address << '127.0.0.0/8'::inet
            OR address << '169.254.0.0/16'::inet OR address << '224.0.0.0/4'::inet
            OR address << '240.0.0.0/4'::inet)),
    CONSTRAINT ck_ip_addresses_version CHECK (version >= 1)
);

CREATE UNIQUE INDEX uq_ip_addresses_cluster_id_address
    ON ip_addresses (cluster_id, address) WHERE deleted_at IS NULL;

CREATE INDEX ix_ip_addresses_network_id   ON ip_addresses (network_id);
CREATE INDEX ix_ip_addresses_cluster_id   ON ip_addresses (cluster_id);
CREATE INDEX ix_ip_addresses_interface_id ON ip_addresses (interface_id);
CREATE INDEX ix_ip_addresses_ip_pool_id   ON ip_addresses (ip_pool_id);
CREATE INDEX ix_ip_addresses_deleted_at   ON ip_addresses (deleted_at);
```

不落字段（§13/DR-123/I-3）：`metadata`、`name`、`status`、实时探测状态。

## 3. 交核裁定

### 3.1 I-1/DR-119 同 Cluster 未删地址唯一

**表示法裁定：采纳冗余 `cluster_id` + 部分唯一 `(cluster_id,address) WHERE deleted_at IS NULL`。**
- 唯一作用域是 **Cluster**、跨 Network/Pool（§14）；`network_id` 无法表达；PG 唯一索引不能跨表取 `networks.cluster_id`；`UNIQUE(network_id,address)` 不满足 §14；纯触发器有并发窗口且 §27 要求 PostgreSQL 兜底。故冗余列是必要载体。
- `cluster_id` 恒等于 `networks.cluster_id`：创建在事务内先取 `_lock_network`（FOR UPDATE），由应用从锁定 Network 取值写入；有未删 IP 时 Network 不可改 cluster（F010 引用检查器）；DB BEFORE 触发 backstop（DB-D121）对 `networks` 行 `FOR KEY SHARE` 校验；行缺失交 FK 报错。
- 软删（释放）释放索引项，地址可重用；恢复置 `deleted_at=null` 重新进入索引，冲突由部分唯一直接拒绝 → 应用 409 `unique_conflict{field:"address"}`，不覆盖新占用。
- **拒绝的替代方案**：复合 FK `(network_id, cluster_id) REFERENCES networks(id, cluster_id)` 需在 `networks` 上新增 `UNIQUE(id, cluster_id)`（跨 Feature 改 F008 schema + 额外索引），且仍不能替代部分唯一的人可读冲突语义，不采用。

```sql
CREATE OR REPLACE FUNCTION fn_ip_addresses_cluster_consistent()
RETURNS trigger AS $$
DECLARE
    net_cluster uuid;
BEGIN
    SELECT n.cluster_id INTO net_cluster
      FROM networks n
     WHERE n.id = NEW.network_id
     FOR KEY SHARE;
    IF NOT FOUND THEN
        RETURN NEW;   -- 交 FK 报错
    END IF;
    IF NEW.cluster_id IS DISTINCT FROM net_cluster THEN
        RAISE EXCEPTION
            'ip_addresses.cluster_id must equal the owning network cluster'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ip_addresses_cluster_consistent
BEFORE INSERT OR UPDATE ON ip_addresses
FOR EACH ROW EXECUTE FUNCTION fn_ip_addresses_cluster_consistent();
```

### 3.2 DR-120 地址边界与 CIDR 归属

- `address` 用 PG 原生 `inet`，`ck_ip_addresses_address_host` 恒为 IPv4 主机地址（`family=4 AND masklen=32`）：带掩码/CIDR 形式与 IPv6 被 DB 拒（应用先 422）。
- §11.1 五段禁用地址用纯 SQL `ck_ip_addresses_address_not_disabled` 作 backstop。
- 网络/广播与 CIDR 归属为跨表规则，`fn/trg_ip_addresses_cidr_contains` 作 backstop：`address <<= networks.cidr`；`masklen(cidr) <= 30` 时排除网络地址与广播地址；`/31` 两址可用、`/32` 唯一地址可用。

```sql
CREATE OR REPLACE FUNCTION fn_ip_addresses_cidr_contains()
RETURNS trigger AS $$
DECLARE
    net_cidr cidr;
BEGIN
    SELECT n.cidr INTO net_cidr
      FROM networks n
     WHERE n.id = NEW.network_id
     FOR KEY SHARE;
    IF NOT FOUND THEN
        RETURN NEW;   -- FK 报错
    END IF;
    IF NOT (NEW.address <<= net_cidr::inet) THEN
        RAISE EXCEPTION
            'ip_addresses.address must belong to the owning network CIDR'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF masklen(net_cidr) <= 30
       AND (NEW.address = host(network(net_cidr))::inet
            OR NEW.address = host(broadcast(net_cidr))::inet) THEN
        RAISE EXCEPTION
            'ip_addresses.address must not be the network/broadcast address'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ip_addresses_cidr_contains
BEFORE INSERT OR UPDATE ON ip_addresses
FOR EACH ROW EXECUTE FUNCTION fn_ip_addresses_cidr_contains();
```

- 触发器对任意 UPDATE 生效（含软删/恢复）；恢复越界被拒。
- **未由 DB 承担**（应用主校验 + `_lock_network` + 占用提供者）：gateway、RESERVED 池范围排除。`<<=`/`<<` 要求 family 相同，IPv4 已由 CHECK 排除 IPv6。
- **network/address 不可变裁定（DB-D123）**：**不建 DB 不可变触发器**，应用 PATCH 含 `network`/`address`/`network_id`/`cluster_id`/`ip_pool`→422。理由：后果已由触发/索引兜底；沿用 F008 DB-D93、F009 §3.5 先例。

### 3.3 DR-121 绑定 Interface 的 Cluster 一致性

```sql
CREATE OR REPLACE FUNCTION fn_ip_addresses_interface_cluster()
RETURNS trigger AS $$
DECLARE
    res_cluster uuid;
BEGIN
    IF NEW.interface_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT r.cluster_id INTO res_cluster
      FROM interfaces i
      JOIN resources r ON r.id = i.resource_id
     WHERE i.id = NEW.interface_id;
    IF NOT FOUND THEN
        RETURN NEW;   -- interface FK 报错
    END IF;
    IF res_cluster IS DISTINCT FROM NEW.cluster_id THEN
        RAISE EXCEPTION
            'bound interface resource must be in the same cluster as the IP'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ip_addresses_interface_cluster
BEFORE INSERT OR UPDATE ON ip_addresses
FOR EACH ROW EXECUTE FUNCTION fn_ip_addresses_interface_cluster();
```

- 不加行锁：`interfaces.resource_id`（F007 DB-D74）与 `resources.cluster_id`（F004 DB-D40）均不可变，链路值稳定；物理删由两个 FK RESTRICT 阻断。
- **软删 Interface 的绑定**留应用承担（引用检查器 + 恢复重检 `dependency_deleted`），DB 仅保证 Cluster 一致性（§14）。
- 解绑（`interface_id` 显式 null）不受 Network INACTIVE 限制（DR-136）；DB 触发器在 `NULL` 时直接放行。

### 3.4 DR-122 分配来源（`ip_pool_id`）

- `ip_pool_id` 可空 FK→`ip_pools(id)` ON DELETE RESTRICT + `ix_ip_addresses_ip_pool_id`，承接 F009 DB-D105 的「来源历史」：自动=指定 AUTO 池；手动=地址所属未删池或 null（服务端推导，创建后不可改）；Pool 软删行永不物理删除，FK 软删后仍有效；Pool 删除/缩小不回收、不删除、不阻止（§12/§21 例外）；Pool 物理删除被 FK RESTRICT 拒。
- 本表 FK/index 落实 F009 DB-D105 交 F010 的责任。

### 3.5 I-8/DR-134/D02：索引集合与查询支撑

| 索引/约束 | 服务的查询或约束 | 说明 |
| --- | --- | --- |
| `uq_ip_addresses_cluster_id_address`（部分唯一，`WHERE deleted_at IS NULL`） | 同 Cluster 未删地址唯一（§14/§27）；恢复重检；占用点查/范围扫描（`cluster_id` 前导 + `address` 次列） | 唯一载体；软删释放；恢复冲突原子拒绝 |
| `ix_ip_addresses_network_id` | §20 Network 未删占用计数；列表 `network_id` 过滤；Network 引用检查器；FK RESTRICT | 全量（含软删） |
| `ix_ip_addresses_cluster_id` | FK RESTRICT 校验父 Cluster 删除；`cluster_id` 过滤含 `deleted=include/only` | 全量 btree |
| `ix_ip_addresses_interface_id` | Interface 引用检查器；列表 `interface_id`/`bound` 过滤；FK RESTRICT | 全量 |
| `ix_ip_addresses_ip_pool_id` | 列表 `ip_pool_id` 过滤；FK RESTRICT；F009 DB-D105 | 全量 |
| `ix_ip_addresses_deleted_at` | `deleted=include/only` 可见性过滤 | 与 F008/F009 一致 |

- **不建** pg_trgm/GIN；**不建** `address` 单列 B-tree；**不建**额外复合 `(network_id,address)`。
- **`IpAddressOccupancyProvider` 查询支撑**（F009 DR-109/110）：同一事务、已持 `_lock_network`：范围冲突（RESERVED）`WHERE cluster_id=:c AND deleted_at IS NULL AND address BETWEEN :s AND :e` 走部分唯一范围扫描；gateway 点查 `start=end`；Network 占用计数走 `ix_ip_addresses_network_id`。若 EXPLAIN 显示全量排序再评估新增复合索引（NOTE）。
- D02 关闭输入：唯一/索引集合、`_lock_network` 复用、占用提供者索引支撑、T07/T35 并发方案。

### 3.6 并发与生命周期边界

| 场景 | DB 机制 | 应用机制 |
| --- | --- | --- |
| 手动/自动分配同 Network 并发 | 触发 `FOR KEY SHARE` + 部分唯一 | `_lock_network`（FOR UPDATE）串行；升序选择；耗尽 409 `no_available_address` |
| 跨 Network 同 Cluster 重复 | 部分唯一 `(cluster_id,address)` 原子兜底 | 409 `unique_conflict{field:"address"}` |
| 分配 vs RESERVED/网关/范围变更（T35/§12.1） | 触发 KEY SHARE 与 `_lock_network` FOR UPDATE 串行 | 共享 `_lock_network` + `IpAddressOccupancyProvider` |
| `cluster_id` 一致性 | `trg_ip_addresses_cluster_consistent`（KEY SHARE） | 创建自锁定 Network 取值 |
| 绑定 Interface 跨 Cluster | `trg_ip_addresses_interface_cluster` | 应用校验 422 field="interface" |
| 恢复重检 | 部分唯一重新入索引 + 三个 BEFORE UPDATE 触发重跑 | 地址唯一 409 → 依赖失效 409 → 越界 422；不覆盖新对象 |
| 乐观锁 | `version` CHECK + 条件 UPDATE | rowcount=0 → 409 VERSION_CONFLICT |
| 软删/恢复 | `deleted_at`；部分唯一随 `deleted_at` 进退 | 默认过滤；不级联 |
| Network/Interface 引用 | FK RESTRICT（物理删）；无软删引用约束 | F010 注册引用检查器 → 409 `reference_exists` |
| Endpoint 引用（F012） | — | F010 提供 `register_ip_address_reference_checker`（默认空集） |
| IPPool 来源 | FK RESTRICT（物理删） | 不注册引用检查、不阻止、不回收（§21 例外） |

**`_lock_network` 复用说明**：锁为 `SELECT ... FROM networks WHERE id=:id FOR UPDATE`（F008 DB-D90/DB-D93）。F010 手动分配、自动分配、恢复事务内先取该锁；F009 RESERVED/范围/gateway 变更共用同一锁域。触发 backstop 的 `FOR KEY SHARE` 与同事务已持的 FOR UPDATE 不冲突；跨事务则 KEY SHARE 阻塞至 FOR UPDATE 释放，天然串行化。

## 4. 数据完整性对应表（Database 视角，精简）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证（计划） |
| --- | --- | --- | --- | --- | --- |
| §14/§27/DR-119 同 Cluster 未删地址唯一 | 手动/自动分配、恢复 | 部分唯一 `(cluster_id,address) WHERE deleted_at IS NULL` | 409 `unique_conflict{field:"address"}` | 索引仲裁；软删释放；恢复重检 | V-DB-102/110 |
| §11.1/§13.2/§14/DR-120 地址主机/IP 属 CIDR/非禁用/非网络广播 | POST/自动分配/恢复 | `ck_address_host`；`ck_address_not_disabled`；`trg_ip_addresses_cidr_contains`（KEY SHARE） | 422 field="address" | 触发器与 `_lock_network` 串行 Network 改 cidr | V-DB-97/98/99 |
| §14/DR-119 `cluster_id` 一致 | POST/restore | `trg_ip_addresses_cluster_consistent`（KEY SHARE） | 创建取锁定 Network；改 cluster 被引用检查器阻 | — | V-DB-100 |
| §14/DR-121 绑定 Cluster 一致 | 绑定/转移（PATCH） | `trg_ip_addresses_interface_cluster` | 422 field="interface" | interface/resource cluster 不可变 | V-DB-101 |
| §13.1/§27/DR-126 自动分配不重复、升序 | 自动分配 | 部分唯一兜底 + 触发 KEY SHARE | `_lock_network` + 升序；耗尽不切换 | T07 双会话 | V-DB-106 |
| §13.1/§13.2 Network ACTIVE/auto_allocate/Pool AUTO | 手动/自动分配 | 无 | 409 `allocation_not_allowed{condition}` | — | 契约/集成 |
| §11.1/§12.1 gateway/RESERVED 占用 | Network/池变更 + 分配 | 无跨表约束 | `IpAddressOccupancyProvider` + `_lock_network` → 409 `address_in_use` | T35 双会话 | V-DB-106 |
| §12/§21/§13 `ip_pool_id` 来源历史例外 | Pool 删除/缩小 | `fk_ip_addresses_ip_pool_id_ip_pools` RESTRICT（物理）；软删无约束 | 不级联、不回收；来源保留 | 软删保行；FK 仍有效 | V-DB-103 |
| §13.3/§16 Endpoint 引用（F012） | 解绑/转移/释放 | — | 引用检查器 → 409 `reference_exists` | F012 注册挂钩 | F010 桩 + F012 端到端 |
| §21/§27 Network/Interface 引用 | Network/Interface 删除/改 cidr/cluster | FK RESTRICT（物理删） | F010 注册引用检查器 → 409 `reference_exists` | FOR UPDATE 串行 | F008/F009 集成 |
| §21/§27 软删/恢复 | 释放/恢复 | `deleted_at`；部分唯一；三个 BEFORE UPDATE 触发重跑 | 恢复重检地址唯一→依赖→越界；不覆盖 | 不级联 | V-DB-110 |
| §4.1/§21 network/address/ip_pool 归属不可改 | PATCH | 无触发器（DB-D123） | 含不可变字段→422 | — | V-DB-104 |
| §23 乐观锁 | PATCH/DELETE/restore | `version` CHECK + 条件 UPDATE | rowcount=0→409 | 真并发 | V-DB-105 |
| §26/§27 真实 PG | 迁移/约束 | 0010 up/down/up、单一 head、无回填、扩展不重复启用 | — | — | V-DB-95/111 |

## 5. 迁移 `0010_ip_addresses`

- `revision = "0010_ip_addresses"`、`down_revision = "0009_ip_pools"`；单一 head。
- **不重复启用扩展**：btree_gist 由 `0008`、pg_trgm 由 `0001` 启用；本迁移无排他约束，**不需要**任何 gist opclass，不含 `CREATE EXTENSION`。
- 无回填（全表新建）。

upgrade 顺序：
1. `create_table("ip_addresses", ...)`：全部列 + PK + 4 个 FK + 3 个 CHECK。
2. 部分唯一索引 `uq_ip_addresses_cluster_id_address`（`unique=True, postgresql_where=sa.text("deleted_at IS NULL")`）。
3. 五个普通索引。
4. `op.execute` 建 `fn_ip_addresses_cluster_consistent()` + `trg_ip_addresses_cluster_consistent`。
5. `op.execute` 建 `fn_ip_addresses_cidr_contains()` + `trg_ip_addresses_cidr_contains`。
6. `op.execute` 建 `fn_ip_addresses_interface_cluster()` + `trg_ip_addresses_interface_cluster`。

downgrade（对称逆序）：依次 DROP 三个 TRIGGER/FUNCTION → 六个索引 → `drop_table("ip_addresses")`；**不 DROP btree_gist / pg_trgm**（F001 DB-D4）。

校验计划：真库 `up → down → up`；`alembic heads` 唯一 = `0010_ip_addresses`；对象齐全（列/CHECK/部分唯一/5 索引/4 FK/3 触发）；`pg_extension` 在 0010 前后无新增。

## 6. Backend 可依赖保证与测试项

**保证（DB 层）**：`id` 唯一（PK）；`network_id`/`cluster_id` 非空指向存在 Network/Cluster（FK），物理删被引用父对象被 RESTRICT 拒；`cluster_id` 恒等于锁定 Network 的 cluster（触发）；`address` 恒为 IPv4 主机地址；`address` 恒不在 §11.1 五段禁用范围（CHECK）；`address` 恒属所属 Network CIDR 且非网络/广播（`masklen<=30` 时）（触发）；绑定 `interface_id` 非空时其 Resource 与 IP 同 Cluster（触发）；同 Cluster 未删 `(cluster_id,address)` 唯一、跨 Cluster 允许、软删释放、恢复冲突拒（部分唯一）；`interface_id`/`ip_pool_id` 可空指向存在对象；`description` 可空无上限；`version` ≥1 默认 1；索引集合存在且无 pg_trgm/GIN、无 address 单列 B-tree；0010 有真实 downgrade、单一 head、无回填、扩展不重复启用。

**不保证（应用/Contract 层）**：Network ACTIVE、`auto_allocate`、Pool `allocation_mode=AUTO` 与耗尽判定；gateway/RESERVED 占用冲突；network/address/cluster/ip_pool 不可变（应用 422）；软删 Network/Interface 引用保护；Endpoint 引用（F012 挂钩）；软删 Interface 的绑定校验；`cluster_id` 创建取值正确性；§20 容量计算；`address` 输入归一化为 `/32`（应用）。

**计划测试项（真实 PG，V-DB-95–V-DB-111，无 PASS）**：
- **V-DB-95** 迁移 `up/down/up` 一致；`down_revision=0009_ip_pools`；`alembic heads` 唯一；对象齐全；无回填；`pg_extension` 无新增。
- **V-DB-96** 默认/NOT NULL。
- **V-DB-97** `ck_address_host`：普通 IPv4 接受；带掩码/IPv6/非 32 拒。
- **V-DB-98** `ck_address_not_disabled`：五段内拒、紧邻段外接受。
- **V-DB-99** CIDR 包含触发：越界拒；`/32` 网络地址接受；`/31` 两址接受；`/24` 网络/广播拒；Network 改 cidr 与分配并发串行。
- **V-DB-100** `cluster_id` 一致性触发。
- **V-DB-101** 绑定 Cluster 触发。
- **V-DB-102** 部分唯一：同 Cluster 重复拒、跨 Cluster 允许、软删重建、恢复冲突、并发仅一成功。
- **V-DB-103** FK RESTRICT：物理删被引用父对象拒；软删池 FK 仍有效。
- **V-DB-104** 归属不可改断言（无 DB 触发器，应用 422）。
- **V-DB-105** `version` 默认/`<1` 拒；乐观锁双会话。
- **V-DB-106** 并发：`_lock_network` 串行化 T07；RESERVED/gateway vs 分配互斥 T35；无重复占用。
- **V-DB-107** 索引目录：6 索引/约束、谓词正确；无 pg_trgm/GIN、无 address 单列 B-tree。
- **V-DB-108** 占用/容量查询索引使用（EXPLAIN）。
- **V-DB-109** 触发属性（BEFORE INSERT OR UPDATE、软删/普通 UPDATE 不误拒）。
- **V-DB-110** 恢复重检（DB 层）。
- **V-DB-111** 迁移边界：0010 不含 `CREATE EXTENSION`；downgrade 后可再 upgrade；既有表无结构改动。

## 7. 已有数据影响

- **全表新建，无已有数据迁移**；不新增列到既有表、不回填（DB-D127）。
- **不修改既有表结构**：`networks`/`interfaces`/`ip_pools`/`clusters` 不变。
- **新增入向 FK（RESTRICT）**：有 `ip_addresses` 子行时物理删 Network/Interface/IPPool/Cluster 被拒；新增 Interface 的 DB RESTRICT 兜底，符合 §21。
- **落实 F009 交接**：`fk_ip_addresses_ip_pool_id_ip_pools` 与索引为 F009 DB-D105 约定由 F010 建。
- **扩展**：不新增/不删除；btree_gist（0008）与 pg_trgm（0001）前后一致。
- **回滚风险**：downgrade 丢弃 `ip_addresses` 数据；生产回滚依赖 F001 全库备份（DB-D127/F001 DB-D12）。
- **单 head 链**：0009→0010。

## 8. 未验证项与风险

- I-1（已闭合，交 CONTRACT/DATABASE 签核）：冗余 `cluster_id` + 部分唯一 + 一致性触发闭环；`address` 属 CIDR 触发 backstop；软删释放、恢复重检不覆盖。真实 PG 与并发以 V-DB-95–V-DB-111 核对。
- I-2（已闭合，设计层）：`_lock_network` 复用 + 部分唯一 + 升序；T07/T35 方案见 §3.6/§6；实现须真正取锁方可闭合（ISSUES）。
- I-3/I-4/I-6（LOW，交 CONTRACT/D01 v9 §5.9）：不落 metadata、`address` host 口径、`network/address/ip_pool` 不可改、来源设置待 Contract 固定；Database 按 DR-119/120/122/123 采纳，非阻塞。
- 禁用段 check 与 `restrict_violation` 触发均为 backstop，应用须先校验并映射 422。
- `remaining` 负值口径、`allocation_not_allowed`/`no_available_address` 登记、I-10 errata 属 CONTRACT/协调器，不阻塞 DATABASE。
- 触发副作用（NOTE）：三个 BEFORE 触发对任意 UPDATE 生效（含软删）；越界/不一致幽灵行的软删亦被拒，属预期。
- I-7（NOTE）：downgrade 丢弃 `ip_addresses` 数据不可逆，生产回滚用 F001 全库备份。
- 只读签核，全部为计划验证无 PASS。

## 9. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-09 | 初次签核（DB-D111–DB-D127）；`ip_addresses` 首次建表；I-1/DR-119 冗余 `cluster_id` + 部分唯一；`ck_address_host`/`ck_address_not_disabled`；三个触发 backstop；`ip_pool_id` FK RESTRICT 承接 F009 来源历史；不建不可变触发器（应用 422）；索引集合与占用提供者查询支撑；`_lock_network` 复用与 T07/T35 并发方案；迁移 `0010_ip_addresses`；V-DB-95–V-DB-111；已有数据影响。 |