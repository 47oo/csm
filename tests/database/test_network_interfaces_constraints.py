"""F004 NetworkInterface 数据库约束断言（V-10、V-11，绕过应用层直连 PostgreSQL）。

证明枚举 CHECK / FK / NOT NULL / 无唯一性由数据库保证，而非应用逻辑：

- V-10：直连插入非法 ``technology_type`` / ``purpose`` → ``23514``；
  插入指向不存在宿主的行 → ``23503``；
- V-11：直连插入同宿主同名两行 → **成功**（无唯一性约束）；
- ``name`` 中文 / 空串 / 首尾空白原样存取。
"""

from __future__ import annotations

import psycopg
import pytest

CHINESE_NAME = "网卡-甲"


def _new_cluster(raw_conn, name: str) -> int:
    return raw_conn.execute(
        "INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()[0]


def _new_bare_metal(raw_conn, cluster_id: int, hostname: str) -> int:
    return raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, %s) RETURNING id",
        (cluster_id, hostname),
    ).fetchone()[0]


# --------------------------------------------------------------------------- #
# V-10：非法枚举 → 23514；无效宿主 → 23503
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "technology_type",
    ["FibreChannel", "ethernet", "Other ", "", None, "InfiniBand ", "OTHER"],
)
def test_v10_invalid_technology_type_rejected_with_23514(raw_conn, technology_type):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    # None → NOT NULL（23502）；其余非法值 → CHECK（23514）。两者都必须是 4xx，不得 5xx。
    with pytest.raises(psycopg.errors.IntegrityError) as excinfo:
        raw_conn.execute(
            "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
            "VALUES (%s, 'eth0', %s, 'Business')",
            (host, technology_type),
        )
    assert excinfo.value.sqlstate in ("23514", "23502")


@pytest.mark.parametrize(
    "purpose",
    ["mgmt", "business", "", None, "Data Transfer", "OTHER"],
)
def test_v10_invalid_purpose_rejected_with_23514(raw_conn, purpose):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    with pytest.raises(psycopg.errors.IntegrityError) as excinfo:
        raw_conn.execute(
            "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
            "VALUES (%s, 'eth0', 'Ethernet', %s)",
            (host, purpose),
        )
    assert excinfo.value.sqlstate in ("23514", "23502")


def test_v10_all_closed_enum_values_accepted(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    for tech in ("Ethernet", "InfiniBand", "RoCE", "Other"):
        raw_conn.execute(
            "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
            "VALUES (%s, %s, %s, 'Business')",
            (host, f"nic-{tech}", tech),
        )
    for purpose in (
        "BMC",
        "Management",
        "Business",
        "Compute",
        "Storage",
        "DataTransfer",
        "Other",
    ):
        raw_conn.execute(
            "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
            "VALUES (%s, %s, 'Ethernet', %s)",
            (host, f"nic-{purpose}", purpose),
        )
    total = raw_conn.execute(
        "SELECT count(*) FROM network_interfaces WHERE deleted_at IS NULL"
    ).fetchone()[0]
    assert total == 11


def test_v10_invalid_bare_metal_id_rejected_with_23503(raw_conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
            "VALUES (999999999, 'eth0', 'Ethernet', 'Business')"
        )
    assert excinfo.value.sqlstate == "23503"


def test_v10_not_null_name_rejected_with_23502(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    with pytest.raises(psycopg.errors.NotNullViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
            "VALUES (%s, NULL, 'Ethernet', 'Business')",
            (host,),
        )
    assert excinfo.value.sqlstate == "23502"


# --------------------------------------------------------------------------- #
# V-11 / G-4：同宿主同名两行均可插入（无唯一性约束）
# --------------------------------------------------------------------------- #
def test_v11_same_host_same_name_two_rows_succeed(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    first = raw_conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
        "VALUES (%s, 'eth0', 'Ethernet', 'Business') RETURNING id",
        (host,),
    ).fetchone()[0]
    second = raw_conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
        "VALUES (%s, 'eth0', 'Ethernet', 'Business') RETURNING id",
        (host,),
    ).fetchone()[0]
    assert first != second


# --------------------------------------------------------------------------- #
# V-11：name 原样存取（中文 / 空串 / 首尾空白 / "/" / 点号 / 连字符）
# --------------------------------------------------------------------------- #
def test_v11_chinese_name_roundtrip(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    raw_conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
        "VALUES (%s, %s, 'Ethernet', 'Business')",
        (host, CHINESE_NAME),
    )
    fetched = raw_conn.execute(
        "SELECT name FROM network_interfaces WHERE name = %s AND deleted_at IS NULL",
        (CHINESE_NAME,),
    ).fetchone()
    assert fetched is not None
    assert fetched[0] == CHINESE_NAME


@pytest.mark.parametrize("name", ["", "  padded  ", "has/slash", "eth0.100", "ib-0"])
def test_v11_name_is_stored_verbatim(raw_conn, name):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    raw_conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
        "VALUES (%s, %s, 'Ethernet', 'Business')",
        (host, name),
    )
    fetched = raw_conn.execute(
        "SELECT name FROM network_interfaces WHERE bare_metal_id = %s AND deleted_at IS NULL",
        (host,),
    ).fetchone()[0]
    assert fetched == name
