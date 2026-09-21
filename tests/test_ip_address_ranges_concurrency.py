"""F020 IPAddressRange 并发 / 锁序测试（V-21 / V-22，真实 PostgreSQL）。

使用真实 SQLAlchemy 会话直接驱动服务函数，在提交前精确控制事务持锁时刻：

- 创建范围段对父 Cluster 行取 ``FOR SHARE``，与 Cluster 删除的 ``FOR UPDATE`` 互斥；
- 同 Cluster 两条重叠范围段的第二条由排它约束拒绝（``23P01``）。

两种交错结束后，不变式「活跃范围段挂已软删 Cluster」与「同 Cluster 活跃范围重叠」
恒为 **0**。
"""

from __future__ import annotations

import threading
import time

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.clusters import service as cluster_service
from app.common.errors import ConflictError, NotFoundError
from app.ip_address_ranges import service as range_service
from app.ip_address_ranges.schemas import IpAddressRangeCreate
from tests.database.helpers import raw_connection_dsn, upgrade_to_head

OVERLAP_QUERY = """
SELECT a.id AS a_id, b.id AS b_id
FROM ip_address_ranges a
JOIN ip_address_ranges b
  ON a.cluster_id = b.cluster_id AND a.id < b.id
 AND a.deleted_at IS NULL AND b.deleted_at IS NULL
 AND a.start_ip <= b.end_ip AND a.end_ip >= b.start_ip
"""

ORPHAN_QUERY = """
SELECT count(*) FROM ip_address_ranges r
JOIN clusters c ON c.id = r.cluster_id
WHERE r.deleted_at IS NULL AND c.deleted_at IS NOT NULL
"""


@pytest.fixture
def concurrency_env(database_url):
    upgrade_to_head(database_url)
    engine = create_engine(database_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with psycopg.connect(raw_connection_dsn(database_url)) as conn:
        conn.autocommit = True
        yield factory, conn
    engine.dispose()


def _scalar(conn: psycopg.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


def _insert_cluster(conn: psycopg.Connection, name: str) -> int:
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[
        0
    ]


def _payload(cluster_id: int, start_ip: str, end_ip: str) -> IpAddressRangeCreate:
    return IpAddressRangeCreate(cluster_id=cluster_id, start_ip=start_ip, end_ip=end_ip)


# --------------------------------------------------------------------------- #
# V-21：登记范围段 × 删除其 Cluster，恰有一个成功；V-18 = 0
# --------------------------------------------------------------------------- #
def test_v21_create_commits_first_delete_conflicts(concurrency_env):
    factory, conn = concurrency_env
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
        except Exception as exc:  # noqa: BLE001
            outcome["delete"] = exc

    try:
        range_service.create_ip_address_range(
            create_session, _payload(cluster_id, "10.0.0.1", "10.0.0.10")
        )
        thread = threading.Thread(target=do_delete)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "登记持有 Cluster 行 FOR SHARE 时，删除必须阻塞"

        create_session.commit()
        create_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["delete"] == "conflict", outcome
        assert (
            conn.execute("SELECT deleted_at FROM clusters WHERE id=%s", (cluster_id,)).fetchone()[0]
            is None
        )
        assert _scalar(conn, ORPHAN_QUERY) == 0
        assert _scalar(conn, "SELECT count(*) FROM ip_address_ranges") == 1
    finally:
        delete_session.close()


def test_v21_delete_commits_first_create_rejected(concurrency_env):
    factory, conn = concurrency_env
    cluster_id = _insert_cluster(conn, "cluster-a")

    create_session: Session = factory()
    delete_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_create() -> None:
        try:
            range_service.create_ip_address_range(
                create_session, _payload(cluster_id, "10.0.0.1", "10.0.0.10")
            )
            create_session.commit()
            outcome["create"] = "ok"
        except NotFoundError:
            create_session.rollback()
            outcome["create"] = "not_found"
        except Exception as exc:  # noqa: BLE001
            outcome["create"] = exc

    try:
        cluster_service.delete_cluster(delete_session, cluster_id)
        thread = threading.Thread(target=do_create)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "删除持有 Cluster 行 FOR UPDATE 时，登记必须阻塞"

        delete_session.commit()
        delete_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["create"] == "not_found", outcome
        assert _scalar(conn, "SELECT count(*) FROM ip_address_ranges") == 0
        assert _scalar(conn, ORPHAN_QUERY) == 0
    finally:
        create_session.close()


# --------------------------------------------------------------------------- #
# V-22：同 Cluster 两条重叠范围段，至多一条成功；V-17 = 0
# --------------------------------------------------------------------------- #
def test_v22_concurrent_overlapping_ranges_at_most_one_succeeds(concurrency_env):
    factory, conn = concurrency_env
    cluster_id = _insert_cluster(conn, "cluster-a")

    first_session: Session = factory()
    second_session: Session = factory()
    outcome: dict[str, object] = {}

    def do_second_create() -> None:
        try:
            range_service.create_ip_address_range(
                second_session, _payload(cluster_id, "10.0.0.5", "10.0.0.25")
            )
            second_session.commit()
            outcome["second"] = "ok"
        except (ConflictError, IntegrityError) as exc:
            second_session.rollback()
            outcome["second"] = exc
        except Exception as exc:  # noqa: BLE001
            outcome["second"] = exc

    try:
        # session 1 先写但尚未提交（持有 EXCLUDE 索引项与父行共享锁）。
        range_service.create_ip_address_range(
            first_session, _payload(cluster_id, "10.0.0.1", "10.0.0.20")
        )
        thread = threading.Thread(target=do_second_create)
        thread.start()
        time.sleep(1.5)
        assert thread.is_alive(), "第二条重叠范围必须阻塞在排它约束上"

        first_session.commit()
        first_session.close()
        thread.join(timeout=15)
        assert not thread.is_alive()

        assert outcome["second"] != "ok", outcome
        failure = outcome["second"]
        if isinstance(failure, IntegrityError):
            assert "23P01" in str(failure.orig) or getattr(failure.orig, "sqlstate", "") == "23P01"
        else:
            assert isinstance(failure, ConflictError), outcome

        assert _scalar(conn, "SELECT count(*) FROM ip_address_ranges WHERE deleted_at IS NULL") == 1
        assert conn.execute(OVERLAP_QUERY).fetchall() == []
    finally:
        second_session.close()
