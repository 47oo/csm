# ADR-0002: 数据库选型、大小写敏感唯一性与迁移策略

## Status

`PROPOSED`（等待用户批准；批准前不得视为已确定）

## Context

V1 有三条必须在**数据库层真实成立**、且不得被默认配置静默破坏的唯一性规则：

- `Cluster.name` 全局唯一，比较**大小写敏感**（R-CLUSTER-002，§22）；
- `(Cluster, hostname)` 唯一，比较**大小写敏感**（R-BM-002，§22）；
- `(Cluster, ip_address)` 唯一，**跨 Cluster 可重复**（R-IP-001 ~ 003）。

叠加 R-DELETE-006「**已逻辑删除的资源不继续占用唯一性**」。

`requirements.md` §21 明确要求不能只依赖 UI 校验。数据与界面含中文。部署目标为单台内网虚拟机（R-DEPLOY-001）。

## Decision

1. 采用 **PostgreSQL** 作为关系数据库，字符集 UTF-8。
2. 所有标识列显式声明大小写敏感的**确定性** collation，不依赖数据库实例或列的默认 collation。
3. 唯一性一律表达为 **partial unique index**：

   ```sql
   -- 示意，非最终实现
   CREATE UNIQUE INDEX ux_cluster_name_active
     ON cluster (name) WHERE deleted_at IS NULL;

   CREATE UNIQUE INDEX ux_bare_metal_hostname_active
     ON bare_metal (cluster_id, hostname) WHERE deleted_at IS NULL;

   CREATE UNIQUE INDEX ux_ip_address_active
     ON ip_address (cluster_id, ip_address) WHERE deleted_at IS NULL;
   ```

4. `ip_address` 持久化 `cluster_id`（由后端从 IPAddress → NetworkInterface → BareMetal → Cluster 推导写入），并提供一致性保障机制，使「同 Cluster IP 唯一」可被数据库直接约束。
5. `bare_metal.status` 为 `NOT NULL DEFAULT 'IDLE'` + CHECK 约束，取值限定 `IDLE` / `ALLOC` / `DOWN` / `UNKNOWN`。**不建立通用 status 表**。
6. 迁移采用版本化、向前、随代码提交的方式（Alembic）；F012 建立基线迁移；破坏性变更须单独说明回滚策略并经用户确认（`AGENTS.md` §6）。

## 待用户确认的子项（本 ADR 中的开放点）

**1. collation 策略**

`requirements.md` 只规定「比较区分大小写」，没有规定使用哪个 collation。补充事实：

- **PostgreSQL 的 `text` 等值比较在标准 locale 下本身已是大小写敏感**（`'a' = 'A'` 为 false），这与 MySQL 的 `utf8mb4_0900_ai_ci` 默认**不同**。
- 因此「显式声明 collation」的价值是**显式化、与 locale 无关、跨环境可复现**，而不是修正 PostgreSQL 的错误缺省行为。
- 副作用：若选用 `COLLATE "C"`，排序按 UTF-8 码点而非拼音，中文列表排序语义会变化（等值比较仍正确）。

需在以下之间选择：

- **选项 1**：使用数据库 / 实例默认 collation（PG 下已大小写敏感），并把该事实写入测试固定下来。
- **选项 2**：在标识列或唯一索引上显式声明 `COLLATE "C"`，换取与部署环境 locale 完全解耦的可复现性，接受码点排序。

**2. `ip_address.cluster_id` 的一致性保障机制**

需在以下之间选择（由 Database Agent 细化）：

- 复合外键（`(nic_id, cluster_id)` 引用 `network_interface(id, cluster_id)`，逐级传递）；
- 受控写入路径（仅由领域服务写入，配合一致性测试）；
- 数据库触发器（不推荐，规则会隐藏进 Schema）。

## Consequences

- 三条唯一性规则与大小写敏感语义由数据库强制，满足 §21。
- R-DELETE-006 由 partial predicate 自然满足，无需 sentinel 列或应用层补偿。
- 未来若要改为大小写不敏感，必须改产品规则（§22）并重建索引，不能靠改配置实现。
- 引入了反规范化列 `ip_address.cluster_id`，需要一致性测试防止漂移。
- 单机 PostgreSQL 在 M1 之前没有容量数据支撑，需用户确认规模量级（见架构文档 BQ-1）。

## Alternatives Considered

- **MySQL 8**：运维人员更熟悉，但默认 collation `utf8mb4_0900_ai_ci` **大小写不敏感**，必须显式改成 `utf8mb4_bin` 或 `_as_cs`，很容易在迁移或新建表时忘掉；且**不支持 partial unique index**，「已删不占唯一性」需要 sentinel 列或生成列技巧，复杂度显著上升。
- **SQLite**：零运维、`BINARY` collation 默认大小写敏感、支持 partial index；但并发写受限、备份 / 恢复与多人访问能力与 R-DEPLOY-001 的多用户内网平台定位不符。仅适合骨架期本地开发。
- **仅应用层唯一性检查**：违反 §21，明确排除。
- **通用 `resources` 表 / EAV / JSONB**：违反 §4 / §24，明确排除。
- **`lower(name)` 上的唯一索引**：等于把规则改成大小写不敏感，违反 §22。

## Affected Features

F012、F014 直接；F001、F002、F004、F005、F006、F007、F008、F011、F015 受影响。

Milestone: **M1**（入口条件 DEC-010）。

## Reversibility

**高代价**。数据库产品一旦落库，切换涉及数据迁移、collation 语义差与索引能力差。这是本批决策中回退代价最高的一项之一。