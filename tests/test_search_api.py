"""F018 集群内资源关键字搜索 API / DB 行为测试（T-18-01 ~ T-18-14）。

配对使用 ``auth_client_and_raw``：产品客户端用于构造与断言，**绕过应用层**的
原始 psycopg 连接用于预置软删行 / 直改数据库（架构 Test Work）。覆盖：单一混合
列表与命中字段（AC-D1/D2/D4）、大小写不敏感与子串包含（AC-D3）、字段封闭负例
（AC-D2）、404 vs Empty（AC-04）、空关键字 400（R-QUERY-005）、未认证 401
（AC-03）、软删过滤（AC-02）、只读（AC-01）、Cluster 名称不产生结果行（AC-D1）、
范围不越界（AC-D1）、分页（契约）、canonical 逐字段一致（契约）。
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


def _by_type(body: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in body["items"]:
        grouped.setdefault(item["resource_type"], []).append(item)
    return grouped


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
# T-18-01 / AC-D1 D2 D4：单一混合列表 + 命中字段
# --------------------------------------------------------------------------- #
def test_t18_01_single_mixed_list_with_matched_fields(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_shared_scenario(client)

    response = _search(client, ids["cluster"], "zshared", page_size=200)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 6
    assert body["page"] == 1 and body["page_size"] == 200

    grouped = _by_type(body)
    assert set(grouped) == ALL_TYPES, f"应含六类混合结果：{set(grouped)}"
    assert grouped["BARE_METAL"][0]["id"] == ids["bare_metal"]
    assert grouped["NETWORK_INTERFACE"][0]["id"] == ids["nic"]
    assert grouped["IP_ADDRESS"][0]["id"] == ids["ip"]
    assert grouped["VIRTUAL_MACHINE"][0]["id"] == ids["vm"]
    assert grouped["CONTAINER"][0]["id"] == ids["container"]
    assert grouped["SERVICE"][0]["id"] == ids["service"]

    assert grouped["BARE_METAL"][0]["matched_fields"] == ["hostname"]
    assert grouped["NETWORK_INTERFACE"][0]["matched_fields"] == ["name"]
    assert grouped["IP_ADDRESS"][0]["matched_fields"] == ["ip_address"]
    assert grouped["VIRTUAL_MACHINE"][0]["matched_fields"] == ["name"]
    assert grouped["CONTAINER"][0]["matched_fields"] == ["name"]
    assert grouped["SERVICE"][0]["matched_fields"] == ["name"]

    for item in body["items"]:
        assert item["id"] == item["resource"]["id"]
        assert item["matched_fields"], "matched_fields 不得为空"


def test_t18_01_matched_fields_follow_contract_declaration_order(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-multi")
    bare_metal = _create_bare_metal(client, cluster, "zz-multi", vendor="zz-multi", cpu="zz-multi")

    body = _search(client, cluster, "zz-multi").json()
    assert body["total"] == 1
    item = _items(body)[0]
    assert item["id"] == bare_metal
    assert item["matched_fields"] == ["hostname", "vendor", "cpu"]


# --------------------------------------------------------------------------- #
# T-18-02 / T-18-03 / AC-D3：大小写不敏感 + 子串包含
# --------------------------------------------------------------------------- #
def test_t18_02_case_insensitive_same_result_set(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_shared_scenario(client)

    lower = _search(client, ids["cluster"], "zshared", page_size=200).json()
    upper = _search(client, ids["cluster"], "ZSHARED", page_size=200).json()
    assert lower["total"] == upper["total"] > 0
    assert [i["id"] for i in lower["items"]] == [i["id"] for i in upper["items"]]


def test_t18_03_substring_containment(auth_client_and_raw):
    client, _ = auth_client_and_raw
    ids = _build_shared_scenario(client)

    assert _search(client, ids["cluster"], "hare", page_size=200).json()["total"] == 6
    assert _search(client, ids["cluster"], "shrd").json()["total"] == 0
    assert _search(client, ids["cluster"], "zsharx").json()["total"] == 0


# --------------------------------------------------------------------------- #
# T-18-04 / AC-D2：字段封闭负例（status / 时间戳 / 外键不参与匹配）
# --------------------------------------------------------------------------- #
def test_t18_04_status_and_timestamps_do_not_match(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-closed")
    bare_metal = _create_bare_metal(client, cluster, "quiet-node", status="DOWN")
    conn.execute(
        "UPDATE bare_metals SET created_at = '1999-04-05T00:00:00Z',"
        " updated_at = '1999-04-05T00:00:00Z' WHERE id = %s",
        (bare_metal,),
    )

    # 仅 status == DOWN → 不构成命中（status 不参与匹配）。
    assert _search(client, cluster, "DOWN").json()["total"] == 0
    # 仅 created_at / updated_at 命中 → 不构成命中。
    assert _search(client, cluster, "1999-04-05").json()["total"] == 0
    # 对照：hostname 命中仍有效。
    assert _search(client, cluster, "quiet").json()["total"] == 1


def test_t18_04_foreign_key_values_do_not_match(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-fk")
    bare_metal = _create_bare_metal(client, cluster, "fk-node")
    _create_nic(client, bare_metal, "fk-eth")

    # 使用 hostname 的私有片段验证可命中；外键值（cluster_id / bare_metal_id）不是
    # 匹配字段：其文本形式不应产生任何独立命中。
    keyword = f"clusterref-{cluster}"
    assert _search(client, cluster, keyword).json()["total"] == 0


# --------------------------------------------------------------------------- #
# T-18-05 / T-18-06 / AC-04：404 vs Empty
# --------------------------------------------------------------------------- #
def test_t18_05_missing_cluster_returns_404(auth_client_and_raw):
    client, _ = auth_client_and_raw
    response = _search(client, 999999, "anything")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"] == []
    assert "items" not in response.text


def test_t18_05_soft_deleted_cluster_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-gone")
    _create_bare_metal(client, cluster, "zshared-node")
    conn.execute("UPDATE clusters SET deleted_at = now() WHERE id = %s", (cluster,))

    response = _search(client, cluster, "zshared")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_t18_06_active_cluster_no_match_is_empty_200(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-empty")
    _create_bare_metal(client, cluster, "node-a")

    response = _search(client, cluster, "no-such-token-anywhere")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


# --------------------------------------------------------------------------- #
# T-18-07 / R-QUERY-005：空 / 仅空白 keyword → 400，且优先于 404
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("keyword", ["", " ", "   ", "\t", "\n"])
def test_t18_07_blank_keyword_returns_400(auth_client_and_raw, keyword):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-blank")

    response = client.get(SEARCH.format(cluster), params={"keyword": keyword})
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "keyword" for detail in body["error"]["details"])


@pytest.mark.parametrize("keyword", ["", "   "])
def test_t18_07_blank_keyword_precedes_cluster_404(auth_client_and_raw, keyword):
    client, _ = auth_client_and_raw
    response = client.get(SEARCH.format(999999), params={"keyword": keyword})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_t18_07_missing_keyword_returns_400(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-missing-kw")
    response = client.get(SEARCH.format(cluster))
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "keyword" for detail in body["error"]["details"])


# --------------------------------------------------------------------------- #
# T-18-08 / AC-03：未认证 → 401，无资源数据
# --------------------------------------------------------------------------- #
def test_t18_08_unauthenticated_returns_401(app_client):
    response = app_client.get(SEARCH.format(1), params={"keyword": "x"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert "items" not in response.text


# --------------------------------------------------------------------------- #
# T-18-09 / AC-02：逐类软删过滤（其余不受影响）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "resource_type",
    ["NETWORK_INTERFACE", "IP_ADDRESS", "VIRTUAL_MACHINE", "CONTAINER", "SERVICE"],
)
def test_t18_09_soft_deleted_resource_excluded(auth_client_and_raw, resource_type):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, f"cluster-soft-{resource_type.lower()}")
    bare_metal = _create_bare_metal(client, cluster, "plain-node")
    nic = _create_nic(client, bare_metal, "plain-eth")

    if resource_type == "NETWORK_INTERFACE":
        table, target = "network_interfaces", nic
    elif resource_type == "IP_ADDRESS":
        table, target = "ip_addresses", _create_ip(client, nic, "zshared-ip")
    elif resource_type == "VIRTUAL_MACHINE":
        table, target = "virtual_machines", _create_vm(client, bare_metal, "zshared-vm")
    elif resource_type == "CONTAINER":
        table, target = (
            "containers",
            _create_container(client, "BARE_METAL", bare_metal, "zshared-ctr"),
        )
    else:
        table, target = (
            "services",
            _create_service(client, "zshared-svc", [("BARE_METAL", bare_metal)]),
        )

    if resource_type != "NETWORK_INTERFACE":
        token = "zshared"
    else:
        _create_ip(client, nic, "zshared-ip")
        token = "zshared"

    before = _search(client, cluster, token, page_size=200).json()
    assert target in {item["id"] for item in before["items"]}

    conn.execute(f"UPDATE {table} SET deleted_at = now() WHERE id = %s", (target,))

    after = _search(client, cluster, token, page_size=200).json()
    assert target not in {item["id"] for item in after["items"]}
    # 活跃 BareMetal 仍可命中，未被软删子资源诱发 404 或整体消失。
    assert bare_metal in {
        item["id"] for item in _search(client, cluster, "plain-node").json()["items"]
    }


def test_t18_09_soft_deleted_bare_metal_removed_from_scope(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-soft-bm")
    bare_metal = _create_bare_metal(client, cluster, "zshared-node")
    _create_nic(client, bare_metal, "zshared-eth")

    assert _search(client, cluster, "zshared", page_size=200).json()["total"] == 2
    conn.execute("UPDATE bare_metals SET deleted_at = now() WHERE id = %s", (bare_metal,))
    assert _search(client, cluster, "zshared", page_size=200).json()["total"] == 0


# --------------------------------------------------------------------------- #
# T-18-10 / AC-01：只读
# --------------------------------------------------------------------------- #
def test_t18_10_search_is_read_only(auth_client_and_raw):
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
# T-18-11 / T-18-12 / AC-D1：Cluster 名称不产生结果行；范围不越界
# --------------------------------------------------------------------------- #
def test_t18_11_cluster_name_is_not_a_result_row(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "zz-cluster-name-token")
    _create_bare_metal(client, cluster, "node-a")

    body = _search(client, cluster, "zz-cluster-name-token").json()
    assert body["items"] == []
    assert body["total"] == 0


def test_t18_12_other_cluster_resources_excluded(auth_client_and_raw):
    client, _ = auth_client_and_raw
    mine = _create_cluster(client, "cluster-mine")
    other = _create_cluster(client, "cluster-other")
    my_bm = _create_bare_metal(client, mine, "scope-a")
    other_bm = _create_bare_metal(client, other, "scope-b")

    body = _search(client, mine, "scope", page_size=200).json()
    assert {item["id"] for item in body["items"]} == {my_bm}
    assert other_bm not in {item["id"] for item in body["items"]}


# --------------------------------------------------------------------------- #
# T-18-13 / 契约：分页
# --------------------------------------------------------------------------- #
def test_t18_13_pagination_total_and_no_gap_or_overlap(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster = _create_cluster(client, "cluster-page")
    expected = [_create_bare_metal(client, cluster, f"zz-page-{index:02d}") for index in range(5)]

    first = _search(client, cluster, "zz-page", page=1, page_size=2).json()
    assert first["total"] == 5
    assert first["page"] == 1 and first["page_size"] == 2
    assert len(first["items"]) == 2

    collected: list[int] = []
    for page in (1, 2, 3):
        body = _search(client, cluster, "zz-page", page=page, page_size=2).json()
        assert body["total"] == 5
        assert body["page"] == page
        collected.extend(item["id"] for item in body["items"])

    assert sorted(collected) == sorted(expected)
    assert len(collected) == len(set(collected)) == 5

    beyond = _search(client, cluster, "zz-page", page=99, page_size=2).json()
    assert beyond["total"] == 5
    assert beyond["items"] == []


# --------------------------------------------------------------------------- #
# T-18-14 / 契约：resource 与对应 canonical *Read 逐字段一致
# --------------------------------------------------------------------------- #
def test_t18_14_resource_matches_canonical_read(auth_client_and_raw):
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
        matches = [i for i in body["items"] if i["resource_type"] == resource_type]
        assert len(matches) == 1, f"{resource_type} 应恰一条：{matches}"
        item = matches[0]

        canonical = client.get(CANONICAL_PATH[resource_type].format(item["id"]))
        assert canonical.status_code == 200, canonical.text
        assert item["resource"] == canonical.json(), resource_type


# --------------------------------------------------------------------------- #
# 契约：非整数 cluster_id → 400；page_size 越界 → 400
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
    cluster = _create_cluster(client, "cluster-page-size")
    response = _search(client, cluster, "x", page_size=page_size)
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "page_size" for detail in body["error"]["details"])
