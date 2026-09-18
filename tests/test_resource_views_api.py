"""F010 资源详情与关联查询 API / DB 行为测试（T-10-01 ~ T-10-10）。

配对使用 ``auth_client_and_raw``：产品客户端用于构造与断言，**绕过应用层**的原始
psycopg 连接用于预置软删行 / 绕过守卫地直改数据库（架构 Test Work）。

覆盖：五类成员集合与条目字段（AC-01~AC-08）、中文 / 特殊字符字面往返（AC-09）、
不存在与已软删主体的 404（AC-10）、空集合（AC-11/AC-12）、已软删子资源不出现
（AC-14）、DELETE 后消失且不级联（AC-15）、主体软删 → 404（AC-16）、
与 canonical 的成员集合深等（AC-18）、未认证 401（AC-24）、非整数 id 400。
"""

from __future__ import annotations

import pytest

RELATED = "/api/bare-metals/{}/related"

NIC_FIELDS = {
    "id",
    "bare_metal_id",
    "name",
    "technology_type",
    "purpose",
    "created_at",
    "updated_at",
}
IP_FIELDS = {"id", "network_interface_id", "ip_address", "created_at", "updated_at"}
VM_FIELDS = {
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
CONTAINER_FIELDS = {
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
SERVICE_FIELDS = {
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
CLASSES = (
    "network_interfaces",
    "ip_addresses",
    "virtual_machines",
    "containers",
    "services",
)


# --------------------------------------------------------------------------- #
# 构造辅助（全部走既有 canonical 写入端点）
# --------------------------------------------------------------------------- #
def _create_cluster(client, name: str) -> int:
    response = client.post("/api/clusters", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_bare_metal(client, cluster_id: int, hostname: str) -> int:
    response = client.post(
        "/api/bare-metals", json={"cluster_id": cluster_id, "hostname": hostname}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_nic(
    client,
    bare_metal_id: int,
    name: str,
    technology_type: str = "Ethernet",
    purpose: str = "Business",
) -> int:
    response = client.post(
        "/api/network-interfaces",
        json={
            "bare_metal_id": bare_metal_id,
            "name": name,
            "technology_type": technology_type,
            "purpose": purpose,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_ip(client, network_interface_id: int, ip_address: str) -> int:
    response = client.post(
        "/api/ip-addresses",
        json={"network_interface_id": network_interface_id, "ip_address": ip_address},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_vm(client, bare_metal_id: int, name: str) -> int:
    response = client.post(
        "/api/virtual-machines", json={"bare_metal_id": bare_metal_id, "name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_container(client, carrier_type: str, carrier_id: int, name: str) -> int:
    response = client.post(
        "/api/containers",
        json={"carrier_type": carrier_type, "carrier_id": carrier_id, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_service(client, name: str, carriers: list[tuple[str, int]]) -> int:
    response = client.post(
        "/api/services",
        json={
            "name": name,
            "carriers": [
                {"carrier_type": carrier_type, "carrier_id": carrier_id}
                for carrier_type, carrier_id in carriers
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _related(client, bare_metal_id: int):
    return client.get(RELATED.format(bare_metal_id))


def _ids(body: dict, key: str) -> list[int]:
    return [item["id"] for item in body[key]["items"]]


def _assert_envelope(body: dict) -> None:
    assert set(body) == set(CLASSES)
    for key in CLASSES:
        value = body[key]
        assert set(value) == {"items", "total"}
        assert value["total"] == len(value["items"])


def _build_scenario(client) -> dict[str, int]:
    """B 上：2 NIC（3 IP）、2 VM、直接与间接 Container、B/VM/Container 三载体 Service。"""
    cluster = _create_cluster(client, "cluster-a")
    bare_metal = _create_bare_metal(client, cluster, "node-a")
    other = _create_bare_metal(client, cluster, "node-b")

    nic1 = _create_nic(client, bare_metal, "eth0")
    nic2 = _create_nic(client, bare_metal, "eth1")
    other_nic = _create_nic(client, other, "eth-other")

    ip1 = _create_ip(client, nic1, "10.0.0.1")
    ip2 = _create_ip(client, nic1, "10.0.0.2")
    ip3 = _create_ip(client, nic2, "10.0.0.3")
    _create_ip(client, other_nic, "9.9.9.9")

    vm1 = _create_vm(client, bare_metal, "vm-a")
    vm2 = _create_vm(client, bare_metal, "vm-b")
    _create_vm(client, other, "vm-other")

    ctr_direct = _create_container(client, "BARE_METAL", bare_metal, "ctr-direct")
    ctr_indirect = _create_container(client, "VIRTUAL_MACHINE", vm1, "ctr-vm")
    _create_container(client, "BARE_METAL", other, "ctr-other")

    svc_b = _create_service(client, "svc-b", [("BARE_METAL", bare_metal)])
    svc_vm = _create_service(client, "svc-vm", [("VIRTUAL_MACHINE", vm1)])
    svc_ctr = _create_service(client, "svc-ctr", [("CONTAINER", ctr_indirect)])
    svc_multi = _create_service(
        client, "svc-multi", [("BARE_METAL", bare_metal), ("VIRTUAL_MACHINE", vm1)]
    )
    _create_service(client, "svc-other", [("BARE_METAL", other)])

    return {
        "cluster": cluster,
        "bare_metal": bare_metal,
        "other": other,
        "nic1": nic1,
        "nic2": nic2,
        "ip1": ip1,
        "ip2": ip2,
        "ip3": ip3,
        "vm1": vm1,
        "vm2": vm2,
        "ctr_direct": ctr_direct,
        "ctr_indirect": ctr_indirect,
        "svc_b": svc_b,
        "svc_vm": svc_vm,
        "svc_ctr": svc_ctr,
        "svc_multi": svc_multi,
    }


# --------------------------------------------------------------------------- #
# T-10-01 / AC-01 ~ AC-08：五类成员集合、条目字段与关系依据
# --------------------------------------------------------------------------- #
def test_t10_01_member_sets_and_entry_fields(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_scenario(client)

    response = _related(client, ids["bare_metal"])
    assert response.status_code == 200, response.text
    body = response.json()
    _assert_envelope(body)

    assert _ids(body, "network_interfaces") == [ids["nic1"], ids["nic2"]]
    assert _ids(body, "ip_addresses") == [ids["ip1"], ids["ip2"], ids["ip3"]]
    assert _ids(body, "virtual_machines") == [ids["vm1"], ids["vm2"]]
    assert _ids(body, "containers") == [ids["ctr_direct"], ids["ctr_indirect"]]
    assert sorted(_ids(body, "services")) == sorted(
        [ids["svc_b"], ids["svc_vm"], ids["svc_ctr"], ids["svc_multi"]]
    )

    assert all(set(item) == NIC_FIELDS for item in body["network_interfaces"]["items"])
    assert all(set(item) == IP_FIELDS for item in body["ip_addresses"]["items"])
    assert all(set(item) == VM_FIELDS for item in body["virtual_machines"]["items"])
    assert all(set(item) == CONTAINER_FIELDS for item in body["containers"]["items"])
    assert all(set(item) == SERVICE_FIELDS for item in body["services"]["items"])


def test_t10_01_relation_evidence_is_visible(auth_client_and_raw):
    """AC-08：每条目可观察到使其与 B 相关的直接绑定依据。"""
    client, _ = auth_client_and_raw
    ids = _build_scenario(client)
    body = _related(client, ids["bare_metal"]).json()

    for item in body["network_interfaces"]["items"]:
        assert item["bare_metal_id"] == ids["bare_metal"]
    for item in body["ip_addresses"]["items"]:
        assert item["network_interface_id"] in {ids["nic1"], ids["nic2"]}
        assert item["ip_address"] in {"10.0.0.1", "10.0.0.2", "10.0.0.3"}
    for item in body["virtual_machines"]["items"]:
        assert item["bare_metal_id"] == ids["bare_metal"]
    for item in body["containers"]["items"]:
        assert (item["carrier_type"], item["carrier_id"]) in {
            ("BARE_METAL", ids["bare_metal"]),
            ("VIRTUAL_MACHINE", ids["vm1"]),
        }

    related_carriers = {
        ("BARE_METAL", ids["bare_metal"]),
        ("VIRTUAL_MACHINE", ids["vm1"]),
        ("VIRTUAL_MACHINE", ids["vm2"]),
        ("CONTAINER", ids["ctr_direct"]),
        ("CONTAINER", ids["ctr_indirect"]),
    }
    for item in body["services"]["items"]:
        observed = {(c["carrier_type"], c["carrier_id"]) for c in item["carriers"]}
        assert observed & related_carriers, item["name"]


def test_t10_01_multi_carrier_service_appears_once(auth_client_and_raw):
    """AC-07-a：同一 Service 绑定多个与 B 相关载体时只出现一次。"""
    client, _ = auth_client_and_raw
    ids = _build_scenario(client)
    services = _ids(_related(client, ids["bare_metal"]).json(), "services")
    assert services.count(ids["svc_multi"]) == 1


def test_t10_01_other_bare_metal_resources_excluded(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_scenario(client)
    body = _related(client, ids["bare_metal"]).json()
    other_body = _related(client, ids["other"]).json()

    # 逐类：B 的成员集合与 B2 的成员集合（同一资源表内 id 唯一）互不相交。
    for key in CLASSES:
        mine = {item["id"] for item in body[key]["items"]}
        theirs = {item["id"] for item in other_body[key]["items"]}
        assert mine & theirs == set(), key
        assert theirs, f"B2 应至少有一个 {key} 成员以证明隔离"


# --------------------------------------------------------------------------- #
# T-10-02 / AC-09：中文 / 特殊字符字面往返
# --------------------------------------------------------------------------- #
def test_t10_02_literal_roundtrip(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "集群-甲")
    bare_metal = _create_bare_metal(client, cluster, "节点｜甲#1")
    nic = _create_nic(client, bare_metal, "网卡-α / eth0")
    ip = _create_ip(client, nic, "地址-特殊#1")
    vm = _create_vm(client, bare_metal, "虚机·β")
    container = _create_container(client, "VIRTUAL_MACHINE", vm, "容器/γ")
    service = _create_service(client, "服务—δ", [("CONTAINER", container)])

    body = _related(client, bare_metal).json()
    assert body["network_interfaces"]["items"][0]["name"] == "网卡-α / eth0"
    assert body["ip_addresses"]["items"][0]["ip_address"] == "地址-特殊#1"
    assert body["virtual_machines"]["items"][0]["name"] == "虚机·β"
    assert body["containers"]["items"][0]["name"] == "容器/γ"
    assert body["services"]["items"][0]["name"] == "服务—δ"

    assert _ids(body, "network_interfaces") == [nic]
    assert _ids(body, "ip_addresses") == [ip]
    assert _ids(body, "virtual_machines") == [vm]
    assert _ids(body, "containers") == [container]
    assert _ids(body, "services") == [service]


# --------------------------------------------------------------------------- #
# T-10-03 / AC-10：不存在与已软删主体 → 404
# --------------------------------------------------------------------------- #
def test_t10_03_missing_bare_metal_returns_404(auth_client_and_raw):
    client, _ = auth_client_and_raw
    response = _related(client, 999999)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["details"] == []


def test_t10_03_soft_deleted_bare_metal_with_children_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    ids = _build_scenario(client)
    conn.execute("UPDATE bare_metals SET deleted_at = now() WHERE id = %s", (ids["bare_metal"],))

    response = _related(client, ids["bare_metal"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert "network_interfaces" not in response.text


# --------------------------------------------------------------------------- #
# T-10-04 / AC-11、AC-12：活跃主体五类分别空 → 200 Empty
# --------------------------------------------------------------------------- #
def test_t10_04_active_bare_metal_all_classes_empty(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    bare_metal = _create_bare_metal(client, cluster, "empty-node")

    response = _related(client, bare_metal)
    assert response.status_code == 200
    body = response.json()
    _assert_envelope(body)
    for key in CLASSES:
        assert body[key] == {"items": [], "total": 0}


def test_t10_04_empty_class_does_not_flip_subject_to_404(auth_client_and_raw):
    """AC-12：B 活跃、仅一类非空，其余为空均 200（不得诱使 404）。"""
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    bare_metal = _create_bare_metal(client, cluster, "node-a")
    nic = _create_nic(client, bare_metal, "eth0")

    response = _related(client, bare_metal)
    assert response.status_code == 200
    body = response.json()
    assert _ids(body, "network_interfaces") == [nic]
    for key in ("ip_addresses", "virtual_machines", "containers", "services"):
        assert body[key] == {"items": [], "total": 0}


# --------------------------------------------------------------------------- #
# T-10-05 / AC-14：逐类已软删子资源不出现，其余不受影响
# --------------------------------------------------------------------------- #
def test_t10_05_soft_deleted_children_excluded(auth_client_and_raw):
    client, conn = auth_client_and_raw
    ids = _build_scenario(client)
    bare_metal = ids["bare_metal"]

    ghost_nic = conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose, deleted_at)"
        " VALUES (%s, 'ghost-nic', 'Ethernet', 'Business', now()) RETURNING id",
        (bare_metal,),
    ).fetchone()[0]
    ghost_ip = conn.execute(
        "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address, deleted_at)"
        " VALUES (%s, %s, '8.8.8.8', now()) RETURNING id",
        (ids["nic1"], ids["cluster"]),
    ).fetchone()[0]
    ghost_vm = conn.execute(
        "INSERT INTO virtual_machines (bare_metal_id, name, deleted_at)"
        " VALUES (%s, 'ghost-vm', now()) RETURNING id",
        (bare_metal,),
    ).fetchone()[0]
    ghost_ctr = conn.execute(
        "INSERT INTO containers (bare_metal_id, name, deleted_at)"
        " VALUES (%s, 'ghost-ctr', now()) RETURNING id",
        (bare_metal,),
    ).fetchone()[0]
    ghost_svc = conn.execute(
        "INSERT INTO services (name, deleted_at) VALUES ('ghost-svc', now()) RETURNING id"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO service_carriers (service_id, bare_metal_id) VALUES (%s, %s)",
        (ghost_svc, bare_metal),
    )

    body = _related(client, bare_metal).json()
    assert ghost_nic not in _ids(body, "network_interfaces")
    assert ghost_ip not in _ids(body, "ip_addresses")
    assert ghost_vm not in _ids(body, "virtual_machines")
    assert ghost_ctr not in _ids(body, "containers")
    assert ghost_svc not in _ids(body, "services")

    # 其余活跃条目不受影响
    assert _ids(body, "network_interfaces") == [ids["nic1"], ids["nic2"]]
    assert _ids(body, "ip_addresses") == [ids["ip1"], ids["ip2"], ids["ip3"]]
    assert _ids(body, "virtual_machines") == [ids["vm1"], ids["vm2"]]
    assert _ids(body, "containers") == [ids["ctr_direct"], ids["ctr_indirect"]]


# --------------------------------------------------------------------------- #
# T-10-06 / AC-15：DELETE 后消失、不级联；主体不受影响
# --------------------------------------------------------------------------- #
def test_t10_06_delete_removes_only_target(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    bare_metal = _create_bare_metal(client, cluster, "node-a")
    nic_with_ip = _create_nic(client, bare_metal, "eth0")
    ip_doomed = _create_ip(client, nic_with_ip, "10.0.0.1")
    nic_doomed = _create_nic(client, bare_metal, "eth1")
    vm_doomed = _create_vm(client, bare_metal, "vm-doomed")
    ctr_doomed = _create_container(client, "BARE_METAL", bare_metal, "ctr-doomed")
    svc_doomed = _create_service(client, "svc-doomed", [("BARE_METAL", bare_metal)])
    bare_metal_before = conn.execute(
        "SELECT cluster_id, hostname, status, created_at, updated_at, deleted_at"
        " FROM bare_metals WHERE id = %s",
        (bare_metal,),
    ).fetchone()

    assert client.delete(f"/api/ip-addresses/{ip_doomed}").status_code == 204
    assert ip_doomed not in _ids(_related(client, bare_metal).json(), "ip_addresses")
    assert nic_with_ip in _ids(_related(client, bare_metal).json(), "network_interfaces")

    assert client.delete(f"/api/network-interfaces/{nic_doomed}").status_code == 204
    assert nic_doomed not in _ids(_related(client, bare_metal).json(), "network_interfaces")

    assert client.delete(f"/api/virtual-machines/{vm_doomed}").status_code == 204
    assert vm_doomed not in _ids(_related(client, bare_metal).json(), "virtual_machines")

    assert client.delete(f"/api/containers/{ctr_doomed}").status_code == 204
    assert ctr_doomed not in _ids(_related(client, bare_metal).json(), "containers")

    assert client.delete(f"/api/services/{svc_doomed}").status_code == 204
    assert svc_doomed not in _ids(_related(client, bare_metal).json(), "services")

    assert (
        conn.execute(
            "SELECT cluster_id, hostname, status, created_at, updated_at, deleted_at"
            " FROM bare_metals WHERE id = %s",
            (bare_metal,),
        ).fetchone()
        == bare_metal_before
    )


# --------------------------------------------------------------------------- #
# T-10-07 / AC-16：主体软删 → 404（即使子行仍在）
# --------------------------------------------------------------------------- #
def test_t10_07_soft_deleted_subject_is_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    ids = _build_scenario(client)
    conn.execute("UPDATE bare_metals SET deleted_at = now() WHERE id = %s", (ids["bare_metal"],))
    children = conn.execute(
        "SELECT count(*) FROM network_interfaces WHERE bare_metal_id = %s", (ids["bare_metal"],)
    ).fetchone()[0]
    assert children == 2

    response = _related(client, ids["bare_metal"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# T-10-08 / AC-18：与 canonical 成员集合深等（证明复用而非重实现）
# --------------------------------------------------------------------------- #
def _canonical_ids(client, path: str, params: dict) -> set[int]:
    response = client.get(path, params={**params, "page_size": 200})
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


def test_t10_08_member_sets_deep_equal_canonical(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_scenario(client)
    bare_metal = ids["bare_metal"]
    body = _related(client, bare_metal).json()
    aggregated = {key: {item["id"] for item in body[key]["items"]} for key in CLASSES}

    canonical_nic = _canonical_ids(client, "/api/network-interfaces", {"bare_metal_id": bare_metal})
    canonical_ip: set[int] = set()
    for nic_id in canonical_nic:
        canonical_ip |= _canonical_ids(
            client, "/api/ip-addresses", {"network_interface_id": nic_id}
        )
    canonical_vm = _canonical_ids(client, "/api/virtual-machines", {"bare_metal_id": bare_metal})

    canonical_container: set[int] = _canonical_ids(
        client, "/api/containers", {"carrier_type": "BARE_METAL", "carrier_id": bare_metal}
    )
    for vm_id in canonical_vm:
        canonical_container |= _canonical_ids(
            client, "/api/containers", {"carrier_type": "VIRTUAL_MACHINE", "carrier_id": vm_id}
        )

    service_carriers = (
        [("BARE_METAL", bare_metal)]
        + [("VIRTUAL_MACHINE", vm_id) for vm_id in canonical_vm]
        + [("CONTAINER", ctr_id) for ctr_id in canonical_container]
    )
    canonical_service: set[int] = set()
    for carrier_type, carrier_id in service_carriers:
        canonical_service |= _canonical_ids(
            client,
            "/api/services",
            {"carrier_type": carrier_type, "carrier_id": carrier_id},
        )

    assert aggregated["network_interfaces"] == canonical_nic
    assert aggregated["ip_addresses"] == canonical_ip
    assert aggregated["virtual_machines"] == canonical_vm
    assert aggregated["containers"] == canonical_container
    assert aggregated["services"] == canonical_service


# --------------------------------------------------------------------------- #
# T-10-09 / AC-24：未认证 → 401
# --------------------------------------------------------------------------- #
def test_t10_09_unauthenticated_returns_401(app_client):
    response = app_client.get(RELATED.format(1))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert "network_interfaces" not in response.text


# --------------------------------------------------------------------------- #
# T-10-10 / 契约：非整数 bare_metal_id → 400 VALIDATION_ERROR
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["abc", "1.5", "12x"])
def test_t10_10_non_integer_id_returns_400(auth_client_and_raw, value):
    client, _ = auth_client_and_raw
    response = client.get(RELATED.format(value))
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "bare_metal_id" for detail in body["error"]["details"])


# --------------------------------------------------------------------------- #
# 完整快照：超过单页窗口的成员不得被静默截断（架构 REQUIRED：完整快照）
# --------------------------------------------------------------------------- #
def test_t10_08_full_snapshot_beyond_one_page(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-a")
    bare_metal = _create_bare_metal(client, cluster, "node-a")
    expected = [_create_nic(client, bare_metal, f"eth{index:03d}") for index in range(210)]

    response = _related(client, bare_metal)
    assert response.status_code == 200
    body = response.json()
    assert body["network_interfaces"]["total"] == 210
    assert _ids(body, "network_interfaces") == sorted(expected)
