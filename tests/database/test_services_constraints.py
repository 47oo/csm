"""F008 Service 数据库约束断言（绕过应用层直连 PostgreSQL）。

证明「全局活跃 name 唯一（大小写敏感、软删释放）」「绑定集合语义（3 条 partial
unique）」「每绑定行恰一个载体（CHECK）」「参照完整性 RESTRICT」由数据库保证，而非
应用逻辑（ADR-0002 / ``docs/database/f008-service-migration.md`` §7）。
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


def _new_container(raw_conn, virtual_machine_id: int, name: str) -> int:
    return raw_conn.execute(
        "INSERT INTO containers (virtual_machine_id, name) VALUES (%s, %s) RETURNING id",
        (virtual_machine_id, name),
    ).fetchone()[0]


def _new_service(raw_conn, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return raw_conn.execute(
            "INSERT INTO services (name, deleted_at) VALUES (%s, now()) RETURNING id", (name,)
        ).fetchone()[0]
    return raw_conn.execute(
        "INSERT INTO services (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()[0]


def _bind_bm(raw_conn, service_id: int, bare_metal_id: int) -> int:
    return raw_conn.execute(
        "INSERT INTO service_carriers (service_id, bare_metal_id) VALUES (%s, %s) RETURNING id",
        (service_id, bare_metal_id),
    ).fetchone()[0]


def _bind_vm(raw_conn, service_id: int, virtual_machine_id: int) -> int:
    return raw_conn.execute(
        "INSERT INTO service_carriers (service_id, virtual_machine_id) "
        "VALUES (%s, %s) RETURNING id",
        (service_id, virtual_machine_id),
    ).fetchone()[0]


def _bind_container(raw_conn, service_id: int, container_id: int) -> int:
    return raw_conn.execute(
        "INSERT INTO service_carriers (service_id, container_id) VALUES (%s, %s) RETURNING id",
        (service_id, container_id),
    ).fetchone()[0]


# --------------------------------------------------------------------------- #
# 同一 Service 内重复绑定同一载体（三类型各一）→ 23505
# --------------------------------------------------------------------------- #
def test_duplicate_binding_same_bare_metal_rejected_with_23505(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    service = _new_service(raw_conn, "mon")
    _bind_bm(raw_conn, service, host)
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        _bind_bm(raw_conn, service, host)
    assert excinfo.value.sqlstate == "23505"


def test_duplicate_binding_same_virtual_machine_rejected_with_23505(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    service = _new_service(raw_conn, "mon")
    _bind_vm(raw_conn, service, vm)
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        _bind_vm(raw_conn, service, vm)
    assert excinfo.value.sqlstate == "23505"


def test_duplicate_binding_same_container_rejected_with_23505(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    container = _new_container(raw_conn, vm, "c1")
    service = _new_service(raw_conn, "mon")
    _bind_container(raw_conn, service, container)
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        _bind_container(raw_conn, service, container)
    assert excinfo.value.sqlstate == "23505"


# --------------------------------------------------------------------------- #
# 核心不变式：同一 Service 绑定三类型的**同数值 id** → 成功（3 partial unique 互不干扰）
# --------------------------------------------------------------------------- #
def test_same_service_three_carrier_types_same_numeric_id_succeeds(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    container = _new_container(raw_conn, vm, "c1")
    assert host == vm == container, "前置条件：三表首个 id 数值相等（各自独立序列）"

    service = _new_service(raw_conn, "mon")
    _bind_bm(raw_conn, service, host)
    _bind_vm(raw_conn, service, vm)
    _bind_container(raw_conn, service, container)
    assert (
        raw_conn.execute(
            "SELECT count(*) FROM service_carriers WHERE service_id=%s", (service,)
        ).fetchone()[0]
        == 3
    )


# --------------------------------------------------------------------------- #
# N:M 另一方向：不同 Service 绑定同一载体 → 成功
# --------------------------------------------------------------------------- #
def test_different_services_bind_same_carrier_succeeds(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    s1 = _new_service(raw_conn, "s1")
    s2 = _new_service(raw_conn, "s2")
    _bind_bm(raw_conn, s1, host)
    _bind_bm(raw_conn, s2, host)
    assert raw_conn.execute("SELECT count(*) FROM service_carriers").fetchone()[0] == 2


# --------------------------------------------------------------------------- #
# 23514：0 / 2 / 3 个载体列
# --------------------------------------------------------------------------- #
def test_zero_carriers_rejected_with_23514(raw_conn):
    service = _new_service(raw_conn, "mon")
    with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        raw_conn.execute("INSERT INTO service_carriers (service_id) VALUES (%s)", (service,))
    assert excinfo.value.sqlstate == "23514"


@pytest.mark.parametrize("pair", ["bm_vm", "bm_ct", "vm_ct"])
def test_two_carriers_rejected_with_23514(raw_conn, pair):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    container = _new_container(raw_conn, vm, "c1")
    service = _new_service(raw_conn, "mon")

    columns = {
        "bm_vm": ("bare_metal_id, virtual_machine_id", (host, vm)),
        "bm_ct": ("bare_metal_id, container_id", (host, container)),
        "vm_ct": ("virtual_machine_id, container_id", (vm, container)),
    }
    column_sql, values = columns[pair]
    with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        raw_conn.execute(
            f"INSERT INTO service_carriers (service_id, {column_sql}) VALUES (%s, %s, %s)",
            (service, *values),
        )
    assert excinfo.value.sqlstate == "23514"


def test_three_carriers_rejected_with_23514(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    container = _new_container(raw_conn, vm, "c1")
    service = _new_service(raw_conn, "mon")
    with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO service_carriers (service_id, bare_metal_id, virtual_machine_id, "
            "container_id) VALUES (%s, %s, %s, %s)",
            (service, host, vm, container),
        )
    assert excinfo.value.sqlstate == "23514"


# --------------------------------------------------------------------------- #
# name 全局唯一：23505；大小写敏感；软删释放
# --------------------------------------------------------------------------- #
def test_duplicate_active_name_rejected_with_23505(raw_conn):
    _new_service(raw_conn, "mon")
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        _new_service(raw_conn, "mon")
    assert excinfo.value.sqlstate == "23505"


def test_soft_deleted_name_does_not_occupy_uniqueness(raw_conn):
    first = _new_service(raw_conn, "mon", deleted=True)
    second = _new_service(raw_conn, "mon")
    assert first != second
    assert (
        raw_conn.execute(
            "SELECT count(*) FROM services WHERE name='mon' AND deleted_at IS NULL"
        ).fetchone()[0]
        == 1
    )


def test_case_sensitive_names_coexist_at_db(raw_conn):
    _new_service(raw_conn, "mon")
    _new_service(raw_conn, "MON")
    assert (
        raw_conn.execute("SELECT count(*) FROM services WHERE deleted_at IS NULL").fetchone()[0]
        == 2
    )


def test_soft_delete_releases_name_without_rewriting_old_row(raw_conn):
    service = _new_service(raw_conn, "mon")
    raw_conn.execute("UPDATE services SET deleted_at=now() WHERE id=%s", (service,))
    deleted_at_after = raw_conn.execute(
        "SELECT deleted_at FROM services WHERE id=%s", (service,)
    ).fetchone()[0]

    recreated = _new_service(raw_conn, "mon")
    assert recreated != service
    assert (
        raw_conn.execute("SELECT deleted_at FROM services WHERE id=%s", (service,)).fetchone()[0]
        == deleted_at_after
    )


# --------------------------------------------------------------------------- #
# 未定义约束「不实现」：空串 / 首尾空白 name、任意 url / port 不被拒绝
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("name", "url", "port"),
    [
        ("", None, None),
        ("  padded  ", None, None),
        ("has/slash", "这不是一个 URL", "abc"),
        ("mon", "这不是一个 URL", "8080-8090"),
        ("  ", "x", "y"),
    ],
)
def test_undefined_field_constraints_not_enforced_in_db(raw_conn, name, url, port):
    service_id = raw_conn.execute(
        "INSERT INTO services (name, url, port) VALUES (%s, %s, %s) RETURNING id",
        (name, url, port),
    ).fetchone()[0]
    fetched = raw_conn.execute(
        "SELECT name, url, port FROM services WHERE id=%s", (service_id,)
    ).fetchone()
    assert fetched == (name, url, port)


# --------------------------------------------------------------------------- #
# 23503：引用不存在的载体；物理删除被绑定的载体 → RESTRICT
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("carrier_kind", ["bare_metal", "virtual_machine", "container"])
def test_nonexistent_carrier_rejected_with_23503(raw_conn, carrier_kind):
    service = _new_service(raw_conn, "mon")
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO service_carriers (service_id, " + carrier_kind + "_id) "
            "VALUES (%s, 999999999)",
            (service,),
        )
    assert excinfo.value.sqlstate == "23503"


def test_physical_delete_of_bound_carriers_rejected_with_23503(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    vm = _new_virtual_machine(raw_conn, host, "vm1")
    container = _new_container(raw_conn, vm, "c1")
    service = _new_service(raw_conn, "mon")
    _bind_bm(raw_conn, service, host)
    _bind_vm(raw_conn, service, vm)
    _bind_container(raw_conn, service, container)

    for table, row_id in (
        ("containers", container),
        ("virtual_machines", vm),
        ("bare_metals", host),
    ):
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
            raw_conn.execute(f"DELETE FROM {table} WHERE id=%s", (row_id,))
        assert excinfo.value.sqlstate == "23503", table
        raw_conn.rollback()


# --------------------------------------------------------------------------- #
# 释放不是写入：软删 Service 后绑定行逐字段不变
# --------------------------------------------------------------------------- #
def test_soft_deleted_service_keeps_bindings_unchanged(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    service = _new_service(raw_conn, "mon")
    _bind_bm(raw_conn, service, host)
    before = raw_conn.execute(
        "SELECT id, service_id, bare_metal_id, virtual_machine_id, container_id "
        "FROM service_carriers WHERE service_id=%s",
        (service,),
    ).fetchall()

    raw_conn.execute("UPDATE services SET deleted_at=now() WHERE id=%s", (service,))
    after = raw_conn.execute(
        "SELECT id, service_id, bare_metal_id, virtual_machine_id, container_id "
        "FROM service_carriers WHERE service_id=%s",
        (service,),
    ).fetchall()
    assert after == before


# --------------------------------------------------------------------------- #
# AC-49：零载体不变式回归查询 = 0 行
# --------------------------------------------------------------------------- #
def test_ac49_zero_carrier_query_returns_zero(raw_conn):
    cluster = _new_cluster(raw_conn, "cluster-a")
    host = _new_bare_metal(raw_conn, cluster, "n1")
    service = _new_service(raw_conn, "mon")
    _bind_bm(raw_conn, service, host)
    raw_conn.execute("UPDATE services SET deleted_at=now() WHERE id=%s", (service,))

    count = raw_conn.execute(
        "SELECT count(*) FROM services s WHERE s.deleted_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM service_carriers sc WHERE sc.service_id = s.id)"
    ).fetchone()[0]
    assert count == 0
