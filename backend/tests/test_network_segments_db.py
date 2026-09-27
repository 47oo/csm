"""F005 数据库约束测试（数据库设计 §10.1，真实 PostgreSQL）。

覆盖同集群 name/cidr_key 唯一、生成列、CHECK 护栏、RESTRICT FK 与保留地址可真实删除。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import engine


def _insert_cluster(conn, code: str, name: str) -> int:
    return conn.execute(
        text(
            "INSERT INTO clusters (code, name, purpose) "
            "VALUES (:c, :n, 'p') RETURNING id"
        ),
        {"c": code, "n": name},
    ).scalar_one()


def _insert_segment(
    conn,
    cluster_id: int,
    name: str,
    cidr: str,
    *,
    purpose: str = "p",
    technology: str = "t",
    vlan=None,
    gateway=None,
    auto_start=None,
    auto_end=None,
) -> int:
    return conn.execute(
        text(
            "INSERT INTO network_segments "
            "(cluster_id, name, cidr, purpose, technology, vlan, gateway, "
            " auto_alloc_start, auto_alloc_end) "
            "VALUES (:cid, :n, :c, :p, :t, :v, :g, :s, :e) RETURNING id"
        ),
        {
            "cid": cluster_id,
            "n": name,
            "c": cidr,
            "p": purpose,
            "t": technology,
            "v": vlan,
            "g": gateway,
            "s": auto_start,
            "e": auto_end,
        },
    ).scalar_one()


def _insert_reserved(conn, segment_id: int, start: str, end: str) -> int:
    return conn.execute(
        text(
            "INSERT INTO segment_reserved_addresses (segment_id, start_ip, end_ip) "
            "VALUES (:s, :a, :b) RETURNING id"
        ),
        {"s": segment_id, "a": start, "b": end},
    ).scalar_one()


def test_name_unique_case_sensitive_per_cluster() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "D1", "D1")
        c2 = _insert_cluster(conn, "D2", "D2")
        _insert_segment(conn, c1, "ABC", "10.0.0.0/24")
        _insert_segment(conn, c1, "abc", "10.0.1.0/24")  # 区分大小写，允许
        _insert_segment(conn, c2, "ABC", "10.0.0.0/24")  # 跨集群允许

    # 同集群同名拒绝。
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_segment(conn, c1, "ABC", "10.0.2.0/24")


def test_cidr_key_generated_and_unique_per_cluster() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "E1", "E1")
        c2 = _insert_cluster(conn, "E2", "E2")
        seg = _insert_segment(conn, c1, "n1", "10.1.0.0/24")
        assert (
            conn.execute(
                text("SELECT cidr_key FROM network_segments WHERE id=:i"),
                {"i": seg},
            ).scalar_one()
            == "10.1.0.0/24"
        )
        # 跨集群同 CIDR 允许。
        _insert_segment(conn, c2, "n2", "10.1.0.0/24")

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_segment(conn, c1, "n3", "10.1.0.0/24")


def test_name_and_purpose_checks() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "F1", "F1")

    for bad in [" x", "x ", "   ", "x" * 129]:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert_segment(conn, c1, bad, "10.2.0.0/24")

    for bad in ["", "   ", "x" * 201]:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert_segment(
                    conn, c1, "ok", "10.2.0.0/24", purpose=bad
                )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_segment(
                conn, c1, "ok2", "10.2.1.0/24", technology="x" * 101
            )


def test_cidr_format_check() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "G1", "G1")

    for bad in ["2001:db8::/32", "not-a-cidr", "10.0.0.0/33", "010.0.0.0/24"]:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert_segment(conn, c1, "c", bad)

    # 合法 CIDR 通过。
    with engine.begin() as conn:
        _insert_segment(conn, c1, "good", "0.0.0.0/0")


def test_vlan_gateway_auto_checks() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "H1", "H1")

    for bad in [0, 4095, -1]:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert_segment(conn, c1, f"v{bad}", "10.3.0.0/24", vlan=bad)

    with engine.begin() as conn:
        _insert_segment(conn, c1, "v-ok", "10.3.1.0/24", vlan=1)
        _insert_segment(conn, c1, "v-null", "10.3.2.0/24", vlan=None)

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_segment(conn, c1, "g-bad", "10.3.3.0/24", gateway="not-ip")

    # 自动范围仅一端非空 → 拒绝。
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_segment(
                conn, c1, "a-one", "10.3.4.0/24", auto_start="10.3.4.10"
            )
    # 非法地址 → 拒绝。
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_segment(
                conn,
                c1,
                "a-bad",
                "10.3.5.0/24",
                auto_start="bad",
                auto_end="10.3.5.20",
            )

    with engine.begin() as conn:
        _insert_segment(
            conn,
            c1,
            "a-ok",
            "10.3.6.0/24",
            auto_start="10.3.6.10",
            auto_end="10.3.6.20",
        )


def test_version_check_and_optimistic_update() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "I1", "I1")
        seg = _insert_segment(conn, c1, "vers", "10.4.0.0/24")

        stale = conn.execute(
            text(
                "UPDATE network_segments SET version=version+1 "
                "WHERE id=:i AND version=:v"
            ),
            {"i": seg, "v": 99},
        )
        assert stale.rowcount == 0

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE network_segments SET version=0 WHERE id=:i"),
                {"i": seg},
            )


def test_cluster_restrict_fk() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "J1", "J1")
        _insert_segment(conn, c1, "child", "10.5.0.0/24")

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM clusters WHERE id=:i"), {"i": c1})


def test_reserved_restrict_fk_and_real_delete() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "K1", "K1")
        seg = _insert_segment(conn, c1, "seg", "10.6.0.0/24")
        rid = _insert_reserved(conn, seg, "10.6.0.100", "10.6.0.110")

    # 有保留地址时网段不可删（RESTRICT）。
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM network_segments WHERE id=:i"), {"i": seg})

    # 保留地址可真实删行（无 append-only 触发器）。
    with engine.begin() as conn:
        assert conn.execute(
            text("DELETE FROM segment_reserved_addresses WHERE id=:i"), {"i": rid}
        ).rowcount == 1
        assert conn.execute(
            text("DELETE FROM network_segments WHERE id=:i"), {"i": seg}
        ).rowcount == 1


def test_reserved_ip_format_checks() -> None:
    with engine.begin() as conn:
        c1 = _insert_cluster(conn, "L1", "L1")
        seg = _insert_segment(conn, c1, "seg", "10.7.0.0/24")

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_reserved(conn, seg, "bad", "10.7.0.1")
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_reserved(conn, seg, "10.7.0.1", "10.7.0.999")

    # 单地址 start == end 合法。
    with engine.begin() as conn:
        _insert_reserved(conn, seg, "10.7.0.5", "10.7.0.5")