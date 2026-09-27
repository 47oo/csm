"""F006 数据库约束测试（数据库设计 §10.1，真实 PostgreSQL）。

覆盖同集群唯一（可延迟）、CHECK、RESTRICT FK、复合归属 FK、管理 IP 归属/删除
保护、F002 表附加唯一约束与幂等初始化。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.bootstrap import create_schema
from app.db import engine


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


def _insert_resource(conn, cluster_id: int, name: str) -> int:
    return conn.execute(
        text(
            "INSERT INTO resources (cluster_id, name, resource_type) "
            "VALUES (:c, :n, 'bare_metal') RETURNING id"
        ),
        {"c": cluster_id, "n": name},
    ).scalar_one()


def _insert_interface(
    conn, resource_id: int, cluster_id: int, name: str, segment_id: int | None
) -> int:
    return conn.execute(
        text(
            "INSERT INTO network_interfaces "
            "(resource_id, cluster_id, name, segment_id) "
            "VALUES (:r, :c, :n, :s) RETURNING id"
        ),
        {"r": resource_id, "c": cluster_id, "n": name, "s": segment_id},
    ).scalar_one()


def _insert_ip(
    conn,
    interface_id: int,
    resource_id: int,
    cluster_id: int,
    segment_id: int,
    ip: str,
) -> int:
    return conn.execute(
        text(
            "INSERT INTO ip_addresses "
            "(interface_id, resource_id, cluster_id, segment_id, ip) "
            "VALUES (:i, :r, :c, :s, :ip) RETURNING id"
        ),
        {
            "i": interface_id,
            "r": resource_id,
            "c": cluster_id,
            "s": segment_id,
            "ip": ip,
        },
    ).scalar_one()


def _constraint_name(exc: IntegrityError) -> str:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", "") or ""


def test_unique_cluster_ip_and_cross_cluster_reuse() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "F1")
        seg1 = _insert_segment(conn, c1, "s1", "10.0.0.0/24")
        r1 = _insert_resource(conn, c1, "r1")
        i1 = _insert_interface(conn, r1, c1, "eth0", seg1)
        ip_id = _insert_ip(conn, i1, r1, c1, seg1, "10.0.0.5")
        assert (
            conn.execute(
                text("SELECT ip_key FROM ip_addresses WHERE id=:i"), {"i": ip_id}
            ).scalar_one()
            == "10.0.0.5"
        )
        c2 = _insert_cluster(conn, "F2")
        seg2 = _insert_segment(conn, c2, "s2", "10.0.0.0/24")
        r2 = _insert_resource(conn, c2, "r2")
        i2 = _insert_interface(conn, r2, c2, "eth0", seg2)
        # 跨集群同地址允许。
        _insert_ip(conn, i2, r2, c2, seg2, "10.0.0.5")

def test_cluster_ip_unique_conflict_immediate() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "G1")
        seg = _insert_segment(conn, c1, "s", "10.1.0.0/24")
        r1 = _insert_resource(conn, c1, "r1")
        i1 = _insert_interface(conn, r1, c1, "eth0", seg)
        _insert_ip(conn, i1, r1, c1, seg, "10.1.0.5")

    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            _insert_ip(conn, i1, r1, c1, seg, "10.1.0.5")
    assert "uq_ip_addresses_cluster_ip" in _constraint_name(exc.value)


def test_delete_then_reinsert_and_deferrable_swap() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "G2")
        seg = _insert_segment(conn, c1, "s", "10.2.0.0/24")
        r1 = _insert_resource(conn, c1, "r1")
        i1 = _insert_interface(conn, r1, c1, "eth0", seg)
        ip1 = _insert_ip(conn, i1, r1, c1, seg, "10.2.0.5")

    # 真实删除后可复用同地址。
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ip_addresses WHERE id=:i"), {"i": ip1})
        _insert_ip(conn, i1, r1, c1, seg, "10.2.0.5")

    # deferrable：同事务内交换两个地址。
    with engine.begin() as conn:
        _insert_ip(conn, i1, r1, c1, seg, "10.2.0.6")
    with engine.begin() as conn:
        conn.execute(
            text("SET CONSTRAINTS uq_ip_addresses_cluster_ip DEFERRED")
        )
        conn.execute(
            text(
                "UPDATE ip_addresses SET ip='10.2.0.9' "
                "WHERE cluster_id=:c AND ip='10.2.0.6'"
            ),
            {"c": c1},
        )
        conn.execute(
            text(
                "UPDATE ip_addresses SET ip='10.2.0.6' "
                "WHERE cluster_id=:c AND ip='10.2.0.5'"
            ),
            {"c": c1},
        )
        conn.execute(
            text(
                "UPDATE ip_addresses SET ip='10.2.0.5' "
                "WHERE cluster_id=:c AND ip='10.2.0.9'"
            ),
            {"c": c1},
        )


def test_ip_format_check() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "G3")
        seg = _insert_segment(conn, c1, "s", "10.3.0.0/24")
        r1 = _insert_resource(conn, c1, "r1")
        i1 = _insert_interface(conn, r1, c1, "eth0", seg)

    for bad in ["2001:db8::1", "not-ip", "010.3.0.1", "10.3.0"]:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert_ip(conn, i1, r1, c1, seg, bad)


def test_interface_and_segment_restrict_fk() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "G4")
        seg = _insert_segment(conn, c1, "s", "10.4.0.0/24")
        r1 = _insert_resource(conn, c1, "r1")
        i1 = _insert_interface(conn, r1, c1, "eth0", seg)
        _insert_ip(conn, i1, r1, c1, seg, "10.4.0.5")

    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM network_interfaces WHERE id=:i"), {"i": i1}
            )
    assert "fk_ip_addresses_interface" in _constraint_name(exc.value)

    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM network_segments WHERE id=:i"), {"i": seg}
            )
    assert "fk_ip_addresses_segment" in _constraint_name(exc.value)


def test_interface_segment_composite_fk() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "G5")
        seg_a = _insert_segment(conn, c1, "a", "10.5.0.0/24")
        seg_b = _insert_segment(conn, c1, "b", "10.5.1.0/24")
        r1 = _insert_resource(conn, c1, "r1")
        i1 = _insert_interface(conn, r1, c1, "eth0", seg_a)

    # IP 的 segment_id 必须等于网卡所选网段。
    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            _insert_ip(conn, i1, r1, c1, seg_b, "10.5.1.5")
    assert "fk_ip_addresses_interface_segment" in _constraint_name(exc.value)

    # 网卡未选网段时不可插入 IP。
    with engine.begin() as conn:
        i2 = _insert_interface(conn, r1, c1, "eth1", None)
    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            _insert_ip(conn, i2, r1, c1, seg_a, "10.5.0.6")
    assert "fk_ip_addresses_interface_segment" in _constraint_name(exc.value)

    # 仍有 IP 时改网卡网段 → 23503。
    with engine.begin() as conn:
        _insert_ip(conn, i1, r1, c1, seg_a, "10.5.0.6")
    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE network_interfaces SET segment_id=:s WHERE id=:i"),
                {"s": seg_b, "i": i1},
            )
    assert "fk_ip_addresses_interface_segment" in _constraint_name(exc.value)


def test_redundant_columns_pinned() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "G6")
        c2 = _insert_cluster(conn, "G7")
        seg = _insert_segment(conn, c1, "s", "10.6.0.0/24")
        r1 = _insert_resource(conn, c1, "r1")
        r2 = _insert_resource(conn, c1, "r2")
        i1 = _insert_interface(conn, r1, c1, "eth0", seg)

    # resource_id 与网卡不符。
    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            _insert_ip(conn, i1, r2, c1, seg, "10.6.0.5")
    assert "fk_ip_addresses_interface_resource" in _constraint_name(exc.value)

    # cluster_id 与网卡不符。
    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            _insert_ip(conn, i1, r1, c2, seg, "10.6.0.5")
    assert "fk_ip_addresses_interface_resource" in _constraint_name(exc.value)


def test_management_ip_ownership_and_delete_protection() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "G8")
        seg = _insert_segment(conn, c1, "s", "10.8.0.0/24")
        r1 = _insert_resource(conn, c1, "r1")
        r2 = _insert_resource(conn, c1, "r2")
        i1 = _insert_interface(conn, r1, c1, "eth0", seg)
        ip1 = _insert_ip(conn, i1, r1, c1, seg, "10.8.0.5")

    # 本资源引用通过。
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE resources SET management_ip_id=:p WHERE id=:r"),
            {"p": ip1, "r": r1},
        )
        assert (
            conn.execute(
                text("SELECT management_ip_id FROM resources WHERE id=:r"),
                {"r": r1},
            ).scalar_one()
            == ip1
        )

    # 他资源引用被拒。
    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE resources SET management_ip_id=:p WHERE id=:r"),
                {"p": ip1, "r": r2},
            )
    assert "fk_resources_management_ip" in _constraint_name(exc.value)

    # 删除仍被引用的 IP 被拒。
    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM ip_addresses WHERE id=:p"), {"p": ip1})
    assert "fk_resources_management_ip" in _constraint_name(exc.value)

    # 先清空再删通过。
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE resources SET management_ip_id=NULL WHERE id=:r"),
            {"r": r1},
        )
        assert conn.execute(
            text("DELETE FROM ip_addresses WHERE id=:p"), {"p": ip1}
        ).rowcount == 1


def test_f002_attached_constraints_and_column_exist() -> None:
    with engine.begin() as conn:
        for name in (
            "uq_network_interfaces_id_segment",
            "uq_network_interfaces_id_resource_cluster",
            "uq_ip_addresses_cluster_ip",
            "uq_ip_addresses_resource_id",
            "fk_resources_management_ip",
        ):
            assert (
                conn.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint WHERE conname=:n"
                    ),
                    {"n": name},
                )
                == 1
            ), name
        # resources.management_ip_id 可空、默认 NULL。
        assert (
            conn.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name='resources' AND column_name='management_ip_id'"
                )
            )
            == "YES"
        )
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE indexname='ix_resources_management_ip_id'"
                )
            )
            == 1
        )


def test_create_schema_idempotent() -> None:
    create_schema(engine)
    create_schema(engine)
    with engine.begin() as conn:
        assert conn.scalar(
            text("SELECT count(*) FROM pg_constraint WHERE conname='uq_ip_addresses_cluster_ip'")
        ) == 1


def test_concurrent_same_address_only_one_succeeds() -> None:
    import threading

    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "H1")
        seg = _insert_segment(conn, c1, "s", "10.30.0.0/24")
        r1 = _insert_resource(conn, c1, "r1")
        i1 = _insert_interface(conn, r1, c1, "eth0", seg)

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            with engine.begin() as conn:
                barrier.wait(timeout=10)
                _insert_ip(conn, i1, r1, c1, seg, "10.30.0.5")
            outcome = "ok"
        except IntegrityError:
            outcome = "conflict"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["conflict", "ok"]