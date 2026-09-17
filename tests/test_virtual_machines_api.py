"""F006 VirtualMachine API 行为测试（T-01 ~ T-23、T-28 ~ T-30）。

数据库夹具 ``auth_client_and_raw`` 同时提供产品客户端与**绕过应用层**的原始
psycopg 连接，用于断言数据库侧状态与预置软删行。
"""

from __future__ import annotations

import pytest

READ_FIELDS = {
    "id",
    "bare_metal_id",
    "name",
    "cpu",
    "memory",
    "disk",
    "os",
    "hypervisor",
    "owner",
    "created_at",
    "updated_at",
}

OPTIONAL_FIELDS = ("cpu", "memory", "disk", "os", "hypervisor", "owner")

POSITION_FIELDS = {
    "data_center",
    "datacenter",
    "location",
    "room",
    "rack",
    "u_position",
    "site",
    "campus",
}

PLATFORM_FIELDS = {
    "platform_id",
    "external_id",
    "external_platform_id",
    "credential",
    "api_key",
    "token",
    "password",
    "discovered",
    "last_seen",
    "sync_status",
    "last_sync_at",
}


def _create_cluster(client, name: str) -> int:
    response = client.post("/api/clusters", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_bm(client, cluster_id: int, hostname: str) -> dict:
    response = client.post(
        "/api/bare-metals", json={"cluster_id": cluster_id, "hostname": hostname}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _raw_bm(conn, cluster_id: int, hostname: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO bare_metals (cluster_id, hostname, deleted_at) "
            "VALUES (%s, %s, now()) RETURNING id",
            (cluster_id, hostname),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, %s) RETURNING id",
        (cluster_id, hostname),
    ).fetchone()[0]


def _raw_cluster(conn, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO clusters (name, deleted_at) VALUES (%s, now()) RETURNING id", (name,)
        ).fetchone()[0]
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[
        0
    ]


def _vm_payload(bare_metal_id: int, name: str, **extra) -> dict:
    return {"bare_metal_id": bare_metal_id, "name": name, **extra}


def _active_vm_count(conn) -> int:
    return conn.execute(
        "SELECT count(*) FROM virtual_machines WHERE deleted_at IS NULL"
    ).fetchone()[0]


def _total_vm_rows(conn) -> int:
    return conn.execute("SELECT count(*) FROM virtual_machines").fetchone()[0]


# --------------------------------------------------------------------------- #
# T-01 / AC-01：登记成功，响应字段集合恰为 11 字段
# --------------------------------------------------------------------------- #
def test_t01_create_returns_closed_field_set(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    response = client.post("/api/virtual-machines", json=_vm_payload(host["id"], "vm1"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == READ_FIELDS
    assert "deleted_at" not in body
    assert "status" not in body
    assert "cluster_id" not in body
    assert not (POSITION_FIELDS & set(body))
    assert not (PLATFORM_FIELDS & set(body))
    assert body["bare_metal_id"] == host["id"]
    assert body["name"] == "vm1"
    assert _active_vm_count(conn) == 1


# --------------------------------------------------------------------------- #
# T-04 / AC-05：POST 请求 schema 封闭（多宿主 / 载体类型 / VM 作宿主）→ 400，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "extra",
    [
        {"hosts": [1, 2]},
        {"carrier_type": "bare_metal"},
        {"container_id": 1},
        {"virtual_machine_id": 1},
        {"cluster_id": 1},
        {"status": "RUNNING"},
        {"rack": "R01"},
    ],
)
def test_t04_unknown_or_overreaching_create_fields_rejected(auth_client_and_raw, extra):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    response = client.post("/api/virtual-machines", json=_vm_payload(host["id"], "vm1", **extra))

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert _total_vm_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-02 / AC-02：name 必填 / 非字符串 → 400 + field == "name"，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["MISSING", 123, None])
def test_t02_invalid_name_returns_400_without_write(auth_client_and_raw, name):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    payload = {"bare_metal_id": host["id"]}
    if name != "MISSING":
        payload["name"] = name

    response = client.post("/api/virtual-machines", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "name" for detail in body["error"]["details"])
    assert _total_vm_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-03 / AC-03 / AC-04 / NQ-2：宿主必填 / 类型；不存在 / 已删宿主 → 404，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("host_value", ["MISSING", "abc", None, 1.5])
def test_t03_invalid_bare_metal_id_type_returns_400(auth_client_and_raw, host_value):
    client, conn = auth_client_and_raw
    payload = {"name": "vm1"}
    if host_value != "MISSING":
        payload["bare_metal_id"] = host_value

    response = client.post("/api/virtual-machines", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "bare_metal_id" for detail in body["error"]["details"])
    assert _total_vm_rows(conn) == 0


def test_t03_missing_or_deleted_host_returns_404_without_write(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    missing = client.post("/api/virtual-machines", json=_vm_payload(999999, "vm1"))
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert missing.json()["error"]["details"] == []

    gone_host = _raw_bm(conn, cluster_id, "gone", deleted=True)
    deleted = client.post("/api/virtual-machines", json=_vm_payload(gone_host, "vm2"))
    assert deleted.status_code == 404
    assert deleted.json()["error"]["code"] == "NOT_FOUND"

    assert _total_vm_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-05 / AC-06：可选字段缺失 → 201，六字段响应为 null
# --------------------------------------------------------------------------- #
def test_t05_missing_optional_fields_return_null(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    response = client.post("/api/virtual-machines", json=_vm_payload(host["id"], "vm1"))

    assert response.status_code == 201
    body = response.json()
    for field in OPTIONAL_FIELDS:
        assert field in body, f"{field} 必须返回 null 而非省略"
        assert body[field] is None


# --------------------------------------------------------------------------- #
# T-06 / AC-07：中文 name 与 "8 vCPU" 等原样往返
# --------------------------------------------------------------------------- #
def test_t06_chinese_name_and_text_roundtrip(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    name = "虚拟机-甲"

    created = client.post(
        "/api/virtual-machines",
        json=_vm_payload(host["id"], name, cpu="8 vCPU", memory="32 GB"),
    )
    assert created.status_code == 201
    assert created.json()["name"] == name
    assert created.json()["cpu"] == "8 vCPU"

    detail = client.get(f"/api/virtual-machines/{created.json()['id']}")
    assert detail.json()["name"] == name
    assert detail.json()["memory"] == "32 GB"


# --------------------------------------------------------------------------- #
# T-07 / AC-08：空串 / 首尾空白 name 不被拒绝（未定义约束不实现）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["", "  padded  ", "has/slash"])
def test_t07_undefined_name_constraints_not_enforced(auth_client_and_raw, name):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    response = client.post("/api/virtual-machines", json=_vm_payload(host["id"], name))

    assert response.status_code == 201, response.text
    assert response.json()["name"] == name


# --------------------------------------------------------------------------- #
# T-08 / AC-09 / AC-10：全局活跃 name 唯一（跨宿主、跨 Cluster）→ 409 DUPLICATE
# --------------------------------------------------------------------------- #
def test_t08_global_duplicate_name_returns_409(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    host_a = _create_bm(client, cluster_a, "n1")
    host_b = _create_bm(client, cluster_b, "n1")

    assert (
        client.post("/api/virtual-machines", json=_vm_payload(host_a["id"], "vm1")).status_code
        == 201
    )

    # 跨宿主（且跨 Cluster）同名 → 409
    response = client.post("/api/virtual-machines", json=_vm_payload(host_b["id"], "vm1"))

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    detail = next(d for d in body["error"]["details"] if d["field"] == "name")
    assert detail["code"] == "DUPLICATE"
    assert _active_vm_count(conn) == 1


# --------------------------------------------------------------------------- #
# T-09 / AC-11：大小写敏感
# --------------------------------------------------------------------------- #
def test_t09_case_sensitive_names_coexist(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    assert (
        client.post("/api/virtual-machines", json=_vm_payload(host["id"], "vm1")).status_code == 201
    )
    assert (
        client.post("/api/virtual-machines", json=_vm_payload(host["id"], "VM1")).status_code == 201
    )

    listed = client.get("/api/virtual-machines").json()
    assert sorted(item["name"] for item in listed["items"]) == ["VM1", "vm1"]
    assert _active_vm_count(conn) == 2


# --------------------------------------------------------------------------- #
# T-11 / AC-13：软删释放唯一性；旧行 deleted_at 未被改写
# --------------------------------------------------------------------------- #
def test_t11_soft_delete_releases_name(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    host_a = _create_bm(client, cluster_a, "n1")
    host_b = _create_bm(client, cluster_b, "n1")

    created = client.post("/api/virtual-machines", json=_vm_payload(host_a["id"], "vm1")).json()
    assert client.delete(f"/api/virtual-machines/{created['id']}").status_code == 204
    deleted_at_after = conn.execute(
        "SELECT deleted_at FROM virtual_machines WHERE id = %s", (created["id"],)
    ).fetchone()[0]

    recreated = client.post("/api/virtual-machines", json=_vm_payload(host_b["id"], "vm1"))
    assert recreated.status_code == 201
    assert recreated.json()["id"] != created["id"]

    total = conn.execute("SELECT count(*) FROM virtual_machines WHERE name = 'vm1'").fetchone()[0]
    assert total == 2
    assert (
        conn.execute(
            "SELECT deleted_at FROM virtual_machines WHERE id = %s", (created["id"],)
        ).fetchone()[0]
        == deleted_at_after
    )


# --------------------------------------------------------------------------- #
# T-12 / AC-14：列表、分页、Empty
# --------------------------------------------------------------------------- #
def test_t12_empty_list_is_200_empty_items(auth_client_and_raw):
    client, _ = auth_client_and_raw
    response = client.get("/api/virtual-machines")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 50}


def test_t12_pagination(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    for index in range(3):
        assert (
            client.post(
                "/api/virtual-machines", json=_vm_payload(host["id"], f"vm{index}")
            ).status_code
            == 201
        )

    first = client.get("/api/virtual-machines", params={"page_size": 2, "page": 1}).json()
    assert first["total"] == 3
    assert [item["name"] for item in first["items"]] == ["vm0", "vm1"]

    second = client.get("/api/virtual-machines", params={"page_size": 2, "page": 2}).json()
    assert [item["name"] for item in second["items"]] == ["vm2"]


# --------------------------------------------------------------------------- #
# T-13 / AC-15：详情 Not Found（不区分不存在 / 已删）
# --------------------------------------------------------------------------- #
def test_t13_detail_not_found(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    assert client.get("/api/virtual-machines/999999").status_code == 404

    conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name, deleted_at) "
        "VALUES (%s, 'ghost', now())",
        (host["id"],),
    )
    ghost_id = conn.execute("SELECT id FROM virtual_machines WHERE name = 'ghost'").fetchone()[0]
    response = client.get(f"/api/virtual-machines/{ghost_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# T-14 / AC-16：绕过应用层预置软删行 → 排除；按 id → 404
# --------------------------------------------------------------------------- #
def test_t14_soft_deleted_row_excluded_from_reads(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name, deleted_at) "
        "VALUES (%s, 'ghost', now())",
        (host["id"],),
    )
    ghost_id = conn.execute("SELECT id FROM virtual_machines WHERE name = 'ghost'").fetchone()[0]

    listed = client.get("/api/virtual-machines").json()
    assert listed["total"] == 0
    assert [item["id"] for item in listed["items"]] == []

    by_host = client.get("/api/virtual-machines", params={"bare_metal_id": host["id"]}).json()
    assert by_host["total"] == 0

    assert client.get(f"/api/virtual-machines/{ghost_id}").status_code == 404


# --------------------------------------------------------------------------- #
# T-15 / AC-17：宿主绑定可观察；无 Cluster 维度字段
# --------------------------------------------------------------------------- #
def test_t15_host_binding_observable_without_cluster_fields(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/virtual-machines", json=_vm_payload(host["id"], "vm1")).json()

    assert created["bare_metal_id"] == host["id"]
    for forbidden in ("cluster_id", "cluster_name", "cluster"):
        assert forbidden not in created


# --------------------------------------------------------------------------- #
# T-16 / AC-18：无 status（请求 / 响应 / 表 / 端点 / 参数）
# --------------------------------------------------------------------------- #
def test_t16_no_status_anywhere(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base
    from app.virtual_machines.schemas import (
        VirtualMachineCreate,
        VirtualMachineRead,
        VirtualMachineUpdate,
    )

    for model in (VirtualMachineCreate, VirtualMachineRead, VirtualMachineUpdate):
        assert "status" not in model.model_fields, model.__name__

    columns = {column.name for column in Base.metadata.tables["virtual_machines"].columns}
    assert "status" not in columns
    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='virtual_machines'"
        ).fetchall()
    }
    assert "status" not in db_columns

    for path, operations in client.app.openapi()["paths"].items():
        if not path.startswith("/api/virtual-machines"):
            continue
        assert "status" not in path.lower()
        for operation in operations.values():
            param_names = {p.get("name") for p in operation.get("parameters", [])}
            assert not any("status" in (name or "").lower() for name in param_names)


# --------------------------------------------------------------------------- #
# T-17 / AC-19：PATCH 合法字段；null 清空；缺省不变
# --------------------------------------------------------------------------- #
def test_t17_patch_optional_fields_and_clear(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post(
        "/api/virtual-machines",
        json=_vm_payload(host["id"], "vm1", cpu="8 vCPU", owner="ops"),
    ).json()

    patched = client.patch(
        f"/api/virtual-machines/{created['id']}", json={"cpu": "16 vCPU", "owner": None}
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["cpu"] == "16 vCPU"
    assert body["owner"] is None
    assert body["id"] == created["id"]
    assert body["bare_metal_id"] == created["bare_metal_id"]
    assert body["name"] == created["name"]
    assert body["created_at"] == created["created_at"]

    reread = client.get(f"/api/virtual-machines/{created['id']}").json()
    assert reread["cpu"] == "16 vCPU"
    assert reread["owner"] is None


# --------------------------------------------------------------------------- #
# T-18 / AC-20：PATCH 未识别 / 不可变字段 → 400；空 body → 400
# --------------------------------------------------------------------------- #
def test_t18_patch_rejects_unknown_and_immutable(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/virtual-machines", json=_vm_payload(host["id"], "vm1")).json()

    empty = client.patch(f"/api/virtual-machines/{created['id']}", json={})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "VALIDATION_ERROR"

    for field, value in (
        ("name", "x"),
        ("bare_metal_id", host["id"]),
        ("id", 1),
        ("deleted_at", None),
        ("cluster_id", 1),
        ("status", "RUNNING"),
    ):
        forbidden = client.patch(f"/api/virtual-machines/{created['id']}", json={field: value})
        assert forbidden.status_code == 400, field
        assert any(detail["field"] == field for detail in forbidden.json()["error"]["details"]), (
            field
        )


def test_t18_patch_missing_or_deleted_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    assert client.patch("/api/virtual-machines/999999", json={"cpu": "x"}).status_code == 404

    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name, deleted_at) VALUES (%s, 'gone', now())",
        (host["id"],),
    )
    gone_id = conn.execute("SELECT id FROM virtual_machines WHERE name = 'gone'").fetchone()[0]
    assert client.patch(f"/api/virtual-machines/{gone_id}", json={"cpu": "x"}).status_code == 404


# --------------------------------------------------------------------------- #
# T-19 / AC-21：逻辑删除（204 无响应体；行仍物理存在）
# --------------------------------------------------------------------------- #
def test_t19_delete_returns_204_and_row_survives(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/virtual-machines", json=_vm_payload(host["id"], "vm1")).json()
    rows_before = _total_vm_rows(conn)

    response = client.delete(f"/api/virtual-machines/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert _total_vm_rows(conn) == rows_before
    row = conn.execute(
        "SELECT deleted_at FROM virtual_machines WHERE id = %s", (created["id"],)
    ).fetchone()
    assert row is not None, "逻辑删除不得物理删除行"
    assert row[0] is not None

    assert client.get("/api/virtual-machines").json()["total"] == 0
    assert client.get(f"/api/virtual-machines/{created['id']}").status_code == 404
    # 重复删除 → 404
    assert client.delete(f"/api/virtual-machines/{created['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# T-20 / AC-22：删除不级联（宿主不变）
# --------------------------------------------------------------------------- #
def test_t20_delete_does_not_cascade(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    other = client.post("/api/virtual-machines", json=_vm_payload(host["id"], "keep")).json()
    target = client.post("/api/virtual-machines", json=_vm_payload(host["id"], "gone")).json()

    host_before = conn.execute(
        "SELECT hostname, status, created_at, updated_at, deleted_at "
        "FROM bare_metals WHERE id = %s",
        (host["id"],),
    ).fetchone()
    other_before = conn.execute(
        "SELECT name, deleted_at FROM virtual_machines WHERE id = %s", (other["id"],)
    ).fetchone()
    rows_before = _total_vm_rows(conn)

    assert client.delete(f"/api/virtual-machines/{target['id']}").status_code == 204

    assert (
        conn.execute(
            "SELECT hostname, status, created_at, updated_at, deleted_at "
            "FROM bare_metals WHERE id = %s",
            (host["id"],),
        ).fetchone()
        == host_before
    )
    assert (
        conn.execute(
            "SELECT name, deleted_at FROM virtual_machines WHERE id = %s", (other["id"],)
        ).fetchone()
        == other_before
    )
    assert _total_vm_rows(conn) == rows_before


# --------------------------------------------------------------------------- #
# T-21 / AC-23：无恢复 / 批量 / include_deleted / by-name
# --------------------------------------------------------------------------- #
def test_t21_no_out_of_scope_routes_or_params(auth_client_and_raw):
    client, _ = auth_client_and_raw
    paths = client.app.openapi()["paths"]

    forbidden_tokens = ("restore", "undelete", "purge", "trash", "batch", "deleted", "by-name")
    offenders = [
        path
        for path in paths
        if path.startswith("/api/virtual-machines")
        and any(token in path.lower() for token in forbidden_tokens)
    ]
    assert offenders == [], f"不存在恢复 / 批量 / by-name 端点：{offenders}"

    list_op = paths["/api/virtual-machines"]["get"]
    param_names = {p.get("name") for p in list_op.get("parameters", [])}
    assert not any("deleted" in (name or "").lower() for name in param_names)
    assert not any("include" in (name or "").lower() for name in param_names)


# --------------------------------------------------------------------------- #
# T-22 / AC-24：宿主有活跃 VM → 拒绝删除宿主（409 ACTIVE_CHILDREN_EXIST）
# --------------------------------------------------------------------------- #
def test_t22_host_with_active_vm_cannot_be_deleted(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    assert (
        client.post("/api/virtual-machines", json=_vm_payload(host["id"], "vm1")).status_code == 201
    )

    response = client.delete(f"/api/bare-metals/{host['id']}")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(detail["code"] == "ACTIVE_CHILDREN_EXIST" for detail in body["error"]["details"])
    # 无部分写入
    assert (
        conn.execute("SELECT deleted_at FROM bare_metals WHERE id = %s", (host["id"],)).fetchone()[
            0
        ]
        is None
    )


# --------------------------------------------------------------------------- #
# T-23 / AC-25：软删全部活跃 VM 后宿主可删
# --------------------------------------------------------------------------- #
def test_t23_host_deletable_after_children_soft_deleted(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    first = client.post("/api/virtual-machines", json=_vm_payload(host["id"], "vm1")).json()
    second = client.post("/api/virtual-machines", json=_vm_payload(host["id"], "vm2")).json()

    assert client.delete(f"/api/virtual-machines/{first['id']}").status_code == 204
    assert client.delete(f"/api/virtual-machines/{second['id']}").status_code == 204

    assert client.delete(f"/api/bare-metals/{host['id']}").status_code == 204


# --------------------------------------------------------------------------- #
# T-28 / AC-30：无平台接入 / 凭据 / 同步字段或端点
# --------------------------------------------------------------------------- #
def test_t28_no_platform_integration(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base

    columns = {column.name for column in Base.metadata.tables["virtual_machines"].columns}
    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='virtual_machines'"
        ).fetchall()
    }
    for forbidden in PLATFORM_FIELDS:
        assert forbidden not in columns
        assert forbidden not in db_columns

    for path in client.app.openapi()["paths"]:
        if path.startswith("/api/virtual-machines"):
            assert not any(
                token in path.lower()
                for token in ("sync", "discover", "platform", "credential", "external")
            )


# --------------------------------------------------------------------------- #
# T-29 / AC-31：不越界其它资源 / 位置字段
# --------------------------------------------------------------------------- #
def test_t29_no_other_resource_or_position_structure(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base

    paths = set(client.app.openapi()["paths"])
    # F008 演进：Service 已成为合法资源（``/api/services``），从越界 prefix 中移除
    # ``service``。
    forbidden_prefixes = ("nic", "network-interface", "ip-address", "container")
    offenders = [
        path
        for path in paths
        if path.startswith("/api/virtual-machines")
        and any(
            path[len("/api/virtual-machines") :].lstrip("/").startswith(p)
            for p in forbidden_prefixes
        )
    ]
    assert offenders == [], f"F006 不得注册其它资源端点：{offenders}"

    columns = {column.name for column in Base.metadata.tables["virtual_machines"].columns}
    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='virtual_machines'"
        ).fetchall()
    }
    for forbidden in POSITION_FIELDS:
        assert forbidden not in columns
        assert forbidden not in db_columns
    for token in ("network_interface", "ip_address", "container_id", "service_id"):
        assert token not in columns
        assert token not in db_columns


# --------------------------------------------------------------------------- #
# T-30 / 决策 3：按宿主读取；Empty 与 Not Found 可区分
# --------------------------------------------------------------------------- #
def test_t30_list_by_host_semantics(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    host_a = _create_bm(client, cluster_a, "n1")
    host_b = _create_bm(client, cluster_b, "n1")

    # 宿主不存在 → 404
    missing = client.get("/api/virtual-machines", params={"bare_metal_id": 999999})
    assert missing.status_code == 404

    # 宿主已删 → 404
    gone_host = _raw_bm(conn, cluster_a, "gone", deleted=True)
    deleted = client.get("/api/virtual-machines", params={"bare_metal_id": gone_host})
    assert deleted.status_code == 404

    # 宿主存在但无活跃 VM → 200 空集
    empty = client.get("/api/virtual-machines", params={"bare_metal_id": host_a["id"]})
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["total"] == 0

    # 只返回该宿主子集
    client.post("/api/virtual-machines", json=_vm_payload(host_a["id"], "a1"))
    client.post("/api/virtual-machines", json=_vm_payload(host_b["id"], "b1"))
    only_a = client.get("/api/virtual-machines", params={"bare_metal_id": host_a["id"]}).json()
    assert [item["name"] for item in only_a["items"]] == ["a1"]
    assert only_a["total"] == 1


@pytest.mark.parametrize("bare_metal_id", ["abc", 0.5])
def test_t30_non_integer_host_query_returns_400(auth_client_and_raw, bare_metal_id):
    client, _ = auth_client_and_raw
    response = client.get("/api/virtual-machines", params={"bare_metal_id": bare_metal_id})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "bare_metal_id" for detail in body["error"]["details"])


# --------------------------------------------------------------------------- #
# 认证覆盖：未认证 → 401（不改变数据）
# --------------------------------------------------------------------------- #
def test_unauthenticated_requires_session(app_client_and_raw):
    client, conn = app_client_and_raw
    response = client.get("/api/virtual-machines")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert _total_vm_rows(conn) == 0
