# F002 认证、初始账号与权限横切 — DATABASE 设计（D02 认证部分）

- **签核**：Database；设计版本 v1（2026-10-06）
- **上游依据**：requirements-v3.md revision 3（§4、§21–§23、§26–§27、§30–§31、§35.3 D01/D02）；docs/features/F002/architecture.md（READY FOR DESIGN，DR-07–DR-16）；docs/database/f001-baseline.md v1（DB-D1–DB-D12）
- **覆盖**：users / user_sessions 实体与约束、索引、迁移 0002、Backend 可依赖保证与测试项。不覆盖 F003 业务表/deleted_at/Audit 表/D01 全量字段字典、用户管理 UI（F015）、认证业务实现。

## 1. 范围与前提

F002 首次建用户表、无历史数据；仅本地账号（§23），不开放注册。稳定 ID 用 PG 核心 `gen_random_uuid()`，不启用 pgcrypto/uuid-ossp（f001-baseline §3）。会话为服务端不透明会话（DR-08），DB 存 SHA-256 哈希。时间 `timestamptz`/UTC。

## 2. 设计决策汇总

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D13 | `users.id`、`user_sessions.id` 用 PG 原生 UUID + server_default gen_random_uuid()；作为 D01 稳定 ID 形态首个落地，F003 须沿用 | DESIGN（D02；D01 协调项） |
| DB-D14 | username 唯一以单列小写规范化值 + UNIQUE + CHECK 归一化实现；不用 citext、不设独立归一化键列 | DESIGN |
| DB-D15 | role/status 用 varchar + CHECK，不用原生 ENUM | DESIGN |
| DB-D16 | user_sessions.user_id FK ON DELETE RESTRICT；显式建 user_id、expires_at 索引 | DESIGN |
| DB-D17 | 迁移 0002_users_sessions 追加，up/down 对称可逆，单一 head，真库 up/down/up | DESIGN（DB-D7） |
| DB-D18 | 会话过期不预建清理任务：读时惰性判定 + 登出删除 | DESIGN |
| DB-D19 | 时间列 timestamptz/UTC、now() 默认；updated_at 应用维护无触发器 | DESIGN |

稳定 ID 对齐义务：F002 先行采用 PG UUID；F003 起业务对象主键须沿用，写入 D01 共享约定；同时满足操作者 user_id 与 F003 Audit 对齐。

## 3. users 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK pk_users |
| username | varchar(64) | NOT NULL | — | UNIQUE uq_users_username；CHECK ck_users_username_format |
| password_hash | varchar(255) | NOT NULL | — | CHECK ck_users_password_hash_nonempty（argon2 PHC） |
| role | varchar(16) | NOT NULL | — | CHECK ck_users_role: role IN ('VIEWER','EDITOR','ADMIN') |
| status | varchar(16) | NOT NULL | 'ACTIVE' | CHECK ck_users_status: status IN ('ACTIVE','DISABLED') |
| version | integer | NOT NULL | 1 | CHECK ck_users_version: version >= 1 |
| created_at | timestamptz | NOT NULL | now() | UTC |
| updated_at | timestamptz | NOT NULL | now() | 应用层更新 |

**无 deleted_at**（§21：账号停用非软删）。

username 归一化裁定：单列存已归一化（小写、去首尾空白）值，UNIQUE 兜底；CHECK `username ~ '^[a-z0-9._-]{3,64}$'` 使直接 SQL 也无法绕过。理由：DR-14 限定为小写专用字符集，无独立展示大小写需求，归一化键列冗余；CHECK 使归一化成为 DB 可保证完整性（§27）。

枚举 varchar+CHECK（不用原生 ENUM）：新增值只需改 CHECK；与 Python StrEnum 直接映射；避免 ALTER TYPE 演进成本。

## 4. user_sessions 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK pk_user_sessions |
| user_id | UUID | NOT NULL | — | FK fk_user_sessions_user_id_users → users.id ON DELETE RESTRICT |
| token_hash | varchar(64) | NOT NULL | — | UNIQUE uq_user_sessions_token_hash；CHECK ck_user_sessions_token_hash_format: ^[0-9a-f]{64}$ |
| created_at | timestamptz | NOT NULL | now() | UTC |
| expires_at | timestamptz | NOT NULL | — | CHECK ck_user_sessions_expires_after_created: expires_at > created_at |
| last_seen_at | timestamptz | NULL | — | 可选 |

索引：ix_user_sessions_user_id（FK 查询/PG 不自动建 FK 索引）、ix_user_sessions_expires_at（惰性过期/未来维护）。

FK ON DELETE RESTRICT（非 CASCADE）：§21 无删除用户路径；RESTRICT 使误删显式失败，不静默丢弃会话/历史身份。用户停用对会话即时失效由应用层请求时 join users 校验 status='ACTIVE' 实现，停用时显式删会话（Backend 责任）。

过期清理：不预建定时任务（无 Redis/调度，§29）；请求命中后 expires_at <= now() 视为无效；登出删行；不做批量后台清理。

## 5. 迁移 0002_users_sessions（DB-D7）

- 追加于 0001_baseline 后，revision="0002_users_sessions"、down_revision="0001_baseline"，单一 head，不改已发布 revision。
- 新表无回填；upgrade 先 users 后 user_sessions（FK 顺序），downgrade 逆序 drop。
- 命名按 DB-D6；迁移 DDL 约束显式给全名（op.create_table 不自动套用 Base.metadata 命名约定，autogenerate 不识别 CHECK，故手写）。
- 迁移只建 Schema 不写业务数据（DR-12）。

```python
"""users and user_sessions for F002 auth.

Revision ID: 0002_users_sessions
Revises: 0001_baseline
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0002_users_sessions"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.CheckConstraint("username ~ '^[a-z0-9._-]{3,64}$'", name="ck_users_username_format"),
        sa.CheckConstraint("role IN ('VIEWER','EDITOR','ADMIN')", name="ck_users_role"),
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_users_status"),
        sa.CheckConstraint("version >= 1", name="ck_users_version"),
        sa.CheckConstraint("length(btrim(password_hash)) > 0", name="ck_users_password_hash_nonempty"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_user_sessions_user_id_users", ondelete="RESTRICT"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_user_sessions_token_hash_format"),
        sa.CheckConstraint("expires_at > created_at", name="ck_user_sessions_expires_after_created"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
```

可逆性：up/down 对称；F002 首次建表无生产数据，drop 表可接受；F003 起破坏性 downgrade 须按 DB-D7 数据安全策略。

## 6. 数据完整性对应表（F002 适用项）

| 规则依据 | 作用域 | DB 保证 | 业务层保证 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §23/DR-14 | 用户创建 | uq_users_username + ck_users_username_format | 应用先归一化再写 | 并发同名 UNIQUE 兜底；只停用不删 | 计划：重复/并发插入 IntegrityError |
| §21/§22 | 账号生命周期 | 无 deleted_at；FK RESTRICT | 无删除路径；停用保留身份；停用删会话 | 带会话用户删除失败 | 计划：删除被 RESTRICT 拒绝 |
| §22/DR-08 | 会话创建 | uq_user_sessions_token_hash + 格式 CHECK | 仅存 SHA-256 hex | 碰撞 UNIQUE 兜底 | 计划：重复 token_hash 失败；无明文列 |
| §22 | 凭据/令牌 | 仅存 password_hash/token_hash | 响应排除；日志脱敏 | DB 泄露不暴露可用令牌 | 计划：列清单+扫描 |
| §23/DR-11 | 乐观锁 | version + ck_users_version | 比较-写入（端到端 F003） | 并发以 version 检测 | 计划：过期 version 不生效（机制级） |
| §26/§27 | 枚举演进 | varchar+CHECK 拒非法 role/status | 应用枚举与 CHECK 一致 | 扩展走迁移 | 计划：非法值被 CHECK 拒绝 |
| §30/DR-12 | 初始 ADMIN 幂等 | uq_users_username 兜底 | bootstrap 事务内"存在任何用户 no-op" | 重复启动不重复 | 计划：干净库恰一 ADMIN，重启 no-op |

## 7. Backend 可依赖保证与测试项

保证：username 唯一由 DB 保证；CHECK 保证库内 username 小写 3–64 合法字符集；token_hash 唯一且格式受 CHECK；非法 role/status/version/expires_at 由 CHECK 拒绝；带会话用户无法删除；UUID 默认生成供 F003 沿用；0002 有真实 downgrade。

计划测试项：V-DB-1 真库 up/down/up；V-DB-2 重复/非法 username 拒绝；V-DB-3 重复/非法 token_hash 拒绝；V-DB-4 非法 role/status 拒绝；V-DB-5 删除有会话 user 被 RESTRICT；V-DB-6 默认值与时间列断言；V-DB-7 索引/唯一约束存在断言。均真实 PostgreSQL 执行，Mock/SQLite 不作证据。

## 8. 未验证项与风险

只读签核，所有验证为计划验证无 PASS。稳定 ID 形态属 D01，本 Gate 先签发并要求 F003 沿用；若 CONTRACT 改选其它形态（无数据可改未发布 0002）须走变更控制。CHECK 内嵌 username 字符集依赖 D02/DR-14，调整需新增迁移。expires_at 无自动清理，长期产生过期行（索引支持未来清理，本期不实现）。version 端到端属 F003/T26。操作者持久表示在 F003 Audit 最终形态待 F003 裁定。
