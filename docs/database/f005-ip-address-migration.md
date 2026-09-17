# F005 Database Design — `ip_addresses`

> Status: `READY FOR DATABASE IMPLEMENTATION`
> Feature: F005（E02，P1）
> Author Role: database design（依据已批准 `docs/architecture/f005-ip-address-handoff.md` 的 Database Work / 决策 1 规格，未新增任何决策）
> 权威来源：`docs/architecture/f005-ip-address-handoff.md`、`docs/api/f005-ip-address.md`、`docs/product/handoffs/f005-ip-address.md`、ADR-0002 / ADR-0004、`docs/database/csm-v1-schema-design.md`

---

## 1. 范围

覆盖 **新增一张表** `ip_addresses` 与**一次增量 migration** `0006_f005_ip_addresses`。

- **不改** `0001`–`0005`。
- **无**数据迁移（表为首次创建，系统内不存在 IPAddress 数据）。
- 无新 extension / database / role；无触发器；无 `COLLATE`；无 CASCADE；无复合外键。
- **本表是本次唯一新增的表**；不改变任何既有表的列 / 约束 / 索引。

---

## 2. Migration

| 项 | 值 |
|---|---|
| revision | `0006_f005_ip_addresses` |
| down_revision | `0005_f004_network_interfaces`（当前 head；维持单一线性 head） |
| upgrade | `CREATE TABLE ip_addresses`（7 列 + PK + 2 FK `RESTRICT`/`RESTRICT`，**0 个 CHECK**）→ `CREATE UNIQUE INDEX ux_ip_addresses_cluster_ip_active` → `CREATE INDEX ix_ip_addresses_cluster_id` → `CREATE INDEX ix_ip_addresses_network_interface_id` |
| downgrade（严格逆序） | `DROP INDEX ix_ip_addresses_network_interface_id` → `DROP INDEX ix_ip_addresses_cluster_id` → `DROP INDEX ux_ip_addresses_cluster_ip_active` → `DROP TABLE ip_addresses` |

`downgrade` 为破坏性操作（丢失全部 IP 登记历史），生产环境禁止。

---

## 3. DDL

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

列集合**恰为 7 列**。**CHECK 约束集合为空**。

---

## 4. 约束与设计依据

| 约束 / 索引 | 定义 | 依据 |
|---|---|---|
| `pk_ip_addresses` | `PRIMARY KEY (id)` | ADR-0003：`id` 为规范路径与写操作标识 |
| `fk_ip_addresses_network_interface` | `FOREIGN KEY (network_interface_id) REFERENCES network_interfaces (id) ON DELETE RESTRICT ON UPDATE RESTRICT` | IP→NIC 必选（用户 2026-09-15 裁定）；R-DELETE-005 不级联；ADR-0004 |
| `fk_ip_addresses_cluster` | `FOREIGN KEY (cluster_id) REFERENCES clusters (id) ON DELETE RESTRICT ON UPDATE RESTRICT` | 反规范化列存在性；**不**保证与推导链一致（ADR-0002 已知取舍，见 §5） |
| `ux_ip_addresses_cluster_ip_active` | `UNIQUE (cluster_id, ip_address) WHERE deleted_at IS NULL` | R-IP-001 同 Cluster 内唯一；R-DELETE-006 软删释放；§21 数据库为最终权威 |
| `ix_ip_addresses_cluster_id` | `INDEX (cluster_id)` | FK 引用检查 + 含已删行的 Cluster 维度查询（partial unique 不覆盖已删行，不能替代） |
| `ix_ip_addresses_network_interface_id` | `INDEX (network_interface_id)` | FK 引用检查 + 按 NIC 读取（`?network_interface_id=`，F010 复用） |

**明确不添加**（未确认或已排除）：

- `status` 列 / 状态枚举 → Q-002=B。
- VRF / 租户 / 网络命名空间列（`vrf` / `vrf_id` / `rd` / `tenant` / `namespace` / `netns` / `vni`）→ R-IP-003 明确不考虑。
- IP 池 / 网段 / 子网 / 网关 / VLAN / DHCP / DNS / 自动发现 / 外部平台 id / 凭据列 → 无任何已确认需求。
- 载体多态列（`bare_metal_id` / `virtual_machine_id` / `container_id` / `carrier_type`）→ IP 必挂在 NIC 上，不存在多态父。
- `ip_address` 的长度 / 首尾空白 / 空串 / 字符 / 格式 / CIDR / 正则 CHECK → 未定义约束（NQ-1）；**也不得**声明列级 collation、不得建 `lower(ip_address)` 表达式索引（比较必须是字面精确、大小写敏感，§22）。
- 用途 / 备注 / 负责人 / 分配对象 / 回收状态列 → 未确认字段。
- `ON DELETE CASCADE` / 触发器 / 复合外键 / 一致性 CHECK / 生成列 → R-DELETE-005 / ADR-0002 明确排除。

**类型选择**：`ip_address` 使用 `TEXT` 而非 PostgreSQL `inet` / `cidr`。理由（承 `csm-v1-schema-design.md` 关键设计决策）：`inet` / `cidr` 会引入产品未确认的**表示归一化语义**（例如 `10.0.1.1` 与 `10.0.1.1/16` 的等价性、IPv6 十六进制大小写折叠），等于把「格式规则」这一未确认项偷偷变成已确认约束。V1 采用 `TEXT` 做**字面值精确比较**。

---

## 5. 一致性：数据库不保证的 invariant（必须如实记录）

`fk_ip_addresses_cluster` 只保证被引用的 Cluster **物理存在**；它 **不保证** `ip_addresses.cluster_id` 等于沿 `network_interface_id → network_interfaces.bare_metal_id → bare_metals.cluster_id` 推导出的 Cluster。这是 ADR-0002 的**已知取舍**：表达该约束需要复合外键逐级传递、触发器或生成列，三者均被 ADR-0002 / AGENTS.md §2.4 排除（不把业务规则藏进 Schema）。

**因此一致性由两层保证，缺一不可：**

1. **受控写入路径（应用层，唯一）**：`app/ip_addresses/derivation.py::derive_cluster_id()` 推导 → `app/ip_addresses/repository.py::IpAddressRepository.create` 写入。任何第二条写入路径的出现由**可失败静态 guard** 检出。
2. **漂移检测回归（数据层可执行）**：以下查询必须恒为 **0 行**：

```sql
SELECT ip.id, ip.cluster_id AS stored_cluster, bm.cluster_id AS derived_cluster
FROM ip_addresses ip
JOIN network_interfaces nic ON nic.id = ip.network_interface_id
JOIN bare_metals        bm  ON bm.id  = nic.bare_metal_id
WHERE ip.cluster_id <> bm.cluster_id;   -- 期望 0 行
```

**为什么检测不是可选项**：`ux_ip_addresses_cluster_ip_active` 按**存储的** `cluster_id` 判断唯一性。若 `cluster_id` 漂移（例如真实属于 Cluster A 的行存了 `cluster_id = B`），唯一索引看到的是 `(B, 10.0.0.10)`，于是**同一 Cluster A 内可以出现两条活跃的 `10.0.0.10` 而不被阻止** —— R-IP-001 被静默绕过。漂移查询是**唯一**能从数据库侧发现该情形的手段。

**数据库层不做的事**：本设计**不**新增漂移查询端点、不在生产代码中放未被调用的死代码；漂移查询以测试侧常量交付并作为持续回归。

**未来变更的触发条件**：若将来允许修改 `bare_metals.cluster_id`（F002）或 `network_interfaces.bare_metal_id`（F004），必须在**同一事务内**重推导受影响 IP 的 `cluster_id` 并对目标 Cluster 重校验唯一性；否则漂移查询将 > 0 行。本 Feature **不实现、不预留**该能力。

---

## 6. 并发协议（由 Backend 实现，DDL 提供基础）

1. **创建 IP**：在同一请求事务内，以 `network_interface_id` 定位父 NIC 行取 `FOR SHARE OF network_interfaces`，并在**同一语句**内读取 `bare_metals.cluster_id` 作为推导值；`WHERE` 同时要求父 NIC 与其宿主 BareMetal 均 `deleted_at IS NULL`。未命中 → `404`。
2. **不额外锁定 BareMetal / Cluster**：`network_interfaces.bare_metal_id` 与 `bare_metals.cluster_id` 在 V1 均不可变（F002 / F004 的 `PATCH` 均不含这两个字段），持有父 NIC 行共享锁已足以固定推导结果；「活跃 NIC ⇒ 活跃宿主」由宿主删除的活跃子检查（含活跃 NIC）保证。额外加锁不带来额外保证，只增加锁 footprint 与跨表锁序审计成本。
3. **删除父 NIC**：`DELETE /api/network-interfaces/{id}` 对自身行取 `FOR UPDATE`，再检查活跃子资源（`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`，F005 后含活跃 IPAddress）。
4. **不变式**：并发结束后
   - `SELECT count(*) FROM ip_addresses ip JOIN network_interfaces nic ON nic.id = ip.network_interface_id WHERE ip.deleted_at IS NULL AND nic.deleted_at IS NOT NULL` = **0**；
   - 漂移查询 = **0 行**。
5. **死锁**：本 Feature 只新增「NIC 行 `FOR SHARE` →（同语句内）读 BareMetal」，而 NIC 删除为「NIC 行 `FOR UPDATE` → 读 IP 行（无锁）」、宿主删除为「BareMetal 行 `FOR UPDATE` → 读 NIC 行（无锁）」；**新增路径不引入任何反向持锁**，故不新增死锁序。

---

## 7. 验证（Verification）

| # | 验证 | 方法 |
|---|---|---|
| V-1 | 列集合恰为 7 列，且不含 `status` / VRF / 池 / DHCP / DNS / 载体 / 备注类列 | `information_schema.columns` |
| V-2 | **CHECK 约束集合为空** | `pg_constraint`（`contype='c'`） |
| V-3 | `ip_address` 为 `TEXT` 且 `character_maximum_length IS NULL` | `information_schema.columns` |
| V-4 | PK 恰为 `pk_ip_addresses` | `pg_constraint` |
| V-5 | FK 恰为 `{fk_ip_addresses_network_interface, fk_ip_addresses_cluster}`，均 `confdeltype='r'`、`confupdtype='r'` | `pg_constraint` |
| V-6 | 全库无 `confdeltype='c'`（无 CASCADE） | `pg_constraint` |
| V-7 | 唯一索引集合恰为 `{ux_ip_addresses_cluster_ip_active}`，`indexdef` 含 `UNIQUE`、列序 `(cluster_id, ip_address)`、`WHERE (deleted_at IS NULL)`，且**不含 `COLLATE` / `lower(`** | `pg_indexes` |
| V-8 | `ix_ip_addresses_cluster_id` 与 `ix_ip_addresses_network_interface_id` 存在 | `pg_indexes` |
| V-9 | `ip_addresses` 所有列 `collation_name IS NULL` | `information_schema.columns` |
| V-10 | 无触发器 | `information_schema.triggers` |
| V-11 | 直连插入同 Cluster 内字面相同的**活跃**两行 → `23505`；跨 Cluster 相同字面 → 成功 | psycopg 异常 / 行为断言 |
| V-12 | 直连插入 `ip_address`（同 Cluster）为空串 / 含首尾空白 / `not-an-ip` / 超长 → **均成功**（无格式约束） | 行为断言 |
| V-13 | 直连把某行 `cluster_id` 改成与推导链不一致的值 → **成功**（数据库不保证该 invariant，ADR-0002 已知取舍），且**漂移查询能查出**（1 行） | 行为断言 + 漂移查询 |
| V-14 | 软删某行后，同 Cluster 可再次插入相同字面值的活跃行 | 行为断言 |
| V-15 | `alembic upgrade head` ×2 幂等；`downgrade base` → `upgrade head` 可重建 | alembic |
| V-16 | `alembic downgrade 0005_f004_network_interfaces` 后本表被删、既有表完好 | alembic + 结构断言 |
| V-17 | `alembic check` 无 schema 漂移 | alembic |
| V-18 | 既有表 `clusters` / `users` / `sessions` / `bare_metals` / `virtual_machines` / `network_interfaces` 结构与本 migration 之前一致 | 结构断言 |

---

## 8. 与既有表的关系

- `ip_addresses.network_interface_id → network_interfaces.id`：N:1，必选，`RESTRICT`。
- `ip_addresses.cluster_id → clusters.id`：N:1，必选，`RESTRICT`（反规范化，唯一性边界）。
- 不引用 `bare_metals`（Cluster 归属经 NIC→BareMetal 推导，不在本表建立到 BareMetal 的外键）。
- 新增表不改变任何既有表的列 / 约束 / 索引。
- 本表是 **V1 叶子资源**：无其它表以其为主键外键（`IP_ADDRESS_ACTIVE_CHILD_CHECKS` 显式空元组）。

---

## 9. 文档同步状态

- `docs/database/csm-v1-schema-design.md`：`ip_addresses` 段已补 migration 版本 `0006_f005_ip_addresses`；关键设计决策 #3 的「受控写入路径」归属已由 F014 **更正为 F005**（`app/ip_addresses/derivation.py::derive_cluster_id` + `IpAddressRepository.create`），并记录归属变更原因。
- `docs/database/f012-baseline-migration.md`：revision 序列加入 `0006_f005_ip_addresses`（建议，非阻塞）。

GIT: NONE
