"""F020 IPAddressRange API 行为测试（AC-01 ~ AC-27 的产品路径部分）。

数据库夹具 ``auth_client_and_raw`` 同时提供产品客户端与**绕过应用层**的原始 psycopg
连接，用于断言数据库侧状态与预置软删行；约束证伪见
``tests/database/test_ip_address_ranges_constraints.py``，并发见
``tests/test_ip_address_ranges_concurrency.py``。
"""

from __future__ import annotations

import pytest

READ_FIELDS = {
    "id",
    "cluster_id",
    "start_ip",
    "end_ip",
    # F022 纯增量：3 个可选元数据字段。
    "name",
    "subnet_mask",
    "vlan",
    "created_at",
    "updated_at",
}

# F022：name / vlan 已成为合法字段，从禁令牌移除；其余保持不变。
FORBIDDEN_READ_FIELDS = {
    "deleted_at",
    "status",
    "state",
    "description",
    "purpose",
    "cidr",
    "prefix_length",
    "network_address",
    "broadcast_address",
    "gateway",
    "dhcp",
    "dns",
    "capacity",
    "usage",
    "utilization",
    "assigned_at",
    "reclaimed_at",
    "assigned_to",
    "address_pool",
}


# --------------------------------------------------------------------------- #
# 夹具辅助
# --------------------------------------------------------------------------- #
def _create_cluster(client, name: str) -> int:
    response = client.post("/api/clusters", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_bm(client, cluster_id: int, hostname: str = "n1") -> int:
    response = client.post(
        "/api/bare-metals", json={"cluster_id": cluster_id, "hostname": hostname}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_nic(client, bare_metal_id: int, name: str = "eth0") -> int:
    response = client.post(
        "/api/network-interfaces",
        json={
            "bare_metal_id": bare_metal_id,
            "name": name,
            "technology_type": "Ethernet",
            "purpose": "Business",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_ip(client, network_interface_id: int, ip_address: str) -> dict:
    response = client.post(
        "/api/ip-addresses",
        json={"network_interface_id": network_interface_id, "ip_address": ip_address},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_range(client, cluster_id: int, start_ip: str, end_ip: str):
    return client.post(
        "/api/ip-address-ranges",
        json={"cluster_id": cluster_id, "start_ip": start_ip, "end_ip": end_ip},
    )


def _raw_cluster(conn, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO clusters (name, deleted_at) VALUES (%s, now()) RETURNING id", (name,)
        ).fetchone()[0]
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[
        0
    ]


def _raw_range(conn, cluster_id: int, start_ip: int, end_ip: int, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip, deleted_at) "
            "VALUES (%s, %s, %s, now()) RETURNING id",
            (cluster_id, start_ip, end_ip),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip) "
        "VALUES (%s, %s, %s) RETURNING id",
        (cluster_id, start_ip, end_ip),
    ).fetchone()[0]


def _active_range_count(conn) -> int:
    return conn.execute(
        "SELECT count(*) FROM ip_address_ranges WHERE deleted_at IS NULL"
    ).fetchone()[0]


def _total_range_count(conn) -> int:
    return conn.execute("SELECT count(*) FROM ip_address_ranges").fetchone()[0]


# --------------------------------------------------------------------------- #
# AC-01：未认证
# --------------------------------------------------------------------------- #
def test_ac01_unauthenticated_is_rejected_without_data(app_client):
    assert app_client.get("/api/ip-address-ranges").status_code == 401
    assert app_client.get("/api/ip-address-ranges/1").status_code == 401
    assert (
        app_client.post(
            "/api/ip-address-ranges",
            json={"cluster_id": 1, "start_ip": "10.0.0.1", "end_ip": "10.0.0.2"},
        ).status_code
        == 401
    )
    assert (
        app_client.patch("/api/ip-address-ranges/1", json={"start_ip": "10.0.0.1"}).status_code
        == 401
    )
    assert app_client.delete("/api/ip-address-ranges/1").status_code == 401


# --------------------------------------------------------------------------- #
# AC-02 / AC-09：登记成功、字段集合封闭、规范化
# --------------------------------------------------------------------------- #
def test_ac02_create_returns_closed_field_set(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    response = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == READ_FIELDS
    assert not (FORBIDDEN_READ_FIELDS & set(body))
    assert body["cluster_id"] == cluster_id
    assert body["start_ip"] == "10.0.0.1"
    assert body["end_ip"] == "10.0.0.255"
    assert _active_range_count(conn) == 1


def test_ac09_leading_zeros_are_normalized_on_store_and_read(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    response = _create_range(client, cluster_id, "010.000.000.001", "010.000.000.255")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["start_ip"] == "10.0.0.1"
    assert body["end_ip"] == "10.0.0.255"
    detail = client.get(f"/api/ip-address-ranges/{body['id']}").json()
    assert detail["start_ip"] == "10.0.0.1"
    assert detail["end_ip"] == "10.0.0.255"
    stored = conn.execute(
        "SELECT start_ip, end_ip FROM ip_address_ranges WHERE id = %s", (body["id"],)
    ).fetchone()
    assert stored == (167772161, 167772415)


# --------------------------------------------------------------------------- #
# AC-03：请求字段封闭
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "extra",
    [
        {"description": "x"},
        {"status": "ACTIVE"},
        {"deleted_at": None},
        {"id": 1},
        {"created_at": "2026-01-01T00:00:00Z"},
        {"cidr": "10.0.0.0/24"},
        {"prefix_length": 24},
        {"usage": 1},
    ],
)
def test_ac03_unknown_create_fields_are_rejected(auth_client_and_raw, extra):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    payload = {
        "cluster_id": cluster_id,
        "start_ip": "10.0.0.1",
        "end_ip": "10.0.0.2",
        **extra,
    }
    response = client.post("/api/ip-address-ranges", json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_range_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-04 / AC-05：cluster_id 必填 / 活跃
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cluster_id", ["MISSING", "abc", None])
def test_ac04_missing_or_invalid_cluster_id(auth_client_and_raw, cluster_id):
    client, conn = auth_client_and_raw
    payload = {"start_ip": "10.0.0.1", "end_ip": "10.0.0.2"}
    if cluster_id != "MISSING":
        payload["cluster_id"] = cluster_id
    response = client.post("/api/ip-address-ranges", json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert any(d["field"] == "cluster_id" for d in response.json()["error"]["details"])
    assert _total_range_count(conn) == 0


def test_ac05_nonexistent_or_deleted_cluster_is_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    missing = _create_range(client, 999999999, "10.0.0.1", "10.0.0.2")
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"]["code"] == "NOT_FOUND"

    deleted_id = _raw_cluster(conn, "deleted-cluster", deleted=True)
    deleted = _create_range(client, deleted_id, "10.0.0.1", "10.0.0.2")
    assert deleted.status_code == 404, deleted.text
    assert deleted.json()["error"]["code"] == "NOT_FOUND"
    assert _total_range_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-06 / AC-07 / AC-08：start / end 必填、顺序、IPv4 合法性
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", ["start_ip", "end_ip"])
@pytest.mark.parametrize("value", ["MISSING", 123, None])
def test_ac06_missing_or_non_string_bounds(auth_client_and_raw, field, value):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    payload = {"cluster_id": cluster_id, "start_ip": "10.0.0.1", "end_ip": "10.0.0.2"}
    if value == "MISSING":
        payload.pop(field)
    else:
        payload[field] = value
    response = client.post("/api/ip-address-ranges", json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_range_count(conn) == 0


def test_ac07_start_greater_than_end_is_400(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    response = _create_range(client, cluster_id, "10.0.0.10", "10.0.0.1")
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_range_count(conn) == 0


@pytest.mark.parametrize(
    "bad",
    [
        "10.0.0.256",
        "10.0.0",
        "abc",
        "1.2.3.4/24",
        "2001:db8::1",
        "",
        " 10.0.0.1",
        "10.0.0.1 ",
        "1.2.3.4.5",
    ],
)
def test_ac08_invalid_ipv4_is_400(auth_client_and_raw, bad):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    response = _create_range(client, cluster_id, bad, "10.0.0.255")
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(d["field"] == "start_ip" for d in body["error"]["details"])
    assert _total_range_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-10 / AC-11：同 Cluster 重叠拒绝 / 跨 Cluster 共存
# --------------------------------------------------------------------------- #
def test_ac10_overlap_same_cluster_is_409_overlap(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    assert _create_range(client, cluster_id, "10.0.0.1", "10.0.0.100").status_code == 201

    for start, end in [
        ("10.0.0.100", "10.0.0.200"),  # 共享端点
        ("10.0.0.50", "10.0.0.60"),  # 完全包含
        ("10.0.0.0", "10.0.0.1"),  # 部分重叠
    ]:
        response = _create_range(client, cluster_id, start, end)
        assert response.status_code == 409, response.text
        body = response.json()
        assert body["error"]["code"] == "CONFLICT"
        assert body["error"]["details"][0]["code"] == "OVERLAP"
    assert _active_range_count(conn) == 1


def test_ac10_adjacent_ranges_do_not_overlap(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    assert _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10").status_code == 201
    adjacent = _create_range(client, cluster_id, "10.0.0.11", "10.0.0.20")
    assert adjacent.status_code == 201, adjacent.text
    assert _active_range_count(conn) == 2


def test_exclusion_constraint_is_authority_and_maps_to_409(auth_client_and_raw, monkeypatch):
    """绕过应用层预检后，EXCLUDE 排它约束仍拒绝重叠并经 23P01 映射返回 409 OVERLAP。"""
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    assert _create_range(client, cluster_id, "10.0.0.1", "10.0.0.100").status_code == 201

    monkeypatch.setattr(
        "app.ip_address_ranges.repository.IpAddressRangeRepository.overlap_exists",
        lambda *args, **kwargs: False,
    )
    response = _create_range(client, cluster_id, "10.0.0.50", "10.0.0.60")
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["details"][0]["code"] == "OVERLAP"
    assert _active_range_count(conn) == 1


def test_ac11_cross_cluster_same_range_coexist(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    assert _create_range(client, cluster_a, "10.0.0.1", "10.0.0.255").status_code == 201
    assert _create_range(client, cluster_b, "10.0.0.1", "10.0.0.255").status_code == 201
    assert _active_range_count(conn) == 2


# --------------------------------------------------------------------------- #
# AC-12 / AC-13：PATCH 重校验 / 成功
# --------------------------------------------------------------------------- #
def test_ac12_patch_overlap_is_409_without_partial_write(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    first = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10").json()
    second = _create_range(client, cluster_id, "10.0.0.20", "10.0.0.30").json()

    response = client.patch(
        f"/api/ip-address-ranges/{second['id']}",
        json={"start_ip": "10.0.0.5", "end_ip": "10.0.0.25"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["details"][0]["code"] == "OVERLAP"
    # 无部分写入：原值不变。
    stored = conn.execute(
        "SELECT start_ip, end_ip FROM ip_address_ranges WHERE id = %s", (second["id"],)
    ).fetchone()
    assert stored == (167772180, 167772190)
    assert client.get(f"/api/ip-address-ranges/{first['id']}").status_code == 200


def test_ac13_patch_updates_bounds_and_is_read_back(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10").json()

    response = client.patch(
        f"/api/ip-address-ranges/{created['id']}",
        json={"end_ip": "10.0.0.50"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["start_ip"] == "10.0.0.1"
    assert body["end_ip"] == "10.0.0.50"
    assert body["cluster_id"] == created["cluster_id"]
    assert body["created_at"] == created["created_at"]
    read_back = client.get(f"/api/ip-address-ranges/{created['id']}").json()
    assert read_back["end_ip"] == "10.0.0.50"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"start_ip": None},
        {"end_ip": None},
        {"cluster_id": 1},
        {"id": 1},
        {"status": "ACTIVE"},
        {"deleted_at": None},
    ],
)
def test_patch_invalid_bodies_are_400(auth_client_and_raw, payload):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10").json()
    response = client.patch(f"/api/ip-address-ranges/{created['id']}", json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    stored = conn.execute(
        "SELECT start_ip, end_ip FROM ip_address_ranges WHERE id = %s", (created["id"],)
    ).fetchone()
    assert stored == (167772161, 167772170)


# --------------------------------------------------------------------------- #
# AC-14 / AC-15 / AC-22：软删
# --------------------------------------------------------------------------- #
def test_ac14_delete_is_soft_and_row_remains(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10").json()

    response = client.delete(f"/api/ip-address-ranges/{created['id']}")
    assert response.status_code == 204, response.text
    assert response.content == b""
    row = conn.execute(
        "SELECT deleted_at FROM ip_address_ranges WHERE id = %s", (created["id"],)
    ).fetchone()
    assert row is not None and row[0] is not None
    assert _total_range_count(conn) == 1
    assert client.get(f"/api/ip-address-ranges/{created['id']}").status_code == 404
    assert client.delete(f"/api/ip-address-ranges/{created['id']}").status_code == 404


def test_ac15_soft_deleted_range_releases_overlap(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.100").json()
    assert client.delete(f"/api/ip-address-ranges/{created['id']}").status_code == 204
    recreated = _create_range(client, cluster_id, "10.0.0.50", "10.0.0.60")
    assert recreated.status_code == 201, recreated.text


def test_ac22_deleted_range_absent_from_list_and_total(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10").json()
    assert client.delete(f"/api/ip-address-ranges/{created['id']}").status_code == 204
    listing = client.get("/api/ip-address-ranges").json()
    assert listing["items"] == []
    assert listing["total"] == 0


# --------------------------------------------------------------------------- #
# AC-16 / AC-17 / AC-18：删除守卫
# --------------------------------------------------------------------------- #
def test_ac16_active_ip_in_range_blocks_delete_without_partial_write(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm = _create_bm(client, cluster_id)
    nic = _create_nic(client, bm)
    _create_ip(client, nic, "10.0.0.5")
    created = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10").json()

    response = client.delete(f"/api/ip-address-ranges/{created['id']}")
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["details"][0]["code"] == "ACTIVE_CHILDREN_EXIST"
    deleted_at = conn.execute(
        "SELECT deleted_at FROM ip_address_ranges WHERE id = %s", (created["id"],)
    ).fetchone()[0]
    assert deleted_at is None, "命中守卫时不得写 deleted_at"


def test_ac17_after_soft_deleting_ip_range_can_be_deleted(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm = _create_bm(client, cluster_id)
    nic = _create_nic(client, bm)
    ip = _create_ip(client, nic, "10.0.0.5")
    created = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10").json()

    assert client.delete(f"/api/ip-addresses/{ip['id']}").status_code == 204
    response = client.delete(f"/api/ip-address-ranges/{created['id']}")
    assert response.status_code == 204, response.text


def test_ac17_ip_outside_range_does_not_block(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm = _create_bm(client, cluster_id)
    nic = _create_nic(client, bm)
    _create_ip(client, nic, "10.0.1.5")
    created = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10").json()

    response = client.delete(f"/api/ip-address-ranges/{created['id']}")
    assert response.status_code == 204, response.text


def test_ac18_delete_does_not_cascade(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm = _create_bm(client, cluster_id)
    nic = _create_nic(client, bm)
    ip = _create_ip(client, nic, "10.0.1.5")
    created = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10").json()

    assert client.delete(f"/api/ip-address-ranges/{created['id']}").status_code == 204

    assert conn.execute("SELECT count(*) FROM clusters").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM bare_metals").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM network_interfaces").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM ip_addresses").fetchone()[0] == 1
    assert client.get(f"/api/ip-addresses/{ip['id']}").status_code == 200, (
        "IPAddress 不得被范围段删除影响"
    )


@pytest.mark.parametrize("literal", ["10.0.1.1/16", "abc", "", " 10.0.1.1", "2001:db8::1"])
def test_delete_guard_ip_literal_semantics(auth_client_and_raw, literal):
    """`/` 前缀取地址部分；不可解析字面值跳过（不得 500），范围可删。"""
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, f"cluster-{abs(hash(literal)) % 100000}")
    bm = _create_bm(client, cluster_id)
    nic = _create_nic(client, bm)
    _create_ip(client, nic, literal)
    created = _create_range(client, cluster_id, "10.0.1.0", "10.0.1.255").json()

    response = client.delete(f"/api/ip-address-ranges/{created['id']}")
    if literal.startswith("10.0.1.1/") or literal == "10.0.1.1":
        assert response.status_code == 409, response.text
        assert response.json()["error"]["details"][0]["code"] == "ACTIVE_CHILDREN_EXIST"
    else:
        assert response.status_code == 204, response.text


# --------------------------------------------------------------------------- #
# AC-19：无状态
# --------------------------------------------------------------------------- #
def test_ac19_no_status_in_model_schema_or_endpoints(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base
    from app.ip_address_ranges.schemas import (
        IpAddressRangeCreate,
        IpAddressRangeRead,
        IpAddressRangeUpdate,
    )

    assert "status" not in {c.name for c in Base.metadata.tables["ip_address_ranges"].columns}
    for model in (IpAddressRangeCreate, IpAddressRangeUpdate, IpAddressRangeRead):
        assert "status" not in model.model_fields

    cluster_id = _create_cluster(client, "cluster-a")
    created = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.2").json()
    assert "status" not in created
    assert (
        conn.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_name='ip_address_ranges' "
            "AND column_name='status'"
        ).fetchone()[0]
        == 0
    )


# --------------------------------------------------------------------------- #
# AC-20 / AC-21：查询
# --------------------------------------------------------------------------- #
def test_ac20_list_empty_and_cluster_filter_semantics(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")

    empty = client.get(f"/api/ip-address-ranges?cluster_id={cluster_a}")
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"items": [], "total": 0, "page": 1, "page_size": 50}

    _create_range(client, cluster_a, "10.0.0.1", "10.0.0.10")
    _create_range(client, cluster_b, "10.0.0.1", "10.0.0.10")

    filtered = client.get(f"/api/ip-address-ranges?cluster_id={cluster_a}").json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["cluster_id"] == cluster_a

    all_items = client.get("/api/ip-address-ranges").json()
    assert all_items["total"] == 2

    missing_parent = client.get("/api/ip-address-ranges?cluster_id=999999999")
    assert missing_parent.status_code == 404, missing_parent.text
    assert missing_parent.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "query", ["page=0", "page=abc", "page_size=0", "page_size=201", "cluster_id=abc"]
)
def test_ac20_invalid_query_params_are_400(auth_client_and_raw, query):
    client, _ = auth_client_and_raw
    response = client.get(f"/api/ip-address-ranges?{query}")
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_ac21_detail_not_found_for_missing_and_deleted(auth_client_and_raw):
    client, conn = auth_client_and_raw
    assert client.get("/api/ip-address-ranges/999999999").status_code == 404
    cluster_id = _create_cluster(client, "cluster-a")
    deleted_id = _raw_range(conn, cluster_id, 1, 2, deleted=True)
    assert client.get(f"/api/ip-address-ranges/{deleted_id}").status_code == 404


@pytest.mark.parametrize("bad_id", ["abc", "1.5"])
def test_detail_and_delete_non_integer_id_is_400(auth_client_and_raw, bad_id):
    client, _ = auth_client_and_raw
    assert client.get(f"/api/ip-address-ranges/{bad_id}").status_code == 400
    assert client.delete(f"/api/ip-address-ranges/{bad_id}").status_code == 400


# --------------------------------------------------------------------------- #
# AC-23 / AC-24：ip_address 自由文本语义不变
# --------------------------------------------------------------------------- #
def test_ac23_ip_address_free_text_is_unchanged(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm = _create_bm(client, cluster_id)
    nic = _create_nic(client, bm)

    literal = "  weird literal  "
    ip = _create_ip(client, nic, literal)
    assert ip["ip_address"] == literal
    stored = conn.execute(
        "SELECT ip_address FROM ip_addresses WHERE id = %s", (ip["id"],)
    ).fetchone()[0]
    assert stored == literal

    # 同 Cluster 字面重复仍被拒绝（R-IP-001 不变）。
    duplicate = client.post(
        "/api/ip-addresses",
        json={"network_interface_id": nic, "ip_address": literal},
    )
    assert duplicate.status_code == 409


# --------------------------------------------------------------------------- #
# AC-25 / AC-26 / AC-27：边界（无分配 / 无 CIDR / 无 IPv6 / 无未确认能力）
# --------------------------------------------------------------------------- #
def test_ac25_26_27_no_allocation_cidr_or_extra_capabilities(auth_client_and_raw):
    client, _ = auth_client_and_raw
    paths = client.get("/openapi.json").json()["paths"]
    range_paths = [p for p in paths if p.startswith("/api/ip-address-ranges")]
    assert set(range_paths) == {
        "/api/ip-address-ranges",
        "/api/ip-address-ranges/{ip_address_range_id}",
    }
    forbidden = ("allocate", "assignment", "usage", "utilization", "capacity", "conflict", "sync")
    assert not any(token in p.lower() for p in range_paths for token in forbidden), (
        "不得出现分配 / 使用率 / 冲突扫描等端点"
    )

    cluster_id = _create_cluster(client, "cluster-a")
    assert _create_range(client, cluster_id, "10.0.0.0/24", "10.0.0.255").status_code == 400
    assert _create_range(client, cluster_id, "2001:db8::1", "2001:db8::2").status_code == 400
