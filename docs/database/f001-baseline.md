# F001 数据库基线设计（D02 基础部分）

- **签核**：Database；设计版本 v1（2026-10-06）
- **上游依据**：`docs/product/requirements-v3.md` revision 3（§17、§22、§26–§27、§30–§31）；`docs/features/F001/architecture.md`（READY FOR DESIGN）
- **覆盖**：F001 D02 数据库基础部分——基线迁移、扩展清单、Alembic 环境、连接池/超时/隔离骨架、测试库供给、备份骨架。不覆盖：业务 Schema/索引/IPAM 锁（F003、F008–F010）、TEST 执行（Tester）、Contract 定稿（Architect）。
- **决策状态**：CONFIRMED = 需求已确认；DESIGN（签核）= 本 Gate 在已批准边界内的专业设计决定。

## 1. 范围与前提

F001 为一期首次建库、无业务表、无历史数据。本文件只覆盖工程/部署底座；业务实体、唯一性/关系/生命周期与索引自 F003 起在各 Feature DATABASE Gate 落定。技术栈以 §26 为输入，不重新选型。

## 2. 设计决策汇总

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D1 | `0001_baseline.py` 手写迁移，只启用扩展，不创建业务表 | DESIGN |
| DB-D2 | 基线只启用 pg_trgm；btree_gist 推迟 | DESIGN |
| DB-D3 | 扩展以 `CREATE EXTENSION IF NOT EXISTS … WITH SCHEMA public` 版本化启用 | DESIGN |
| DB-D4 | 基线 downgrade 为文档化非对称（不 drop 扩展） | DESIGN |
| DB-D5 | env.py 从 Settings 读 URL、`target_metadata=Base.metadata`、`compare_type=True`、迁移引擎 NullPool、在线/离线双支持 | DESIGN |
| DB-D6 | 命名约定 `pk_/fk_/uq_/ix_/ck_` 落于 `app/models/base.py` | DESIGN |
| DB-D7 | 后续迁移规范：追加 revision、禁改已发布 revision、单一 head、真实 PG up/down/up | DESIGN |
| DB-D8 | App engine：`pool_pre_ping=True`、`pool_size=5`、`max_overflow=10`、`pool_recycle=1800`、`pool_timeout=30`；`statement_timeout=30000ms`、`lock_timeout=5000ms`（可配置）；隔离级别默认 READ COMMITTED | DESIGN |
| DB-D9 | `get_db()` 交付 Session，提交责任在 Service 层；不启用 async、不引入连接池中间件 | DESIGN |
| DB-D10 | 测试用独立测试库（非 schema 隔离）；会话级重建 public + upgrade head；函数级事务回滚；并发用例真实提交 + teardown | DESIGN |
| DB-D11 | 目标扩展在 PG16 为 trusted，安装仅需数据库 owner/CREATE，测试与部署不需 superuser（待 V3b 证实） | DESIGN |
| DB-D12 | 备份骨架 `pg_dump -Fc --no-owner --no-privileges` + 恢复脚本 + 文档 + 冒烟；不宣称 Audit 覆盖（T36 归 F016） | DESIGN |

## 3. 扩展清单裁定

| 扩展 | 裁定 | 理由 |
| --- | --- | --- |
| pg_trgm | **基线必启（0001）** | §26/§17 CONFIRMED；显式启用、可审计 |
| btree_gist | **基线不启用；推迟**至首个需要 gist+btree 排他约束的 Feature（预计 F008/F009），由该 Feature DATABASE Gate 按最终约束形态以 `IF NOT EXISTS` 幂等启用 | ①约束形态尚未设计；②不预建无需求支撑；③后续启用成本极低且同为 trusted |
| pgcrypto / uuid-ossp | 不启用 | PG13+ 核心自带 `gen_random_uuid()`；稳定 ID 形态由 F003/D01 裁定 |
| citext | 不启用 | 大小写不敏感唯一性以归一化键列 + 唯一索引显式实现，避免 citext 隐式语义 |
| unaccent / fuzzystrmatch / postgis 等 | 不启用 | §17 仅需 pg_trgm；一期仅 IPv4，INET/CIDR 足够 |

基线扩展集合 = `{pg_trgm}`（唯一）。

## 4. 基线迁移 `alembic/versions/0001_baseline.py`

- 手写（F001 target_metadata 为空，autogenerate 无意义）；`revision = "0001_baseline"`、`down_revision = None`。
- 只启用扩展；扩展启用由 Alembic 执行而非 initdb 脚本；`CREATE EXTENSION` 可在事务内执行。
- 固定 `WITH SCHEMA public` 保证安装位置确定；扩展名来自代码常量、无注入面。

```python
"""baseline: enable required extensions (no business tables).

Revision ID: 0001_baseline
"""
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

EXTENSIONS = [("pg_trgm", "public")]


def upgrade() -> None:
    for name, schema in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {name} WITH SCHEMA {schema}")


def downgrade() -> None:
    # Intentionally asymmetric: extensions are NOT dropped here.
    # See docs/database/f001-baseline.md §4.
    pass
```

**downgrade 非对称裁定（DB-D4）**：①扩展是数据库级对象，drop 是跨对象破坏性操作；②`IF NOT EXISTS` 意味着迁移可能并未创建该扩展，downgrade 不应删除自己可能不拥有的对象；③CASCADE 会静默销毁未来依赖索引、不带 CASCADE 则破坏降级链；④drop 扩展需更高权限。扩展生命周期由基线 provision/DBA 拥有；验收"可回滚/up→down→up 一致"由回滚移除 alembic_version 行 + 再 upgrade 幂等满足。彻底清除扩展用独立管理脚本，不纳入迁移链。

## 5. Alembic 环境与迁移规范

- `alembic.ini`：`script_location=alembic`、`prepend_sys_path=.`、`sqlalchemy.url` 留空由 env.py 注入。
- `env.py`：URL 来源 `Settings`；`target_metadata=Base.metadata`；`compare_type=True`；`compare_server_default=False`；迁移引擎 `NullPool` 且不继承 app statement_timeout（避免长 DDL 被杀）；离线/在线双支持。
- 命名约定（`app/models/base.py`）：

```python
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s)",
}
```
（实现时以实际可用模板语法为准；`CheckConstraint` 必须显式命名，表达式索引必须显式给名字。）

- **后续 Feature 迁移规范（DB-D7）**：追加 revision、单一 head；禁改已发布 revision；upgrade/downgrade 均实现（确不可逆须显式记录并签核）；破坏性操作需影响评估与分步；新增非空列走"可空→回填→置 NOT NULL"；大表索引评估 CONCURRENTLY（autocommit block）；扩展新增用 IF NOT EXISTS；真实 PG 执行 up/down/up；扩展/表达式索引手写（autogenerate 不识别）。

## 6. 连接管理骨架（`app/core/db.py`）

```python
engine = create_engine(
    settings.database_url,                      # postgresql+psycopg://…
    pool_pre_ping=True, pool_size=5, max_overflow=10,
    pool_recycle=1800, pool_timeout=30,
    connect_args={
        "application_name": "csm-backend",
        "options": "-c statement_timeout=30000 -c lock_timeout=5000",
    },
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

- 同步 SQLAlchemy 2.x + psycopg3；`def` 路由走 FastAPI 线程池；不引入 async ORM 与连接池中间件。
- `get_db` 不自动 commit；提交/回滚由 Service 层掌控（§24）。
- **IPAM 衔接**：F008–F010 的并发分配/保留范围冲突用事务级锁（`SELECT … FOR UPDATE`、Network 级 advisory lock 或排他约束+btree_gist），按事务申请、不改 engine；可按事务覆盖隔离级别。F001 仅保证 engine 支持按事务覆盖。
- Settings 配置位：`DATABASE_URL`、`DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`DB_POOL_RECYCLE`、`DB_POOL_TIMEOUT`、`DB_STATEMENT_TIMEOUT_MS`、`DB_LOCK_TIMEOUT_MS`、`DB_APPLICATION_NAME`；敏感值仅经 .env/环境注入。

## 7. 测试库供给与权限

- `TEST_DATABASE_URL` 独立专用测试库（库名含 `test`）；采用独立数据库而非 schema 隔离（扩展是数据库级对象，独立库可确定性重建）。
- 安全护栏：conftest 断言库名含 `test` 且 `TEST_DATABASE_URL != DATABASE_URL`，否则中止。
- Fixture 分层：会话级重建 public schema + `alembic upgrade head`；函数级外层事务 + savepoint 回滚；并发用例真实提交 + teardown `TRUNCATE`（排除 alembic_version），新连接断言最终状态。
- 权限（DB-D11）：pg_trgm（及未来 btree_gist 等）在 PG13+ 为 trusted，安装仅需目标库 CREATE 权限（owner 天然满足），无需 superuser。部署权限分层建议：迁移/建库角色=owner；应用运行角色=仅 DML+USAGE（Compose 首期可简化单角色，文档标注"非生产加固"）。备选：DBA 预装扩展，迁移 IF NOT EXISTS 变 no-op，偏离须记录。

## 8. 备份骨架与恢复文档（`deploy/backup/`）

- `pg_dump.sh`：读 DATABASE_URL、不回显/不落盘凭据、`set -euo pipefail`、`pg_dump -Fc --no-owner --no-privileges`、原子 mv 带时间戳文件、失败非零退出。
- `restore.sh`：默认恢复到全新目标库；`--clean --if-exists` 仅显式 `--force` 启用；要求显式目标库名。
- `README.md`：前提（PG16 含 contrib）、步骤、验证判据、范围声明、回滚步骤；RPO/RTO 不在 F001 范围。
- **冒烟判据（F001 级）**：①`SELECT 1` 成功；②`pg_extension` 有 pg_trgm；③`alembic_version` == 源库 head；④`alembic current` 为 head、再 upgrade 幂等；⑤后端连恢复库 `/api/v1/health/ready` 返回 200。
- **明确不宣称**：不验证 Audit 数据覆盖（T36 属 F016）；pg_dump 默认覆盖全库（含未来 audit 表）。

## 9. 数据完整性对应表（F001 适用项）

| 规则依据及版本 | 作用域 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据（计划） |
| --- | --- | --- | --- | --- | --- |
| §26/§17 | Alembic 基线 | `CREATE EXTENSION IF NOT EXISTS pg_trgm` | 无（F001 无业务写入） | downgrade 不 drop 扩展 | V3 pg_extension 断言 |
| §27 | 迁移链 | 单一 head、up/down/up 一致 | 无 | 无历史数据 | V2 真库循环 |
| §31 T07/T35 前提 | 测试 fixture | 独立测试库、真实提交跨连接可见 | 无 | 多连接最终持久化状态 | V7 并发 fixture |
| §22/§30 | 备份/恢复脚本 | pg_dump -Fc 覆盖全库 | 脚本+文档+冒烟 | Audit 覆盖未验证（F016） | V5 恢复冒烟 |

## 10. Backend 可依赖的保证与测试项

- `alembic upgrade head` 后 PG16 上 `public.pg_trgm` 存在、`gin_trgm_ops` 可解析。
- 迁移引擎与应用引擎分离（NullPool、不继承超时）。
- `get_db()` 同步 Session；默认 READ COMMITTED、可按事务覆盖；超时可配。
- 命名约定对 F003 起新建对象生效。
- 测试项：V2 迁移循环；V3 扩展存在；**V3b 非 superuser owner 安装 pg_trgm（验证 trusted 假设）**；V4 fixture 重复运行无残留；V5 备份恢复冒烟（§8 判据）；V6 凭据边界；V7 并发提交可见性。

## 11. 未验证项与风险

- 本设计为只读签核，所有"验证"为计划验证，无 PASS 声称。
- trusted 扩展假设待 V3b 证实；不满足则转 DBA 预装备选。
- `WITH SCHEMA public` 与未来独立应用 schema 的交互不阻塞，必要时后续 revision 调整。
- btree_gist 推迟意味着 F008/F009 承担一次扩展启用 migration（成本已评估）。
- 连接池/超时数值为骨架默认，IPAM 终稿在 F008–F010，届时调整不视为本 Gate 失效。
