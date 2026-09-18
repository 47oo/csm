"""F007 Container 数据库约束断言（绕过应用层直连 PostgreSQL，AC-15 / AC-17 / AC-18 /
AC-19 / AC-11 / 23514 / 23503）。

证明「恰好一个多态载体」「载体内活跃 name 唯一（大小写敏感、软删释放）」「参照完整性
RESTRICT」由数据库保证，而非应用逻辑（ADR-0002 / ``docs/database/f007-container-migration.md``
§7）。
"""

from __future__ import annotations

import psycopg
import pytest


def _new_cluster(raw_conn, name: str) -> int:
    return raw_conn.execute(
        "INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()[0]


def _new_bare_metal(raw_conn, cluster_id: int, hostname: str) -> int:
    return raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, %s) RETURNING id",
        (cluster_id, hostname),
    ).fetchone()[0]


def _new_virtual_machine(raw_conn, bare_metal_id: int, name: str) -> int:
    return raw_conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, %s) RETURNING id",
        (bare_metal_id, name),
    ).fetchone()[0]


def _insert_on_bare_metal(raw_conn, bare_metal_id: int, name: str) -> int:
    return raw_conn.execute(
        "INSERT INTO containers (bare_metal_id, name) VALUES (%s, %s) RETURNING id",
        (bare_metal_id, name),
    ).fetchone()[0]


def _insert_on_vm(raw_conn, virtual_machine_id: int, name: str) -> int:
    return raw_conn.execute(
        "INSERT INTO containers (virtual_machine_id, name) VALUES (%s, %s) RETURNING id",
        (virtual_machine_id, name),
    ).fetchone()[0]


# --------------------------------------------------------------------------- #
# AC-18 / AC-12：同载体重复活跃 name → 23505（BM 与 VM 各一次）
# --------------------------------------------------------------------------- #
def test_duplicate_active_name_on_bare_metal_rejected_with_23505(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    _insert_on_bare_metal(raw_conn, host, "web")
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        _insert_on_bare_metal(raw_conn, host, "web")
    assert excinfo.value.sqlstate == "23505"


def test_duplicate_active_name_on_virtual_machine_rejected_with_23505(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    _insert_on_vm(raw_conn, vm, "web")
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        _insert_on_vm(raw_conn, vm, "web")
    assert excinfo.value.sqlstate == "23505"


# --------------------------------------------------------------------------- #
# AC-15：跨载体类型同数值 id 同名 → 成功（本设计的核心不变式）
# --------------------------------------------------------------------------- #
def test_cross_carrier_type_same_numeric_id_same_name_succeeds(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    assert host == vm, "前置条件：两表首个 id 数值相等（各自独立序列）"

    bm_container = _insert_on_bare_metal(raw_conn, host, "web")
    vm_container = _insert_on_vm(raw_conn, vm, "web")
    assert bm_container != vm_container

    active = raw_conn.execute(
        "SELECT count(*) FROM containers WHERE name = 'web' AND deleted_at IS NULL"
    ).fetchone()[0]
    assert active == 2


# --------------------------------------------------------------------------- #
# AC-13 / AC-14：不同载体可重名（跨类型 / 同类型不同 id）
# --------------------------------------------------------------------------- #
def test_same_type_different_carriers_same_name_succeeds(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host_a = _new_bare_metal(raw_conn, cluster, "n1")
    host_b = _new_bare_metal(raw_conn, cluster, "n2")
    _insert_on_bare_metal(raw_conn, host_a, "web")
    _insert_on_bare_metal(raw_conn, host_b, "web")
    active = raw_conn.execute(
        "SELECT count(*) FROM containers WHERE name = 'web' AND deleted_at IS NULL"
    ).fetchone()[0]
    assert active == 2


def test_cross_type_different_carriers_same_name_succeeds(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    _insert_on_bare_metal(raw_conn, host, "web")
    _insert_on_vm(raw_conn, vm, "web")
    assert raw_conn.execute("SELECT count(*) FROM containers").fetchone()[0] == 2


# --------------------------------------------------------------------------- #
# AC-17：大小写敏感共存
# --------------------------------------------------------------------------- #
def test_case_sensitive_names_coexist(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    _insert_on_bare_metal(raw_conn, host, "web")
    _insert_on_bare_metal(raw_conn, host, "WEB")
    active = raw_conn.execute(
        "SELECT count(*) FROM containers WHERE deleted_at IS NULL"
    ).fetchone()[0]
    assert active == 2


# --------------------------------------------------------------------------- #
# AC-11：空串 / 首尾空白 name 不被拒绝（未定义约束不实现）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["", "  padded  ", "has/slash"])
def test_undefined_name_constraints_not_enforced_in_db(raw_conn, name):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    _insert_on_bare_metal(raw_conn, host, name)
    fetched = raw_conn.execute(
        "SELECT name FROM containers WHERE bare_metal_id = %s AND deleted_at IS NULL",
        (host,),
    ).fetchone()[0]
    assert fetched == name


# --------------------------------------------------------------------------- #
# AC-19 / R-DELETE-006：软删释放唯一性；旧行 deleted_at 未被改写
# --------------------------------------------------------------------------- #
def test_soft_delete_releases_name_on_same_carrier(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    container = _insert_on_bare_metal(raw_conn, host, "web")
    raw_conn.execute("UPDATE containers SET deleted_at = now() WHERE id = %s", (container,))
    deleted_at_after = raw_conn.execute(
        "SELECT deleted_at FROM containers WHERE id = %s", (container,)
    ).fetchone()[0]

    recreated = _insert_on_bare_metal(raw_conn, host, "web")
    assert recreated != container

    total = raw_conn.execute("SELECT count(*) FROM containers WHERE name = 'web'").fetchone()[0]
    assert total == 2
    assert (
        raw_conn.execute(
            "SELECT deleted_at FROM containers WHERE id = %s", (container,)
        ).fetchone()[0]
        == deleted_at_after
    )


# --------------------------------------------------------------------------- #
# AC-04 / AC-05：0 个载体 / 2 个载体 → 23514（CHECK 为最终权威）
# --------------------------------------------------------------------------- #
def test_zero_carriers_rejected_with_23514(raw_conn):
    with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        raw_conn.execute("INSERT INTO containers (name) VALUES ('web')")
    assert excinfo.value.sqlstate == "23514"


def test_two_carriers_rejected_with_23514(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO containers (bare_metal_id, virtual_machine_id, name) "
            "VALUES (%s, %s, 'web')",
            (host, vm),
        )
    assert excinfo.value.sqlstate == "23514"


# --------------------------------------------------------------------------- #
# AC-08 / RESTRICT：引用不存在载体 → 23503；物理删除有容器的载体 → 23503
# --------------------------------------------------------------------------- #
def test_invalid_carrier_id_rejected_with_23503(raw_conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        _insert_on_bare_metal(raw_conn, 999999999, "web")
    assert excinfo.value.sqlstate == "23503"

    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        _insert_on_vm(raw_conn, 999999999, "web")
    assert excinfo.value.sqlstate == "23503"


def test_physical_delete_of_carrier_with_container_rejected_with_23503(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    _insert_on_bare_metal(raw_conn, host, "web-bm")
    _insert_on_vm(raw_conn, vm, "web-vm")

    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        raw_conn.execute("DELETE FROM virtual_machines WHERE id = %s", (vm,))
    assert excinfo.value.sqlstate == "23503"

    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        raw_conn.execute("DELETE FROM bare_metals WHERE id = %s", (host,))
    assert excinfo.value.sqlstate == "23503"


# --------------------------------------------------------------------------- #
# 载体列结构性 NULL：每行恰一列非空
# --------------------------------------------------------------------------- #
def test_active_rows_have_exactly_one_carrier_column(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    _insert_on_bare_metal(raw_conn, host, "web-bm")
    _insert_on_vm(raw_conn, vm, "web-vm")
    rows = raw_conn.execute("SELECT bare_metal_id, virtual_machine_id FROM containers").fetchall()
    assert len(rows) == 2
    for bare_metal_id, virtual_machine_id in rows:
        assert (bare_metal_id is None) != (virtual_machine_id is None)
