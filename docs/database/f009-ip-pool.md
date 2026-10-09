# F009 IP Pool 地址池 — DATABASE 设计

- **签核**：Database；设计版本 v1（2026-10-09）
- **上游依据**：requirements-v3.md revision 3（§4、§4.1、§11、§11.1、§12、§12.1、§14、§20、§21、§22、§23、§26、§27、§31 T15/T33/T34/T40/T41、§35.2 Q04-A/Q04-B/Q10-A/Q10-B、§35.3 D01/D02）；docs/features/F009/product.md（A1–A23、I-1–I-6）；docs/features/F009/architecture.md（DR-102–DR-117）；docs/api/F009.md 草案 v0；docs/database/f001-baseline.md v1（DB-D2/DB-D4/DB-D7）、f004-resource.md v1（模式）、f007-interface.md v1（模式）、f008-network.md v1（DB-D80–D94、DB-D90 行锁）；docs/architecture/d01-conventions.md v7（§5/§5.7，v8 §5.8 拟增）；backend/alembic/versions/0008_networks.py
- **覆盖**：ip_pools 表、字段/类型/必填/默认、约束/索引/FK 命名、范围不重叠排他约束（生成列 + `int8range`）、名称部分唯一、`allocation_mode`、CIDR 包含 backstop 触发器、I-1/I-5/DR-104 裁定、迁移 `0009_ip_pools`、真 PG 验证项（V-DB-82–V-DB-94）、F008 遗留订正。不覆盖 docs/api/F009.md 定稿、D01 v8 签核、TEST 执行与实现。

## 1. 设计决策汇总（DB-D95–DB-D110）

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D95 | ip_pools 独立对象表，id UUID PK pk_ip_pools 默认 gen_random_uuid()；network_id UUID NOT NULL FK fk_ip_pools_network_id_networks→networks(id) ON DELETE RESTRICT + ix_ip_pools_network_id | CONFIRMED（§12/§21/DR-102）+DESIGN |
| DB-D96 | name varchar(255) NOT NULL + trim/非空/ASCII 控制 backstop/长度 1–255 CHECK；name_key varchar(255) NOT NULL，`ASCII_lower(btrim(name))` translate 口径 CHECK（不得用 lower()） | PROPOSED→CONTRACT(1–255)+DESIGN（DR-103/D01 §5.8） |
| DB-D97 | 部分唯一 uq_ip_pools_network_id_name_key UNIQUE(network_id,name_key) WHERE deleted_at IS NULL | CONFIRMED（§4.1/§27/DR-103）+DESIGN |
| DB-D98 | start_address/end_address PG 原生 inet NOT NULL；ck 单主机：`family=4 且 masklen=32`；ck `start_address <= end_address`；host 归一化为应用责任（测试/导入同 Service） | CONFIRMED（§12/§26/DR-104）+DESIGN |
| DB-D99 | address_range int8range NOT NULL **生成列**（`GENERATED ALWAYS AS (int8range(set_masklen(start,32)-'0.0.0.0'::inet, set_masklen(end,32)-'0.0.0.0'::inet,'[]')) STORED`）；闭区间载体 | PROPOSED→DATABASE（DR-106/I-1）+DESIGN |
| DB-D100 | 排他约束 excl_ip_pools_network_id_address_range EXCLUDE USING gist (network_id WITH =, address_range WITH &&) WHERE (deleted_at IS NULL)；network_id WITH = 需 btree_gist（0008 已启用，0009 不重复启用） | PROPOSED→DATABASE（DR-106/I-1）+DESIGN |
| DB-D101 | allocation_mode varchar(16) NOT NULL DEFAULT 'MANUAL' + CHECK IN ('MANUAL','AUTO','RESERVED') | CONFIRMED（§12/DR-105）+DESIGN |
| DB-D102 | description text NULL（无长度上限，同 F003/F004/F007/F008） | DESIGN（D01 §5.8 拟） |
| DB-D103 | version integer NOT NULL DEFAULT 1 CHECK≥1；created_at/updated_at timestamptz NOT NULL now()（updated_at 应用维护无触发器）；deleted_at timestamptz NULL 软删 | DESIGN |
| DB-D104 | 跨表 CIDR 包含 DB backstop：fn/trg_ip_pools_cidr_contains（BEFORE INSERT/UPDATE）校验 start/end `<<=` networks.cidr，并对 networks 行 `FOR KEY SHARE`；应用主校验→422 | PROPOSED→DATABASE（DR-104 裁定）+DESIGN |
| DB-D105 | I-5 占用冲突 DB 侧无约束（F009 无 IP 数据）；由应用 `IpOccupancyProvider` 承担（F009 注册空集）；复用 `_lock_network`（networks 行 FOR UPDATE）；来源历史由 F010 `ip_addresses.ip_pool_id` FK RESTRICT 承接 | PROPOSED→DATABASE（DR-108/DR-109/I-5）+DESIGN |
| DB-D106 | 索引仅 ix_ip_pools_network_id、ix_ip_pools_allocation_mode、ix_ip_pools_deleted_at；不建 pg_trgm/GIN、不建 start/end 单列 B-tree | DESIGN |
| DB-D107 | 迁移 0009_ip_pools，down_revision=0008_networks；不重复启用 btree_gist/pg_trgm（0008/0001 已启用）；单一 head、全表新建无回填、对称可逆 | DESIGN（DR-114） |
| DB-D108 | F009 注册 Network 引用检查器（未删 Pool 阻止 Network 删除/改 cidr/cluster → references:[{object_type:"ip_pool",...}]）；Pool 自身删除引用集为空（§21 例外/DR-116）；DB 仅 FK RESTRICT 保证物理删 | CONFIRMED（§21/DR-96/DR-116）+DESIGN |
| DB-D109 | F008 遗留订正（errata，非阻塞）：见 §7 | NOTE |
| DB-D110 | 100% 新建对象；downgrade 丢弃 ip_pools 数据不可逆，生产回滚用 F001 全库备份 | DESIGN |

## 2. ip_pools 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK pk_ip_pools |
| network_id | UUID | NOT NULL | — | FK fk_ip_pools_network_id_networks→networks(id) ON DELETE RESTRICT；ix_ip_pools_network_id |
| name | varchar(255) | NOT NULL | — | ck_ip_pools_name_not_blank/_trimmed/_no_control/_length |
| name_key | varchar(255) | NOT NULL | — | ck_ip_pools_name_key_matches（translate 口径） |
| start_address | inet | NOT NULL | — | ck_ip_pools_start_address_host：family=4 且 masklen=32 |
| end_address | inet | NOT NULL | — | ck_ip_pools_end_address_host：family=4 且 masklen=32；ck_ip_pools_address_order：start_address ≤ end_address |
| address_range | int8range | NOT NULL | 生成列（STORED） | 生成列 `int8range(...,'[]')`；排他约束载体；ORM 只读 |
| allocation_mode | varchar(16) | NOT NULL | 'MANUAL' | ck_ip_pools_allocation_mode：IN ('MANUAL','AUTO','RESERVED') |
| description | text | NULL | — | — |
| version | integer | NOT NULL | 1 | ck_ip_pools_version：≥1 |
| created_at/updated_at | timestamptz | NOT NULL | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | NULL | — | 软删 |

CHECK 形态（表达式与命名，`ck_` 由 naming convention 展开为 `ck_ip_pools_<name>`）：

| 约束名 | 表达式 |
| --- | --- |
| ck_ip_pools_name_not_blank | `btrim(name) <> ''` |
| ck_ip_pools_name_trimmed | `name = btrim(name)` |
| ck_ip_pools_name_no_control | `name !~ '[[:cntrl:]]'`（ASCII backstop；内部普通空格允许） |
| ck_ip_pools_name_length | `char_length(name) BETWEEN 1 AND 255` |
| ck_ip_pools_name_key_matches | `name_key = translate(btrim(name), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')` |
| ck_ip_pools_start_address_host | `family(start_address) = 4 AND masklen(start_address) = 32` |
| ck_ip_pools_end_address_host | `family(end_address) = 4 AND masklen(end_address) = 32` |
| ck_ip_pools_address_order | `start_address <= end_address` |
| ck_ip_pools_allocation_mode | `allocation_mode IN ('MANUAL','AUTO','RESERVED')` |
| ck_ip_pools_version | `version >= 1` |

生成列（DDL 形态，供迁移使用）：

```sql
address_range int8range
  GENERATED ALWAYS AS (
    int8range(
      set_masklen(start_address, 32) - '0.0.0.0'::inet,
      set_masklen(end_address, 32)   - '0.0.0.0'::inet,
      '[]'
    )
  ) STORED
```

约束/索引：

- `uq_ip_pools_network_id_name_key` UNIQUE(network_id, name_key) WHERE deleted_at IS NULL（部分唯一）。
- `excl_ip_pools_network_id_address_range` EXCLUDE USING gist (network_id WITH =, address_range WITH &&) WHERE (deleted_at IS NULL)。
- `ix_ip_pools_network_id`、`ix_ip_pools_allocation_mode`、`ix_ip_pools_deleted_at`。
- 触发器 `trg_ip_pools_cidr_contains`（BEFORE INSERT OR UPDATE FOR EACH ROW）+ 函数 `fn_ip_pools_cidr_contains()`。
- 不建 pg_trgm/GIN，不建 start/end 单列 B-tree。

不落字段（§12/DR-117/I-6）：metadata、status、auto_allocate、IP 列表、容量数值（归 F010/F013）。

## 3. 交核裁定

### 3.1 I-1 范围不重叠排他约束（DB-D98/DB-D99/DB-D100）

**表示法裁定：采用生成存储列 `address_range int8range`，而非在排他约束里写表达式索引。**
- 两者都要求表达式 immutable；生成列在 DDL 时即校验 immutable，且可被直接查询/断言（V-DB 更易验证），并避免 `EXCLUDE` 表达式元素语法差异，选生成列。
- 闭区间语义：`int8range(lower, upper, '[]')` 两端含；`&&` 命中共端点与完全相同。`start=end` 为 `[x,x]`，单地址池仍参与重叠判定（A7）。
- `start_address/end_address` 为 `inet`，直接对 `inet` 做 `&&`/重叠无区间语义（`&&` 对 inet 表示「重叠网段」，非地址区间），故必须转整数区间。

**`inet - inet` 不可变性核对（I-1 关键）**：整数映射用 `set_masklen(x,32) - '0.0.0.0'::inet`。
- `inet - inet` 即函数 `inetmi(inet,inet) → bigint`，PG16 标为 `IMMUTABLE`；`set_masklen(inet,integer)` 亦为 `IMMUTABLE`；`int8range` 构造器、比较/`&&`、`host/network/broadcast/family/masklen` 均 immutable。
- 佐证：F008 `ck_networks_gateway` 已在真实 PG 上以 `network()/broadcast()/host()/family()/masklen()` 作为 CHECK 表达式通过（V-DB-73），说明网络函数族为 immutable，`inetmi` 同族；CHECK 与生成列对 immutable 的要求一致。
- 备选/兜底（若真实 PG 核对 `pg_proc.provolatile` 非 `'i'`，迁移 `CREATE TABLE` 会以「generation expression is not immutable」显式失败，须改）：将整数映射包成显式 `IMMUTABLE` 的 SQL 函数 `fn_ip_pool_addr_int(inet) RETURNS bigint`，生成列引用该函数；语义等价、DDL 可执行。此为设计 II 备选，非默认。
- V-DB-82/87 强制核对 `provolatile='i'` 与生成列可用性。

**排他约束**：

```sql
ALTER TABLE ip_pools
  ADD CONSTRAINT excl_ip_pools_network_id_address_range
  EXCLUDE USING gist (network_id WITH =, address_range WITH &&)
  WHERE (deleted_at IS NULL);
```

- `network_id WITH =` 需 **btree_gist**（uuid 等值只读 `gist_uuid_ops`）；已由 `0008_networks` 首次 `IF NOT EXISTS` 启用，F009 **不重复启用**。
- `address_range WITH &&` 用 PG core `int8range` GiST `range_ops`（内建），不依赖 btree_gist。
- 软删谓词仅 `deleted_at IS NULL`：软删池释放范围；INACTIVE Network 的池照常参与（不由状态过滤），与 F008 CIDR 排他一致。
- 恢复重检：RESTORE 置 `deleted_at = NULL` 重新进入索引，与存活池重叠即被约束拒绝 → 应用映射 409 `range_overlap`（A15/A16）。
- 并发：创建/改起止/恢复由排他约束原子兜底，无需「先查后写」即可防重复；应用仍先查以返回可读 `conflicts` 明细。

### 3.2 I-5 占用冲突与来源历史（数据库侧，DB-D105）

- **占用冲突无 DB 约束**：F009 交付时不存在 IPAddress 行（F010）。RESERVED 新建/扩大、AUTO/MANUAL→RESERVED、已占用地址设 gateway 的「范围内是否存在未删 IP」无法用 CHECK/排他约束跨表表达。DB 侧**不新增**任何约束/触发器；由应用占用提供者 `IpOccupancyProvider`（F009 注册 `NullIpOccupancyProvider` 返回空集，F010 注册真实 `IpAddressOccupancyProvider`）检查并返回 409 `address_in_use{conflict_count,conflicts}`。
- **Network 行锁协议承接**：RESERVED/范围/gateway 变更与 F010 分配共用 `_lock_network`（`SELECT ... FROM networks WHERE id=:id FOR UPDATE`）。DB 只提供 networks 行（F008），锁为事务级协议，非 DB 约束；F009 建/改池事务内先取该锁（并触发 §3.3 触发器的 `FOR KEY SHARE`），F010 必须复用。
- **来源引用历史保留**：F010 `ip_addresses.ip_pool_id`（可空）置为 FK → `ip_pools(id)` **ON DELETE RESTRICT**，物理删除受引用即被拒；Pool 生命周期为**软删**（`deleted_at`），行永不物理删除，故 FK 在池软删后仍有效，来源历史自然保留（§12/§21 例外）。F009 **不为 Pool 删除注册 IP 引用检查器**（删除池不阻止、不回收、不级联），Pool 删除引用集为空。F010 建表时自行加该 FK 与 `ix_ip_addresses_ip_pool_id`（F010 DATABASE 责任）。

### 3.3 DR-104 起止属 Network CIDR 的 DB 保证（DB-D104 裁定：加触发器 backstop）

结论：**同时采用应用主校验 + DB 触发器 backstop**。
- FK 只证明 Network 行存在，不证明 `start/end` 落在 `networks.cidr` 内；§27 要求「IP 属于 CIDR、Network/Pool 不重叠」由 DB 与业务共同保证；F007/F008 已有跨行不变式用触发器的先例（`trg_interfaces_parent_valid`、`trg_resources_immutable_fields`）。
- 触发器在写入时点保证，覆盖 RESTORE（`deleted_at` 置 null 触发 UPDATE）；应用先校验返回 422。
- 触发器只对 networks 行取 `FOR KEY SHARE`（不改变 networks 表结构），与 F008 `_lock_network`（FOR UPDATE）串行化 Network 改 cidr 的并发窗口。

```sql
CREATE OR REPLACE FUNCTION fn_ip_pools_cidr_contains()
RETURNS trigger AS $$
DECLARE
    net_cidr inet;
BEGIN
    SELECT n.cidr::inet INTO net_cidr
      FROM networks n
     WHERE n.id = NEW.network_id
     FOR KEY SHARE;
    IF NOT FOUND THEN
        -- Network 行缺失：交给 FK 报错，保持与 FK 语义一致的错误来源。
        RETURN NEW;
    END IF;
    IF NOT (NEW.start_address <<= net_cidr)
       OR NOT (NEW.end_address <<= net_cidr) THEN
        RAISE EXCEPTION 'ip_pools start_address/end_address must belong to the network CIDR'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ip_pools_cidr_contains
BEFORE INSERT OR UPDATE ON ip_pools
FOR EACH ROW EXECUTE FUNCTION fn_ip_pools_cidr_contains();
```

说明：
- 用 `<<=`（contained within or equals），使 `/32` Network 内 `start=end=该地址` 通过；用 `<<` 会把「等于」判为不包含。`<<=`/`<<` 均要求 family 相同，IPv4 由 CHECK 排除 IPv6。
- 触发器对 `description`/`deleted_at` 的普通 UPDATE 也生效：RESTORE 越界时被拒（正确的恢复重检）；软删一个越界幽灵池亦被拒（越界池不应存在，属可接受副作用）。
- 不建 networks 侧触发器（不阻塞 Network 改 cidr/cluster）；该保护仍由应用引用检查器承担（见 §3.6 / DB-D108），与 F008 DB-D90/DB-D93 一致。

`CHECK start_address <= end_address`：两值 masklen 均被约束为 32，inet 比较退化为地址数值比较，语义与业务一致。单地址池（start=end）通过（A6）。

### 3.4 name / name_key 归一化键与部分唯一（DB-D96/DB-D97）

- name 口径（D01 §5/§5.7 同形）：trim 首尾 → 非空 → 禁控制字符（应用 Unicode Cc/Cf；DB `[[:cntrl:]]` ASCII backstop，允许内部普通空格、不合并）→ 长度 1–255（Unicode code point）→ 保留展示大小写。
- `name_key = ASCII_lower(btrim(name))`：仅 ASCII `A-Z`→`a-z`，非 ASCII 原样，locale 无关；应用逐码位、DB `translate`，**禁 `lower()`/`str.lower()`**；`ck_ip_pools_name_key_matches` 锁定口径。
- 唯一：`uq_ip_pools_network_id_name_key` UNIQUE(network_id, name_key) WHERE deleted_at IS NULL。同 Network 未删唯一（大小写不敏感）、跨 Network 允许、软删释放、恢复重检冲突不覆盖新对象（A2/A3/A21）。

### 3.5 allocation_mode / description / network 不可改

- `allocation_mode` varchar(16) NOT NULL DEFAULT 'MANUAL' + CHECK 3 值；语义（AUTO 允许自动+手动 / MANUAL 仅手动 / RESERVED 禁分配）由应用消费，F009 只保存与暴露；枚举扩展走迁移（DB-D101）。
- `description` text NULL 无上限（DB-D102）。
- `network_id` NOT NULL、创建必填、**创建后不可改**（DR-107/I-2）：应用 PATCH 含 network/network_id → 422。DB **不建** network_id 不可变触发器（与本项目 F008 对 cidr/cluster 的处理一致，DR-107 为 CONTRACT 层约束）；FK 仅保证存在，物理删 Network 被 RESTRICT 拒。
- network 引用须存在、未软删（应用 422）；DB 无软删引用约束（软删 Network 不删 ip_pools 行）。

### 3.6 Network 引用检查器与 Pool 删除例外（DB-D108）

- F009 在应用注册 Network 引用检查器：存在未删除 ip_pools 时，Network 删除/改 cidr/改 cluster 被拒 → 409 `reference_exists` + `references:[{object_type:"ip_pool",object_id,label}]`。
- DB 侧：`fk_ip_pools_network_id_networks ON DELETE RESTRICT` 阻止 Network **物理删除**（含软删残留行仍计数）；Network 软删与改 cidr/cluster 的 DB 保护**不存在**，由应用检查器 + `_lock_network` 承担；Network 改 cidr 后若使软删池越界，RESTORE 由 §3.3 触发器兜底拒绝。
- Pool 自身删除（软删）**引用集为空**：不检查 IP 分配来源、不级联、不回收（§12/§21 例外，DR-108）。

### 3.7 并发与生命周期边界

| 场景 | DB 机制 | 应用机制 |
| --- | --- | --- |
| 创建/改起止/恢复重叠 | `excl_ip_pools_network_id_address_range` 原子兜底 | 先查 `conflicts` → 409 range_overlap |
| 同名创建/改名/恢复 | 部分唯一致 | 归一化键 → 409 unique_conflict{name} |
| 起/止越界 | `trg_ip_pools_cidr_contains`（FOR KEY SHARE） | 应用校验 → 422 |
| Network 改 cidr vs 建池 | 触发器 KEY SHARE 与 `_lock_network` FOR UPDATE 串行 | `_lock_network` 统一锁域 |
| RESERVED/网关 vs 并发分配 | 无 DB 约束 | `IpOccupancyProvider` + `_lock_network`（F010 复用） |
| 乐观锁 | version CHECK + 条件 UPDATE | rowcount=0 → 409 VERSION_CONFLICT |
| 软删/恢复 | 排他/部分唯一致随 `deleted_at` 进退 | 恢复重检 name/network/overlap/(RESERVED 占用) |

## 4. 迁移 0009_ip_pools

- `revision = "0009_ip_pools"`、`down_revision = "0008_networks"`；单一 head。
- **不重复启用扩展**：btree_gist 由 0008、pg_trgm 由 0001 启用；0009 不含 `CREATE EXTENSION`。

upgrade 顺序：
1. `create_table("ip_pools", ...)`：全部列（含 `sa.Computed(_ADDRESS_RANGE, persisted=True)` 生成列）+ PK + FK + 全部 CHECK（`op.f()` 显式名）。
2. 部分唯一索引 `uq_ip_pools_network_id_name_key`（`unique=True, postgresql_where=sa.text("deleted_at IS NULL")`）。
3. `ix_ip_pools_network_id`、`ix_ip_pools_allocation_mode`、`ix_ip_pools_deleted_at`。
4. `op.execute` 添加排他约束 `excl_ip_pools_network_id_address_range`。
5. `op.execute` 建 `fn_ip_pools_cidr_contains()` 与 `CREATE TRIGGER trg_ip_pools_cidr_contains`。
无回填（全表新建）。

downgrade（对称逆序）：
1. `DROP TRIGGER IF EXISTS trg_ip_pools_cidr_contains ON ip_pools`。
2. `DROP FUNCTION IF EXISTS fn_ip_pools_cidr_contains()`。
3. `ALTER TABLE ip_pools DROP CONSTRAINT IF EXISTS excl_ip_pools_network_id_address_range`。
4. `drop_index` 三普通索引 + 部分唯一索引。
5. `drop_table("ip_pools")`。
**不 DROP btree_gist / pg_trgm**（F001 DB-D4）。

迁移骨架（关键片段，供 Backend 落地）：

```python
_ADDRESS_RANGE = (
    "int8range("
    "set_masklen(start_address, 32) - '0.0.0.0'::inet, "
    "set_masklen(end_address, 32) - '0.0.0.0'::inet, "
    "'[]')"
)
# ...
sa.Column("address_range", INT8RANGE(),
          sa.Computed(_ADDRESS_RANGE, persisted=True), nullable=False),
# ...
op.execute(
    "ALTER TABLE ip_pools ADD CONSTRAINT excl_ip_pools_network_id_address_range "
    "EXCLUDE USING gist (network_id WITH =, address_range WITH &&) "
    "WHERE (deleted_at IS NULL)"
)
```

校验计划：真库 `up → down → up`；`alembic heads` 唯一 = `0009_ip_pools`；对象齐全（列/CHECK/部分唯一/排他/生成列/触发器/FK/索引）；`pg_extension` 在 0009 前后无新增（btree_gist 仍由 0008 引入）。

## 5. 数据完整性对应表（Database 视角，精简）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证（计划） |
| --- | --- | --- | --- | --- | --- |
| §4.1/§27/DR-103 name 同 Network 未删唯一 | POST/PATCH/restore | 部分唯一 (network_id,name_key) WHERE deleted_at IS NULL；name_key CHECK | trim；ASCII 折叠（逐码位）；409 unique_conflict{field:"name"} | 索引仲裁；软删释放；恢复冲突拒 | V-DB-83/84/85 |
| §4.1/T40 name 规范 | POST/PATCH | ck_name_*（ASCII backstop）+ 长度 1–255 | trim→非空→禁 Cc/Cf→1–255；内部普通空格保留 | Cc/Cf 应用责任 | V-DB-83 |
| §12/§27/DR-106 池范围同 Network 未删不重叠（闭区间） | POST/PATCH/restore | excl_ip_pools_network_id_address_range（gist，int8range '[]'）WHERE deleted_at IS NULL | 先查冲突→409 range_overlap+conflicts | 约束原子兜底；INACTIVE 参与；软删排除；恢复重检 | V-DB-86/87/88 |
| §12/§14 起止属 Network CIDR | POST/PATCH/restore | trg_ip_pools_cidr_contains（BEFORE INSERT/UPDATE，FOR KEY SHARE）；FK 仅保证 Network 存在 | 应用校验→422 field start/end | 触发器与 `_lock_network` 串行 Network 改 cidr | V-DB-89 |
| §12 起≤止；IPv4 主机 | POST/PATCH | ck_address_order；ck_*_host（family=4 且 masklen=32） | 逆序/非 IPv4/带掩码→422 | — | V-DB-90 |
| §12.1/T33 占用冲突（RESERVED/网关） | POST/PATCH（含 Network gateway）/restore | 无（IP 数据在 F010）；F009 不建约束 | IpOccupancyProvider（F009 空集）→409 address_in_use+数量+明细 | `_lock_network` 串行化；F010 真实占用 | F009 桩 + F010 端到端 |
| §12/§21/DR-108 池变更不回收、来源历史 | DELETE/restore | deleted_at 软删；F010 ip_addresses.ip_pool_id FK RESTRICT（物理）；Pool 删除不检查 IP 引用 | 不级联、不回收；来源历史保留 | 软删保行；FK 仍有效 | F010 集成 / V-DB-91 |
| §21/§27 软删/恢复/引用例外 | DELETE/restore | deleted_at；排他/部分唯一致；FK RESTRICT | 恢复重检 name/network/overlap/(RESERVED 占用)；Pool 删除引用集为空 | 不级联；不回收 | V-DB-85/88 |
| §4.1/§21 network 归属不可改 | POST/PATCH | FK NOT NULL RESTRICT（物理）；无不可变触发器（应用 422） | PATCH network→422 | — | V-DB-92 |
| §11/§27 有未删 Pool 禁改/禁删 Network | Network PATCH/DELETE | 无（应用注册表；FK RESTRICT 仅物理删） | F009 注册引用检查器→409 reference_exists；`_lock_network` | FOR UPDATE 串行 | F009/F008 集成 |
| §23 乐观锁 | PATCH/DELETE/restore | version CHECK + 条件 UPDATE | rowcount=0→409 | 真并发 | V-DB-93 |
| §26/§27 真实 PG | 迁移/约束 | 0009 up/down/up、单一 head、无回填、扩展不重复启用 | — | — | V-DB-82/94 |

## 6. Backend 可依赖保证与测试项

**保证**：id 唯一（PK）；network_id 非空指向存在 Network（FK），物理删有 Pool 的 Network 被 RESTRICT 拒；同 Network 未删 name 大小写不敏感唯一（name_key 部分唯一），跨 Network 允许、软删释放、恢复冲突拒；name 已 trim 非空 1–255、无 ASCII 控制字符；start/end 恒 IPv4 主机地址（family=4、masklen=32）且 start ≤ end；start/end 恒落在所属 Network 的 CIDR 内（触发器）；同 Network 未删池闭区间两两不重叠（含软删释放、恢复重检）；allocation_mode 恒 3 值默认 MANUAL；description 可空无上限；version ≥1 默认 1；`address_range` 为生成列（只读、闭区间、随 start/end 自动重算）；索引 ix_ip_pools_network_id/_allocation_mode/_deleted_at；0009 有真实 downgrade、单一 head、无回填、扩展不重复启用。

**不保证**：占用冲突（RESERVED vs 未删 IP、已占用 gateway）——F010 数据 + 应用 provider；Network 软删与改 cidr/cluster 的引用保护——应用注册表 + `_lock_network`；Network cidr 变更与建池并发串行化的 DB 独立保证（依赖锁协议 + 触发器 KEY SHARE）；name 的 Unicode Cc/Cf（ASCII backstop）；network 不可变（应用 422，无 DB 触发器）；F010 ip_addresses.ip_pool_id FK/index（F010 责任）。

**计划测试项（真实 PG，V-DB-82–V-DB-94，无 PASS）**：
- V-DB-82 迁移 up/down/up 一致、down_revision=0008_networks、单一 head、对象齐全、无回填、btree_gist 未重复启用断言。
- V-DB-83 name 边界（NULL/空/纯空白/首尾/ASCII 控制/256 拒、1–255 接受、内部普通空格与中文保留不合并）。
- V-DB-84 name_key CHECK 与 translate 一致（多码位 Unicode `ß`/`ﬁ` 原样、`Web`/`WEB` 同键）。
- V-DB-85 部分唯一（同 Network 大小写重名拒/跨 Network 允许/软删后重建/存活同名拒/恢复冲突/并发仅一成功）。
- V-DB-86 排他约束（重叠/完全相同/共享端点拒；跨 Network 允许；INACTIVE Network 的池参与；软删后插入允许）。
- V-DB-87 生成列 `address_range`（单地址池 `[x,x]`；闭区间；UPDATE start/end 后重算；`set_masklen` 归一化；`provolatile='i'` 断言）。
- V-DB-88 恢复重检（重叠时置 `deleted_at=null` 被排他约束拒）。
- V-DB-89 CIDR 包含触发器（越界 INSERT/UPDATE 拒；/32 池相等通过；start=end 通过；Network 缺失交 FK；Network 改 cidr 并发串行）。
- V-DB-90 start>end 逆序拒、start=end 允许；IPv6/带掩码值拒（family/masklen CHECK）。
- V-DB-91 FK RESTRICT（物理删有 Pool 的 Network 拒；软删 Pool 行仍在）；F010 ip_pool_id FK 端到端（F010）。
- V-DB-92 allocation_mode 默认/非法/显式 null；NOT NULL；network 变更无 DB 触发器（应用 422）断言。
- V-DB-93 version 默认 1、<1 拒；乐观锁（双会话仅一成功）。
- V-DB-94 对象存在/不存在断言（生成列、排他、部分唯一、触发器、3 索引；无 pg_trgm GIN；btree_gist 属 0008）。

## 7. F008 遗留订正（errata，非阻塞）

以下为 F008 文档遗留（F008-REV-01/02），不影响 F009 行为；F009 文档与迁移均按**正确口径**表述。是否回改 F008 正文/迁移注释由协调器决定。

- **F008-REV-01（文档）**：`docs/database/f008-network.md` §3.3 gateway CHECK 示例 SQL 应把 `network(cidr)::inet` / `broadcast(cidr)` 套 `host()`：
  ```sql
  gateway <> host(network(cidr))::inet AND gateway <> host(broadcast(cidr))::inet
  ```
  （`network()`/`broadcast()` 返回带掩码的 `inet`，与 `gateway`（主机 `/32`）直接比较恒真；`0008_networks.py` 已用正确写法。）
- **F008-REV-01（措辞）**：DB-D83「host 位由 cidr 类型归一化为网络地址」不成立——PG `cidr` **拒绝** host 位（`'10.0.0.5/24'::cidr` 报错），归一化实为应用 `ipaddress.ip_network(strict=False)`（`app/services/normalization.py::normalize_cidr`）完成。`0008_networks.py` 模块注释同措辞应一并订正。
- **F008-REV-02（文档）**：DB-D88 未注明排他约束必须显式写 `cidr inet_ops WITH &&`——btree_gist 安装后 `cidr` 默认 GiST opclass 变为仅支持等值的 `gist_cidr_ops`，重叠 `&&` 必须显式 `inet_ops`。迁移代码注释已说明，设计正文缺注，建议补注。

## 8. 未验证项与风险

- I-1（已闭合）：`int8range` 生成列 + 排他约束闭环；`inet - inet` 不可变性以 V-DB-82/87 核对；btree_gist 由 0008 提供。
- I-4（LOW，交 CONTRACT/D01 v8 §5.8）：name 1–255、start/end host、allocation_mode 默认、description 无上限待 D01/Contract 固定；Database 按架构 DR-113 采纳，非阻塞。
- I-5（MEDIUM，交 Backend/Architect）：占用冲突 DB 无约束，F009 空集 provider，真实端到端留 F010；若 F010 未复用 `_lock_network` 并注册 provider，T33/T35 无法在 F009 闭合。记录 ISSUES，非本 Gate 阻塞。
- I-2（LOW）：network 不可改为应用层 422，无 DB 触发器；DB 只保证存在性。
- 恢复重检越界语义（NOTE，交 CONTRACT）：Network 改 cidr 致软删池越界后 RESTORE，DB 抛 `restrict_violation`，Contract 草案未固定对应 reason，建议明确。
- 触发器副作用（NOTE）：`trg_ip_pools_cidr_contains` 对任意 UPDATE 生效（含软删）；越界幽灵池的软删会被拒，属预期但需在测试覆盖说明。
- I-7（NOTE）：downgrade 丢弃 ip_pools 数据不可逆，生产回滚用 F001 全库备份。
- 只读签核，全部为计划验证无 PASS。

## 9. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-09 | 初次签核（DB-D95–DB-D110）；ip_pools 首次建表、`int8range` 生成列 + 排他约束（网络不重叠，闭区间）、名称部分唯一、CIDR 包含触发器、allocation_mode 默认与 CHECK、索引裁定、迁移 0009（不重复启用扩展）、I-1/I-5/DR-104 落地、F008 遗留订正。 |