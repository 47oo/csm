"""F005 并发 / 锁序测试（T-31、T-32，数据库层，真实 PostgreSQL）。

使用真实 SQLAlchemy 会话直接驱动服务函数（``create_ip_address`` /
``delete_network_interface``），在提交前精确控制事务持锁时刻，验证：

- 创建 IP 对**父 NIC 行**取共享锁（``FOR SHARE``），与父 NIC 删除的 ``FOR UPDATE``
  互斥；
- 两种交错（先建后删 / 先删后建）结束后，孤立记录不变式恒为 **0 行**（不存在
  「父 NIC 已删 + IP 活跃」），且 ``cluster_id`` 漂移查询仍为 **0 行**（ADR-0004 §5 /
  AC-31 / AC-32）。
"""

from __future__ import annotations

import threading
import time

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.common.errors import ConflictError, NotFoundError
from app.ip_addresses import service as ip_address_service
from app.ip_addresses.schemas import IpAddressCreate
from app.network_interfaces import service as network_interface_service
from tests.database.helpers import raw_connection_dsn, upgrade_to_head
from tests.ip_address_drift_helpers import find_drift

# 孤立记录不变式：父 NIC 已删 + IP 活跃 必须为 0 行（AC-31）。
ORPHAN_INVARIANT_SQL = """
SELECT count(*) FROM ip_addresses ip
JOIN network_interfaces nic ON nic.id = ip.network_interface_id
WHERE ip.deleted_at IS NULL AND nic.deleted_at IS NOT NULL
"""


def _invariant(conn: psycopg.Connection) -> int:
    return conn.execute(ORPHAN_INVARIANT_SQL).fetchone()[0]


def _insert_chain(conn: psycopg.Connection, name: str) -> tuple[int, int, int]:
    cluster_id = conn.execute(
        "INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()[0]
    bare_metal_id = conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'n1') RETURNING id",
        (cluster_id,),
    ).fetchone()[0]
    nic_id = conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
        "VALUES (%s, 'eth0', 'Ethernet', 'Business') RETURNING id",
        (bare_metal_id,),
    ).fetchone()[0]
    return cluster_id, bare_metal_id, nic_id


def _payload(network_interface_id: int, ip: str = "10.0.0.1") -> IpAddressCreate:
    return IpAddressCreate(network_interface_id=network_interface_id, ip_address=ip)


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
# T-31 / AC-31：并发「创建 IP vs 删除父 NIC」，孤立记录不变式 = 0
# --------------------------------------------------------------------------- #
def test_t31_create_commits_first_delete_sees_active_child(concurrency_env):
    _, factory, conn = concurrency_env
    _, _, nic_id = _insert_chain(conn, "cluster-a")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_delete() -> None:
        try:
            network_interface_service.delete_network_interface(delete_session, nic_id)
            delete_session.commit()
            outcome["delete"] = "ok"
        except ConflictError:
            delete_session.rollback()
            outcome["delete"] = "conflict"
        except Exception as exc:  # noqa: BLE001 - 记录真实结果
            outcome["delete"] = exc

    try:
        # 创建先取父 NIC 行 FOR SHARE 并插入子行，但**不提交**。
        ip_address_service.create_ip_address(create_session, _payload(nic_id))

        thread = threading.Thread(target=do_delete)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "创建持有父 NIC 行 FOR SHARE 时，删除必须阻塞"

        create_session.commit()
        create_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["delete"] == "conflict", outcome
        assert (
            conn.execute(
                "SELECT deleted_at FROM network_interfaces WHERE id = %s", (nic_id,)
            ).fetchone()[0]
            is None
        )
        assert _invariant(conn) == 0
        assert find_drift(conn) == []
        assert conn.execute("SELECT count(*) FROM ip_addresses").fetchone()[0] == 1
    finally:
        delete_session.close()


def test_t31_delete_commits_first_create_is_rejected(concurrency_env):
    _, factory, conn = concurrency_env
    _, _, nic_id = _insert_chain(conn, "cluster-a")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            ip_address_service.create_ip_address(create_session, _payload(nic_id))
            create_session.commit()
            outcome["create"] = "ok"
        except NotFoundError:
            create_session.rollback()
            outcome["create"] = "not_found"
        except Exception as exc:  # noqa: BLE001 - 记录真实结果
            outcome["create"] = exc

    try:
        # 删除先取父 NIC 行 FOR UPDATE 并软删，但**不提交**。
        network_interface_service.delete_network_interface(delete_session, nic_id)

        thread = threading.Thread(target=do_create)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "删除持有父 NIC 行 FOR UPDATE 时，创建必须阻塞"

        delete_session.commit()
        delete_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["create"] == "not_found", outcome
        assert _invariant(conn) == 0
        assert find_drift(conn) == []
        assert conn.execute("SELECT count(*) FROM ip_addresses").fetchone()[0] == 0
    finally:
        create_session.close()


# --------------------------------------------------------------------------- #
# T-32 / AC-32：创建对父 NIC 行取共享锁并在同一事务内确认活跃
# --------------------------------------------------------------------------- #
def test_t32_create_blocks_on_nic_exclusive_lock_then_rejects(concurrency_env):
    _, factory, conn = concurrency_env
    _, _, nic_id = _insert_chain(conn, "cluster-a")

    # 外部连接持有父 NIC 行排他锁并软删（模拟并发的父 NIC 删除正在提交前）。
    blocker = psycopg.connect(raw_connection_dsn(conn.info.dsn))
    blocker.autocommit = False
    blocker.execute("SELECT id FROM network_interfaces WHERE id = %s FOR UPDATE", (nic_id,))
    blocker.execute("UPDATE network_interfaces SET deleted_at = now() WHERE id = %s", (nic_id,))

    session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            ip_address_service.create_ip_address(session, _payload(nic_id))
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
        assert thread.is_alive(), "父 NIC 行被 FOR UPDATE 锁定时，创建必须阻塞（FOR SHARE 互斥）"
    finally:
        blocker.commit()
        blocker.close()

    thread.join(timeout=15)
    assert not thread.is_alive()
    assert outcome["create"] == "not_found", outcome
    assert conn.execute("SELECT count(*) FROM ip_addresses").fetchone()[0] == 0
    assert _invariant(conn) == 0
    session.close()


def test_t32_create_gate_uses_share_lock(concurrency_env):
    """创建路径对父 NIC 行取共享锁：持锁期间第二条连接的 FOR UPDATE NOWAIT 失败。"""
    _, factory, conn = concurrency_env
    _, _, nic_id = _insert_chain(conn, "cluster-a")

    session: Session = factory()
    try:
        ip_address_service.create_ip_address(session, _payload(nic_id))
        # 创建的同一事务仍持有父 NIC 行 FOR SHARE。
        with psycopg.connect(raw_connection_dsn(conn.info.dsn)) as other:
            other.autocommit = True
            with pytest.raises(psycopg.errors.LockNotAvailable):
                other.execute(
                    "SELECT id FROM network_interfaces WHERE id = %s FOR UPDATE NOWAIT",
                    (nic_id,),
                )
    finally:
        session.rollback()
        session.close()

    # 事务回滚后锁释放。
    with psycopg.connect(raw_connection_dsn(conn.info.dsn)) as other:
        other.autocommit = True
        other.execute(
            "SELECT id FROM network_interfaces WHERE id = %s FOR UPDATE NOWAIT", (nic_id,)
        )
    assert conn.execute("SELECT 1").fetchone()[0] == 1
