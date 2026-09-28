"""F008 统一模糊搜索与排序集成测试（真实 PostgreSQL）。

覆盖集群、网段、资源、已分配 IP 的 ``q`` rank 排序、特殊字符字面量、
空/空白 ``q`` 回初始候选、分页 total 与跨页无重复，以及资源既有语义回归。
"""

from __future__ import annotations

PASSWORD = "Passw0rd1"
CLUSTERS = "/api/v1/clusters"
SEGMENTS = "/api/v1/network-segments"
RESOURCES = "/api/v1/resources"


def _auth(client, add_user, login_as, username: str, role: str = "admin") -> int:
    user_id = add_user(username, PASSWORD, role)
    assert login_as(client, username, PASSWORD).status_code == 200
    return user_id


def _make_cluster(client, code: str, name: str) -> dict:
    resp = client.post(
        CLUSTERS, json={"code": code, "name": name, "purpose": "测试"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_segment(
    client,
    cluster_id: int,
    name: str,
    cidr: str,
    *,
    purpose: str = "用途",
    technology: str = "Ethernet",
) -> dict:
    resp = client.post(
        SEGMENTS,
        json={
            "cluster_id": cluster_id,
            "name": name,
            "cidr": cidr,
            "purpose": purpose,
            "technology": technology,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_resource(client, cluster_id: int, name: str) -> dict:
    resp = client.post(
        RESOURCES,
        json={"cluster_id": cluster_id, "name": name, "resource_type": "bare_metal"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_resource_with_ip(
    client, cluster_id: int, name: str, segment_id: int, address: str
) -> dict:
    resp = client.post(
        RESOURCES,
        json={
            "cluster_id": cluster_id,
            "name": name,
            "resource_type": "bare_metal",
            "interfaces": [
                {
                    "name": "eth0",
                    "segment_id": segment_id,
                    "ips": [{"mode": "manual", "address": address}],
                }
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _cluster_names(client, **params) -> list[str]:
    resp = client.get(CLUSTERS, params=params)
    assert resp.status_code == 200, resp.text
    return [item["name"] for item in resp.json()["items"]]


def _segment_names(client, cluster_id: int, **params) -> list[str]:
    params["cluster_id"] = cluster_id
    resp = client.get(SEGMENTS, params=params)
    assert resp.status_code == 200, resp.text
    return [item["name"] for item in resp.json()["items"]]


# --- 集群：rank + 同级按 sort=name ------------------------------------------


def test_cluster_q_rank_exact_prefix_contains(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root")

    _make_cluster(client, "WEB", "Aaa")  # code 完全
    _make_cluster(client, "EX1", "web")  # name 完全
    _make_cluster(client, "WEBX", "Bbb")  # code 前缀
    _make_cluster(client, "EX2", "website")  # name 前缀
    _make_cluster(client, "CX1", "aweb")  # name 包含
    _make_cluster(client, "CX2", "myweb")  # name 包含

    # 完全(1) > 前缀(2) > 包含(4)；同级按 sort=name + id。
    assert _cluster_names(client, q="web", sort="name") == [
        "Aaa",
        "web",
        "Bbb",
        "website",
        "aweb",
        "myweb",
    ]
    # sort 在 rank 内生效（降序）。
    assert _cluster_names(client, q="web", sort="-name") == [
        "web",
        "Aaa",
        "website",
        "Bbb",
        "myweb",
        "aweb",
    ]
    # 大小写不敏感 + 去首尾空格。
    assert _cluster_names(client, q="  WEB  ", sort="name") == [
        "Aaa",
        "web",
        "Bbb",
        "website",
        "aweb",
        "myweb",
    ]


def test_cluster_q_pagination_total_and_no_duplicates(
    client, add_user, login_as
) -> None:
    _auth(client, add_user, login_as, "root")
    for index, name in enumerate(["web0", "web1", "web2", "web3", "web4"]):
        _make_cluster(client, f"CW{index}", name)

    names: list[str] = []
    for page in (1, 2, 3):
        resp = client.get(
            CLUSTERS, params={"q": "web", "sort": "name", "page": page, "page_size": 2}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        names += [item["name"] for item in body["items"]]

    assert names == ["web0", "web1", "web2", "web3", "web4"]
    assert len(set(names)) == 5

    beyond = client.get(
        CLUSTERS, params={"q": "web", "page": 4, "page_size": 2}
    )
    assert beyond.status_code == 200
    assert beyond.json()["items"] == []
    assert beyond.json()["total"] == 5


# --- 网段：rank 覆盖名称/CIDR/用途/技术类型 ---------------------------------


def test_network_segment_q_rank_all_columns(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root")
    cluster = _make_cluster(client, "C1", "RankCluster")
    cid = cluster["id"]

    _make_segment(client, cid, "alpha", "192.168.1.0/24")  # cidr 前缀
    _make_segment(client, cid, "192.168", "10.0.0.0/24")  # name 完全
    _make_segment(client, cid, "c", "10.1.0.0/24", purpose="192.168")  # purpose 完全
    _make_segment(
        client, cid, "d", "10.2.0.0/24", technology="192.168"
    )  # technology 完全
    _make_segment(client, cid, "192.168.9", "10.3.0.0/24")  # name 前缀
    _make_segment(
        client, cid, "f", "10.4.0.0/24", purpose="xx192.168yy"
    )  # purpose 包含

    assert _segment_names(client, cid, q="192.168", sort="name") == [
        "192.168",
        "c",
        "d",
        "192.168.9",
        "alpha",
        "f",
    ]


def test_network_segment_q_rank_purpose_and_technology(
    client, add_user, login_as
) -> None:
    _auth(client, add_user, login_as, "root")
    cluster = _make_cluster(client, "C2", "PurposeCluster")
    cid = cluster["id"]

    _make_segment(client, cid, "management", "10.0.0.0/24", purpose="管理")
    _make_segment(client, cid, "m2", "10.1.0.0/24", purpose="管理网")
    _make_segment(client, cid, "m3", "10.2.0.0/24", purpose="带内管理")
    _make_segment(client, cid, "ib", "10.3.0.0/24", technology="InfiniBand")
    _make_segment(client, cid, "eth", "10.4.0.0/24", technology="Ethernet")

    assert _segment_names(client, cid, q="管理", sort="name") == [
        "management",
        "m2",
        "m3",
    ]
    assert _segment_names(client, cid, q="infini", sort="name") == ["ib"]


# --- 网段：% / _ / \ 字面量 -------------------------------------------------


def test_network_segment_q_metacharacters_literal(
    client, add_user, login_as
) -> None:
    _auth(client, add_user, login_as, "root")
    cluster = _make_cluster(client, "C3", "LiteralCluster")
    cid = cluster["id"]

    _make_segment(client, cid, "ab", "10.0.0.0/24")
    _make_segment(client, cid, "axb", "10.0.1.0/24")
    _make_segment(client, cid, "a_b", "10.0.2.0/24")
    _make_segment(client, cid, "a%b", "10.0.3.0/24")
    _make_segment(client, cid, "a\\b", "10.0.4.0/24")

    # ``_`` 为字面量，不匹配 ab/axb/a%b/a\b。
    assert _segment_names(client, cid, q="_") == ["a_b"]
    # ``%`` 为字面量，不匹配 ab/a_b。
    assert _segment_names(client, cid, q="%") == ["a%b"]
    # ``\`` 为字面量。
    assert _segment_names(client, cid, q="\\") == ["a\\b"]
    # 完整字面量。
    assert _segment_names(client, cid, q="a_b") == ["a_b"]
    assert _segment_names(client, cid, q="a%b") == ["a%b"]
    assert _segment_names(client, cid, q="a\\b") == ["a\\b"]


# --- 空 / 空白 q 回初始候选 --------------------------------------------------


def test_empty_q_returns_initial_candidates(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root")
    cluster = _make_cluster(client, "C4", "EmptyCluster")
    cid = cluster["id"]
    _make_segment(client, cid, "beta", "10.0.0.0/24")
    _make_segment(client, cid, "alpha", "10.1.0.0/24")

    initial = _segment_names(client, cid)
    assert initial == ["alpha", "beta"]
    assert _segment_names(client, cid, q="") == initial
    assert _segment_names(client, cid, q="   ") == initial

    # 集群同样：无 q / 空 q / 空白 q 一致。
    _make_cluster(client, "Z01", "Zeta")
    _make_cluster(client, "A01", "Alpha")
    base = _cluster_names(client, sort="name")
    assert _cluster_names(client, q="", sort="name") == base
    assert _cluster_names(client, q="   ", sort="name") == base
    assert base[0] == "Alpha"


# --- 资源：既有语义回归 + 跨集群隔离 ----------------------------------------


def test_resource_q_regression_and_scope(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root")
    c1 = _make_cluster(client, "R1", "ResCluster1")["id"]
    c2 = _make_cluster(client, "R2", "ResCluster2")["id"]
    seg1 = _make_segment(client, c1, "seg1", "10.0.0.0/24")["id"]
    seg2 = _make_segment(client, c2, "seg2", "10.0.0.0/24")["id"]

    exact = _make_resource(client, c1, "web")
    _make_resource(client, c1, "website")
    _make_resource(client, c1, "myweb")
    ip_res = _make_resource_with_ip(client, c1, "host-ip", seg1, "10.0.0.10")
    # 跨集群同名/同 IP：不得串数据。
    _make_resource(client, c2, "web")
    _make_resource_with_ip(client, c2, "other", seg2, "10.0.0.10")

    # 名称权重：完全 > 前缀 > 包含。
    resp = client.get(RESOURCES, params={"cluster_id": c1, "q": "web"})
    assert [i["name"] for i in resp.json()["items"]] == ["web", "website", "myweb"]
    # 本集群 IP 部分匹配。
    resp = client.get(RESOURCES, params={"cluster_id": c1, "q": "10.0.0"})
    assert [i["id"] for i in resp.json()["items"]] == [ip_res["id"]]
    # 跨集群隔离：c2 的同 IP 资源不出现。
    resp = client.get(RESOURCES, params={"cluster_id": c2, "q": "10.0.0"})
    assert [i["name"] for i in resp.json()["items"]] == ["other"]
    assert exact["id"] not in [i["id"] for i in resp.json()["items"]]


def test_resource_q_by_id_exact(client, add_user, login_as) -> None:
    """纯数字 q 精确等于资源 ID（rank 3）。"""
    _auth(client, add_user, login_as, "root")
    c1 = _make_cluster(client, "R3", "IdCluster")["id"]
    target = _make_resource(client, c1, "res-a")
    _make_resource(client, c1, "res-b")

    resp = client.get(RESOURCES, params={"cluster_id": c1, "q": str(target["id"])})
    assert [i["id"] for i in resp.json()["items"]] == [target["id"]]
    assert resp.json()["total"] == 1


# --- 已分配 IP：可选 rank 接入 ----------------------------------------------


def test_allocated_ips_q_rank(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root")
    cid = _make_cluster(client, "IP1", "IpCluster")["id"]
    sid = _make_segment(client, cid, "seg", "10.0.0.0/24")["id"]

    _make_resource_with_ip(client, cid, "aweb", sid, "10.0.0.10")  # 包含(4)
    _make_resource_with_ip(client, cid, "web", sid, "10.0.0.11")  # 完全(1)
    _make_resource_with_ip(client, cid, "website", sid, "10.0.0.12")  # 前缀(2)

    resp = client.get(f"{SEGMENTS}/{sid}/allocated-ips", params={"q": "web"})
    assert resp.status_code == 200, resp.text
    assert [i["resource_name"] for i in resp.json()["items"]] == [
        "web",
        "website",
        "aweb",
    ]

    # 无 q：保持地址数值升序。
    all_resp = client.get(f"{SEGMENTS}/{sid}/allocated-ips")
    assert [i["address"] for i in all_resp.json()["items"]] == [
        "10.0.0.10",
        "10.0.0.11",
        "10.0.0.12",
    ]