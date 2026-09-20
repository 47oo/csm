"""F019 搜索结果聚合视图 API / DB 行为测试（T-19-01 ~ T-19-12）。

配对使用 ``auth_client_and_raw``：产品客户端用于构造与断言，**绕过应用层**的
原始 psycopg 连接用于预置软删行 / 直改数据库（架构 Test Work）。覆盖：用户示例
（IP → NIC → BareMetal 关系扩展，AC-A3）、命中 / 关联行标注与推导路径（AC-A2）、
单元组织顺序与标识字段优先（AC-A6/A8）、跨单元不去重（AC-A5）、仅搜索涉及资源
（AC-A4）、单元级分页（契约）、canonical 逐字段一致（T-19-11）、软删过滤
（AC-02）、只读（AC-01）、401/400/404/Empty（AC-03/04）、大小写不敏感与子串包含、
字段封闭负例。

顶层响应恒为**单一扁平列表**（AC-A1），不按资源类型分区。
"""

from __future__ import annotations

import pytest

SEARCH = "/api/clusters/{}/search"

CANONICAL_PATH = {
    "BARE_METAL": "/api/bare-metals/{}",
    "NETWORK_INTERFACE": "/api/network-interfaces/{}",
    "IP_ADDRESS": "/api/ip-addresses/{}",
    "VIRTUAL_MACHINE": "/api/virtual-machines/{}",
    "CONTAINER": "/api/containers/{}",
    "SERVICE": "/api/services/{}",
}

ALL_TYPES = set(CANONICAL_PATH)

#: 契约 §4.1 ``SearchResultRow`` 的封闭字段集合。
ROW_FIELDS = {
    "resource_type",
    "id",
    "role",
    "group_key",
    "matched_fields",
    "derivation_path",
    "resource",
}


# --------------------------------------------------------------------------- #
# 构造辅助（全部走既有 canonical 写入端点）
# --------------------------------------------------------------------------- #
def _create_cluster(client, name: str) -> int:
    response = client.post("/api/clusters", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_bare_metal(client, cluster_id: int, hostname: str, **fields) -> int:
    payload = {"cluster_id": cluster_id, "hostname": hostname, **fields}
    response = client.post("/api/bare-metals", json=payload)
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


def _create_vm(client, bare_metal_id: int, name: str, **fields) -> int:
    response = client.post(
        "/api/virtual-machines", json={"bare_metal_id": bare_metal_id, "name": name, **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_container(client, carrier_type: str, carrier_id: int, name: str, **fields) -> int:
    response = client.post(
        "/api/containers",
        json={
            "carrier_type": carrier_type,
            "carrier_id": carrier_id,
            "name": name,
            **fields,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_service(client, name: str, carriers: list[tuple[str, int]], **fields) -> int:
    response = client.post(
        "/api/services",
        json={
            "name": name,
            "carriers": [
                {"carrier_type": carrier_type, "carrier_id": carrier_id}
                for carrier_type, carrier_id in carriers
            ],
            **fields,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _search(client, cluster_id: int, keyword: str, **params):
    return client.get(SEARCH.format(cluster_id), params={"keyword": keyword, **params})


def _items(body: dict) -> list[dict]:
    return body["items"]


def _hit_rows(body: dict) -> list[dict]:
    return [item for item in body["items"] if item["role"] == "HIT"]


def _units(body: dict) -> list[tuple[dict, list[dict]]]:
    """按 ``group_key`` 连续段切分组织单元（保持响应顺序）。"""
    units: list[tuple[dict, list[dict]]] = []
    for item in body["items"]:
        key = item["group_key"]
        if not units or units[-1][0] != key:
            units.append((key, []))
        units[-1][1].append(item)
    return units


def _key(resource_type: str, resource_id: int) -> dict:
    return {"resource_type": resource_type, "id": resource_id}


def _assert_row_invariants(body: dict) -> None:
    """逐行断言契约封闭字段、角色与推导路径头尾（AC-A1/A2）。"""
    for item in body["items"]:
        assert set(item) == ROW_FIELDS, item
        assert set(item["group_key"]) == {"resource_type", "id"}
        assert item["id"] == item["resource"]["id"]
        assert item["role"] in {"HIT", "RELATED"}
        if item["role"] == "HIT":
            assert item["matched_fields"], "HIT 行 matched_fields 必须非空"
            assert item["derivation_path"] is None
        else:
            path = item["derivation_path"]
            assert path is not None and len(path) >= 2, item
            assert path[0] == item["group_key"], "推导路径首元素 = 本单元命中项"
            assert path[-1] == _key(item["resource_type"], item["id"])


def _assert_unit_invariants(body: dict) -> None:
    for group_key, rows in _units(body):
        assert rows[0]["role"] == "HIT", "命中行恒为单元首行（AC-A8）"
        assert rows[0]["group_key"] == group_key
        for row in rows[1:]:
            assert row["role"] == "RELATED"
            assert row["group_key"] == group_key


def _build_shared_scenario(client) -> dict[str, int]:
    """同一 BM 下六类资源均以 ``zshared`` 命名 / 标识（供混合列表测试）。"""
    cluster = _create_cluster(client, "cluster-shared")
    bare_metal = _create_bare_metal(client, cluster, "zshared-node")
    nic = _create_nic(client, bare_metal, "zshared-eth")
    ip = _create_ip(client, nic, "zshared-ip")
    vm = _create_vm(client, bare_metal, "zshared-vm")
    container = _create_container(client, "BARE_METAL", bare_metal, "zshared-ctr")
    service = _create_service(client, "zshared-svc", [("BARE_METAL", bare_metal)])
    return {
        "cluster": cluster,
        "bare_metal": bare_metal,
        "nic": nic,
        "ip": ip,
        "vm": vm,
        "container": container,
        "service": service,
    }


# --------------------------------------------------------------------------- #
# T-19-01 / AC-A3 / 用户示例：IP → NIC → BareMetal 关系扩展
# --------------------------------------------------------------------------- #
def test_t19_01_ip_hit_expands_to_nic_and_bare_metal(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-ip")
    bare_metal = _create_bare_metal(client, cluster, "cn001")
    nic = _create_nic(client, bare_metal, "eth0")
    ip = _create_ip(client, nic, "10.0.1.1/16")

    response = _search(client, cluster, "10.0.1")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1, "仅一个命中项（该 IP）"
    assert body["page"] == 1 and body["page_size"] == 50

    _assert_row_invariants(body)
    _assert_unit_invariants(body)

    # 单一扁平列表：HIT(IP) + RELATED(BM) + RELATED(NIC)，不按类型分区。
    assert [item["role"] for item in body["items"]] == ["HIT", "RELATED", "RELATED"]
    by_key = {(item["resource_type"], item["id"]): item for item in body["items"]}
    assert set(by_key) == {
        ("IP_ADDRESS", ip),
        ("BARE_METAL", bare_metal),
        ("NETWORK_INTERFACE", nic),
    }

    hit = by_key[("IP_ADDRESS", ip)]
    assert hit["matched_fields"] == ["ip_address"]
    assert hit["derivation_path"] is None

    # 网卡 / 裸金属自身字段未命中关键字，仍作为 RELATED 出现（AC-A3）。
    bare_metal_row = by_key[("BARE_METAL", bare_metal)]
    assert bare_metal_row["role"] == "RELATED"
    assert bare_metal_row["matched_fields"] == []
    assert bare_metal_row["derivation_path"] == [
        _key("IP_ADDRESS", ip),
        _key("NETWORK_INTERFACE", nic),
        _key("BARE_METAL", bare_metal),
    ]

    nic_row = by_key[("NETWORK_INTERFACE", nic)]
    assert nic_row["role"] == "RELATED"
    assert nic_row["matched_fields"] == []
    assert nic_row["derivation_path"] == [
        _key("IP_ADDRESS", ip),
        _key("NETWORK_INTERFACE", nic),
    ]


def test_t19_02_derivation_path_through_vm_and_container_to_service(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-chain")
    bare_metal = _create_bare_metal(client, cluster, "chain-node")
    vm = _create_vm(client, bare_metal, "chain-vm")
    container = _create_container(client, "VIRTUAL_MACHINE", vm, "chain-ctr")
    service = _create_service(client, "chain-svc", [("CONTAINER", container)])

    body = _search(client, cluster, "chain-node").json()
    assert body["total"] == 1
    _assert_row_invariants(body)
    _assert_unit_invariants(body)

    by_key = {(item["resource_type"], item["id"]): item for item in body["items"]}
    assert by_key[("SERVICE", service)]["derivation_path"] == [
        _key("BARE_METAL", bare_metal),
        _key("VIRTUAL_MACHINE", vm),
        _key("CONTAINER", container),
        _key("SERVICE", service),
    ]
    assert by_key[("CONTAINER", container)]["derivation_path"] == [
        _key("BARE_METAL", bare_metal),
        _key("VIRTUAL_MACHINE", vm),
        _key("CONTAINER", container),
    ]


# --------------------------------------------------------------------------- #
# T-19-03 / AC-A1 / AC-A6 / AC-A8：混合列表、单元顺序、标识字段优先
# --------------------------------------------------------------------------- #
def test_t19_03_identity_field_hits_rank_before_descriptive_hits(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-rank")
    identity = _create_bare_metal(client, cluster, "acme-host")
    descriptive = _create_bare_metal(client, cluster, "plain-host", vendor="acme-vendor")

    body = _search(client, cluster, "acme", page_size=200).json()
    hit_ids = [item["id"] for item in _hit_rows(body)]
    assert hit_ids == [identity, descriptive], "标识字段命中必须排在仅描述性字段命中之前"
    assert _hit_rows(body)[0]["resource_type"] == "BARE_METAL"


def test_t19_03_single_flat_list_and_unit_order(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_shared_scenario(client)

    body = _search(client, ids["cluster"], "zshared", page_size=200).json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 6, "六类资源各自为一个命中项（组织单元）"
    _assert_row_invariants(body)
    _assert_unit_invariants(body)

    # 单元按 (type rank, id) 排列；命中行顺序即为固定类型序。
    hit_types = [item["resource_type"] for item in _hit_rows(body)]
    assert hit_types == [
        "BARE_METAL",
        "NETWORK_INTERFACE",
        "IP_ADDRESS",
        "VIRTUAL_MACHINE",
        "CONTAINER",
        "SERVICE",
    ]

    # 每个单元的命中行恒为首行，关联行紧随其后（AC-A8）。
    for _, rows in _units(body):
        assert rows[0]["resource_type"] == rows[0]["group_key"]["resource_type"]
        assert rows[0]["id"] == rows[0]["group_key"]["id"]


def test_t19_03_matched_fields_follow_contract_declaration_order(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-multi")
    bare_metal = _create_bare_metal(client, cluster, "zz-multi", vendor="zz-multi", cpu="zz-multi")

    body = _search(client, cluster, "zz-multi").json()
    assert body["total"] == 1
    hit = _hit_rows(body)[0]
    assert hit["id"] == bare_metal
    assert hit["matched_fields"] == ["hostname", "vendor", "cpu"]


# --------------------------------------------------------------------------- #
# T-19-04 / AC-A5：跨单元不去重
# --------------------------------------------------------------------------- #
def test_t19_04_related_resource_repeats_across_units(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-dedupe")
    bare_metal = _create_bare_metal(client, cluster, "dedupe-node")
    nic_a = _create_nic(client, bare_metal, "eth-aa")
    nic_b = _create_nic(client, bare_metal, "eth-bb")
    ip_a = _create_ip(client, nic_a, "10.9.9.1")
    ip_b = _create_ip(client, nic_b, "10.9.9.2")

    body = _search(client, cluster, "10.9.9", page_size=200).json()
    assert body["total"] == 2, "两个 IP 命中项 → 两个组织单元"

    units = _units(body)
    assert [unit[0] for unit in units] == [_key("IP_ADDRESS", ip_a), _key("IP_ADDRESS", ip_b)]

    # 裸金属同时属于两条命中链 → 出现两次，分属不同单元（AC-A5）。
    bare_metal_rows = [
        item
        for item in body["items"]
        if item["resource_type"] == "BARE_METAL" and item["id"] == bare_metal
    ]
    assert len(bare_metal_rows) == 2
    assert {row["group_key"]["id"] for row in bare_metal_rows} == {ip_a, ip_b}

    # 每条单元都完整包含 G(BM) 的其余成员。
    expected_chain = {
        ("BARE_METAL", bare_metal),
        ("NETWORK_INTERFACE", nic_a),
        ("NETWORK_INTERFACE", nic_b),
        ("IP_ADDRESS", ip_a),
        ("IP_ADDRESS", ip_b),
    }
    for _, rows in units:
        assert {(row["resource_type"], row["id"]) for row in rows} == expected_chain


# --------------------------------------------------------------------------- #
# T-19-06 / AC-A4：仅搜索涉及资源；不做全量倾销
# --------------------------------------------------------------------------- #
def test_t19_06_unrelated_resource_not_dumped(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-scope")
    involved = _create_bare_metal(client, cluster, "zz-involved")
    involved_nic = _create_nic(client, involved, "zz-involved-eth")
    unrelated = _create_bare_metal(client, cluster, "zz-unrelated")

    body = _search(client, cluster, "zz-involved").json()
    found = {(item["resource_type"], item["id"]) for item in body["items"]}
    assert found == {
        ("BARE_METAL", involved),
        ("NETWORK_INTERFACE", involved_nic),
    }, "仅命中项 + 其关联链资源"
    assert all(item["id"] != unrelated for item in body["items"])


def test_t19_06_cluster_name_is_not_a_result_row(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "zz-cluster-name-token")
    _create_bare_metal(client, cluster, "node-a")

    body = _search(client, cluster, "zz-cluster-name-token").json()
    assert body["items"] == []
    assert body["total"] == 0


# --------------------------------------------------------------------------- #
# T-19-07 / AC-02：命中行与关联行均过滤软删
# --------------------------------------------------------------------------- #
def test_t19_07_soft_deleted_related_resource_excluded(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-soft")
    bare_metal = _create_bare_metal(client, cluster, "zagg-node")
    nic = _create_nic(client, bare_metal, "zagg-eth")

    before = _search(client, cluster, "zagg", page_size=200).json()
    assert {item["id"] for item in before["items"]} >= {bare_metal, nic}

    conn.execute("UPDATE network_interfaces SET deleted_at = now() WHERE id = %s", (nic,))

    after = _search(client, cluster, "zagg", page_size=200).json()
    _assert_row_invariants(after)
    assert all(
        (item["resource_type"], item["id"]) != ("NETWORK_INTERFACE", nic) for item in after["items"]
    ), "软删关联行不得出现"
    assert ("BARE_METAL", bare_metal) in {
        (item["resource_type"], item["id"]) for item in _hit_rows(after)
    }
    assert after["total"] == 1, "仅裸金属自身命中"


def test_t19_07_soft_deleted_hit_resource_excluded(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-soft-hit")
    bare_metal = _create_bare_metal(client, cluster, "zsoft-node")
    _create_nic(client, bare_metal, "zsoft-eth")

    assert _search(client, cluster, "zsoft", page_size=200).json()["total"] == 2
    conn.execute("UPDATE bare_metals SET deleted_at = now() WHERE id = %s", (bare_metal,))
    assert _search(client, cluster, "zsoft", page_size=200).json()["total"] == 0


# --------------------------------------------------------------------------- #
# T-19-08 / AC-01：只读
# --------------------------------------------------------------------------- #
def test_t19_08_search_is_read_only(auth_client_and_raw):
    client, conn = auth_client_and_raw
    ids = _build_shared_scenario(client)
    tracked = [
        ("bare_metals", ids["bare_metal"]),
        ("network_interfaces", ids["nic"]),
        ("ip_addresses", ids["ip"]),
        ("virtual_machines", ids["vm"]),
        ("containers", ids["container"]),
        ("services", ids["service"]),
    ]

    def snapshot():
        return {
            (table, row_id): conn.execute(
                f"SELECT updated_at FROM {table} WHERE id = %s", (row_id,)
            ).fetchone()
            for table, row_id in tracked
        }

    before = snapshot()
    assert _search(client, ids["cluster"], "zshared", page_size=200).status_code == 200
    assert snapshot() == before


# --------------------------------------------------------------------------- #
# T-19-09 / AC-03 / AC-04：401 / 400 / 404 / Empty
# --------------------------------------------------------------------------- #
def test_t19_09_missing_cluster_returns_404(auth_client_and_raw):
    client, _ = auth_client_and_raw
    response = _search(client, 999999, "anything")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"] == []
    assert "items" not in response.text


def test_t19_09_soft_deleted_cluster_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-gone")
    _create_bare_metal(client, cluster, "zshared-node")
    conn.execute("UPDATE clusters SET deleted_at = now() WHERE id = %s", (cluster,))

    response = _search(client, cluster, "zshared")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_t19_09_active_cluster_no_match_is_empty_200(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-empty")
    _create_bare_metal(client, cluster, "node-a")

    response = _search(client, cluster, "no-such-token-anywhere")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.parametrize("keyword", ["", " ", "   ", "\t", "\n"])
def test_t19_09_blank_keyword_returns_400(auth_client_and_raw, keyword):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-blank")

    response = client.get(SEARCH.format(cluster), params={"keyword": keyword})
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "keyword" for detail in body["error"]["details"])


@pytest.mark.parametrize("keyword", ["", "   "])
def test_t19_09_blank_keyword_precedes_cluster_404(auth_client_and_raw, keyword):
    client, _ = auth_client_and_raw
    response = client.get(SEARCH.format(999999), params={"keyword": keyword})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_t19_09_missing_keyword_returns_400(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-missing-kw")
    response = client.get(SEARCH.format(cluster))
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "keyword" for detail in body["error"]["details"])


def test_t19_09_unauthenticated_returns_401(app_client):
    response = app_client.get(SEARCH.format(1), params={"keyword": "x"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert "items" not in response.text


# --------------------------------------------------------------------------- #
# T-19-10 / 契约：单元级分页（单元不被拆散，跨页不重不漏）
# --------------------------------------------------------------------------- #
def test_t19_10_unit_level_pagination_never_splits_units(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-page")
    bare_metal = _create_bare_metal(client, cluster, "pg-node")
    nic_a = _create_nic(client, bare_metal, "eth-aa")
    nic_b = _create_nic(client, bare_metal, "eth-bb")
    ip_a = _create_ip(client, nic_a, "10.9.9.1")
    ip_b = _create_ip(client, nic_b, "10.9.9.2")

    overall = _search(client, cluster, "10.9.9", page_size=200).json()
    assert overall["total"] == 2

    first = _search(client, cluster, "10.9.9", page=1, page_size=1).json()
    assert first["total"] == 2
    assert first["page"] == 1 and first["page_size"] == 1
    assert {item["group_key"]["id"] for item in first["items"]} == {ip_a}
    assert len(first["items"]) == 5, "单元的整体（HIT + 4 RELATED）不得被 page_size=1 拆散"

    second = _search(client, cluster, "10.9.9", page=2, page_size=1).json()
    assert {item["group_key"]["id"] for item in second["items"]} == {ip_b}
    assert len(second["items"]) == 5

    beyond = _search(client, cluster, "10.9.9", page=99, page_size=1).json()
    assert beyond["total"] == 2
    assert beyond["items"] == []


def test_t19_10_total_counts_units_not_rows(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_shared_scenario(client)

    body = _search(client, ids["cluster"], "zshared", page_size=200).json()
    assert body["total"] == 6, "total = 组织单元（命中项）数"
    assert len(body["items"]) > body["total"], "每单元可含关联行，故行数可大于 total"


# --------------------------------------------------------------------------- #
# T-19-11 / 契约：resource 与对应 canonical *Read 逐字段一致
# --------------------------------------------------------------------------- #
def test_t19_11_resource_matches_canonical_read(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_shared_scenario(client)
    token_to_type = {
        "zshared-node": "BARE_METAL",
        "zshared-eth": "NETWORK_INTERFACE",
        "zshared-ip": "IP_ADDRESS",
        "zshared-vm": "VIRTUAL_MACHINE",
        "zshared-ctr": "CONTAINER",
        "zshared-svc": "SERVICE",
    }

    for token, resource_type in token_to_type.items():
        body = _search(client, ids["cluster"], token, page_size=200).json()
        hits = [i for i in _hit_rows(body) if i["resource_type"] == resource_type]
        assert len(hits) == 1, f"{resource_type} 应恰一条命中行：{hits}"
        item = hits[0]

        canonical = client.get(CANONICAL_PATH[resource_type].format(item["id"]))
        assert canonical.status_code == 200, canonical.text
        assert item["resource"] == canonical.json(), resource_type
        assert "deleted_at" not in item["resource"]


# --------------------------------------------------------------------------- #
# 匹配语义（继承 F018 §2，未被 F019 取代）：大小写不敏感 + 子串包含
# --------------------------------------------------------------------------- #
def test_search_case_insensitive_same_result_set(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_shared_scenario(client)

    lower = _search(client, ids["cluster"], "zshared", page_size=200).json()
    upper = _search(client, ids["cluster"], "ZSHARED", page_size=200).json()
    assert lower["total"] == upper["total"] > 0
    assert [i["id"] for i in lower["items"]] == [i["id"] for i in upper["items"]]


def test_search_substring_containment(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_shared_scenario(client)

    assert _search(client, ids["cluster"], "hare", page_size=200).json()["total"] == 6
    assert _search(client, ids["cluster"], "shrd").json()["total"] == 0
    assert _search(client, ids["cluster"], "zsharx").json()["total"] == 0


def test_search_status_and_timestamps_do_not_match(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-closed")
    bare_metal = _create_bare_metal(client, cluster, "quiet-node", status="DOWN")
    conn.execute(
        "UPDATE bare_metals SET created_at = '1999-04-05T00:00:00Z',"
        " updated_at = '1999-04-05T00:00:00Z' WHERE id = %s",
        (bare_metal,),
    )

    assert _search(client, cluster, "DOWN").json()["total"] == 0
    assert _search(client, cluster, "1999-04-05").json()["total"] == 0
    assert _search(client, cluster, "quiet").json()["total"] == 1


def test_search_other_cluster_resources_excluded(auth_client_and_raw):
    client, _ = auth_client_and_raw
    mine = _create_cluster(client, "cluster-agg-mine")
    other = _create_cluster(client, "cluster-agg-other")
    my_bm = _create_bare_metal(client, mine, "scope-a")
    other_bm = _create_bare_metal(client, other, "scope-b")

    body = _search(client, mine, "scope", page_size=200).json()
    assert {item["id"] for item in body["items"]} == {my_bm}
    assert other_bm not in {item["id"] for item in body["items"]}


# --------------------------------------------------------------------------- #
# 契约：非整数 cluster_id → 400；分页参数越界 → 400
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["abc", "1.5", "12x"])
def test_non_integer_cluster_id_returns_400(auth_client_and_raw, value):
    client, _ = auth_client_and_raw
    response = client.get(f"/api/clusters/{value}/search", params={"keyword": "x"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("page_size", [0, 201])
def test_invalid_page_size_returns_400(auth_client_and_raw, page_size):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-agg-page-size")
    response = _search(client, cluster, "x", page_size=page_size)
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "page_size" for detail in body["error"]["details"])
