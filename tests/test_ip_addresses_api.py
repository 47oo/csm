"""F005 IPAddress API 行为测试（T-01 ~ T-42）。

数据库夹具 ``auth_client_and_raw`` 同时提供产品客户端与**绕过应用层**的原始
psycopg 连接，用于断言数据库侧状态与预置软删行。漂移检测三件套见
``tests/test_ip_addresses_consistency.py``；并发 / 锁序见
``tests/test_ip_addresses_concurrency.py``。
"""

from __future__ import annotations

import pytest

READ_FIELDS = {
    "id",
    "network_interface_id",
    "ip_address",
    "created_at",
    "updated_at",
}

FORBIDDEN_READ_FIELDS = {
    "cluster_id",
    "deleted_at",
    "status",
    "vrf",
    "vrf_id",
    "tenant",
    "namespace",
    "netns",
    "pool",
    "pool_id",
    "subnet",
    "gateway",
    "dhcp",
    "dns",
    "discovered",
    "external_id",
    "carrier_type",
    "owner_type",
    "bare_metal_id",
    "virtual_machine_id",
    "container_id",
    "service_id",
    "purpose",
    "note",
    "remark",
    "owner",
    "assigned_at",
    "reclaimed_at",
}


def _create_cluster(client, name: str) -> int:
    response = client.post("/api/clusters", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_bm(client, cluster_id: int, hostname: str) -> int:
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


def _raw_cluster(conn, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO clusters (name, deleted_at) VALUES (%s, now()) RETURNING id", (name,)
        ).fetchone()[0]
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[
        0
    ]


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


def _raw_nic(conn, bare_metal_id: int, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO network_interfaces "
            "(bare_metal_id, name, technology_type, purpose, deleted_at) "
            "VALUES (%s, %s, 'Ethernet', 'Business', now()) RETURNING id",
            (bare_metal_id, name),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
        "VALUES (%s, %s, 'Ethernet', 'Business') RETURNING id",
        (bare_metal_id, name),
    ).fetchone()[0]


def _raw_ip(
    conn, network_interface_id: int, cluster_id: int, ip_address: str, *, deleted: bool = False
) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO ip_addresses "
            "(network_interface_id, cluster_id, ip_address, deleted_at) "
            "VALUES (%s, %s, %s, now()) RETURNING id",
            (network_interface_id, cluster_id, ip_address),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address) "
        "VALUES (%s, %s, %s) RETURNING id",
        (network_interface_id, cluster_id, ip_address),
    ).fetchone()[0]


def _active_ip_count(conn) -> int:
    return conn.execute("SELECT count(*) FROM ip_addresses WHERE deleted_at IS NULL").fetchone()[0]


def _total_ip_rows(conn) -> int:
    return conn.execute("SELECT count(*) FROM ip_addresses").fetchone()[0]


# --------------------------------------------------------------------------- #
# T-01 / AC-01：登记成功，响应字段集合恰 5 字段
# --------------------------------------------------------------------------- #
def test_t01_create_returns_closed_field_set(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster, "n1")
    nic = _create_nic(client, host)

    response = client.post(
        "/api/ip-addresses", json={"network_interface_id": nic, "ip_address": "10.0.0.1"}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == READ_FIELDS
    assert body["network_interface_id"] == nic
    assert body["ip_address"] == "10.0.0.1"
    assert _active_ip_count(conn) == 1


# --------------------------------------------------------------------------- #
# T-02 / AC-02：ip_address 必填 / 非字符串 → 400 + field == "ip_address"，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ip", ["MISSING", 123, None, {"x": 1}, ["10.0.0.1"]])
def test_t02_invalid_ip_address_returns_400(auth_client_and_raw, ip):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster, "n1")
    nic = _create_nic(client, host)
    payload: dict = {"network_interface_id": nic, "ip_address": "10.0.0.1"}
    if ip == "MISSING":
        del payload["ip_address"]
    else:
        payload["ip_address"] = ip

    response = client.post("/api/ip-addresses", json=payload)

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "ip_address" for detail in body["error"]["details"])
    assert _total_ip_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-03 / AC-03：network_interface_id 必填 / 非整数 → 400 + field
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("parent", ["MISSING", "abc", None, 1.5])
def test_t03_invalid_network_interface_id_returns_400(auth_client_and_raw, parent):
    client, conn = auth_client_and_raw
    payload: dict = {"ip_address": "10.0.0.1"}
    if parent != "MISSING":
        payload["network_interface_id"] = parent

    response = client.post("/api/ip-addresses", json=payload)

    assert response.status_code == 400, response.text
    assert any(
        detail["field"] == "network_interface_id" for detail in response.json()["error"]["details"]
    )
    assert _total_ip_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-04 / AC-04：父不存在 / 已软删 → 404（details == []），无写入；?network_interface_id= 同语义
# --------------------------------------------------------------------------- #
def test_t04_missing_or_deleted_parent_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")

    missing = client.post(
        "/api/ip-addresses", json={"network_interface_id": 999999, "ip_address": "10.0.0.1"}
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert missing.json()["error"]["details"] == []

    gone_host = _raw_bm(conn, cluster, "gone", deleted=True)
    gone_nic = _raw_nic(conn, gone_host, "gone-eth0", deleted=True)
    deleted = client.post(
        "/api/ip-addresses", json={"network_interface_id": gone_nic, "ip_address": "10.0.0.2"}
    )
    assert deleted.status_code == 404
    assert deleted.json()["error"]["code"] == "NOT_FOUND"
    assert _total_ip_rows(conn) == 0

    assert (
        client.get("/api/ip-addresses", params={"network_interface_id": 999999}).status_code == 404
    )
    assert (
        client.get("/api/ip-addresses", params={"network_interface_id": gone_nic}).status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# T-05 / AC-05：绑定恰好一个 NIC，schema 封闭；DB 父列 NOT NULL + FK RESTRICT
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "extra",
    [
        {"parents": [1, 2]},
        {"carrier_type": "bare_metal"},
        {"bare_metal_id": 1},
        {"virtual_machine_id": 1},
        {"container_id": 1},
        {"service_id": 1},
        {"cluster_id": 1},
        {"status": "UP"},
        {"vrf": "default"},
        {"pool_id": 1},
    ],
)
def test_t05_create_schema_is_closed(auth_client_and_raw, extra):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster, "n1")
    nic = _create_nic(client, host)

    response = client.post(
        "/api/ip-addresses",
        json={"network_interface_id": nic, "ip_address": "10.0.0.1", **extra},
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_ip_rows(conn) == 0


def test_t05_parent_columns_not_null_and_fk_restrict(auth_client_and_raw):
    _, conn = auth_client_and_raw
    nullability = dict(
        conn.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='ip_addresses'"
        ).fetchall()
    )
    assert nullability["network_interface_id"] == "NO"
    assert nullability["cluster_id"] == "NO"
    assert nullability["deleted_at"] == "YES"

    fks = conn.execute(
        "SELECT conname, confdeltype, confupdtype FROM pg_constraint "
        "WHERE conrelid = 'ip_addresses'::regclass AND contype = 'f'"
    ).fetchall()
    assert {row[0] for row in fks} == {
        "fk_ip_addresses_network_interface",
        "fk_ip_addresses_cluster",
    }
    assert all((row[1], row[2]) == ("r", "r") for row in fks)


# --------------------------------------------------------------------------- #
# T-06 / AC-06：同一 NIC 多个 IP
# --------------------------------------------------------------------------- #
def test_t06_one_nic_multiple_ips(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster, "n1")
    nic = _create_nic(client, host)

    first = _create_ip(client, nic, "10.0.0.1")
    second = _create_ip(client, nic, "10.0.0.2")
    assert first["id"] != second["id"]
    assert _active_ip_count(conn) == 2


# --------------------------------------------------------------------------- #
# T-07 / AC-07 / AC-42：请求携带 cluster_id / vrf / status / pool_id → 400，无记录
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "extra", [{"cluster_id": 1}, {"vrf": "x"}, {"status": "UP"}, {"pool_id": 1}]
)
def test_t07_forbidden_request_fields_rejected(auth_client_and_raw, extra):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster, "n1")
    nic = _create_nic(client, host)

    response = client.post(
        "/api/ip-addresses",
        json={"network_interface_id": nic, "ip_address": "10.0.0.1", **extra},
    )
    assert response.status_code == 400
    assert _total_ip_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-08 / AC-08：同 Cluster 内唯一（跨 BM / 跨 NIC），保存前阻止
# --------------------------------------------------------------------------- #
def test_t08_same_cluster_duplicate_across_nics_is_blocked(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    host_1 = _create_bm(client, cluster, "n1")
    host_2 = _create_bm(client, cluster, "n2")
    nic_1 = _create_nic(client, host_1, "n1-eth0")
    nic_2 = _create_nic(client, host_2, "n2-eth0")

    _create_ip(client, nic_1, "10.0.0.10")
    response = client.post(
        "/api/ip-addresses", json={"network_interface_id": nic_2, "ip_address": "10.0.0.10"}
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(
        detail.get("field") == "ip_address" and detail.get("code") == "DUPLICATE"
        for detail in body["error"]["details"]
    )
    assert _active_ip_count(conn) == 1


# --------------------------------------------------------------------------- #
# T-09 / AC-09：跨 Cluster 同 IP 均 201
# --------------------------------------------------------------------------- #
def test_t09_cross_cluster_same_ip_allowed(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    nic_a = _create_nic(client, _create_bm(client, cluster_a, "a1"), "a-eth0")
    nic_b = _create_nic(client, _create_bm(client, cluster_b, "b1"), "b-eth0")

    first = _create_ip(client, nic_a, "10.0.0.10")
    second = _create_ip(client, nic_b, "10.0.0.10")
    assert first["id"] != second["id"]
    assert _active_ip_count(conn) == 2


# --------------------------------------------------------------------------- #
# T-10 / AC-10：字面精确、大小写敏感；无 lower() 索引 / 无 COLLATE
# --------------------------------------------------------------------------- #
def test_t10_case_variants_coexist(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))

    upper = _create_ip(client, nic, "2001:DB8::1")
    lower = _create_ip(client, nic, "2001:db8::1")
    assert upper["ip_address"] == "2001:DB8::1"
    assert lower["ip_address"] == "2001:db8::1"


def test_t10_db_has_no_lower_index_or_collation(auth_client_and_raw):
    _, conn = auth_client_and_raw
    indexdef = conn.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname='public' AND indexname='ux_ip_addresses_cluster_ip_active'"
    ).fetchone()[0]
    assert "lower(" not in indexdef.lower()
    assert "collate" not in indexdef.lower()

    collated = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='ip_addresses' AND collation_name IS NOT NULL"
    ).fetchall()
    assert collated == []


# --------------------------------------------------------------------------- #
# T-11 / AC-11：数据库最终权威；23505 → 409，永不 500
# --------------------------------------------------------------------------- #
def test_t11_app_level_conflict_is_409_not_500(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    _create_ip(client, nic, "10.0.0.10")

    response = client.post(
        "/api/ip-addresses", json={"network_interface_id": nic, "ip_address": "10.0.0.10"}
    )
    assert response.status_code == 409
    assert response.status_code != 500


def test_t11_db_fallback_after_bypassing_preflight_is_409(auth_client_and_raw, monkeypatch):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    _create_ip(client, nic, "10.0.0.10")

    from app.ip_addresses import service
    from app.ip_addresses.repository import IpAddressRepository

    # 绕过应用层预检 → 直写到 DB，触发 ux_ip_addresses_cluster_ip_active（23505）。
    monkeypatch.setattr(IpAddressRepository, "active_ip_exists", lambda *a, **k: False)
    response = client.post(
        "/api/ip-addresses", json={"network_interface_id": nic, "ip_address": "10.0.0.10"}
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "CONFLICT"
    assert any(d.get("code") == "DUPLICATE" for d in response.json()["error"]["details"])
    assert _active_ip_count(conn) == 1
    assert service is not None


def test_t11_direct_duplicate_insert_raises_23505(auth_client_and_raw):
    import psycopg

    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    _create_ip(client, nic, "10.0.0.10")

    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        _raw_ip(conn, nic, cluster, "10.0.0.10")
    assert excinfo.value.sqlstate == "23505"

    predicate = conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE indexname='ux_ip_addresses_cluster_ip_active'"
    ).fetchone()[0]
    assert "deleted_at IS NULL" in predicate


# --------------------------------------------------------------------------- #
# T-12 / AC-12：格式规则「不实现」——不被拒绝，原样往返
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "literal", ["not-an-ip", "", "  padded  ", "x" * 300, "10.0.0.1/16", "10.0.0.1"]
)
def test_t12_undefined_format_constraints_not_enforced(auth_client_and_raw, literal):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, f"cluster-{abs(hash(literal)) % 100000}")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))

    created = client.post(
        "/api/ip-addresses", json={"network_interface_id": nic, "ip_address": literal}
    )
    assert created.status_code == 201, created.text
    assert created.json()["ip_address"] == literal

    detail = client.get(f"/api/ip-addresses/{created.json()['id']}")
    assert detail.json()["ip_address"] == literal


# --------------------------------------------------------------------------- #
# T-13 / AC-13：无 status
# --------------------------------------------------------------------------- #
def test_t13_no_status_anywhere(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base
    from app.ip_addresses.schemas import IpAddressCreate, IpAddressRead, IpAddressUpdate

    for model in (IpAddressCreate, IpAddressRead, IpAddressUpdate):
        assert "status" not in model.model_fields
    columns = {column.name for column in Base.metadata.tables["ip_addresses"].columns}
    assert "status" not in columns
    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='ip_addresses'"
        ).fetchall()
    }
    assert "status" not in db_columns
    for path, operations in client.app.openapi()["paths"].items():
        if path.startswith("/api/ip-addresses"):
            assert "status" not in path.lower()
            for operation in operations.values():
                names = {p.get("name") for p in operation.get("parameters", [])}
                assert not any("status" in (n or "").lower() for n in names)


# --------------------------------------------------------------------------- #
# T-14 / T-15 / AC-14 / AC-15：无 VRF / 无未确认字段 / 无自动发现
# --------------------------------------------------------------------------- #
def test_t14_t15_no_vrf_or_unconfirmed_fields(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base
    from app.ip_addresses.schemas import IpAddressCreate, IpAddressRead, IpAddressUpdate

    forbidden = (
        "vrf",
        "vrf_id",
        "tenant",
        "namespace",
        "netns",
        "vni",
        "pool",
        "pool_id",
        "subnet",
        "gateway",
        "dhcp",
        "dns",
        "discovered",
        "external_id",
        "last_seen",
        "credential",
        "purpose",
        "note",
        "remark",
        "owner",
        "assigned_at",
        "reclaimed_at",
    )
    columns = {column.name for column in Base.metadata.tables["ip_addresses"].columns}
    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='ip_addresses'"
        ).fetchall()
    }
    for token in forbidden:
        assert token not in columns, token
        assert token not in db_columns, token
        for model in (IpAddressCreate, IpAddressRead, IpAddressUpdate):
            assert token not in model.model_fields, f"{model.__name__}.{token}"

    for path in client.app.openapi()["paths"]:
        if path.startswith("/api/ip-addresses"):
            assert not any(
                token in path.lower()
                for token in ("vrf", "dhcp", "dns", "discover", "sync", "credential", "external")
            )


# --------------------------------------------------------------------------- #
# T-16 / AC-16：列表分页 Empty；非法参数 400
# --------------------------------------------------------------------------- #
def test_t16_empty_list_is_200_empty(auth_client_and_raw):
    client, _ = auth_client_and_raw
    response = client.get("/api/ip-addresses")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 50}


def test_t16_pagination(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    for index in range(3):
        _create_ip(client, nic, f"10.0.0.{index}")

    first = client.get("/api/ip-addresses", params={"page_size": 2, "page": 1}).json()
    assert first["total"] == 3
    assert len(first["items"]) == 2
    second = client.get("/api/ip-addresses", params={"page_size": 2, "page": 2}).json()
    assert len(second["items"]) == 1


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"page": "abc"}, {"page_size": 0}, {"page_size": 201}]
)
def test_t16_invalid_pagination_returns_400(auth_client_and_raw, params):
    client, _ = auth_client_and_raw
    response = client.get("/api/ip-addresses", params=params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- #
# T-17 / AC-17：详情 Not Found；重复删除 404
# --------------------------------------------------------------------------- #
def test_t17_detail_not_found_and_repeat_delete(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    created = _create_ip(client, nic, "10.0.0.1")

    assert client.get("/api/ip-addresses/999999").status_code == 404

    ghost = _raw_ip(conn, nic, cluster, "10.0.0.9", deleted=True)
    assert client.get(f"/api/ip-addresses/{ghost}").status_code == 404

    assert client.delete(f"/api/ip-addresses/{created['id']}").status_code == 204
    assert client.get(f"/api/ip-addresses/{created['id']}").status_code == 404
    assert client.delete(f"/api/ip-addresses/{created['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# T-18 / AC-18：按 NIC Empty vs Not Found
# --------------------------------------------------------------------------- #
def test_t18_list_by_nic_semantics(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    nic_a = _create_nic(client, _create_bm(client, cluster_a, "a1"), "a-eth0")
    nic_b = _create_nic(client, _create_bm(client, cluster_b, "b1"), "b-eth0")

    assert (
        client.get("/api/ip-addresses", params={"network_interface_id": 999999}).status_code == 404
    )
    gone_host = _raw_bm(conn, cluster_a, "gone", deleted=True)
    gone_nic = _raw_nic(conn, gone_host, "gone", deleted=True)
    assert (
        client.get("/api/ip-addresses", params={"network_interface_id": gone_nic}).status_code
        == 404
    )

    empty = client.get("/api/ip-addresses", params={"network_interface_id": nic_a})
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["total"] == 0

    _create_ip(client, nic_a, "10.0.0.1")
    _create_ip(client, nic_b, "10.0.0.2")
    only_a = client.get("/api/ip-addresses", params={"network_interface_id": nic_a}).json()
    assert [item["network_interface_id"] for item in only_a["items"]] == [nic_a]
    assert only_a["total"] == 1


@pytest.mark.parametrize("value", ["abc", 0.5])
def test_t18_non_integer_nic_query_returns_400(auth_client_and_raw, value):
    client, _ = auth_client_and_raw
    response = client.get("/api/ip-addresses", params={"network_interface_id": value})
    assert response.status_code == 400
    assert any(
        detail["field"] == "network_interface_id" for detail in response.json()["error"]["details"]
    )


# --------------------------------------------------------------------------- #
# T-19 / AC-19：绕过应用层预置软删行 → 排除；按 id → 404
# --------------------------------------------------------------------------- #
def test_t19_soft_deleted_row_excluded(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    ghost = _raw_ip(conn, nic, cluster, "10.0.0.1", deleted=True)

    listed = client.get("/api/ip-addresses").json()
    assert listed["total"] == 0
    assert listed["items"] == []

    by_nic = client.get("/api/ip-addresses", params={"network_interface_id": nic}).json()
    assert by_nic["total"] == 0
    assert client.get(f"/api/ip-addresses/{ghost}").status_code == 404


# --------------------------------------------------------------------------- #
# T-20 / AC-20：PATCH 修正字面值；不可变字段不变；响应无 cluster_id
# --------------------------------------------------------------------------- #
def test_t20_patch_literal_value(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    created = _create_ip(client, nic, "10.0.0.1")

    patched = client.patch(f"/api/ip-addresses/{created['id']}", json={"ip_address": "10.0.0.2"})
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert set(body) == READ_FIELDS
    assert body["ip_address"] == "10.0.0.2"
    assert body["id"] == created["id"]
    assert body["network_interface_id"] == nic
    assert body["created_at"] == created["created_at"]
    assert "cluster_id" not in body

    reread = client.get(f"/api/ip-addresses/{created['id']}").json()
    assert reread["ip_address"] == "10.0.0.2"


# --------------------------------------------------------------------------- #
# T-21 / AC-21：修正后重校验唯一性
# --------------------------------------------------------------------------- #
def test_t21_patch_revalidates_uniqueness(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    nic_a1 = _create_nic(client, _create_bm(client, cluster_a, "a1"), "a1")
    nic_a2 = _create_nic(client, _create_bm(client, cluster_a, "a2"), "a2")
    nic_b = _create_nic(client, _create_bm(client, cluster_b, "b1"), "b1")

    _create_ip(client, nic_a1, "10.0.0.10")
    target = _create_ip(client, nic_a2, "10.0.0.20")
    _create_ip(client, nic_b, "10.0.0.30")

    # 目标 Cluster 内已占用 → 409 DUPLICATE，无部分写入。
    conflict = client.patch(f"/api/ip-addresses/{target['id']}", json={"ip_address": "10.0.0.10"})
    assert conflict.status_code == 409, conflict.text
    assert any(d.get("code") == "DUPLICATE" for d in conflict.json()["error"]["details"])
    assert client.get(f"/api/ip-addresses/{target['id']}").json()["ip_address"] == "10.0.0.20"

    # 另一 Cluster 已占用但目标 Cluster 未占用 → 200。
    ok = client.patch(f"/api/ip-addresses/{target['id']}", json={"ip_address": "10.0.0.30"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["ip_address"] == "10.0.0.30"
    assert _active_ip_count(conn) == 3


# --------------------------------------------------------------------------- #
# T-22 / AC-22：PATCH schema 封闭；空 body / null → 400；父绑定不可变
# --------------------------------------------------------------------------- #
def test_t22_patch_schema_closed(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    created = _create_ip(client, nic, "10.0.0.1")

    empty = client.patch(f"/api/ip-addresses/{created['id']}", json={})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "VALIDATION_ERROR"

    null = client.patch(f"/api/ip-addresses/{created['id']}", json={"ip_address": None})
    assert null.status_code == 400
    assert any(d["field"] == "ip_address" for d in null.json()["error"]["details"])

    for field, value in (
        ("network_interface_id", nic),
        ("id", 1),
        ("cluster_id", 1),
        ("created_at", created["created_at"]),
        ("deleted_at", None),
        ("status", "UP"),
        ("vrf", "x"),
        ("bare_metal_id", 1),
    ):
        forbidden = client.patch(f"/api/ip-addresses/{created['id']}", json={field: value})
        assert forbidden.status_code == 400, field
        assert any(d["field"] == field for d in forbidden.json()["error"]["details"]), field


def test_t22_patch_missing_or_deleted_returns_404(auth_client_and_raw):
    client, _ = auth_client_and_raw
    assert client.patch("/api/ip-addresses/999999", json={"ip_address": "x"}).status_code == 404


# --------------------------------------------------------------------------- #
# T-23 / AC-23：DELETE 204；行仍物理存在
# --------------------------------------------------------------------------- #
def test_t23_delete_returns_204_and_row_survives(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    created = _create_ip(client, nic, "10.0.0.1")
    rows_before = _total_ip_rows(conn)

    response = client.delete(f"/api/ip-addresses/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert _total_ip_rows(conn) == rows_before
    row = conn.execute(
        "SELECT deleted_at FROM ip_addresses WHERE id = %s", (created["id"],)
    ).fetchone()
    assert row is not None
    assert row[0] is not None


# --------------------------------------------------------------------------- #
# T-24 / AC-24：软删释放唯一性；旧行 deleted_at 不被改写
# --------------------------------------------------------------------------- #
def test_t24_soft_delete_releases_uniqueness(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    created = _create_ip(client, nic, "10.0.0.10")

    assert client.delete(f"/api/ip-addresses/{created['id']}").status_code == 204
    deleted_at_after = conn.execute(
        "SELECT deleted_at FROM ip_addresses WHERE id = %s", (created["id"],)
    ).fetchone()[0]

    recreated = _create_ip(client, nic, "10.0.0.10")
    assert recreated["id"] != created["id"]
    assert (
        conn.execute(
            "SELECT deleted_at FROM ip_addresses WHERE id = %s", (created["id"],)
        ).fetchone()[0]
        == deleted_at_after
    )


# --------------------------------------------------------------------------- #
# T-25 / AC-25：删除不级联（父 NIC / BM / Cluster 逐字段不变）
# --------------------------------------------------------------------------- #
def test_t25_delete_does_not_cascade(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster, "n1")
    nic = _create_nic(client, host)
    target = _create_ip(client, nic, "10.0.0.1")
    _create_ip(client, nic, "10.0.0.2")

    nic_before = conn.execute(
        "SELECT name, technology_type, purpose, bare_metal_id, created_at, updated_at, deleted_at "
        "FROM network_interfaces WHERE id = %s",
        (nic,),
    ).fetchone()
    bm_before = conn.execute(
        "SELECT hostname, status, cluster_id, deleted_at FROM bare_metals WHERE id = %s",
        (host,),
    ).fetchone()
    cluster_before = conn.execute(
        "SELECT name, deleted_at FROM clusters WHERE id = %s", (cluster,)
    ).fetchone()

    assert client.delete(f"/api/ip-addresses/{target['id']}").status_code == 204

    assert (
        conn.execute(
            "SELECT name, technology_type, purpose, bare_metal_id, created_at, updated_at, "
            "deleted_at FROM network_interfaces WHERE id = %s",
            (nic,),
        ).fetchone()
        == nic_before
    )
    assert (
        conn.execute(
            "SELECT hostname, status, cluster_id, deleted_at FROM bare_metals WHERE id = %s",
            (host,),
        ).fetchone()
        == bm_before
    )
    assert (
        conn.execute("SELECT name, deleted_at FROM clusters WHERE id = %s", (cluster,)).fetchone()
        == cluster_before
    )


# --------------------------------------------------------------------------- #
# T-26 / AC-26：无 restore / undelete / purge / 批量 / include_deleted / by-name
# --------------------------------------------------------------------------- #
def test_t26_no_out_of_scope_routes_or_params(auth_client_and_raw):
    client, _ = auth_client_and_raw
    paths = client.app.openapi()["paths"]
    forbidden = ("restore", "undelete", "purge", "trash", "batch", "deleted", "by-name")
    offenders = [
        path
        for path in paths
        if path.startswith("/api/ip-addresses")
        and any(token in path.lower() for token in forbidden)
    ]
    assert offenders == []

    op = paths["/api/ip-addresses"]["get"]
    names = {p.get("name") for p in op.get("parameters", [])}
    assert not any("deleted" in (n or "").lower() or "include" in (n or "").lower() for n in names)


# --------------------------------------------------------------------------- #
# T-27 / T-28 / AC-27 / AC-28：NIC 有活跃 IP → 拒删；软删后可删
# --------------------------------------------------------------------------- #
def test_t27_nic_with_active_ip_cannot_be_deleted(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    _create_ip(client, nic, "10.0.0.1")

    response = client.delete(f"/api/network-interfaces/{nic}")

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(d.get("code") == "ACTIVE_CHILDREN_EXIST" for d in body["error"]["details"])
    assert (
        conn.execute("SELECT deleted_at FROM network_interfaces WHERE id = %s", (nic,)).fetchone()[
            0
        ]
        is None
    )


def test_t28_nic_deletable_after_all_ips_soft_deleted(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    first = _create_ip(client, nic, "10.0.0.1")
    second = _create_ip(client, nic, "10.0.0.2")

    assert client.delete(f"/api/network-interfaces/{nic}").status_code == 409
    assert client.delete(f"/api/ip-addresses/{first['id']}").status_code == 204
    assert client.delete(f"/api/network-interfaces/{nic}").status_code == 409
    assert client.delete(f"/api/ip-addresses/{second['id']}").status_code == 204
    assert client.delete(f"/api/network-interfaces/{nic}").status_code == 204


# --------------------------------------------------------------------------- #
# T-29 / AC-29：链条闭合 Cluster → BareMetal → NIC → IP
# --------------------------------------------------------------------------- #
def test_t29_bare_metal_with_active_ip_chain_cannot_be_deleted(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster, "n1")
    nic = _create_nic(client, host)
    _create_ip(client, nic, "10.0.0.1")

    assert client.delete(f"/api/bare-metals/{host}").status_code == 409
    assert client.delete(f"/api/clusters/{cluster}").status_code == 409

    # 软删 IP → NIC → BM → Cluster 链条逐层释放。
    ip = client.get("/api/ip-addresses", params={"network_interface_id": nic}).json()["items"][0]
    assert client.delete(f"/api/ip-addresses/{ip['id']}").status_code == 204
    assert client.delete(f"/api/network-interfaces/{nic}").status_code == 204
    assert client.delete(f"/api/bare-metals/{host}").status_code == 204
    assert client.delete(f"/api/clusters/{cluster}").status_code == 204


# --------------------------------------------------------------------------- #
# T-30 / T-31 / AC-30 / AC-31：F014 端到端（AST guard 见 guards 文件）
# --------------------------------------------------------------------------- #
def test_t30_nic_checks_non_empty_and_consumed():
    from app.ip_addresses.deletion import has_active_ip_addresses
    from app.network_interfaces.deletion import NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS

    assert NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS
    assert has_active_ip_addresses in NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS


# --------------------------------------------------------------------------- #
# T-38 / AC-38：不越界 F009 / F010 / F011；无第二维度过滤
# --------------------------------------------------------------------------- #
def test_t38_no_cluster_view_aggregation_or_import(auth_client_and_raw):
    client, _ = auth_client_and_raw
    paths = client.app.openapi()["paths"]
    ip_paths = [path for path in paths if path.startswith("/api/ip-addresses")]
    assert ip_paths == [
        "/api/ip-addresses",
        "/api/ip-addresses/{ip_address_id}",
        "/api/ip-addresses/allocate",
        "/api/ip-addresses/allocate-manual",
    ]

    for path in ip_paths:
        assert not any(
            token in path.lower()
            for token in ("cluster", "aggregate", "count", "excel", "import", "export")
        )


# --------------------------------------------------------------------------- #
# T-40 / AC-40：未认证 401 且不改数据；已认证用户即可增改删
# --------------------------------------------------------------------------- #
def test_t40_unauthenticated_returns_401_without_data_change(app_client_and_raw):
    client, conn = app_client_and_raw
    responses = [
        client.get("/api/ip-addresses"),
        client.get("/api/ip-addresses/1"),
        client.post(
            "/api/ip-addresses", json={"network_interface_id": 1, "ip_address": "10.0.0.1"}
        ),
        client.patch("/api/ip-addresses/1", json={"ip_address": "10.0.0.2"}),
        client.delete("/api/ip-addresses/1"),
    ]
    for response in responses:
        assert response.status_code == 401, response.text
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert _total_ip_rows(conn) == 0


def test_t40_authenticated_user_needs_no_role(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    nic = _create_nic(client, _create_bm(client, cluster, "n1"))
    created = _create_ip(client, nic, "10.0.0.1")
    assert (
        client.patch(
            f"/api/ip-addresses/{created['id']}", json={"ip_address": "10.0.0.2"}
        ).status_code
        == 200
    )
    assert client.delete(f"/api/ip-addresses/{created['id']}").status_code == 204


# --------------------------------------------------------------------------- #
# T-42 / AC-42：OpenAPI 中无为未确认能力预留的字段 / 参数
# --------------------------------------------------------------------------- #
def test_t42_no_reserved_fields_in_openapi(auth_client_and_raw):
    client, _ = auth_client_and_raw
    spec = client.app.openapi()
    read_props = spec["components"]["schemas"]["IpAddressRead"]["properties"]
    assert set(read_props) == READ_FIELDS
    assert not (FORBIDDEN_READ_FIELDS & set(read_props))

    create_props = spec["components"]["schemas"]["IpAddressCreate"]["properties"]
    assert set(create_props) == {"network_interface_id", "ip_address"}
    update_props = spec["components"]["schemas"]["IpAddressUpdate"]["properties"]
    assert set(update_props) == {"ip_address"}
