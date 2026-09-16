"""F004 NetworkInterface API 行为测试（T-01 ~ T-23、T-30 ~ T-32）。

数据库夹具 ``auth_client_and_raw`` 同时提供产品客户端与**绕过应用层**的原始
psycopg 连接，用于断言数据库侧状态与预置软删行。
"""

from __future__ import annotations

import pytest

READ_FIELDS = {
    "id",
    "bare_metal_id",
    "name",
    "technology_type",
    "purpose",
    "created_at",
    "updated_at",
}

TECHNOLOGY_TYPES = ("Ethernet", "InfiniBand", "RoCE", "Other")
PURPOSES = ("BMC", "Management", "Business", "Compute", "Storage", "DataTransfer", "Other")

IP_FIELDS = {"ip", "ip_address", "ipv4", "ipv6", "prefix_len"}
HARDWARE_FIELDS = {
    "mac",
    "mac_address",
    "speed",
    "rate",
    "mtu",
    "port",
    "module",
    "transceiver",
    "discovered",
    "external_id",
    "last_seen",
}
CARRIER_FIELDS = {
    "vm_id",
    "virtual_machine_id",
    "container_id",
    "service_id",
    "cluster_id",
    "carrier_type",
    "owner_type",
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


def _raw_cluster(conn, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO clusters (name, deleted_at) VALUES (%s, now()) RETURNING id", (name,)
        ).fetchone()[0]
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[
        0
    ]


def _nic_payload(bare_metal_id: int, name: str, **extra) -> dict:
    return {
        "bare_metal_id": bare_metal_id,
        "name": name,
        "technology_type": "Ethernet",
        "purpose": "Business",
        **extra,
    }


def _active_nic_count(conn) -> int:
    return conn.execute(
        "SELECT count(*) FROM network_interfaces WHERE deleted_at IS NULL"
    ).fetchone()[0]


def _total_nic_rows(conn) -> int:
    return conn.execute("SELECT count(*) FROM network_interfaces").fetchone()[0]


# --------------------------------------------------------------------------- #
# T-01 / AC-01：登记成功，响应字段集合恰为 7 字段
# --------------------------------------------------------------------------- #
def test_t01_create_returns_closed_field_set(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    response = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == READ_FIELDS
    assert "deleted_at" not in body
    assert "status" not in body
    assert not (IP_FIELDS & set(body))
    assert not (HARDWARE_FIELDS & set(body))
    assert not (CARRIER_FIELDS & set(body))
    assert body["bare_metal_id"] == host["id"]
    assert body["name"] == "eth0"
    assert body["technology_type"] == "Ethernet"
    assert body["purpose"] == "Business"
    assert _active_nic_count(conn) == 1


# --------------------------------------------------------------------------- #
# T-02 / AC-02：name 必填 / 非字符串 → 400 + field == "name"，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["MISSING", 123, None, {"x": 1}, ["eth0"]])
def test_t02_invalid_name_returns_400_without_write(auth_client_and_raw, name):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    payload = _nic_payload(host["id"], "eth0")
    if name == "MISSING":
        del payload["name"]
    else:
        payload["name"] = name

    response = client.post("/api/network-interfaces", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "name" for detail in body["error"]["details"])
    assert _total_nic_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-03 / AC-03：technology_type 必填且封闭
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tech", TECHNOLOGY_TYPES)
def test_t03_technology_type_accepts_four_values(auth_client_and_raw, tech):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    response = client.post(
        "/api/network-interfaces", json=_nic_payload(host["id"], "eth0", technology_type=tech)
    )
    assert response.status_code == 201, response.text
    assert response.json()["technology_type"] == tech


@pytest.mark.parametrize("tech", ["FibreChannel", "ethernet", "Other ", "", None, "InfiniBand ", 5])
def test_t03_invalid_technology_type_returns_400(auth_client_and_raw, tech):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    response = client.post(
        "/api/network-interfaces", json=_nic_payload(host["id"], "eth0", technology_type=tech)
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "technology_type" for detail in body["error"]["details"])
    assert _total_nic_rows(conn) == 0


def test_t03_missing_technology_type_returns_400(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    payload = _nic_payload(host["id"], "eth0")
    del payload["technology_type"]
    response = client.post("/api/network-interfaces", json=payload)
    assert response.status_code == 400
    assert any(
        detail["field"] == "technology_type" for detail in response.json()["error"]["details"]
    )
    assert _total_nic_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-04 / AC-04：purpose 必填且封闭
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("purpose", PURPOSES)
def test_t04_purpose_accepts_seven_values(auth_client_and_raw, purpose):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    response = client.post(
        "/api/network-interfaces", json=_nic_payload(host["id"], "eth0", purpose=purpose)
    )
    assert response.status_code == 201, response.text
    assert response.json()["purpose"] == purpose


@pytest.mark.parametrize("purpose", ["mgmt", "business", "", None, "Data Transfer", "OTHER", 7])
def test_t04_invalid_purpose_returns_400(auth_client_and_raw, purpose):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    response = client.post(
        "/api/network-interfaces", json=_nic_payload(host["id"], "eth0", purpose=purpose)
    )
    assert response.status_code == 400, response.text
    assert any(detail["field"] == "purpose" for detail in response.json()["error"]["details"])
    assert _total_nic_rows(conn) == 0


def test_t04_missing_purpose_returns_400(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    payload = _nic_payload(host["id"], "eth0")
    del payload["purpose"]
    response = client.post("/api/network-interfaces", json=payload)
    assert response.status_code == 400
    assert any(detail["field"] == "purpose" for detail in response.json()["error"]["details"])
    assert _total_nic_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-05 / AC-05：Other 是合法成员，无伴随自由文本
# --------------------------------------------------------------------------- #
def test_t05_other_is_plain_enum_member(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    response = client.post(
        "/api/network-interfaces",
        json=_nic_payload(host["id"], "eth0", technology_type="Other", purpose="Other"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["technology_type"] == "Other"
    assert body["purpose"] == "Other"
    assert "other_text" not in body
    assert "description" not in body

    from app.network_interfaces.schemas import NetworkInterfaceCreate, NetworkInterfaceRead

    for model in (NetworkInterfaceCreate, NetworkInterfaceRead):
        assert "other_text" not in model.model_fields
        assert "description" not in model.model_fields


# --------------------------------------------------------------------------- #
# T-06 / AC-06：宿主必填 / 非整数 → 400 + field == "bare_metal_id"，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("host_value", ["MISSING", "abc", None, 1.5])
def test_t06_invalid_bare_metal_id_returns_400(auth_client_and_raw, host_value):
    client, conn = auth_client_and_raw
    payload = {
        "name": "eth0",
        "technology_type": "Ethernet",
        "purpose": "Business",
    }
    if host_value != "MISSING":
        payload["bare_metal_id"] = host_value
    response = client.post("/api/network-interfaces", json=payload)
    assert response.status_code == 400
    assert any(detail["field"] == "bare_metal_id" for detail in response.json()["error"]["details"])
    assert _total_nic_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-07 / AC-07 / NQ-5：父不存在 / 已删 → 404，无写入；?bare_metal_id= 同语义
# --------------------------------------------------------------------------- #
def test_t07_missing_or_deleted_host_returns_404_without_write(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    missing = client.post("/api/network-interfaces", json=_nic_payload(999999, "eth0"))
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert missing.json()["error"]["details"] == []

    gone_host = _raw_bm(conn, cluster_id, "gone", deleted=True)
    deleted = client.post("/api/network-interfaces", json=_nic_payload(gone_host, "eth1"))
    assert deleted.status_code == 404
    assert deleted.json()["error"]["code"] == "NOT_FOUND"
    assert _total_nic_rows(conn) == 0


def test_t07_list_by_missing_or_deleted_host_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    assert (
        client.get("/api/network-interfaces", params={"bare_metal_id": 999999}).status_code == 404
    )
    gone_host = _raw_bm(conn, cluster_id, "gone", deleted=True)
    response = client.get("/api/network-interfaces", params={"bare_metal_id": gone_host})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# T-08 / AC-08：多父 / 载体字段 / 未识别字段 → 400，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "extra",
    [
        {"hosts": [1, 2]},
        {"carrier_type": "bare_metal"},
        {"container_id": 1},
        {"virtual_machine_id": 1},
        {"vm_id": 1},
        {"service_id": 1},
        {"cluster_id": 1},
        {"status": "UP"},
        {"ip_address": "10.0.0.1"},
        {"mac_address": "aa:bb:cc:dd:ee:ff"},
        {"mtu": 1500},
    ],
)
def test_t08_unknown_or_overreaching_create_fields_rejected(auth_client_and_raw, extra):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    response = client.post(
        "/api/network-interfaces", json=_nic_payload(host["id"], "eth0", **extra)
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_nic_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-09 / AC-09 / AC-12：同宿主同名两张均 201（无唯一性）
# --------------------------------------------------------------------------- #
def test_t09_same_host_same_name_both_created(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    first = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0"))
    second = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0"))

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["bare_metal_id"] == second.json()["bare_metal_id"] == host["id"]
    assert first.json()["id"] != second.json()["id"]
    assert _active_nic_count(conn) == 2


# --------------------------------------------------------------------------- #
# T-10 / AC-10：中文 / 点号 / 连字符 name 与枚举字面值原样往返
# --------------------------------------------------------------------------- #
def test_t10_chinese_and_punctuation_name_roundtrip(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    name = "网卡-甲.0/1"

    created = client.post("/api/network-interfaces", json=_nic_payload(host["id"], name))
    assert created.status_code == 201
    assert created.json()["name"] == name

    detail = client.get(f"/api/network-interfaces/{created.json()['id']}")
    assert detail.json()["name"] == name


# --------------------------------------------------------------------------- #
# T-11 / AC-11：空串 / 首尾空白 name 不被拒绝
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["", "  padded  ", "eth/0"])
def test_t11_undefined_name_constraints_not_enforced(auth_client_and_raw, name):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    response = client.post("/api/network-interfaces", json=_nic_payload(host["id"], name))
    assert response.status_code == 201, response.text
    assert response.json()["name"] == name


# --------------------------------------------------------------------------- #
# T-12 / AC-13：请求 / 响应 / 表 / 端点 / 参数无 status
# --------------------------------------------------------------------------- #
def test_t12_no_status_anywhere(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base
    from app.network_interfaces.schemas import (
        NetworkInterfaceCreate,
        NetworkInterfaceRead,
        NetworkInterfaceUpdate,
    )

    for model in (NetworkInterfaceCreate, NetworkInterfaceRead, NetworkInterfaceUpdate):
        assert "status" not in model.model_fields, model.__name__

    columns = {column.name for column in Base.metadata.tables["network_interfaces"].columns}
    assert "status" not in columns
    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='network_interfaces'"
        ).fetchall()
    }
    assert "status" not in db_columns

    for path, operations in client.app.openapi()["paths"].items():
        if not path.startswith("/api/network-interfaces"):
            continue
        assert "status" not in path.lower()
        for operation in operations.values():
            param_names = {p.get("name") for p in operation.get("parameters", [])}
            assert not any("status" in (name or "").lower() for name in param_names)


# --------------------------------------------------------------------------- #
# T-13 / AC-14：列表、分页、Empty
# --------------------------------------------------------------------------- #
def test_t13_empty_list_is_200_empty_items(auth_client_and_raw):
    client, _ = auth_client_and_raw
    response = client.get("/api/network-interfaces")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 50}


def test_t13_pagination(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    for index in range(3):
        assert (
            client.post(
                "/api/network-interfaces", json=_nic_payload(host["id"], f"eth{index}")
            ).status_code
            == 201
        )

    first = client.get("/api/network-interfaces", params={"page_size": 2, "page": 1}).json()
    assert first["total"] == 3
    assert [item["name"] for item in first["items"]] == ["eth0", "eth1"]

    second = client.get("/api/network-interfaces", params={"page_size": 2, "page": 2}).json()
    assert [item["name"] for item in second["items"]] == ["eth2"]


# --------------------------------------------------------------------------- #
# T-14 / AC-15：详情 Not Found（不区分不存在 / 已删）
# --------------------------------------------------------------------------- #
def test_t14_detail_not_found(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")

    assert client.get("/api/network-interfaces/999999").status_code == 404

    ghost_id = _raw_nic(conn, host["id"], "ghost", deleted=True)
    response = client.get(f"/api/network-interfaces/{ghost_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# T-15 / AC-16：按宿主读取，Empty 与 Not Found 可区分
# --------------------------------------------------------------------------- #
def test_t15_list_by_host_semantics(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    host_a = _create_bm(client, cluster_a, "n1")
    host_b = _create_bm(client, cluster_b, "n1")

    # 宿主不存在 → 404
    missing = client.get("/api/network-interfaces", params={"bare_metal_id": 999999})
    assert missing.status_code == 404

    # 宿主已删 → 404
    gone_host = _raw_bm(conn, cluster_a, "gone", deleted=True)
    deleted = client.get("/api/network-interfaces", params={"bare_metal_id": gone_host})
    assert deleted.status_code == 404

    # 宿主存在但无活跃 NIC → 200 空集
    empty = client.get("/api/network-interfaces", params={"bare_metal_id": host_a["id"]})
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["total"] == 0

    # 只返回该宿主子集
    client.post("/api/network-interfaces", json=_nic_payload(host_a["id"], "a1"))
    client.post("/api/network-interfaces", json=_nic_payload(host_b["id"], "b1"))
    only_a = client.get("/api/network-interfaces", params={"bare_metal_id": host_a["id"]}).json()
    assert [item["name"] for item in only_a["items"]] == ["a1"]
    assert only_a["total"] == 1


@pytest.mark.parametrize("bare_metal_id", ["abc", 0.5])
def test_t15_non_integer_host_query_returns_400(auth_client_and_raw, bare_metal_id):
    client, _ = auth_client_and_raw
    response = client.get("/api/network-interfaces", params={"bare_metal_id": bare_metal_id})
    assert response.status_code == 400
    assert any(detail["field"] == "bare_metal_id" for detail in response.json()["error"]["details"])


# --------------------------------------------------------------------------- #
# T-16 / AC-17：绕过应用层预置软删行 → 排除；按 id → 404
# --------------------------------------------------------------------------- #
def test_t16_soft_deleted_row_excluded_from_reads(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    ghost_id = _raw_nic(conn, host["id"], "ghost", deleted=True)

    listed = client.get("/api/network-interfaces").json()
    assert listed["total"] == 0
    assert [item["id"] for item in listed["items"]] == []

    by_host = client.get("/api/network-interfaces", params={"bare_metal_id": host["id"]}).json()
    assert by_host["total"] == 0

    assert client.get(f"/api/network-interfaces/{ghost_id}").status_code == 404


# --------------------------------------------------------------------------- #
# T-17 / AC-18：PATCH 合法字段；缺省不变
# --------------------------------------------------------------------------- #
def test_t17_patch_enum_fields(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0")).json()

    patched = client.patch(
        f"/api/network-interfaces/{created['id']}",
        json={"technology_type": "InfiniBand", "purpose": "Compute"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["technology_type"] == "InfiniBand"
    assert body["purpose"] == "Compute"
    assert body["id"] == created["id"]
    assert body["bare_metal_id"] == created["bare_metal_id"]
    assert body["name"] == created["name"]
    assert body["created_at"] == created["created_at"]

    # 只改一个字段，另一个不变
    only_purpose = client.patch(
        f"/api/network-interfaces/{created['id']}", json={"purpose": "Storage"}
    )
    assert only_purpose.json()["technology_type"] == "InfiniBand"
    assert only_purpose.json()["purpose"] == "Storage"

    reread = client.get(f"/api/network-interfaces/{created['id']}").json()
    assert reread["technology_type"] == "InfiniBand"
    assert reread["purpose"] == "Storage"


# --------------------------------------------------------------------------- #
# T-18 / AC-19：PATCH 非法枚举 → 400 + field；无写入；绕过校验 → 23514 经应用 → 400
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("technology_type", "FibreChannel"),
        ("technology_type", None),
        ("technology_type", "ethernet"),
        ("purpose", "mgmt"),
        ("purpose", None),
        ("purpose", ""),
    ],
)
def test_t18_patch_invalid_enum_returns_400_without_write(auth_client_and_raw, field, value):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0")).json()

    response = client.patch(f"/api/network-interfaces/{created['id']}", json={field: value})
    assert response.status_code == 400, response.text
    assert any(detail["field"] == field for detail in response.json()["error"]["details"])

    unchanged = client.get(f"/api/network-interfaces/{created['id']}").json()
    assert unchanged[field] == created[field]


def test_t18_db_check_violation_maps_to_400_not_500(auth_client_and_raw, monkeypatch):
    """绕过应用层枚举预检，直写非法值 → DB 23514，经通用映射返回 400（永不 500）。"""
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0")).json()

    from app.network_interfaces import service

    monkeypatch.setattr(service.validation, "validate_technology_type", lambda value: None)
    response = client.patch(
        f"/api/network-interfaces/{created['id']}", json={"technology_type": "FibreChannel"}
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- #
# T-19 / AC-20：PATCH 未识别 / 不可变字段 → 400；空 body → 400
# --------------------------------------------------------------------------- #
def test_t19_patch_rejects_unknown_and_immutable(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0")).json()

    empty = client.patch(f"/api/network-interfaces/{created['id']}", json={})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "VALIDATION_ERROR"

    for field, value in (
        ("name", "x"),
        ("bare_metal_id", host["id"]),
        ("id", 1),
        ("deleted_at", None),
        ("created_at", created["created_at"]),
        ("cluster_id", 1),
        ("status", "UP"),
        ("ip_address", "10.0.0.1"),
    ):
        forbidden = client.patch(f"/api/network-interfaces/{created['id']}", json={field: value})
        assert forbidden.status_code == 400, field
        assert any(detail["field"] == field for detail in forbidden.json()["error"]["details"]), (
            field
        )


def test_t19_patch_missing_or_deleted_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    assert (
        client.patch("/api/network-interfaces/999999", json={"technology_type": "RoCE"}).status_code
        == 404
    )

    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    gone_id = _raw_nic(conn, host["id"], "gone", deleted=True)
    assert (
        client.patch(
            f"/api/network-interfaces/{gone_id}", json={"technology_type": "RoCE"}
        ).status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# T-20 / AC-21：逻辑删除（204 无响应体；行仍物理存在）
# --------------------------------------------------------------------------- #
def test_t20_delete_returns_204_and_row_survives(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    created = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0")).json()
    rows_before = _total_nic_rows(conn)

    response = client.delete(f"/api/network-interfaces/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert _total_nic_rows(conn) == rows_before
    row = conn.execute(
        "SELECT deleted_at FROM network_interfaces WHERE id = %s", (created["id"],)
    ).fetchone()
    assert row is not None, "逻辑删除不得物理删除行"
    assert row[0] is not None

    assert client.get("/api/network-interfaces").json()["total"] == 0
    assert client.get(f"/api/network-interfaces/{created['id']}").status_code == 404
    # 重复删除 → 404
    assert client.delete(f"/api/network-interfaces/{created['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# T-21 / AC-22：删除不级联（宿主字段逐字段不变；其它行不变）
# --------------------------------------------------------------------------- #
def test_t21_delete_does_not_cascade(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    other = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "keep")).json()
    target = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "gone")).json()

    host_before = conn.execute(
        "SELECT hostname, status, cluster_id, created_at, updated_at, deleted_at "
        "FROM bare_metals WHERE id = %s",
        (host["id"],),
    ).fetchone()
    other_before = conn.execute(
        "SELECT name, purpose, deleted_at FROM network_interfaces WHERE id = %s", (other["id"],)
    ).fetchone()
    rows_before = _total_nic_rows(conn)

    assert client.delete(f"/api/network-interfaces/{target['id']}").status_code == 204

    assert (
        conn.execute(
            "SELECT hostname, status, cluster_id, created_at, updated_at, deleted_at "
            "FROM bare_metals WHERE id = %s",
            (host["id"],),
        ).fetchone()
        == host_before
    )
    assert (
        conn.execute(
            "SELECT name, purpose, deleted_at FROM network_interfaces WHERE id = %s",
            (other["id"],),
        ).fetchone()
        == other_before
    )
    assert _total_nic_rows(conn) == rows_before


# --------------------------------------------------------------------------- #
# T-22 / AC-23：无恢复 / 批量 / include_deleted / by-name
# --------------------------------------------------------------------------- #
def test_t22_no_out_of_scope_routes_or_params(auth_client_and_raw):
    client, _ = auth_client_and_raw
    paths = client.app.openapi()["paths"]

    forbidden_tokens = ("restore", "undelete", "purge", "trash", "batch", "deleted", "by-name")
    offenders = [
        path
        for path in paths
        if path.startswith("/api/network-interfaces")
        and any(token in path.lower() for token in forbidden_tokens)
    ]
    assert offenders == [], f"不存在恢复 / 批量 / by-name 端点：{offenders}"

    list_op = paths["/api/network-interfaces"]["get"]
    param_names = {p.get("name") for p in list_op.get("parameters", [])}
    assert not any("deleted" in (name or "").lower() for name in param_names)
    assert not any("include" in (name or "").lower() for name in param_names)


# --------------------------------------------------------------------------- #
# T-23 / AC-24：两行同名各自软删可成功；已删行不被改写；无 409 DUPLICATE 路径
# --------------------------------------------------------------------------- #
def test_t23_same_name_rows_soft_delete_independently(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    first = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0")).json()
    second = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0")).json()

    assert client.delete(f"/api/network-interfaces/{first['id']}").status_code == 204
    first_deleted_at = conn.execute(
        "SELECT deleted_at FROM network_interfaces WHERE id = %s", (first["id"],)
    ).fetchone()[0]

    assert client.delete(f"/api/network-interfaces/{second['id']}").status_code == 204
    assert (
        conn.execute(
            "SELECT deleted_at FROM network_interfaces WHERE id = %s", (first["id"],)
        ).fetchone()[0]
        == first_deleted_at
    )

    total = conn.execute("SELECT count(*) FROM network_interfaces WHERE name = 'eth0'").fetchone()[
        0
    ]
    assert total == 2
    assert _active_nic_count(conn) == 0


def test_t23_no_duplicate_conflict_path_for_name(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0"))
    second = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0"))
    assert second.status_code == 201
    # 响应体不含 CONFLICT / DUPLICATE
    assert "DUPLICATE" not in second.text
    assert "CONFLICT" not in second.text


# --------------------------------------------------------------------------- #
# T-24 / AC-25：宿主有活跃 NIC → 拒绝删除宿主（409 ACTIVE_CHILDREN_EXIST）
# --------------------------------------------------------------------------- #
def test_t24_host_with_active_nic_cannot_be_deleted(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    assert (
        client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0")).status_code
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


# --------------------------------------------------------------------------- #
# T-25 / AC-26：软删全部活跃 NIC（及其它活跃子资源）后宿主可删
# --------------------------------------------------------------------------- #
def test_t25_host_deletable_after_nics_soft_deleted(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_id, "n1")
    first = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth0")).json()
    second = client.post("/api/network-interfaces", json=_nic_payload(host["id"], "eth1")).json()

    # 有活跃 NIC 时不可删
    assert client.delete(f"/api/bare-metals/{host['id']}").status_code == 409
    # 软删第一张后仍不可删
    assert client.delete(f"/api/network-interfaces/{first['id']}").status_code == 204
    assert client.delete(f"/api/bare-metals/{host['id']}").status_code == 409
    # 软删第二张后可删
    assert client.delete(f"/api/network-interfaces/{second['id']}").status_code == 204
    assert client.delete(f"/api/bare-metals/{host['id']}").status_code == 204


# --------------------------------------------------------------------------- #
# T-30 / AC-31：不注册 IP 端点、无 ip_addresses 表、无 IP 字段 / cluster_id 列
# --------------------------------------------------------------------------- #
def test_t30_no_ip_semantics(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base

    paths = set(client.app.openapi()["paths"])
    assert not any("ip-address" in path or "ip_address" in path for path in paths)
    assert "ip_addresses" not in Base.metadata.tables
    assert "ip_addresses" not in {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ).fetchall()
    }

    columns = {column.name for column in Base.metadata.tables["network_interfaces"].columns}
    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='network_interfaces'"
        ).fetchall()
    }
    for forbidden in (*IP_FIELDS, "cluster_id"):
        assert forbidden not in columns
        assert forbidden not in db_columns

    from app.network_interfaces.schemas import (
        NetworkInterfaceCreate,
        NetworkInterfaceRead,
        NetworkInterfaceUpdate,
    )

    for model in (NetworkInterfaceCreate, NetworkInterfaceRead, NetworkInterfaceUpdate):
        for forbidden in IP_FIELDS:
            assert forbidden not in model.model_fields, f"{model.__name__}.{forbidden}"


# --------------------------------------------------------------------------- #
# T-31 / AC-32：不越界 VM / Container / Service / Cluster 视角；无 VM 归属列
# --------------------------------------------------------------------------- #
def test_t31_no_other_resource_or_carrier_structure(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base

    paths = set(client.app.openapi()["paths"])
    forbidden_prefixes = ("virtual-machine", "vm", "container", "service", "cluster")
    offenders = [
        path
        for path in paths
        if path.startswith("/api/network-interfaces")
        and any(
            path[len("/api/network-interfaces") :].lstrip("/").startswith(p)
            for p in forbidden_prefixes
        )
    ]
    assert offenders == [], f"F004 不得注册其它资源端点：{offenders}"

    columns = {column.name for column in Base.metadata.tables["network_interfaces"].columns}
    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='network_interfaces'"
        ).fetchall()
    }
    for forbidden in CARRIER_FIELDS:
        assert forbidden not in columns
        assert forbidden not in db_columns


# --------------------------------------------------------------------------- #
# T-32 / AC-33：无 MAC / 速率 / MTU / 光模块 / 端口 / 自动发现 / 外部同步
# --------------------------------------------------------------------------- #
def test_t32_no_unconfirmed_hardware_or_sync_fields(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base

    columns = {column.name for column in Base.metadata.tables["network_interfaces"].columns}
    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='network_interfaces'"
        ).fetchall()
    }
    for forbidden in HARDWARE_FIELDS:
        assert forbidden not in columns
        assert forbidden not in db_columns

    for path in client.app.openapi()["paths"]:
        if path.startswith("/api/network-interfaces"):
            assert not any(
                token in path.lower()
                for token in ("sync", "discover", "platform", "credential", "external")
            )


# --------------------------------------------------------------------------- #
# 认证覆盖：未认证 → 401（不改变数据）
# --------------------------------------------------------------------------- #
def test_unauthenticated_requires_session(app_client_and_raw):
    client, conn = app_client_and_raw
    response = client.get("/api/network-interfaces")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert _total_nic_rows(conn) == 0
