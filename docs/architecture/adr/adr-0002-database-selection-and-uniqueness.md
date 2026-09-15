# ADR-0002: 数据库选型、大小写敏感唯一性与迁移策略

## Status

`ACCEPTED`（2026-09-15 用户批准）

**决策记录**：用户于 2026-09-15 批准 DEC-010（PostgreSQL），并裁定本 ADR 的两个原开放子项：

- **collation 策略 → 选项 1**：使用数据库默认 collation（PostgreSQL 下等值比较已大小写敏感），**不**使用 `COLLATE "C"`；以自动化测试固定该事实。
- **`ip_address.cluster_id` 一致性 → 受控写入路径 + 一致性测试**：不引入逐级复合外键，也不使用数据库触发器。

规模假设已由用户确认：**资源总量约 10⁵（10 万级），并发用户约 50**。

## Context

V1 有三条必须在**数据库层真实成立**、且不得被默认配置静默破坏的唯一性规则：

- `Cluster.name` 全局唯一，比较**大小写敏感**（R-CLUSTER-002，§22）；
- `(Cluster, hostname)` 唯一，比较**大小写敏感**（R-BM-002，§22）；
- `(Cluster, ip_address)` 唯一，**跨 Cluster 可重复**（R-IP-001 ~ 003）。

叠加 R-DELETE-006「**已逻辑删除的资源不继续占用唯一性**」。

`requirements.md` §21 明确要求不能只依赖 UI 校验。数据与界面含中文。部署目标为单台内网虚拟机（R-DEPLOY-001）。

## Decision

1. 采用 **PostgreSQL** 作为关系数据库，字符集 UTF-8。
2. 所有标识列的**等值比较必须大小写敏感**。采用 **PostgreSQL 默认 collation**（PG 的 `text` 等值比较在标准 locale 下已大小写敏感），**不**强制 `COLLATE "C"`。以自动化测试固定该事实，防止未来 locale 变更或数据库升级静默改变语义（见下方「已裁定的子项 1」）。
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

4. `ip_address` 持久化 `cluster_id`（由后端从 IPAddress → NetworkInterface → BareMetal → Cluster 推导写入），并采用**受控写入路径 + 一致性测试**保证其与链路上游一致，使「同 Cluster IP 唯一」可被数据库直接约束（见下方「已裁定的子项 2」）。
5. `bare_metal.status` 为 `NOT NULL DEFAULT 'IDLE'` + CHECK 约束，取值限定 `IDLE` / `ALLOC` / `DOWN` / `UNKNOWN`。**不建立通用 status 表**。
6. 迁移采用版本化、向前、随代码提交的方式（Alembic）；F012 建立基线迁移；破坏性变更须单独说明回滚策略并经用户确认（`AGENTS.md` §6）。

## 已裁定的子项

### 1. collation 策略 → 选项 1（使用默认 collation）

`requirements.md` 只规定「比较区分大小写」，没有规定使用哪个 collation。

- **PostgreSQL 的 `text` 等值比较在标准 locale 下本身已是大小写敏感**（`'a' = 'A'` 为 false），这与 MySQL 的 `utf8mb4_0900_ai_ci` 默认**不同**。
- 因此「显式声明 collation」的价值是**显式化、与 locale 无关、跨环境可复现**，而不是修正 PostgreSQL 的错误缺省行为。
- 副作用：`COLLATE "C"` 会让排序按 UTF-8 码点而非拼音，中文列表排序语义会变化（等值比较仍正确）。

**裁定：使用数据库默认 collation，不声明 `COLLATE "C"`。**

必须配套的措施（否则与「依赖默认配置」无异）：

- 以自动化测试**固定**该事实：`cluster-a` 与 `Cluster-A` 必须可共存，`cn001` 与 `CN001` 在同一 Cluster 内必须可共存；
- 测试必须**绕过应用层直接对数据库插入**，证明约束来自数据库而非应用逻辑；
- 部署文档须记录数据库 locale 要求，避免在不同 locale 的环境中静默改变比较语义；
- 中文列表排序不要求拼音序，按默认 collation 行为处理。

### 2. `ip_address.cluster_id` 一致性 → 受控写入路径 + 一致性测试

**裁定：不引入逐级复合外键，也不使用数据库触发器。**

- `ip_address.cluster_id` **仅由领域服务在受控写入路径中写入**，写入时从 IPAddress → NetworkInterface → BareMetal → Cluster 推导，业务代码不得在其他路径直接赋值。
- 必须配套**一致性测试**：构造 `cluster_id` 与链路推导结果不一致的数据，验证其被拒绝或不被产生；并验证跨 Cluster 的 NIC/IP 变更不会留下漂移。
- 选择理由：复合外键需要把 `cluster_id` 逐级冗余传递到 `network_interface`，会扩大反规范化范围；触发器会把业务规则隐藏进 Schema，违反 `AGENTS.md` §2.4。受控写入路径把规则留在代码中，一致性测试把规则固化为可验证证据。
- **风险**：该方案依赖应用层纪律。任何绕过领域服务的写入（脚本、手工 SQL、未来的新代码路径）都可能造成漂移。因此一致性测试属于必需项，不是可选优化。

## Consequences

- 三条唯一性规则与大小写敏感语义由数据库强制，满足 §21；其正确性由**绕过应用层直接操作数据库的测试**证明（见「已裁定的子项 1」）。
- R-DELETE-006 由 partial predicate 自然满足，无需 sentinel 列或应用层补偿。
- 未来若要改为大小写不敏感，必须改产品规则（§22）并重建索引，不能靠改配置实现。
- 引入了反规范化列 `ip_address.cluster_id`，其一致性依赖**受控写入路径 + 一致性测试**，需在 Database / Backend 阶段落实。
- 规模已确认在阈值内（10⁵ 量级、50 并发），单机 PostgreSQL 足够；无需分区或异步导入。

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