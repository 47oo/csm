"""F007 Container API 行为测试（AC-01 ~ AC-35、AC-38、AC-42/AC-43 API 侧）。

数据库夹具 ``auth_client_and_raw`` 同时提供产品客户端与**绕过应用层**的原始 psycopg
连接，用于断言数据库侧状态与预置软删行。
"""

from __future__ import annotations

import pytest

READ_FIELDS = {
    "id",
    "carrier_type",
    "carrier_id",
    "name",
    "image",
    "cpu",
    "memory",
    "owner",
    "created_at",
    "updated_at",
}

OPTIONAL_FIELDS = ("image", "cpu", "memory", "owner")

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


def _create_vm(client, bare_metal_id: int, name: str) -> dict:
    response = client.post(
        "/api/virtual-machines", json={"bare_metal_id": bare_metal_id, "name": name}
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


def _raw_vm(conn, bare_metal_id: int, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO virtual_machines (bare_metal_id, name, deleted_at) "
            "VALUES (%s, %s, now()) RETURNING id",
            (bare_metal_id, name),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name) VALUES (%s, %s) RETURNING id",
        (bare_metal_id, name),
    ).fetchone()[0]


def _raw_cluster(conn, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO clusters (name, deleted_at) VALUES (%s, now()) RETURNING id", (name,)
        ).fetchone()[0]
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[
        0
    ]


def _payload(carrier_type: str, carrier_id: int, name: str, **extra) -> dict:
    return {"carrier_type": carrier_type, "carrier_id": carrier_id, "name": name, **extra}


def _active_container_count(conn) -> int:
    return conn.execute("SELECT count(*) FROM containers WHERE deleted_at IS NULL").fetchone()[0]


def _total_container_rows(conn) -> int:
    return conn.execute("SELECT count(*) FROM containers").fetchone()[0]


# --------------------------------------------------------------------------- #
# AC-01 / AC-02：以 BareMetal / VirtualMachine 为载体登记成功；字段集合恰 10
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("carrier", ["BARE_METAL", "VIRTUAL_MACHINE"])
def test_create_returns_closed_field_set(auth_client_and_raw, carrier):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    if carrier == "BARE_METAL":
        carrier_id = host["id"]
    else:
        carrier_id = _create_vm(client, host["id"], "vm1")["id"]

    response = client.post("/api/containers", json=_payload(carrier, carrier_id, "web"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == READ_FIELDS
    assert "deleted_at" not in body
    assert "status" not in body
    assert "cluster_id" not in body
    assert "bare_metal_id" not in body
    assert "virtual_machine_id" not in body
    assert not (POSITION_FIELDS & set(body))
    assert not (PLATFORM_FIELDS & set(body))
    assert body["carrier_type"] == carrier
    assert body["carrier_id"] == carrier_id
    assert body["name"] == "web"
    assert _active_container_count(conn) == 1


# --------------------------------------------------------------------------- #
# AC-03：name 必填 / 非字符串 → 400 field == name，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["MISSING", 123, None])
def test_invalid_name_returns_400_without_write(auth_client_and_raw, name):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    payload = {"carrier_type": "BARE_METAL", "carrier_id": host["id"]}
    if name != "MISSING":
        payload["name"] = name

    response = client.post("/api/containers", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "name" for detail in body["error"]["details"])
    assert _total_container_rows(conn) == 0


# --------------------------------------------------------------------------- #
# AC-04：载体必填（两者都不给 / 缺其一）→ 400，field 指向载体字段，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("payload", "expected_field"),
    [
        ({"name": "web"}, "carrier_type"),
        ({"name": "web", "carrier_type": "BARE_METAL"}, "carrier_id"),
        ({"name": "web", "carrier_id": 1}, "carrier_type"),
    ],
)
def test_missing_carrier_returns_400(auth_client_and_raw, payload, expected_field):
    client, conn = auth_client_and_raw
    response = client.post("/api/containers", json=payload)
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == expected_field for detail in body["error"]["details"])
    assert _total_container_rows(conn) == 0


# --------------------------------------------------------------------------- #
# AC-05 / AC-06：拒绝多载体与越界载体字段（请求 schema 封闭）→ 400，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "extra",
    [
        {"carriers": [1, 2]},
        {"bare_metal_id": 1},
        {"virtual_machine_id": 1},
        {"carrier_type": "CLUSTER"},
        {"carrier_type": "SERVICE"},
        {"cluster_id": 1},
        {"service_id": 1},
        {"network_interface_id": 1},
        {"ip_address_id": 1},
        {"carrier": "bare_metal"},
        {"owner_type": "host"},
        {"status": "RUNNING"},
        {"rack": "R01"},
    ],
)
def test_unknown_or_overreaching_create_fields_rejected(auth_client_and_raw, extra):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    payload = {**_payload("BARE_METAL", host["id"], "web"), **extra}

    response = client.post("/api/containers", json=payload)

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_container_rows(conn) == 0


# --------------------------------------------------------------------------- #
# AC-07 / AC-08 / NQ-2：类型与标识不一致 / 不存在 / 已删载体 → 404，无写入
# --------------------------------------------------------------------------- #
def test_carrier_type_and_id_mismatch_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    # 用显式 id 保证两表数值不重叠，从而能真正构造「类型与标识不一致」。
    bm_id = conn.execute(
        "INSERT INTO bare_metals (id, cluster_id, hostname) OVERRIDING SYSTEM VALUE "
        "VALUES (500, %s, 'n1') RETURNING id",
        (cluster_id,),
    ).fetchone()[0]
    vm_id = conn.execute(
        "INSERT INTO virtual_machines (id, bare_metal_id, name) OVERRIDING SYSTEM VALUE "
        "VALUES (900, %s, 'vm1') RETURNING id",
        (bm_id,),
    ).fetchone()[0]
    assert (bm_id, vm_id) == (500, 900)

    # 断言 VM 类型却传入仅存在于 bare_metals 的标识（500 不是 VM）→ 404
    mismatch = client.post("/api/containers", json=_payload("VIRTUAL_MACHINE", 500, "web"))
    assert mismatch.status_code == 404
    assert mismatch.json()["error"]["code"] == "NOT_FOUND"
    assert mismatch.json()["error"]["details"] == []

    # 断言 BareMetal 类型却传入仅存在于 virtual_machines 的标识（900 不是 BM）→ 404
    mismatch2 = client.post("/api/containers", json=_payload("BARE_METAL", 900, "web"))
    assert mismatch2.status_code == 404
    assert _total_container_rows(conn) == 0


def test_missing_or_deleted_carrier_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    missing = client.post("/api/containers", json=_payload("BARE_METAL", 999999, "web"))
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert missing.json()["error"]["details"] == []

    gone_bm = _raw_bm(conn, cluster_id, "gone", deleted=True)
    deleted_bm = client.post("/api/containers", json=_payload("BARE_METAL", gone_bm, "web"))
    assert deleted_bm.status_code == 404

    live_bm = _raw_bm(conn, cluster_id, "live")
    gone_vm = _raw_vm(conn, live_bm, "gone-vm", deleted=True)
    deleted_vm = client.post("/api/containers", json=_payload("VIRTUAL_MACHINE", gone_vm, "web"))
    assert deleted_vm.status_code == 404

    assert _total_container_rows(conn) == 0


# --------------------------------------------------------------------------- #
# AC-09 / AC-10 / AC-11：可选字段 null；原样往返；未定义约束不实现
# --------------------------------------------------------------------------- #
def test_missing_optional_fields_return_null(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    response = client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web"))

    assert response.status_code == 201
    body = response.json()
    for field in OPTIONAL_FIELDS:
        assert field in body, f"{field} 必须返回 null 而非省略"
        assert body[field] is None


def test_chinese_name_and_text_roundtrip(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    name = "容器-甲"
    created = client.post(
        "/api/containers",
        json=_payload(
            "BARE_METAL",
            host["id"],
            name,
            image="registry/nginx:1.25",
            cpu="8 vCPU",
            memory="4G",
            owner="ops",
        ),
    )
    assert created.status_code == 201
    assert created.json()["name"] == name
    assert created.json()["cpu"] == "8 vCPU"

    detail = client.get(f"/api/containers/{created.json()['id']}")
    assert detail.json()["name"] == name
    assert detail.json()["image"] == "registry/nginx:1.25"
    assert detail.json()["memory"] == "4G"


@pytest.mark.parametrize("name", ["", "  padded  ", "has/slash"])
def test_undefined_name_constraints_not_enforced(auth_client_and_raw, name):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    response = client.post("/api/containers", json=_payload("BARE_METAL", host["id"], name))
    assert response.status_code == 201, response.text
    assert response.json()["name"] == name


# --------------------------------------------------------------------------- #
# AC-12：同载体重复活跃 name → 409 DUPLICATE field == name，无第二条
# --------------------------------------------------------------------------- #
def test_duplicate_name_on_same_carrier_returns_409(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    assert (
        client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web")).status_code
        == 201
    )
    response = client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web"))

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    detail = next(d for d in body["error"]["details"] if d["field"] == "name")
    assert detail["code"] == "DUPLICATE"
    assert _active_container_count(conn) == 1


# --------------------------------------------------------------------------- #
# AC-13 / AC-14 / AC-15 / AC-16 / AC-17 / AC-20：唯一性边界是载体
# --------------------------------------------------------------------------- #
def test_same_name_on_bare_metal_and_its_vm_succeeds(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    vm = _create_vm(client, host["id"], "web")  # VM 名与容器名相同也必须允许

    assert (
        client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web")).status_code
        == 201
    )
    assert (
        client.post(
            "/api/containers", json=_payload("VIRTUAL_MACHINE", vm["id"], "web")
        ).status_code
        == 201
    )


def test_cross_carrier_type_same_numeric_id_same_name_succeeds(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    vm = _create_vm(client, host["id"], "vm1")
    assert host["id"] == vm["id"], "前置条件：首个 BM 与首个 VM 的 id 数值相等"

    assert (
        client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web")).status_code
        == 201
    )
    assert (
        client.post(
            "/api/containers", json=_payload("VIRTUAL_MACHINE", vm["id"], "web")
        ).status_code
        == 201
    )


def test_same_name_on_different_carriers_same_type_succeeds(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host_a = _create_bm(client, cluster_id, "n1")
    host_b = _create_bm(client, cluster_id, "n2")

    for host in (host_a, host_b):
        assert (
            client.post(
                "/api/containers", json=_payload("BARE_METAL", host["id"], "web")
            ).status_code
            == 201
        )


def test_case_sensitive_names_coexist(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    assert (
        client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web")).status_code
        == 201
    )
    assert (
        client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "WEB")).status_code
        == 201
    )


# --------------------------------------------------------------------------- #
# AC-19：软删释放唯一性；旧行 deleted_at 未被改写
# --------------------------------------------------------------------------- #
def test_soft_delete_releases_name(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    created = client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web")).json()
    assert client.delete(f"/api/containers/{created['id']}").status_code == 204
    deleted_at_after = conn.execute(
        "SELECT deleted_at FROM containers WHERE id = %s", (created["id"],)
    ).fetchone()[0]

    recreated = client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web"))
    assert recreated.status_code == 201
    assert recreated.json()["id"] != created["id"]

    assert (
        conn.execute(
            "SELECT deleted_at FROM containers WHERE id = %s", (created["id"],)
        ).fetchone()[0]
        == deleted_at_after
    )
    assert _total_container_rows(conn) == 2


# --------------------------------------------------------------------------- #
# AC-24：列表、分页、Empty
# --------------------------------------------------------------------------- #
def test_empty_list_is_200_empty_items(auth_client_and_raw):
    client, _ = auth_client_and_raw
    response = client.get("/api/containers")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 50}


def test_pagination(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    for index in range(3):
        assert (
            client.post(
                "/api/containers", json=_payload("BARE_METAL", host["id"], f"c{index}")
            ).status_code
            == 201
        )

    first = client.get("/api/containers", params={"page_size": 2, "page": 1}).json()
    assert first["total"] == 3
    assert [item["name"] for item in first["items"]] == ["c0", "c1"]

    second = client.get("/api/containers", params={"page_size": 2, "page": 2}).json()
    assert [item["name"] for item in second["items"]] == ["c2"]


# --------------------------------------------------------------------------- #
# AC-25：详情 Not Found（不区分不存在 / 已删）
# --------------------------------------------------------------------------- #
def test_detail_not_found(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    assert client.get("/api/containers/999999").status_code == 404

    ghost = conn.execute(
        "INSERT INTO containers (bare_metal_id, name, deleted_at) "
        "VALUES (%s, 'ghost', now()) RETURNING id",
        (host["id"],),
    ).fetchone()[0]
    response = client.get(f"/api/containers/{ghost}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# AC-26：按载体限定读取；Empty 与 Not Found 可区分（两种载体类型均成立）
# --------------------------------------------------------------------------- #
def test_list_by_carrier_semantics(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    host_a = _create_bm(client, cluster_a, "n1")
    vm_a = _create_vm(client, host_a["id"], "vm1")
    host_b = _create_bm(client, cluster_a, "n2")

    # 载体不存在 → 404（BM / VM）
    assert (
        client.get(
            "/api/containers", params={"carrier_type": "BARE_METAL", "carrier_id": 999999}
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/containers", params={"carrier_type": "VIRTUAL_MACHINE", "carrier_id": 999999}
        ).status_code
        == 404
    )

    # 载体已删 → 404（BM / VM）
    gone_bm = _raw_bm(conn, cluster_a, "gone", deleted=True)
    assert (
        client.get(
            "/api/containers", params={"carrier_type": "BARE_METAL", "carrier_id": gone_bm}
        ).status_code
        == 404
    )
    gone_vm = _raw_vm(conn, host_b["id"], "gone-vm", deleted=True)
    assert (
        client.get(
            "/api/containers", params={"carrier_type": "VIRTUAL_MACHINE", "carrier_id": gone_vm}
        ).status_code
        == 404
    )

    # 载体存在但无活跃 Container → 200 空集（Empty）
    empty = client.get(
        "/api/containers", params={"carrier_type": "BARE_METAL", "carrier_id": host_a["id"]}
    )
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["total"] == 0

    # 只返回该载体子集（BM 与 VM 均成立）
    client.post("/api/containers", json=_payload("BARE_METAL", host_a["id"], "a1"))
    client.post("/api/containers", json=_payload("VIRTUAL_MACHINE", vm_a["id"], "v1"))
    client.post("/api/containers", json=_payload("BARE_METAL", host_b["id"], "b1"))

    only_bm = client.get(
        "/api/containers", params={"carrier_type": "BARE_METAL", "carrier_id": host_a["id"]}
    ).json()
    assert [item["name"] for item in only_bm["items"]] == ["a1"]
    assert only_bm["total"] == 1

    only_vm = client.get(
        "/api/containers", params={"carrier_type": "VIRTUAL_MACHINE", "carrier_id": vm_a["id"]}
    ).json()
    assert [item["name"] for item in only_vm["items"]] == ["v1"]
    assert only_vm["total"] == 1


def test_list_by_carrier_requires_both_params(auth_client_and_raw):
    client, _ = auth_client_and_raw
    only_type = client.get("/api/containers", params={"carrier_type": "BARE_METAL"})
    assert only_type.status_code == 400
    assert any(d["field"] == "carrier_id" for d in only_type.json()["error"]["details"])

    only_id = client.get("/api/containers", params={"carrier_id": 1})
    assert only_id.status_code == 400
    assert any(d["field"] == "carrier_type" for d in only_id.json()["error"]["details"])


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"carrier_type": "NOPE", "carrier_id": 1}, "carrier_type"),
        ({"carrier_type": "BARE_METAL", "carrier_id": "abc"}, "carrier_id"),
    ],
)
def test_list_by_carrier_invalid_params(auth_client_and_raw, params, field):
    client, _ = auth_client_and_raw
    response = client.get("/api/containers", params=params)
    assert response.status_code == 400
    assert any(d["field"] == field for d in response.json()["error"]["details"]), response.text


# --------------------------------------------------------------------------- #
# AC-27：已删不出现在列表 / 按载体结果 / total；按 id → 404
# --------------------------------------------------------------------------- #
def test_soft_deleted_row_excluded_from_reads(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    ghost = conn.execute(
        "INSERT INTO containers (bare_metal_id, name, deleted_at) "
        "VALUES (%s, 'ghost', now()) RETURNING id",
        (host["id"],),
    ).fetchone()[0]

    listed = client.get("/api/containers").json()
    assert listed["total"] == 0
    assert [item["id"] for item in listed["items"]] == []

    by_carrier = client.get(
        "/api/containers", params={"carrier_type": "BARE_METAL", "carrier_id": host["id"]}
    ).json()
    assert by_carrier["total"] == 0

    assert client.get(f"/api/containers/{ghost}").status_code == 404


# --------------------------------------------------------------------------- #
# AC-21 / AC-22 / AC-23：无集群维度字段 / 无状态
# --------------------------------------------------------------------------- #
def test_no_cluster_or_status_fields(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.containers.schemas import ContainerCreate, ContainerRead, ContainerUpdate
    from app.db.base import Base

    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web")).json()

    for forbidden in ("cluster_id", "cluster_name", "cluster", "status"):
        assert forbidden not in created
    assert created["carrier_type"] == "BARE_METAL"
    assert created["carrier_id"] == host["id"]

    for model in (ContainerCreate, ContainerRead, ContainerUpdate):
        for forbidden in ("cluster_id", "cluster", "status"):
            assert forbidden not in model.model_fields, model.__name__

    columns = {column.name for column in Base.metadata.tables["containers"].columns}
    assert "status" not in columns
    assert "cluster_id" not in columns
    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='containers'"
        ).fetchall()
    }
    assert "status" not in db_columns
    assert "cluster_id" not in db_columns

    for path, operations in client.app.openapi()["paths"].items():
        if not path.startswith("/api/containers"):
            continue
        for operation in operations.values():
            param_names = {p.get("name") for p in operation.get("parameters", [])}
            assert not any(
                token in (name or "").lower()
                for name in param_names
                for token in ("status", "cluster")
            )


# --------------------------------------------------------------------------- #
# AC-28：PATCH 合法字段；null 清空；缺省不变；再读一致
# --------------------------------------------------------------------------- #
def test_patch_optional_fields_and_clear(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post(
        "/api/containers",
        json=_payload("BARE_METAL", host["id"], "web", image="img", owner="ops"),
    ).json()

    patched = client.patch(
        f"/api/containers/{created['id']}", json={"image": "img2", "owner": None}
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["image"] == "img2"
    assert body["owner"] is None
    assert body["id"] == created["id"]
    assert body["carrier_type"] == created["carrier_type"]
    assert body["carrier_id"] == created["carrier_id"]
    assert body["name"] == created["name"]
    assert body["created_at"] == created["created_at"]

    reread = client.get(f"/api/containers/{created['id']}").json()
    assert reread["image"] == "img2"
    assert reread["owner"] is None


# --------------------------------------------------------------------------- #
# AC-29：PATCH 未识别 / 不可变字段 → 400；空 body → 400
# --------------------------------------------------------------------------- #
def test_patch_rejects_unknown_and_immutable(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web")).json()

    empty = client.patch(f"/api/containers/{created['id']}", json={})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "VALIDATION_ERROR"

    for field, value in (
        ("name", "x"),
        ("carrier_type", "VIRTUAL_MACHINE"),
        ("carrier_id", 1),
        ("bare_metal_id", host["id"]),
        ("virtual_machine_id", 1),
        ("id", 1),
        ("deleted_at", None),
        ("cluster_id", 1),
        ("status", "RUNNING"),
    ):
        forbidden = client.patch(f"/api/containers/{created['id']}", json={field: value})
        assert forbidden.status_code == 400, field
        assert any(detail["field"] == field for detail in forbidden.json()["error"]["details"]), (
            field
        )


def test_patch_missing_or_deleted_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    assert client.patch("/api/containers/999999", json={"cpu": "x"}).status_code == 404

    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    gone = conn.execute(
        "INSERT INTO containers (bare_metal_id, name, deleted_at) "
        "VALUES (%s, 'gone', now()) RETURNING id",
        (host["id"],),
    ).fetchone()[0]
    assert client.patch(f"/api/containers/{gone}", json={"cpu": "x"}).status_code == 404


# --------------------------------------------------------------------------- #
# AC-30：逻辑删除（204 无响应体；行仍物理存在；重复删除 → 404）
# --------------------------------------------------------------------------- #
def test_delete_returns_204_and_row_survives(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web")).json()
    rows_before = _total_container_rows(conn)

    response = client.delete(f"/api/containers/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert _total_container_rows(conn) == rows_before
    row = conn.execute(
        "SELECT deleted_at FROM containers WHERE id = %s", (created["id"],)
    ).fetchone()
    assert row is not None, "逻辑删除不得物理删除行"
    assert row[0] is not None

    assert client.get("/api/containers").json()["total"] == 0
    assert client.get(f"/api/containers/{created['id']}").status_code == 404
    assert client.delete(f"/api/containers/{created['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# AC-31：删除不级联（载体逐字段不变，BM 与 VM 均成立）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("carrier", ["BARE_METAL", "VIRTUAL_MACHINE"])
def test_delete_does_not_cascade(auth_client_and_raw, carrier):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    if carrier == "BARE_METAL":
        carrier_id = host["id"]
    else:
        carrier_id = _create_vm(client, host["id"], "vm1")["id"]

    keep = client.post("/api/containers", json=_payload(carrier, carrier_id, "keep")).json()
    target = client.post("/api/containers", json=_payload(carrier, carrier_id, "gone")).json()

    host_before = conn.execute(
        "SELECT hostname, status, created_at, updated_at, deleted_at "
        "FROM bare_metals WHERE id = %s",
        (host["id"],),
    ).fetchone()
    other_before = conn.execute(
        "SELECT name, deleted_at FROM containers WHERE id = %s", (keep["id"],)
    ).fetchone()
    rows_before = _total_container_rows(conn)

    assert client.delete(f"/api/containers/{target['id']}").status_code == 204

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
            "SELECT name, deleted_at FROM containers WHERE id = %s", (keep["id"],)
        ).fetchone()
        == other_before
    )
    assert _total_container_rows(conn) == rows_before


# --------------------------------------------------------------------------- #
# AC-32：无恢复 / 批量 / include_deleted / by-name
# --------------------------------------------------------------------------- #
def test_no_out_of_scope_routes_or_params(auth_client_and_raw):
    client, _ = auth_client_and_raw
    paths = client.app.openapi()["paths"]

    forbidden_tokens = ("restore", "undelete", "purge", "trash", "batch", "deleted", "by-name")
    offenders = [
        path
        for path in paths
        if path.startswith("/api/containers")
        and any(token in path.lower() for token in forbidden_tokens)
    ]
    assert offenders == [], f"不存在恢复 / 批量 / by-name 端点：{offenders}"

    list_op = paths["/api/containers"]["get"]
    param_names = {p.get("name") for p in list_op.get("parameters", [])}
    assert not any("deleted" in (name or "").lower() for name in param_names)
    assert not any("include" in (name or "").lower() for name in param_names)


# --------------------------------------------------------------------------- #
# AC-33 / AC-34：载体（BM / VM）有活跃 Container → 拒绝删除载体（409）
# --------------------------------------------------------------------------- #
def test_bare_metal_with_active_container_cannot_be_deleted(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    assert (
        client.post("/api/containers", json=_payload("BARE_METAL", host["id"], "web")).status_code
        == 201
    )

    response = client.delete(f"/api/bare-metals/{host['id']}")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(detail["code"] == "ACTIVE_CHILDREN_EXIST" for detail in body["error"]["details"])
    assert (
        conn.execute("SELECT deleted_at FROM bare_metals WHERE id = %s", (host["id"],)).fetchone()[
            0
        ]
        is None
    )


def test_virtual_machine_with_active_container_cannot_be_deleted(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    vm = _create_vm(client, host["id"], "vm1")
    assert (
        client.post(
            "/api/containers", json=_payload("VIRTUAL_MACHINE", vm["id"], "web")
        ).status_code
        == 201
    )

    response = client.delete(f"/api/virtual-machines/{vm['id']}")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(detail["code"] == "ACTIVE_CHILDREN_EXIST" for detail in body["error"]["details"])
    assert (
        conn.execute(
            "SELECT deleted_at FROM virtual_machines WHERE id = %s", (vm["id"],)
        ).fetchone()[0]
        is None
    )


# --------------------------------------------------------------------------- #
# AC-35：软删 Container 后载体可删（BM / VM 均成立）
# --------------------------------------------------------------------------- #
def test_carrier_deletable_after_container_soft_deleted(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm_host = _create_bm(client, cluster_id, "n1")
    vm_host = _create_bm(client, cluster_id, "n2")
    vm = _create_vm(client, vm_host["id"], "vm1")

    bm_container = client.post(
        "/api/containers", json=_payload("BARE_METAL", bm_host["id"], "web")
    ).json()
    vm_container = client.post(
        "/api/containers", json=_payload("VIRTUAL_MACHINE", vm["id"], "web")
    ).json()

    assert client.delete(f"/api/containers/{vm_container['id']}").status_code == 204
    assert client.delete(f"/api/virtual-machines/{vm['id']}").status_code == 204

    assert client.delete(f"/api/containers/{bm_container['id']}").status_code == 204
    assert client.delete(f"/api/bare-metals/{bm_host['id']}").status_code == 204


# --------------------------------------------------------------------------- #
# 认证覆盖：未认证 → 401（不改变数据）
# --------------------------------------------------------------------------- #
def test_unauthenticated_requires_session(app_client_and_raw):
    client, conn = app_client_and_raw
    response = client.get("/api/containers")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert _total_container_rows(conn) == 0
