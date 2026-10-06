"""F002 数据库约束与行为测试（数据库设计 §10.1，真实 PostgreSQL）。

覆盖资源/网卡唯一、名称与枚举 CHECK、乐观锁、RESTRICT FK、复合 FK 同集群、
F005 表附加唯一约束与冗余 cluster_id 钉住。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import engine


def _insert_user(conn, username: str, role: str = "maintainer") -> int:
    return conn.execute(
        text(
            "INSERT INTO users (username, role, status) "
            "VALUES (:u, :r, 'enabled') RETURNING id"
        ),
        {"u": username, "r": role},
    ).scalar_one()


def _insert_cluster(conn, code: str, name: str | None = None) -> int:
    return conn.execute(
        text(
            "INSERT INTO clusters (code, name, purpose) "
            "VALUES (:c, :n, 'p') RETURNING id"
        ),
        {"c": code, "n": name or code},
    ).scalar_one()


def _insert_segment(conn, cluster_id: int, name: str, cidr: str) -> int:
    return conn.execute(
        text(
            "INSERT INTO network_segments "
            "(cluster_id, name, cidr, purpose, technology) "
            "VALUES (:c, :n, :cid, 'p', 't') RETURNING id"
        ),
        {"c": cluster_id, "n": name, "cid": cidr},
    ).scalar_one()


def _insert_resource(
    conn,
    cluster_id: int,
    name: str,
    *,
    resource_type: str = "bare_metal",
    status: str | None = None,
    status_updated_by: int | None = None,
) -> int:
    return conn.execute(
        text(
            "INSERT INTO resources "
            "(cluster_id, name, resource_type, status, status_updated_by) "
            "VALUES (:c, :n, :t, COALESCE(:s, 'ALLOC'), :by) RETURNING id"
        ),
        {
            "c": cluster_id,
            "n": name,
            "t": resource_type,
            "s": status,
            "by": status_updated_by,
        },
    ).scalar_one()


def _insert_interface(
    conn,
    resource_id: int,
    cluster_id: int,
    name: str,
    segment_id: int | None = None,
) -> int:
    return conn.execute(
        text(
            "INSERT INTO network_interfaces "
            "(resource_id, cluster_id, name, segment_id) "
            "VALUES (:r, :c, :n, :s) RETURNING id"
        ),
        {"r": resource_id, "c": cluster_id, "n": name, "s": segment_id},
    ).scalar_one()


def _constraint_name(exc: IntegrityError) -> str:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", "") or ""


# --- resources --------------------------------------------------------------


def test_resource_name_unique_case_sensitive_per_cluster() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "R1")
        c2 = _insert_cluster(conn, "R2")
        _insert_resource(conn, c1, "ABC")
        _insert_resource(conn, c1, "abc")  # 区分大小写，允许
        _insert_resource(conn, c2, "ABC")  # 跨集群允许
        # 裸金属与 VM 统一判重：先建 VM 同名仍拒绝。
        _insert_resource(conn, c1, "vm1", resource_type="bare_metal")
        _insert_resource(conn, c1, "vm2", resource_type="virtual_machine")

    with pytest.raises(IntegrityError) as dupe:
        with engine.begin() as conn:
            _insert_resource(conn, c1, "ABC")
    assert "uq_resources_cluster_name" in _constraint_name(dupe.value)

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_resource(conn, c1, "vm2", resource_type="virtual_machine")


def test_resource_name_and_enum_checks() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "R3")

    for bad in [" x", "x ", "   ", "x" * 129]:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert_resource(conn, c1, bad)

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_resource(conn, c1, "badtype", resource_type="container")

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_resource(conn, c1, "badstatus", status="BUSY")


def test_resource_status_default_alloc() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "R4")
        rid = _insert_resource(conn, c1, "defstatus")
        assert (
            conn.execute(
                text("SELECT status FROM resources WHERE id=:i"), {"i": rid}
            ).scalar_one()
            == "ALLOC"
        )


def test_resource_version_check_and_optimistic_update() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "R5")
        rid = _insert_resource(conn, c1, "vers")

        stale = conn.execute(
            text(
                "UPDATE resources SET version=version+1 "
                "WHERE id=:i AND version=:v"
            ),
            {"i": rid, "v": 99},
        )
        assert stale.rowcount == 0

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE resources SET version=0 WHERE id=:i"), {"i": rid}
            )


def test_resource_cluster_restrict_fk() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "R6")
        _insert_resource(conn, c1, "child")

    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM clusters WHERE id=:i"), {"i": c1})
    assert "fk_resources_cluster" in _constraint_name(exc.value)


def test_status_updated_by_set_null_on_user_delete() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "R7")
        uid = _insert_user(conn, "statususer")
        rid = _insert_resource(conn, c1, "hasactor", status_updated_by=uid)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id=:i"), {"i": uid})
        row = conn.execute(
            text("SELECT status_updated_by FROM resources WHERE id=:i"), {"i": rid}
        ).scalar_one()
        assert row is None


def test_resource_id_cluster_unique_exists() -> None:
    """复合 FK 目标 uq_resources_id_cluster 存在。"""
    with engine.begin() as conn:
        exists = conn.scalar(
            text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname='uq_resources_id_cluster'"
            )
        )
        assert exists == 1


# --- network_interfaces -----------------------------------------------------


def test_interface_resource_name_unique() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "N1")
        r1 = _insert_resource(conn, c1, "r1")
        r2 = _insert_resource(conn, c1, "r2")
        _insert_interface(conn, r1, c1, "eth0")

    # 不同资源同名允许。
    with engine.begin() as conn:
        _insert_interface(conn, r2, c1, "eth0")

    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            _insert_interface(conn, r1, c1, "eth0")
    assert "uq_network_interfaces_resource_name" in _constraint_name(exc.value)


def test_interface_name_checks() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "N2")
        r1 = _insert_resource(conn, c1, "r1")

    for bad in [" x", "x ", "   ", "x" * 129]:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert_interface(conn, r1, c1, bad)


def test_interface_resource_restrict_fk() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "N3")
        r1 = _insert_resource(conn, c1, "r1")
        _insert_interface(conn, r1, c1, "eth0")

    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM resources WHERE id=:i"), {"i": r1})
    assert "fk_network_interfaces_resource" in _constraint_name(exc.value)


def test_interface_segment_restrict_fk() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "N4")
        r1 = _insert_resource(conn, c1, "r1")
        seg = _insert_segment(conn, c1, "seg", "10.0.0.0/24")
        _insert_interface(conn, r1, c1, "eth0", segment_id=seg)

    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM network_segments WHERE id=:i"), {"i": seg})
    assert "fk_network_interfaces_segment" in _constraint_name(exc.value)

    # 删除网卡后可删网段。
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM network_interfaces WHERE resource_id=:i"), {"i": r1}
        )
        assert conn.execute(
            text("DELETE FROM network_segments WHERE id=:i"), {"i": seg}
        ).rowcount == 1


def test_interface_composite_fk_enforces_same_cluster() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "N5")
        c2 = _insert_cluster(conn, "N6")
        r1 = _insert_resource(conn, c1, "r1")
        own_seg = _insert_segment(conn, c1, "own", "10.1.0.0/24")
        other_seg = _insert_segment(conn, c2, "other", "10.2.0.0/24")

        # 同集群网段通过。
        _insert_interface(conn, r1, c1, "eth0", segment_id=own_seg)
        # 未选网段通过（MATCH SIMPLE）。
        _insert_interface(conn, r1, c1, "eth1", segment_id=None)

    # 跨集群网段被复合 FK 拒绝。
    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            _insert_interface(conn, r1, c1, "eth2", segment_id=other_seg)
    assert "fk_network_interfaces_segment" in _constraint_name(exc.value)


def test_interface_cluster_column_pinned() -> None:
    """冗余 cluster_id 不得与所属资源集群不一致。"""
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "N7")
        c2 = _insert_cluster(conn, "N8")
        r1 = _insert_resource(conn, c1, "r1")

    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            _insert_interface(conn, r1, c2, "eth0")
    assert "fk_network_interfaces_resource" in _constraint_name(exc.value)


def test_network_segments_id_cluster_unique_exists() -> None:
    """F005 表上的附加唯一约束存在且可用于复合 FK。"""
    with engine.begin() as conn:
        exists = conn.scalar(
            text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname='uq_network_segments_id_cluster'"
            )
        )
        assert exists == 1