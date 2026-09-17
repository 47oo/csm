"""F008 Service 并发 / 锁序测试（AC-46 / AC-47，数据库层，真实 PostgreSQL）。

使用真实 SQLAlchemy 会话直接驱动服务函数（``create_service`` /
``delete_bare_metal`` / ``delete_virtual_machine`` / ``delete_container``），在提交前
精确控制事务持锁时刻：

- 登记对**每一个**载体行取共享锁（``FOR SHARE``，按 §3 全序），与载体删除的
  ``FOR UPDATE`` 互斥；
- 两种交错（先建后删 / 先删后建）结束后，三条孤立记录不变式恒为 **0 行**；
- 三种载体类型均验证（AC-46 / AC-47）。
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
from app.services import service as service_service
from app.services.schemas import CarrierRef, ServiceCreate
from app.virtual_machines import service as virtual_machine_service
from tests.database.helpers import raw_connection_dsn, upgrade_to_head

ORPHAN_BM_SQL = """
SELECT count(*) FROM services s
JOIN service_carriers sc ON sc.service_id = s.id
JOIN bare_metals bm ON bm.id = sc.bare_metal_id
WHERE s.deleted_at IS NULL AND bm.deleted_at IS NOT NULL
"""
ORPHAN_VM_SQL = """
SELECT count(*) FROM services s
JOIN service_carriers sc ON sc.service_id = s.id
JOIN virtual_machines vm ON vm.id = sc.virtual_machine_id
WHERE s.deleted_at IS NULL AND vm.deleted_at IS NOT NULL
"""
ORPHAN_CONTAINER_SQL = """
SELECT count(*) FROM services s
JOIN service_carriers sc ON sc.service_id = s.id
JOIN containers c ON c.id = sc.container_id
WHERE s.deleted_at IS NULL AND c.deleted_at IS NOT NULL
"""
AC49_SQL = """
SELECT count(*) FROM services s
WHERE s.deleted_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM service_carriers sc WHERE sc.service_id = s.id)
"""


def _scalar(conn: psycopg.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


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


def _insert_container(conn: psycopg.Connection, virtual_machine_id: int, name: str) -> int:
    return conn.execute(
        "INSERT INTO containers (virtual_machine_id, name) VALUES (%s, %s) RETURNING id",
        (virtual_machine_id, name),
    ).fetchone()[0]


@pytest.fixture
def concurrency_env(database_url):
    upgrade_to_head(database_url)
    engine = create_engine(database_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with psycopg.connect(raw_connection_dsn(database_url)) as conn:
        conn.autocommit = True
        yield factory, conn
    engine.dispose()


def _service_create(carrier_type: str, carrier_id: int, name: str) -> ServiceCreate:
    return ServiceCreate(
        name=name, carriers=[CarrierRef(carrier_type=carrier_type, carrier_id=carrier_id)]
    )


# --------------------------------------------------------------------------- #
# AC-46：BareMetal 载体
# --------------------------------------------------------------------------- #
def test_ac46_bm_create_commits_first_delete_conflicts(concurrency_env):
    factory, conn = concurrency_env
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
        except Exception as exc:  # noqa: BLE001
            outcome["delete"] = exc

    try:
        service_service.create_service(
            create_session, _service_create("BARE_METAL", host_id, "svc")
        )
        thread = threading.Thread(target=do_delete)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "登记持有载体行 FOR SHARE 时，删除必须阻塞"

        create_session.commit()
        create_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["delete"] == "conflict", outcome
        assert (
            conn.execute("SELECT deleted_at FROM bare_metals WHERE id=%s", (host_id,)).fetchone()[0]
            is None
        )
        assert _scalar(conn, ORPHAN_BM_SQL) == 0
        assert _scalar(conn, AC49_SQL) == 0
    finally:
        delete_session.close()


def test_ac46_bm_delete_commits_first_create_rejected(concurrency_env):
    factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            service_service.create_service(
                create_session, _service_create("BARE_METAL", host_id, "svc")
            )
            create_session.commit()
            outcome["create"] = "ok"
        except NotFoundError:
            create_session.rollback()
            outcome["create"] = "not_found"
        except Exception as exc:  # noqa: BLE001
            outcome["create"] = exc

    try:
        bare_metal_service.delete_bare_metal(delete_session, host_id)
        thread = threading.Thread(target=do_create)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "删除持有载体行 FOR UPDATE 时，登记必须阻塞"

        delete_session.commit()
        delete_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["create"] == "not_found", outcome
        assert _scalar(conn, "SELECT count(*) FROM services") == 0
        assert _scalar(conn, "SELECT count(*) FROM service_carriers") == 0
        assert _scalar(conn, ORPHAN_BM_SQL) == 0
    finally:
        create_session.close()


# --------------------------------------------------------------------------- #
# AC-46：VirtualMachine 载体
# --------------------------------------------------------------------------- #
def test_ac46_vm_create_commits_first_delete_conflicts(concurrency_env):
    factory, conn = concurrency_env
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
        except Exception as exc:  # noqa: BLE001
            outcome["delete"] = exc

    try:
        service_service.create_service(
            create_session, _service_create("VIRTUAL_MACHINE", vm_id, "svc")
        )
        thread = threading.Thread(target=do_delete)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "登记持有 VM 行 FOR SHARE 时，删除必须阻塞"

        create_session.commit()
        create_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["delete"] == "conflict", outcome
        assert _scalar(conn, ORPHAN_VM_SQL) == 0
    finally:
        delete_session.close()


def test_ac46_vm_delete_commits_first_create_rejected(concurrency_env):
    factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")
    vm_id = _insert_vm(conn, host_id, "vm1")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            service_service.create_service(
                create_session, _service_create("VIRTUAL_MACHINE", vm_id, "svc")
            )
            create_session.commit()
            outcome["create"] = "ok"
        except NotFoundError:
            create_session.rollback()
            outcome["create"] = "not_found"
        except Exception as exc:  # noqa: BLE001
            outcome["create"] = exc

    try:
        virtual_machine_service.delete_virtual_machine(delete_session, vm_id)
        thread = threading.Thread(target=do_create)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "删除持有 VM 行 FOR UPDATE 时，登记必须阻塞"

        delete_session.commit()
        delete_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["create"] == "not_found", outcome
        assert _scalar(conn, "SELECT count(*) FROM service_carriers") == 0
        assert _scalar(conn, ORPHAN_VM_SQL) == 0
    finally:
        create_session.close()


# --------------------------------------------------------------------------- #
# AC-46：Container 载体（落实 F007 追加点端到端）
# --------------------------------------------------------------------------- #
def test_ac46_container_create_commits_first_delete_conflicts(concurrency_env):
    factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")
    vm_id = _insert_vm(conn, host_id, "vm1")
    container_id = _insert_container(conn, vm_id, "c1")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_delete() -> None:
        try:
            container_service.delete_container(delete_session, container_id)
            delete_session.commit()
            outcome["delete"] = "ok"
        except ConflictError:
            delete_session.rollback()
            outcome["delete"] = "conflict"
        except Exception as exc:  # noqa: BLE001
            outcome["delete"] = exc

    try:
        service_service.create_service(
            create_session, _service_create("CONTAINER", container_id, "svc")
        )
        thread = threading.Thread(target=do_delete)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "登记持有 Container 行 FOR SHARE 时，删除必须阻塞"

        create_session.commit()
        create_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["delete"] == "conflict", outcome
        assert (
            conn.execute(
                "SELECT deleted_at FROM containers WHERE id=%s", (container_id,)
            ).fetchone()[0]
            is None
        )
        assert _scalar(conn, ORPHAN_CONTAINER_SQL) == 0
    finally:
        delete_session.close()


def test_ac46_container_delete_commits_first_create_rejected(concurrency_env):
    factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")
    vm_id = _insert_vm(conn, host_id, "vm1")
    container_id = _insert_container(conn, vm_id, "c1")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            service_service.create_service(
                create_session, _service_create("CONTAINER", container_id, "svc")
            )
            create_session.commit()
            outcome["create"] = "ok"
        except NotFoundError:
            create_session.rollback()
            outcome["create"] = "not_found"
        except Exception as exc:  # noqa: BLE001
            outcome["create"] = exc

    try:
        container_service.delete_container(delete_session, container_id)
        thread = threading.Thread(target=do_create)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "删除持有 Container 行 FOR UPDATE 时，登记必须阻塞"

        delete_session.commit()
        delete_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["create"] == "not_found", outcome
        assert _scalar(conn, "SELECT count(*) FROM service_carriers") == 0
        assert _scalar(conn, ORPHAN_CONTAINER_SQL) == 0
    finally:
        create_session.close()


# --------------------------------------------------------------------------- #
# AC-47：登记对每一个载体取共享锁并在同一事务内确认活跃
# --------------------------------------------------------------------------- #
def test_ac47_create_locks_every_carrier_and_blocks_on_exclusive_lock(concurrency_env):
    factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")
    vm_id = _insert_vm(conn, host_id, "vm1")

    blocker = psycopg.connect(raw_connection_dsn(conn.info.dsn))
    blocker.autocommit = False
    # 对第二个载体（VM）取排他锁并软删，模拟并发删除。
    blocker.execute("SELECT id FROM virtual_machines WHERE id=%s FOR UPDATE", (vm_id,))
    blocker.execute("UPDATE virtual_machines SET deleted_at=now() WHERE id=%s", (vm_id,))

    session: Session = factory()
    outcome: dict[str, object] = {}

    payload = ServiceCreate(
        name="svc",
        carriers=[
            CarrierRef(carrier_type="VIRTUAL_MACHINE", carrier_id=vm_id),
            CarrierRef(carrier_type="BARE_METAL", carrier_id=host_id),
        ],
    )

    def do_create() -> None:
        try:
            service_service.create_service(session, payload)
            session.commit()
            outcome["create"] = "ok"
        except NotFoundError:
            session.rollback()
            outcome["create"] = "not_found"
        except Exception as exc:  # noqa: BLE001
            outcome["create"] = exc

    thread = threading.Thread(target=do_create)
    thread.start()
    try:
        time.sleep(1.5)
        assert thread.is_alive(), "任一载体被 FOR UPDATE 锁定时，登记必须阻塞"
    finally:
        blocker.commit()
        blocker.close()

    thread.join(timeout=15)
    assert not thread.is_alive()
    # 全序下 BARE_METAL 先取锁，VIRTUAL_MACHINE 未命中 → 整请求 404，无部分绑定。
    assert outcome["create"] == "not_found", outcome
    assert _scalar(conn, "SELECT count(*) FROM services") == 0
    assert _scalar(conn, "SELECT count(*) FROM service_carriers") == 0
    assert _scalar(conn, ORPHAN_VM_SQL) == 0
    session.close()


def test_ac47_deterministic_lock_order_no_deadlock(concurrency_env):
    """两笔并发登记以**相反请求顺序**给出同一对载体，最终均成功（共享锁不互斥，无死锁）。"""
    factory, conn = concurrency_env
    host_id = _insert_host(conn, "cluster-a")
    vm_id = _insert_vm(conn, host_id, "vm1")

    session_a: Session = factory()
    session_b: Session = factory()
    outcomes: dict[str, object] = {}

    def create(name: str, session: Session, carriers: list[CarrierRef], key: str) -> None:
        try:
            service_service.create_service(session, ServiceCreate(name=name, carriers=carriers))
            session.commit()
            outcomes[key] = "ok"
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            outcomes[key] = exc

    thread_a = threading.Thread(
        target=create,
        args=(
            "svc-a",
            session_a,
            [
                CarrierRef(carrier_type="BARE_METAL", carrier_id=host_id),
                CarrierRef(carrier_type="VIRTUAL_MACHINE", carrier_id=vm_id),
            ],
            "a",
        ),
    )
    thread_b = threading.Thread(
        target=create,
        args=(
            "svc-b",
            session_b,
            [
                CarrierRef(carrier_type="VIRTUAL_MACHINE", carrier_id=vm_id),
                CarrierRef(carrier_type="BARE_METAL", carrier_id=host_id),
            ],
            "b",
        ),
    )
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=20)
    thread_b.join(timeout=20)
    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    assert outcomes == {"a": "ok", "b": "ok"}, outcomes
    assert _scalar(conn, "SELECT count(*) FROM services") == 2
    assert _scalar(conn, AC49_SQL) == 0
    session_a.close()
    session_b.close()
