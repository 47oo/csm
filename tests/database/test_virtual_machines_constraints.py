"""F006 VirtualMachine 数据库约束断言（V-9 ~ V-11，绕过应用层直连 PostgreSQL）。

证明唯一性 / FK / NOT NULL / NULL 语义由数据库保证，而非应用逻辑：

- V-9：直连插入重复活跃 ``name`` → ``23505``；指向不存在宿主的行 → ``23503``；
- V-10：soft delete 后同一 ``name`` 可再次插入活跃行（R-DELETE-006）；
- V-11：六个可选列缺省为 NULL；中文 / 空串 / 首尾空白原样存取。
"""

from __future__ import annotations

import psycopg
import pytest

CHINESE_NAME = "虚拟机-甲"


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
# V-9：活跃 name 唯一（大小写敏感、全局）；无效宿主 → 23503
# --------------------------------------------------------------------------- #
def test_v9_case_sensitive_global_name_uniqueness(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host_a = _new_bare_metal(raw_conn, cluster, "n1")
    host_b = _new_bare_metal(raw_conn, cluster, "n2")

    raw_conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, 'vm1')", (host_a,)
    )
    # 大小写不同 → 允许共存
    raw_conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, 'VM1')", (host_a,)
    )
    # 跨宿主同名 → 23505（全局唯一）
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, 'vm1')", (host_b,)
        )
    assert excinfo.value.sqlstate == "23505"

    active = raw_conn.execute(
        "SELECT count(*) FROM virtual_machines WHERE deleted_at IS NULL"
    ).fetchone()[0]
    assert active == 2


def test_v9_invalid_bare_metal_id_rejected_with_23503(raw_conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (999999999, 'vm1')"
        )
    assert excinfo.value.sqlstate == "23503"


# --------------------------------------------------------------------------- #
# V-10 / R-DELETE-006：软删释放唯一性
# --------------------------------------------------------------------------- #
def test_v10_soft_deleted_name_can_be_recreated(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host_a = _new_bare_metal(raw_conn, cluster, "n1")
    host_b = _new_bare_metal(raw_conn, cluster, "n2")

    raw_conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, 'vm1')", (host_a,)
    )
    raw_conn.execute(
        "UPDATE virtual_machines SET deleted_at = now() WHERE name = 'vm1' AND deleted_at IS NULL"
    )
    # 已删不占唯一性 → 可在任意宿主重建同名
    raw_conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, 'vm1')", (host_b,)
    )

    total = raw_conn.execute("SELECT count(*) FROM virtual_machines WHERE name = 'vm1'").fetchone()[
        0
    ]
    active = raw_conn.execute(
        "SELECT count(*) FROM virtual_machines WHERE name = 'vm1' AND deleted_at IS NULL"
    ).fetchone()[0]
    assert total == 2
    assert active == 1


def test_v10_not_null_name_rejected_with_23502(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    with pytest.raises(psycopg.errors.NotNullViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, NULL)", (host,)
        )
    assert excinfo.value.sqlstate == "23502"


# --------------------------------------------------------------------------- #
# V-11：可选列缺省 NULL；中文 / 空串 / 首尾空白原样存取
# --------------------------------------------------------------------------- #
def test_v11_optional_columns_default_to_null(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    row = raw_conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, 'vm1') "
        "RETURNING cpu, memory, disk, os, hypervisor, owner",
        (host,),
    ).fetchone()
    assert row == (None, None, None, None, None, None)


def test_v11_chinese_name_roundtrip(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    raw_conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, %s)",
        (host, CHINESE_NAME),
    )
    fetched = raw_conn.execute(
        "SELECT name FROM virtual_machines WHERE name = %s AND deleted_at IS NULL",
        (CHINESE_NAME,),
    ).fetchone()
    assert fetched is not None
    assert fetched[0] == CHINESE_NAME


@pytest.mark.parametrize("name", ["", "  padded  ", "has/slash"])
def test_v11_name_is_stored_verbatim(raw_conn, name):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    raw_conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, %s)",
        (host, name),
    )
    fetched = raw_conn.execute(
        "SELECT name FROM virtual_machines WHERE bare_metal_id = %s AND deleted_at IS NULL",
        (host,),
    ).fetchone()[0]
    assert fetched == name
