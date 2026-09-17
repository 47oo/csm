"""F007 并发 / 锁序测试（AC-36 / AC-37 / AC-38，数据库层，真实 PostgreSQL）。

使用真实 SQLAlchemy 会话直接驱动服务函数（``create_container`` /
``delete_bare_metal`` / ``delete_virtual_machine``），在提交前精确控制事务持锁时刻：

- 创建 Container 对**被选中载体行**（BareMetal / VirtualMachine）取共享锁
  （``FOR SHARE``），与载体删除的 ``FOR UPDATE`` 互斥；
- 两种交错（先建后删 / 先删后建）结束后，孤立记录不变式恒为 **0 行**；
- 两种载体类型均验证（AC-36 / AC-37）。
"""

from __future__ import annotations

import threading
import time

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.bare_metals import service as bare_metal_service
from app.common.errors import ConflictError, NotFoundError
from app.containers import service as container_service
from app.containers.schemas import ContainerCreate
from app.virtual_machines import service as virtual_machine_service
from tests.database.helpers import raw_connection_dsn, upgrade_to_head

ORPHAN_INVARIANT_BM_SQL = """
SELECT count(*) FROM containers c
JOIN bare_metals bm ON bm.id = c.bare_metal_id
WHERE c.deleted_at IS NULL AND bm.deleted_at IS NOT NULL
"""

ORPHAN_INVARIANT_VM_SQL = """
SELECT count(*) FROM containers c
JOIN virtual_machines vm ON vm.id = c.virtual_machine_id
WHERE c.deleted_at IS NULL AND vm.deleted_at IS NOT NULL
"""


def _invariant_bm(conn: psycopg.Connection) -> int:
    return conn.execute(ORPHAN_INVARIANT_BM_SQL).fetchone()[0]


def _invariant_vm(conn: psycopg.Connection) -> int:
    return conn.execute(ORPHAN_INVARIANT_VM_SQL).fetchone()[0]


def _insert_host(conn: psycopg.Connection, name: str) -> int:
    cluster_id = conn.execute(
        "INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()[0]
    return conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, %s) RETURNING id",
        (cluster_id, "n1"),
    ).fetchone()[0]


def _insert_vm(conn: psycopg.Connection, bare_metal_id: int, name: str) -> int:
    return conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, %s) RETURNING id",
        (bare_metal_id, name),
    ).fetchone()[0]


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
# AC-36：BareMetal 载体 —— 并发创建 vs 删除宿主，孤立记录不变式 = 0
# --------------------------------------------------------------------------- #
def test_ac36_create_bm_container_commits_first_delete_conflicts(concurrency_env):
    _, factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_delete() -> None:
        try:
            bare_metal_service.delete_bare_metal(delete_session, host_id)
            delete_session.commit()
            outcome["delete"] = "ok"
        except ConflictError:
            delete_session.rollback()
            outcome["delete"] = "conflict"
        except Exception as exc:  # noqa: BLE001 - 记录真实结果
            outcome["delete"] = exc

    try:
        container_service.create_container(
            create_session,
            ContainerCreate(carrier_type="BARE_METAL", carrier_id=host_id, name="web"),
        )

        thread = threading.Thread(target=do_delete)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "创建持有宿主行 FOR SHARE 时，删除必须阻塞"

        create_session.commit()
        create_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["delete"] == "conflict", outcome
        assert (
            conn.execute("SELECT deleted_at FROM bare_metals WHERE id = %s", (host_id,)).fetchone()[
                0
            ]
            is None
        )
        assert _invariant_bm(conn) == 0
        assert conn.execute("SELECT count(*) FROM containers").fetchone()[0] == 1
    finally:
        delete_session.close()


def test_ac36_delete_bm_commits_first_create_rejected(concurrency_env):
    _, factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            container_service.create_container(
                create_session,
                ContainerCreate(carrier_type="BARE_METAL", carrier_id=host_id, name="web"),
            )
            create_session.commit()
            outcome["create"] = "ok"
        except NotFoundError:
            create_session.rollback()
            outcome["create"] = "not_found"
        except Exception as exc:  # noqa: BLE001 - 记录真实结果
            outcome["create"] = exc

    try:
        bare_metal_service.delete_bare_metal(delete_session, host_id)

        thread = threading.Thread(target=do_create)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "删除持有宿主行 FOR UPDATE 时，创建必须阻塞"

        delete_session.commit()
        delete_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["create"] == "not_found", outcome
        assert _invariant_bm(conn) == 0
        assert conn.execute("SELECT count(*) FROM containers").fetchone()[0] == 0
    finally:
        create_session.close()


# --------------------------------------------------------------------------- #
# AC-37：VirtualMachine 载体 —— 并发创建 vs 删除 VM，孤立记录不变式 = 0
# --------------------------------------------------------------------------- #
def test_ac37_create_vm_container_commits_first_delete_conflicts(concurrency_env):
    _, factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")
    vm_id = _insert_vm(conn, host_id, "vm1")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_delete() -> None:
        try:
            virtual_machine_service.delete_virtual_machine(delete_session, vm_id)
            delete_session.commit()
            outcome["delete"] = "ok"
        except ConflictError:
            delete_session.rollback()
            outcome["delete"] = "conflict"
        except Exception as exc:  # noqa: BLE001 - 记录真实结果
            outcome["delete"] = exc

    try:
        container_service.create_container(
            create_session,
            ContainerCreate(carrier_type="VIRTUAL_MACHINE", carrier_id=vm_id, name="web"),
        )

        thread = threading.Thread(target=do_delete)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "创建持有 VM 行 FOR SHARE 时，删除必须阻塞"

        create_session.commit()
        create_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["delete"] == "conflict", outcome
        assert (
            conn.execute(
                "SELECT deleted_at FROM virtual_machines WHERE id = %s", (vm_id,)
            ).fetchone()[0]
            is None
        )
        assert _invariant_vm(conn) == 0
        assert conn.execute("SELECT count(*) FROM containers").fetchone()[0] == 1
    finally:
        delete_session.close()


def test_ac37_delete_vm_commits_first_create_rejected(concurrency_env):
    _, factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")
    vm_id = _insert_vm(conn, host_id, "vm1")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            container_service.create_container(
                create_session,
                ContainerCreate(carrier_type="VIRTUAL_MACHINE", carrier_id=vm_id, name="web"),
            )
            create_session.commit()
            outcome["create"] = "ok"
        except NotFoundError:
            create_session.rollback()
            outcome["create"] = "not_found"
        except Exception as exc:  # noqa: BLE001 - 记录真实结果
            outcome["create"] = exc

    try:
        virtual_machine_service.delete_virtual_machine(delete_session, vm_id)

        thread = threading.Thread(target=do_create)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "删除持有 VM 行 FOR UPDATE 时，创建必须阻塞"

        delete_session.commit()
        delete_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["create"] == "not_found", outcome
        assert _invariant_vm(conn) == 0
        assert conn.execute("SELECT count(*) FROM containers").fetchone()[0] == 0
    finally:
        create_session.close()


# --------------------------------------------------------------------------- #
# AC-38：创建对载体行取共享锁并在同一事务内确认活跃
# --------------------------------------------------------------------------- #
def test_ac38_create_blocks_on_carrier_exclusive_lock_then_rejects(concurrency_env):
    _, factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")

    blocker = psycopg.connect(raw_connection_dsn(conn.info.dsn))
    blocker.autocommit = False
    blocker.execute("SELECT id FROM bare_metals WHERE id = %s FOR UPDATE", (host_id,))
    blocker.execute("UPDATE bare_metals SET deleted_at = now() WHERE id = %s", (host_id,))

    session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            container_service.create_container(
                session,
                ContainerCreate(carrier_type="BARE_METAL", carrier_id=host_id, name="web"),
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
        assert thread.is_alive(), "载体行被 FOR UPDATE 锁定时，创建必须阻塞（FOR SHARE 互斥）"
    finally:
        blocker.commit()
        blocker.close()

    thread.join(timeout=15)
    assert not thread.is_alive()
    assert outcome["create"] == "not_found", outcome
    assert conn.execute("SELECT count(*) FROM containers").fetchone()[0] == 0
    assert _invariant_bm(conn) == 0
    session.close()


def test_ac38_create_gate_uses_row_lock(concurrency_env):
    """创建路径的载体预检必须真实持锁：持锁期间第二条连接的 FOR UPDATE NOWAIT 失败。"""
    _, factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")

    session: Session = factory()
    try:
        container_service.create_container(
            session,
            ContainerCreate(carrier_type="BARE_METAL", carrier_id=host_id, name="web"),
        )
        with psycopg.connect(raw_connection_dsn(conn.info.dsn)) as other:
            other.autocommit = True
            with pytest.raises(psycopg.errors.LockNotAvailable):
                other.execute(
                    "SELECT id FROM bare_metals WHERE id = %s FOR UPDATE NOWAIT", (host_id,)
                )
    finally:
        session.rollback()
        session.close()

    with psycopg.connect(raw_connection_dsn(conn.info.dsn)) as other:
        other.autocommit = True
        other.execute("SELECT id FROM bare_metals WHERE id = %s FOR UPDATE NOWAIT", (host_id,))
    assert conn.execute("SELECT 1").fetchone()[0] == 1
