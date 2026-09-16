"""F002 并发 / 锁序测试（T-25、T-26，数据库层，真实 PostgreSQL）。

使用真实 SQLAlchemy 会话直接驱动服务函数（``create_bare_metal`` /
``delete_cluster``），以便在提交前精确控制事务持锁时刻，验证：

- 创建对父 Cluster 行取**共享锁**（``FOR SHARE``），与删除的 ``FOR UPDATE`` 互斥；
- 两种交错（先建后删 / 先删后建）结束后，孤立记录不变式恒为 0 行
  （不存在「父已删 + 子活跃」）。
"""

from __future__ import annotations

import threading
import time

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.bare_metals import service as bare_metal_service
from app.bare_metals.schemas import BareMetalCreate
from app.clusters import service as cluster_service
from app.common.errors import ConflictError, NotFoundError
from tests.database.helpers import raw_connection_dsn, upgrade_to_head

# 孤立记录不变式：父已删 + 子活跃 必须为 0 行（ADR-0004 §5 / AC-25）。
ORPHAN_INVARIANT_SQL = """
SELECT count(*) FROM bare_metals bm
JOIN clusters c ON c.id = bm.cluster_id
WHERE bm.deleted_at IS NULL AND c.deleted_at IS NOT NULL
"""


def _invariant(conn: psycopg.Connection) -> int:
    return conn.execute(ORPHAN_INVARIANT_SQL).fetchone()[0]


def _insert_cluster(conn: psycopg.Connection, name: str) -> int:
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[
        0
    ]


@pytest.fixture
def concurrency_env(database_url):
    upgrade_to_head(database_url)
    engine = create_engine(database_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with psycopg.connect(raw_connection_dsn(database_url)) as conn:
        conn.autocommit = True
        yield engine, factory, conn
    engine.dispose()


# --------------------------------------------------------------------------- #
# T-25 / AC-25：并发「创建 BareMetal vs 删除 Cluster」孤立记录不变式 = 0
# --------------------------------------------------------------------------- #
def test_t25_create_commits_first_delete_sees_active_child(concurrency_env):
    _, factory, conn = concurrency_env
    cluster_id = _insert_cluster(conn, "cluster-a")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_delete() -> None:
        try:
            cluster_service.delete_cluster(delete_session, cluster_id)
            delete_session.commit()
            outcome["delete"] = "ok"
        except ConflictError:
            delete_session.rollback()
            outcome["delete"] = "conflict"
        except Exception as exc:  # noqa: BLE001 - 记录真实结果
            outcome["delete"] = exc

    try:
        # 创建先取 FOR SHARE 并插入子行，但**不提交**。
        bare_metal_service.create_bare_metal(
            create_session, BareMetalCreate(cluster_id=cluster_id, hostname="n1")
        )

        thread = threading.Thread(target=do_delete)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "创建持有父行 FOR SHARE 时，删除必须阻塞"

        create_session.commit()
        create_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["delete"] == "conflict", outcome
        # 父行未被软删（无部分写入）
        assert (
            conn.execute("SELECT deleted_at FROM clusters WHERE id = %s", (cluster_id,)).fetchone()[
                0
            ]
            is None
        )
        assert _invariant(conn) == 0
        assert conn.execute("SELECT count(*) FROM bare_metals").fetchone()[0] == 1
    finally:
        delete_session.close()


def test_t25_delete_commits_first_create_is_rejected(concurrency_env):
    _, factory, conn = concurrency_env
    cluster_id = _insert_cluster(conn, "cluster-a")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            bare_metal_service.create_bare_metal(
                create_session, BareMetalCreate(cluster_id=cluster_id, hostname="n1")
            )
            create_session.commit()
            outcome["create"] = "ok"
        except NotFoundError:
            create_session.rollback()
            outcome["create"] = "not_found"
        except Exception as exc:  # noqa: BLE001 - 记录真实结果
            outcome["create"] = exc

    try:
        # 删除先取 FOR UPDATE 并软删父行，但**不提交**。
        cluster_service.delete_cluster(delete_session, cluster_id)

        thread = threading.Thread(target=do_create)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "删除持有父行 FOR UPDATE 时，创建必须阻塞"

        delete_session.commit()
        delete_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["create"] == "not_found", outcome
        assert _invariant(conn) == 0
        assert conn.execute("SELECT count(*) FROM bare_metals").fetchone()[0] == 0
    finally:
        create_session.close()


# --------------------------------------------------------------------------- #
# T-26 / AC-26：创建对父行取共享锁并在同一事务内确认活跃
# --------------------------------------------------------------------------- #
def test_t26_create_blocks_on_parent_exclusive_lock_then_rejects(concurrency_env):
    _, factory, conn = concurrency_env
    cluster_id = _insert_cluster(conn, "cluster-a")

    # 外部连接持有父行排他锁并软删（模拟并发的 Cluster 删除正在提交前）。
    blocker = psycopg.connect(raw_connection_dsn(conn.info.dsn))
    blocker.autocommit = False
    blocker.execute("SELECT id FROM clusters WHERE id = %s FOR UPDATE", (cluster_id,))
    blocker.execute("UPDATE clusters SET deleted_at = now() WHERE id = %s", (cluster_id,))

    session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            bare_metal_service.create_bare_metal(
                session, BareMetalCreate(cluster_id=cluster_id, hostname="n1")
            )
            session.commit()
            outcome["create"] = "ok"
        except NotFoundError:
            session.rollback()
            outcome["create"] = "not_found"
        except Exception as exc:  # noqa: BLE001 - 记录真实结果
            outcome["create"] = exc

    thread = threading.Thread(target=do_create)
    thread.start()
    try:
        time.sleep(1.5)
        assert thread.is_alive(), "父行被 FOR UPDATE 锁定时，创建必须阻塞（FOR SHARE 互斥）"
    finally:
        blocker.commit()
        blocker.close()

    thread.join(timeout=15)
    assert not thread.is_alive()
    # 父删提交后重新求值 → 未命中活跃父 → 拒绝创建，不留无主机器
    assert outcome["create"] == "not_found", outcome
    assert conn.execute("SELECT count(*) FROM bare_metals").fetchone()[0] == 0
    assert _invariant(conn) == 0
    session.close()


def test_t26_parent_gate_uses_row_lock(concurrency_env):
    """创建路径的父预检必须真实持锁：持锁期间第二条连接的 FOR SHARE NOWAIT 失败。"""
    _, factory, conn = concurrency_env
    cluster_id = _insert_cluster(conn, "cluster-a")

    session: Session = factory()
    try:
        bare_metal_service.create_bare_metal(
            session, BareMetalCreate(cluster_id=cluster_id, hostname="n1")
        )
        # 创建的同一事务仍持有父行 FOR SHARE。
        with psycopg.connect(raw_connection_dsn(conn.info.dsn)) as other:
            other.autocommit = True
            with pytest.raises(psycopg.errors.LockNotAvailable):
                other.execute(
                    "SELECT id FROM clusters WHERE id = %s FOR UPDATE NOWAIT", (cluster_id,)
                )
    finally:
        session.rollback()
        session.close()

    # 事务回滚后锁释放。
    with psycopg.connect(raw_connection_dsn(conn.info.dsn)) as other:
        other.autocommit = True
        other.execute("SELECT id FROM clusters WHERE id = %s FOR UPDATE NOWAIT", (cluster_id,))
    assert conn.execute("SELECT 1").fetchone()[0] == 1
