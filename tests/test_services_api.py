"""F008 Service API 行为测试（AC-01 ~ AC-49 的产品路径部分）。

数据库夹具 ``auth_client_and_raw`` 同时提供产品客户端与**绕过应用层**的原始 psycopg
连接，用于断言数据库侧状态与预置软删行。
"""

from __future__ import annotations

import pytest

READ_FIELDS = {
    "id",
    "name",
    "service_type",
    "url",
    "port",
    "protocol",
    "owner",
    "description",
    "carriers",
    "created_at",
    "updated_at",
}

OPTIONAL_FIELDS = ("service_type", "url", "port", "protocol", "owner", "description")

FORBIDDEN_FIELDS = {
    "deleted_at",
    "status",
    "state",
    "cluster_id",
    "cluster",
    "cluster_name",
    "bare_metal_id",
    "virtual_machine_id",
    "container_id",
    "credential",
    "credential_reference",
    "health",
    "health_information",
    "data_center",
    "location",
    "room",
    "rack",
    "site",
    "campus",
}

AC49_ZERO_CARRIER_SQL = """
SELECT count(*) FROM services s
WHERE s.deleted_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM service_carriers sc WHERE sc.service_id = s.id)
"""


# --------------------------------------------------------------------------- #
# 夹具辅助
# --------------------------------------------------------------------------- #
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


def _create_container(client, carrier_type: str, carrier_id: int, name: str) -> dict:
    response = client.post(
        "/api/containers",
        json={"carrier_type": carrier_type, "carrier_id": carrier_id, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _carriers(*refs: tuple[str, int]) -> list[dict]:
    return [{"carrier_type": t, "carrier_id": i} for t, i in refs]


def _payload(name: str, carriers: list[dict], **extra) -> dict:
    return {"name": name, "carriers": carriers, **extra}


def _count(conn, sql: str, params=()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def _active_service_count(conn) -> int:
    return _count(conn, "SELECT count(*) FROM services WHERE deleted_at IS NULL")


def _total_service_count(conn) -> int:
    return _count(conn, "SELECT count(*) FROM services")


def _total_carrier_rows(conn) -> int:
    return _count(conn, "SELECT count(*) FROM service_carriers")


# --------------------------------------------------------------------------- #
# AC-01 / AC-02 / AC-03：以三种载体登记成功；字段集合恰 11
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("carrier", ["BARE_METAL", "VIRTUAL_MACHINE", "CONTAINER"])
def test_create_returns_closed_field_set(auth_client_and_raw, carrier):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    if carrier == "BARE_METAL":
        carrier_id = host["id"]
    elif carrier == "VIRTUAL_MACHINE":
        carrier_id = _create_vm(client, host["id"], "vm1")["id"]
    else:
        carrier_id = _create_container(
            client, "VIRTUAL_MACHINE", _create_vm(client, host["id"], "vm2")["id"], "c1"
        )["id"]

    response = client.post("/api/services", json=_payload("mon", _carriers((carrier, carrier_id))))

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == READ_FIELDS
    assert not (FORBIDDEN_FIELDS & set(body))
    assert body["name"] == "mon"
    assert body["carriers"] == [{"carrier_type": carrier, "carrier_id": carrier_id}]
    for field in OPTIONAL_FIELDS:
        assert field in body and body[field] is None
    assert _active_service_count(conn) == 1
    assert _total_carrier_rows(conn) == 1


# --------------------------------------------------------------------------- #
# AC-04 / AC-16：多载体登记，全部保留；顺序稳定按 (rank, id)
# --------------------------------------------------------------------------- #
def test_create_with_three_carriers_keeps_all_and_stable_order(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    vm = _create_vm(client, host["id"], "vm1")
    container = _create_container(client, "VIRTUAL_MACHINE", vm["id"], "c1")

    # 故意以「CONTAINER, VIRTUAL_MACHINE, BARE_METAL」的逆序请求。
    response = client.post(
        "/api/services",
        json=_payload(
            "mon",
            _carriers(
                ("CONTAINER", container["id"]),
                ("VIRTUAL_MACHINE", vm["id"]),
                ("BARE_METAL", host["id"]),
            ),
        ),
    )

    assert response.status_code == 201, response.text
    expected = sorted(
        [
            {"carrier_type": "BARE_METAL", "carrier_id": host["id"]},
            {"carrier_type": "VIRTUAL_MACHINE", "carrier_id": vm["id"]},
            {"carrier_type": "CONTAINER", "carrier_id": container["id"]},
        ],
        key=lambda c: (
            {"BARE_METAL": 0, "VIRTUAL_MACHINE": 1, "CONTAINER": 2}[c["carrier_type"]],
            c["carrier_id"],
        ),
    )
    assert response.json()["carriers"] == expected
    detail = client.get(f"/api/services/{response.json()['id']}").json()
    assert detail["carriers"] == expected, "多次读取顺序逐字节一致"
    assert _total_carrier_rows(conn) == 3


# --------------------------------------------------------------------------- #
# AC-05 / AC-06 / AC-07：name 必填；carriers 必填 / 非空 → 400，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["MISSING", 123, None])
def test_invalid_name_returns_400_without_write(auth_client_and_raw, name):
    client, conn = auth_client_and_raw
    payload = _payload("x", _carriers(("BARE_METAL", 1)))
    if name == "MISSING":
        payload.pop("name")
    else:
        payload["name"] = name

    response = client.post("/api/services", json=payload)

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(d["field"] == "name" for d in body["error"]["details"])
    assert _total_service_count(conn) == 0
    assert _total_carrier_rows(conn) == 0


@pytest.mark.parametrize("carriers", ["MISSING", []])
def test_missing_or_empty_carriers_returns_400_without_write(auth_client_and_raw, carriers):
    client, conn = auth_client_and_raw
    payload = {"name": "mon"}
    if carriers != "MISSING":
        payload["carriers"] = carriers
    response = client.post("/api/services", json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert any(d["field"] == "carriers" for d in response.json()["error"]["details"])
    assert _total_service_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-08 / AC-10：任一载体无效 / 类型与标识不一致 → 404 且无写入
# --------------------------------------------------------------------------- #
def test_any_invalid_carrier_rejects_whole_request_without_write(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    response = client.post(
        "/api/services",
        json=_payload("mon", _carriers(("BARE_METAL", host["id"]), ("VIRTUAL_MACHINE", 999999))),
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["details"] == []
    assert _total_service_count(conn) == 0
    assert _total_carrier_rows(conn) == 0

    # 类型与标识不一致：VM 类型的标识传入真实 BareMetal 的 id。
    mismatch = client.post(
        "/api/services", json=_payload("mon", _carriers(("VIRTUAL_MACHINE", host["id"])))
    )
    assert mismatch.status_code == 404
    assert _total_service_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-09 / AC-12：请求 schema 封闭（越界字段 / 载体类型）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "carrier_type",
    ["CLUSTER", "NETWORK_INTERFACE", "IP_ADDRESS", "SERVICE", "BARE-METAL"],
)
def test_non_carrier_types_rejected(auth_client_and_raw, carrier_type):
    client, conn = auth_client_and_raw
    response = client.post("/api/services", json=_payload("mon", _carriers((carrier_type, 1))))
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_service_count(conn) == 0


@pytest.mark.parametrize(
    "extra",
    [
        {"id": 1},
        {"status": "RUNNING"},
        {"cluster_id": 1},
        {"cluster_name": "c"},
        {"deleted_at": None},
        {"credential_reference": "x"},
        {"health_information": "ok"},
        {"bare_metal_id": 1},
        {"carrier_type": "BARE_METAL"},
        {"carrier_id": 1},
        {"data_center": "dc"},
        {"monitor": "x"},
    ],
)
def test_unknown_or_forbidden_create_fields_rejected(auth_client_and_raw, extra):
    client, conn = auth_client_and_raw
    payload = {**_payload("mon", _carriers(("BARE_METAL", 1))), **extra}
    response = client.post("/api/services", json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_service_count(conn) == 0


def test_carrier_ref_schema_is_closed(auth_client_and_raw):
    client, _ = auth_client_and_raw
    response = client.post(
        "/api/services",
        json=_payload("mon", [{"carrier_type": "BARE_METAL", "carrier_id": 1, "name": "x"}]),
    )
    assert response.status_code == 400
    assert any(d["field"].startswith("carriers") for d in response.json()["error"]["details"])


# --------------------------------------------------------------------------- #
# AC-06 语义 / 重复载体：同一请求内重复 (carrier_type, carrier_id) → 400 DUPLICATE
# --------------------------------------------------------------------------- #
def test_duplicate_carrier_in_same_request_returns_400_duplicate(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    response = client.post(
        "/api/services",
        json=_payload("mon", _carriers(("BARE_METAL", host["id"]), ("BARE_METAL", host["id"]))),
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    detail = next(d for d in body["error"]["details"] if d["field"] == "carriers")
    assert detail["code"] == "DUPLICATE"
    assert _total_service_count(conn) == 0
    assert _total_carrier_rows(conn) == 0


# --------------------------------------------------------------------------- #
# AC-13 / AC-14：可选字段缺失返 null；纯文本原样往返（不结构化）
# --------------------------------------------------------------------------- #
def test_optional_fields_roundtrip_verbatim(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    values = {
        "service_type": "自研",
        "url": "这不是一个 URL",
        "port": "abc",
        "protocol": "自定义协议",
        "owner": "ops",
        "description": "第一行\n第二行",
    }
    created = client.post(
        "/api/services",
        json=_payload("共享存储服务", _carriers(("BARE_METAL", host["id"])), **values),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    for field, value in values.items():
        assert body[field] == value, field

    reread = client.get(f"/api/services/{body['id']}").json()
    for field, value in values.items():
        assert reread[field] == value, field


@pytest.mark.parametrize("name", ["", "  padded  ", "has/slash"])
def test_undefined_name_constraints_not_enforced(auth_client_and_raw, name):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    response = client.post(
        "/api/services", json=_payload(name, _carriers(("BARE_METAL", host["id"])))
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == name


# --------------------------------------------------------------------------- #
# AC-22 / AC-24 / AC-25 / AC-27：全局唯一、大小写敏感、与其它资源独立、软删释放
# --------------------------------------------------------------------------- #
def test_duplicate_active_name_returns_409(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    assert (
        client.post(
            "/api/services", json=_payload("mon", _carriers(("BARE_METAL", host["id"])))
        ).status_code
        == 201
    )
    response = client.post(
        "/api/services", json=_payload("mon", _carriers(("BARE_METAL", host["id"])))
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    detail = next(d for d in body["error"]["details"] if d["field"] == "name")
    assert detail["code"] == "DUPLICATE"
    assert _active_service_count(conn) == 1


def test_global_uniqueness_across_clusters(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    host_a = _create_bm(client, cluster_a, "n1")
    host_b = _create_bm(client, cluster_b, "n1")
    assert (
        client.post(
            "/api/services", json=_payload("mon", _carriers(("BARE_METAL", host_a["id"])))
        ).status_code
        == 201
    )
    # 不同 Cluster 上同名活跃 Service → 仍 409（全局唯一，不按 Cluster 限定）。
    conflict = client.post(
        "/api/services", json=_payload("mon", _carriers(("BARE_METAL", host_b["id"])))
    )
    assert conflict.status_code == 409
    assert (
        _count(conn, "SELECT count(*) FROM services WHERE name='mon' AND deleted_at IS NULL") == 1
    )


def test_service_name_independent_from_container_name(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    # 同一载体上 Container 名与 Service 名相同 → 均成功（唯一性各自独立）。
    assert _create_container(client, "BARE_METAL", host["id"], "mon")["name"] == "mon"
    assert (
        client.post(
            "/api/services", json=_payload("mon", _carriers(("BARE_METAL", host["id"])))
        ).status_code
        == 201
    )


def test_case_sensitive_names_coexist(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    for name in ("mon", "MON"):
        assert (
            client.post(
                "/api/services", json=_payload(name, _carriers(("BARE_METAL", host["id"])))
            ).status_code
            == 201
        )


def test_soft_delete_releases_name(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post(
        "/api/services", json=_payload("mon", _carriers(("BARE_METAL", host["id"])))
    ).json()
    assert client.delete(f"/api/services/{created['id']}").status_code == 204
    deleted_at_after = conn.execute(
        "SELECT deleted_at FROM services WHERE id = %s", (created["id"],)
    ).fetchone()[0]

    recreated = client.post(
        "/api/services", json=_payload("mon", _carriers(("BARE_METAL", host["id"])))
    )
    assert recreated.status_code == 201
    assert recreated.json()["id"] != created["id"]
    assert (
        conn.execute("SELECT deleted_at FROM services WHERE id = %s", (created["id"],)).fetchone()[
            0
        ]
        == deleted_at_after
    )


# --------------------------------------------------------------------------- #
# AC-17 / AC-18 / AC-19：同一载体被多 Service 绑定；跨 Cluster 共享只登记一次
# --------------------------------------------------------------------------- #
def test_same_carrier_bound_by_multiple_services(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    for name in ("s1", "s2"):
        assert (
            client.post(
                "/api/services", json=_payload(name, _carriers(("BARE_METAL", host["id"])))
            ).status_code
            == 201
        )
    listed = client.get(
        "/api/services", params={"carrier_type": "BARE_METAL", "carrier_id": host["id"]}
    ).json()
    assert sorted(item["name"] for item in listed["items"]) == ["s1", "s2"]
    assert listed["total"] == 2


def test_cross_cluster_carriers_register_once_and_queryable(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    host_a = _create_bm(client, cluster_a, "n1")
    host_b = _create_bm(client, cluster_b, "n1")

    created = client.post(
        "/api/services",
        json=_payload("mon", _carriers(("BARE_METAL", host_a["id"]), ("BARE_METAL", host_b["id"]))),
    )
    assert created.status_code == 201
    assert (
        _count(conn, "SELECT count(*) FROM services WHERE name='mon' AND deleted_at IS NULL") == 1
    )

    for host in (host_a, host_b):
        found = client.get(
            "/api/services", params={"carrier_type": "BARE_METAL", "carrier_id": host["id"]}
        ).json()
        assert [item["id"] for item in found["items"]] == [created.json()["id"]]


# --------------------------------------------------------------------------- #
# AC-29 / AC-30：列表分页 Empty；详情 404
# --------------------------------------------------------------------------- #
def test_empty_list_and_detail_not_found(auth_client_and_raw):
    client, conn = auth_client_and_raw
    assert client.get("/api/services").json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 50,
    }
    assert client.get("/api/services/999999").status_code == 404

    ghost = conn.execute(
        "INSERT INTO services (name, deleted_at) VALUES ('ghost', now()) RETURNING id"
    ).fetchone()[0]
    assert client.get(f"/api/services/{ghost}").status_code == 404


def test_pagination(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    for index in range(3):
        assert (
            client.post(
                "/api/services", json=_payload(f"s{index}", _carriers(("BARE_METAL", host["id"])))
            ).status_code
            == 201
        )
    first = client.get("/api/services", params={"page_size": 2, "page": 1}).json()
    assert first["total"] == 3
    assert [item["name"] for item in first["items"]] == ["s0", "s1"]
    second = client.get("/api/services", params={"page_size": 2, "page": 2}).json()
    assert [item["name"] for item in second["items"]] == ["s2"]


# --------------------------------------------------------------------------- #
# AC-31 / AC-32：按载体限定读取（三类型）；成对约束
# --------------------------------------------------------------------------- #
def test_list_by_carrier_semantics_three_types(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_a, "n1")
    vm = _create_vm(client, host["id"], "vm1")
    container = _create_container(client, "VIRTUAL_MACHINE", vm["id"], "c1")

    # 载体不存在 → 404（三类型均成立）。
    for carrier_type in ("BARE_METAL", "VIRTUAL_MACHINE", "CONTAINER"):
        assert (
            client.get(
                "/api/services", params={"carrier_type": carrier_type, "carrier_id": 999999}
            ).status_code
            == 404
        )

    # 载体存在但无活跃绑定 → 200 空集（三类型）。
    for carrier_type, carrier_id in (
        ("BARE_METAL", host["id"]),
        ("VIRTUAL_MACHINE", vm["id"]),
        ("CONTAINER", container["id"]),
    ):
        empty = client.get(
            "/api/services", params={"carrier_type": carrier_type, "carrier_id": carrier_id}
        )
        assert empty.status_code == 200
        assert empty.json()["items"] == []
        assert empty.json()["total"] == 0

    # 已删载体 → 404。
    gone = conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname, deleted_at) "
        "VALUES (%s, 'gone', now()) RETURNING id",
        (cluster_a,),
    ).fetchone()[0]
    assert (
        client.get(
            "/api/services", params={"carrier_type": "BARE_METAL", "carrier_id": gone}
        ).status_code
        == 404
    )

    # 只返回绑定到该载体的 Service。
    client.post("/api/services", json=_payload("bm-svc", _carriers(("BARE_METAL", host["id"]))))
    client.post("/api/services", json=_payload("vm-svc", _carriers(("VIRTUAL_MACHINE", vm["id"]))))
    client.post("/api/services", json=_payload("ct-svc", _carriers(("CONTAINER", container["id"]))))

    for name, carrier_type, carrier_id in (
        ("bm-svc", "BARE_METAL", host["id"]),
        ("vm-svc", "VIRTUAL_MACHINE", vm["id"]),
        ("ct-svc", "CONTAINER", container["id"]),
    ):
        found = client.get(
            "/api/services", params={"carrier_type": carrier_type, "carrier_id": carrier_id}
        ).json()
        assert [item["name"] for item in found["items"]] == [name]


def test_list_by_carrier_requires_both_params(auth_client_and_raw):
    client, _ = auth_client_and_raw
    only_type = client.get("/api/services", params={"carrier_type": "BARE_METAL"})
    assert only_type.status_code == 400
    assert any(d["field"] == "carrier_id" for d in only_type.json()["error"]["details"])

    only_id = client.get("/api/services", params={"carrier_id": 1})
    assert only_id.status_code == 400
    assert any(d["field"] == "carrier_type" for d in only_id.json()["error"]["details"])


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"carrier_type": "NOPE", "carrier_id": 1}, "carrier_type"),
        ({"carrier_type": "BARE_METAL", "carrier_id": "abc"}, "carrier_id"),
        ({"page": 0}, "page"),
        ({"page_size": 0}, "page_size"),
        ({"page_size": 201}, "page_size"),
    ],
)
def test_list_invalid_params(auth_client_and_raw, params, field):
    client, _ = auth_client_and_raw
    response = client.get("/api/services", params=params)
    assert response.status_code == 400, response.text
    assert any(d["field"] == field for d in response.json()["error"]["details"]), response.text


# --------------------------------------------------------------------------- #
# AC-33：已删 Service 不出现在列表 / total / 按载体结果；按 id → 404
# --------------------------------------------------------------------------- #
def test_soft_deleted_row_excluded_from_reads(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    ghost = conn.execute(
        "INSERT INTO services (name, deleted_at) VALUES ('ghost', now()) RETURNING id"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO service_carriers (service_id, bare_metal_id) VALUES (%s, %s)",
        (ghost, host["id"]),
    )

    listed = client.get("/api/services").json()
    assert listed["total"] == 0
    assert listed["items"] == []
    by_carrier = client.get(
        "/api/services", params={"carrier_type": "BARE_METAL", "carrier_id": host["id"]}
    ).json()
    assert by_carrier["total"] == 0
    assert client.get(f"/api/services/{ghost}").status_code == 404


# --------------------------------------------------------------------------- #
# AC-34 / AC-35 / AC-36：PATCH
# --------------------------------------------------------------------------- #
def test_patch_optional_fields_and_clear(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post(
        "/api/services",
        json=_payload("mon", _carriers(("BARE_METAL", host["id"])), url="u", owner="ops"),
    ).json()

    patched = client.patch(f"/api/services/{created['id']}", json={"port": "8080", "owner": None})
    assert patched.status_code == 200
    body = patched.json()
    assert body["port"] == "8080"
    assert body["owner"] is None
    assert body["url"] == "u"
    assert body["id"] == created["id"]
    assert body["name"] == created["name"]
    assert body["carriers"] == created["carriers"]
    assert body["created_at"] == created["created_at"]

    reread = client.get(f"/api/services/{created['id']}").json()
    assert reread == body


def test_patch_rejects_unknown_and_immutable(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post(
        "/api/services", json=_payload("mon", _carriers(("BARE_METAL", host["id"])))
    ).json()

    empty = client.patch(f"/api/services/{created['id']}", json={})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "VALIDATION_ERROR"

    for field, value in (
        ("name", "x"),
        ("carriers", []),
        ("carrier_type", "BARE_METAL"),
        ("carrier_id", 1),
        ("id", 1),
        ("deleted_at", None),
        ("cluster_id", 1),
        ("status", "RUNNING"),
        ("credential_reference", "x"),
        ("health_information", "x"),
    ):
        forbidden = client.patch(f"/api/services/{created['id']}", json={field: value})
        assert forbidden.status_code == 400, field
        assert any(d["field"] == field for d in forbidden.json()["error"]["details"]), field


def test_patch_missing_or_deleted_returns_404(auth_client_and_raw):
    client, _ = auth_client_and_raw
    assert client.patch("/api/services/999999", json={"owner": "x"}).status_code == 404
    conn = auth_client_and_raw[1]
    ghost = conn.execute(
        "INSERT INTO services (name, deleted_at) VALUES ('ghost', now()) RETURNING id"
    ).fetchone()[0]
    assert client.patch(f"/api/services/{ghost}", json={"owner": "x"}).status_code == 404


# --------------------------------------------------------------------------- #
# AC-37 / AC-38 / AC-48：逻辑删除；不级联；绑定行不被修改 / 删除
# --------------------------------------------------------------------------- #
def test_delete_returns_204_and_preserves_rows(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post(
        "/api/services", json=_payload("mon", _carriers(("BARE_METAL", host["id"])))
    ).json()

    host_before = conn.execute(
        "SELECT hostname, status, created_at, updated_at, deleted_at FROM bare_metals WHERE id=%s",
        (host["id"],),
    ).fetchone()
    bindings_before = conn.execute(
        "SELECT id, service_id, bare_metal_id, virtual_machine_id, container_id "
        "FROM service_carriers WHERE service_id=%s",
        (created["id"],),
    ).fetchall()

    response = client.delete(f"/api/services/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    row = conn.execute("SELECT deleted_at FROM services WHERE id=%s", (created["id"],)).fetchone()
    assert row is not None and row[0] is not None, "逻辑删除不得物理删除行。"
    assert (
        conn.execute(
            "SELECT hostname, status, created_at, updated_at, deleted_at "
            "FROM bare_metals WHERE id=%s",
            (host["id"],),
        ).fetchone()
        == host_before
    )
    assert (
        conn.execute(
            "SELECT id, service_id, bare_metal_id, virtual_machine_id, container_id "
            "FROM service_carriers WHERE service_id=%s",
            (created["id"],),
        ).fetchall()
        == bindings_before
    ), "软删 Service 后绑定行不得被修改 / 删除"

    assert client.get("/api/services").json()["total"] == 0
    assert client.delete(f"/api/services/{created['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# AC-41 / AC-42 / AC-43 / AC-44：三载体父删子拦（真实端到端）
# --------------------------------------------------------------------------- #
def test_bare_metal_with_active_service_cannot_be_deleted(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    client.post("/api/services", json=_payload("mon", _carriers(("BARE_METAL", host["id"]))))

    response = client.delete(f"/api/bare-metals/{host['id']}")
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(d["code"] == "ACTIVE_CHILDREN_EXIST" for d in body["error"]["details"])
    assert (
        conn.execute("SELECT deleted_at FROM bare_metals WHERE id=%s", (host["id"],)).fetchone()[0]
        is None
    )


def test_virtual_machine_with_active_service_cannot_be_deleted(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    vm = _create_vm(client, host["id"], "vm1")
    client.post("/api/services", json=_payload("mon", _carriers(("VIRTUAL_MACHINE", vm["id"]))))

    response = client.delete(f"/api/virtual-machines/{vm['id']}")
    assert response.status_code == 409, response.text
    assert any(d["code"] == "ACTIVE_CHILDREN_EXIST" for d in response.json()["error"]["details"])
    assert (
        conn.execute("SELECT deleted_at FROM virtual_machines WHERE id=%s", (vm["id"],)).fetchone()[
            0
        ]
        is None
    )


def test_container_with_active_service_cannot_be_deleted(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    vm = _create_vm(client, host["id"], "vm1")
    container = _create_container(client, "VIRTUAL_MACHINE", vm["id"], "c1")
    client.post("/api/services", json=_payload("mon", _carriers(("CONTAINER", container["id"]))))

    response = client.delete(f"/api/containers/{container['id']}")
    assert response.status_code == 409, response.text
    assert any(d["code"] == "ACTIVE_CHILDREN_EXIST" for d in response.json()["error"]["details"])
    assert (
        conn.execute(
            "SELECT deleted_at FROM containers WHERE id=%s", (container["id"],)
        ).fetchone()[0]
        is None
    )


# --------------------------------------------------------------------------- #
# AC-39：软删 Service 后其载体可删（三类型）
# --------------------------------------------------------------------------- #
def test_carrier_deletable_after_service_soft_deleted(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm_host = _create_bm(client, cluster_id, "n1")
    vm_host = _create_bm(client, cluster_id, "n2")
    vm = _create_vm(client, vm_host["id"], "vm1")
    container = _create_container(client, "VIRTUAL_MACHINE", vm["id"], "c1")

    bm_svc = client.post(
        "/api/services", json=_payload("s-bm", _carriers(("BARE_METAL", bm_host["id"])))
    ).json()
    vm_svc = client.post(
        "/api/services", json=_payload("s-vm", _carriers(("VIRTUAL_MACHINE", vm["id"])))
    ).json()
    ct_svc = client.post(
        "/api/services", json=_payload("s-ct", _carriers(("CONTAINER", container["id"])))
    ).json()

    assert client.delete(f"/api/services/{ct_svc['id']}").status_code == 204
    assert client.delete(f"/api/containers/{container['id']}").status_code == 204

    assert client.delete(f"/api/services/{vm_svc['id']}").status_code == 204
    assert client.delete(f"/api/virtual-machines/{vm['id']}").status_code == 204

    assert client.delete(f"/api/services/{bm_svc['id']}").status_code == 204
    assert client.delete(f"/api/bare-metals/{bm_host['id']}").status_code == 204


# --------------------------------------------------------------------------- #
# AC-40 / AC-48：无恢复 / 批量 / by-name / 解绑路径；载体写入恰 5 端点
# --------------------------------------------------------------------------- #
def test_no_out_of_scope_routes_or_params(auth_client_and_raw):
    client, _ = auth_client_and_raw
    paths = client.app.openapi()["paths"]
    service_paths = {path for path in paths if path.startswith("/api/services")}
    assert service_paths == {"/api/services", "/api/services/{service_id}"}

    forbidden_tokens = (
        "restore",
        "undelete",
        "purge",
        "trash",
        "batch",
        "deleted",
        "by-name",
        "carrier",
    )
    offenders = [
        path for path in service_paths if any(token in path.lower() for token in forbidden_tokens)
    ]
    assert offenders == [], f"不存在恢复 / 批量 / by-name / carriers 子资源端点：{offenders}"

    list_op = paths["/api/services"]["get"]
    param_names = {p.get("name") for p in list_op.get("parameters", [])}
    assert param_names == {"page", "page_size", "carrier_type", "carrier_id"}


# --------------------------------------------------------------------------- #
# AC-49：零载体不变式（回归查询 = 0）
# --------------------------------------------------------------------------- #
def test_ac49_zero_carrier_invariant(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post(
        "/api/services", json=_payload("mon", _carriers(("BARE_METAL", host["id"])))
    ).json()
    client.delete(f"/api/services/{created['id']}")

    assert _count(conn, AC49_ZERO_CARRIER_SQL) == 0


# --------------------------------------------------------------------------- #
# AC-53：未认证 → 401 且不改变数据
# --------------------------------------------------------------------------- #
def test_unauthenticated_requires_session(app_client_and_raw):
    client, conn = app_client_and_raw
    response = client.get("/api/services")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert _total_service_count(conn) == 0
