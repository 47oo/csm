# ADR-0004: 逻辑删除的持久化与唯一性释放

## Status

`PROPOSED`（等待用户批准；批准前不得视为已确定）

## Context

V1 要求资源保留历史（`requirements.md` §17、§25 History Preservation）：

- 不物理删除（R-DELETE-001）；
- 已删不出现在常规查询（R-DELETE-002）；
- 不提供 undelete（R-DELETE-003）；
- 父资源有活跃子资源时不可删（R-DELETE-004）；
- 不自动级联删除（R-DELETE-005）；
- **已删记录不继续占用正常业务唯一性**（R-DELETE-006）。

同时唯一性边界是分层的（全局 Cluster 名 / Cluster 内 hostname / Cluster 内 IP），且比较大小写敏感（§22）。

「已删不占唯一性」与「数据库唯一索引」天然冲突，必须显式选择一种持久化机制。

## Decision

1. 所有资源表使用 `deleted_at TIMESTAMPTZ NULL` 作为**唯一**删除标记。
2. 所有唯一性约束实现为 **partial unique index**，predicate 为 `deleted_at IS NULL`。
3. 所有常规查询显式附加 `deleted_at IS NULL`；由数据访问层**统一提供**，禁止各模块各写一套。
4. **不提供 undelete**；`deleted_at` 一旦写入不再回退（R-DELETE-003）。
5. 父资源删除前必须在**同一事务内**检查活跃子资源并对父行**加锁**，避免并发下「子资源刚创建、父资源同时被删」产生孤立记录（R-DELETE-004 的并发正确性）。
6. 删除**不级联**；子资源须显式删除（R-DELETE-005）。
7. 唯一性冲突在应用层先行检查以返回 409 与友好提示，但**数据库 partial unique index 是最终权威**（§21），应用层检查仅为体验优化。

## Consequences

- 「大小写敏感」与「已删不占唯一性」由两个正交机制分别保证，互不干扰。
- 删除时间被保留，为历史查询留出空间。
- 唯一索引的 predicate 必须与查询过滤条件保持一致，否则会出现「查得到却写不进」的错位。
- 依赖数据库支持 partial index（已由 ADR-0002 的选型保证）。
- 并发正确性依赖显式加锁，是必须在实现与测试中体现的具体要求。

## Alternatives Considered

- **`is_deleted` 布尔列**：语义直白，但丢失删除时间，且仍需 partial index 才能释放唯一性，在「历史保留」诉求下信息量不足。
- **sentinel 列**（唯一键含删除令牌，如 `deleted_token`）：在无 partial index 的数据库上可行；但把删除语义编码进唯一键，规则不再显式，违反 `AGENTS.md` §2.4，是本项目最想避免的「规则隐藏在实现细节里」。
- **物理删除 + 历史表**：破坏「不物理删除」与「历史保留」的已确认语义。
- **应用层唯一性检查**：违反 §21，排除。

## Affected Features

F014 直接；F001、F002、F004、F005、F006、F007、F008、F011 受约束。

Milestone: **M1**（DEC-012）。

## Reversibility

**高代价**。删除语义一旦写入数据，从 `deleted_at` 改为其他机制需要全表语义迁移，且历史事实（§25 History Preservation）可能被破坏。