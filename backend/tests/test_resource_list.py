"""F003 计算资源统一列表、详情与服务端分页 API 测试（真实 PostgreSQL）。

覆盖：集群作用域/隔离、类型与状态筛选、分页 total/边界/跨页、名称与 IP 搜索
（部分、大小写、``%``/``_`` 字面量、仅本集群、q 命中 id、权重排序）、列表列
（管理 IP、标签、updated_at）、详情回归、权限与参数错误。
"""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app

PASSWORD = "Passw0rd1"
BASE = "/api/v1/resources"
SEGMENTS = "/api/v1/network-segments"


def _auth(client, add_user, login_as, username: str, role: str) -> int:
    user_id = add_user(username, PASSWORD, role)
    assert login_as(client, username, PASSWORD).status_code == 200
    return user_id


def _make_cluster(client, code: str, name: str | None = None) -> int:
    resp = client.post(
        "/api/v1/clusters",
        json={"code": code, "name": name or f"Cluster{code}", "purpose": "测试"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _make_segment(client, cluster_id: int, name: str, cidr: str):
    resp = client.post(
        SEGMENTS,
        json={
            "cluster_id": cluster_id,
            "name": name,
            "cidr": cidr,
            "purpose": "管理",
            "technology": "Ethernet",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_resource(client, cluster_id: int, name: str, **kw):
    body = {"cluster_id": cluster_id, "name": name, "resource_type": "bare_metal"}
    body.update(kw)
    return client.post(BASE, json=body)


def _make_resource_with_ip(
    client, cluster_id, name, segment_id, address, *, management: bool = False, **kw
):
    body = {
        "cluster_id": cluster_id,
        "name": name,
        "resource_type": kw.pop("resource_type", "bare_metal"),
        "interfaces": [
            {
                "name": "eth0",
                "segment_id": segment_id,
                "ips": [{"mode": "manual", "address": address}],
            }
        ],
    }
    if management:
        body["management_ip"] = {"interface_index": 0, "address": address}
    body.update(kw)
    return client.post(BASE, json=body)


def _names(resp) -> list[str]:
    return [item["name"] for item in resp.json()["items"]]


def _list(client, cluster_id, **params):
    params["cluster_id"] = cluster_id
    return client.get(BASE, params=params)


# --- 作用域 -----------------------------------------------------------------


def test_cluster_scope_required_and_invalid(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    _make_cluster(client, "C1")

    missing = client.get(BASE)
    assert missing.status_code == 400
    assert missing.json()["code"] == "INVALID_REQUEST"
    assert missing.json()["errors"][0]["code"] == "CLUSTER_ID_REQUIRED"
    assert missing.json()["errors"][0]["field"] == "cluster_id"

    non_int = client.get(BASE, params={"cluster_id": "abc"})
    assert non_int.status_code == 400
    assert non_int.json()["errors"][0]["code"] == "CLUSTER_ID_INVALID"

    zero = client.get(BASE, params={"cluster_id": 0})
    assert zero.status_code == 400
    assert zero.json()["errors"][0]["code"] == "CLUSTER_ID_INVALID"

    negative = client.get(BASE, params={"cluster_id": -3})
    assert negative.status_code == 400
    assert negative.json()["errors"][0]["code"] == "CLUSTER_ID_INVALID"


def test_scope_isolation_empty_and_nonexistent(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1", "Alpha")
    c2 = _make_cluster(client, "C2", "Beta")
    r1 = _make_resource(client, c1, "shared").json()
    _make_resource(client, c2, "shared")
    empty = _make_cluster(client, "C3", "Gamma")

    resp = _list(client, c1)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [i["id"] for i in body["items"]] == [r1["id"]]
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["scope"] == {
        "cluster_id": c1,
        "cluster_code": "C1",
        "cluster_name": "Alpha",
    }

    empty_resp = _list(client, empty)
    assert empty_resp.status_code == 200
    assert empty_resp.json()["items"] == []
    assert empty_resp.json()["total"] == 0

    missing = _list(client, 999999)
    assert missing.status_code == 200
    assert missing.json()["items"] == []
    assert missing.json()["total"] == 0
    assert missing.json()["scope"]["cluster_id"] == 999999


# --- 类型 / 状态筛选 --------------------------------------------------------


def test_type_and_status_filters(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")
    _make_resource(client, c1, "bm-idle", resource_type="bare_metal", status="IDLE")
    _make_resource(client, c1, "bm-alloc", resource_type="bare_metal", status="ALLOC")
    _make_resource(
        client, c1, "vm-down", resource_type="virtual_machine", status="DOWN"
    )
    _make_resource(
        client, c1, "vm-unknown", resource_type="virtual_machine", status="UNKNOWN"
    )

    assert _names(_list(client, c1)) == [
        "bm-alloc",
        "bm-idle",
        "vm-down",
        "vm-unknown",
    ]
    assert _names(_list(client, c1, resource_type="bare_metal")) == [
        "bm-alloc",
        "bm-idle",
    ]
    assert _names(_list(client, c1, resource_type="virtual_machine")) == [
        "vm-down",
        "vm-unknown",
    ]
    assert _names(_list(client, c1, status="IDLE")) == ["bm-idle"]
    assert _names(_list(client, c1, resource_type="bare_metal", status="ALLOC")) == [
        "bm-alloc"
    ]
    assert _list(client, c1, status="IDLE").json()["total"] == 1


def test_invalid_filter_and_sort_and_paging(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")

    bad_type = _list(client, c1, resource_type="container")
    assert bad_type.status_code == 400
    assert bad_type.json()["errors"][0]["code"] == "RESOURCE_TYPE_INVALID"

    bad_status = _list(client, c1, status="BUSY")
    assert bad_status.status_code == 400
    assert bad_status.json()["errors"][0]["code"] == "STATUS_INVALID"

    bad_sort = _list(client, c1, sort="name2")
    assert bad_sort.status_code == 400
    assert bad_sort.json()["errors"][0]["code"] == "INVALID_SORT"

    bad_page = _list(client, c1, page=0)
    assert bad_page.status_code == 400
    assert bad_page.json()["errors"][0]["code"] == "INVALID_PAGE"

    non_int_page = _list(client, c1, page="abc")
    assert non_int_page.status_code == 400
    assert non_int_page.json()["errors"][0]["code"] == "INVALID_PAGE"

    bad_size = _list(client, c1, page_size=0)
    assert bad_size.status_code == 400
    assert bad_size.json()["errors"][0]["code"] == "INVALID_PAGE_SIZE"

    too_big = _list(client, c1, page_size=101)
    assert too_big.status_code == 400
    assert too_big.json()["errors"][0]["code"] == "INVALID_PAGE_SIZE"

    non_int_size = _list(client, c1, page_size="xyz")
    assert non_int_size.status_code == 400
    assert non_int_size.json()["errors"][0]["code"] == "INVALID_PAGE_SIZE"


# --- 排序 / 分页 ------------------------------------------------------------


def test_sort_whitelist_and_stability(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")
    _make_resource(client, c1, "b", status="DOWN")
    _make_resource(client, c1, "a", status="IDLE")
    _make_resource(client, c1, "c", status="IDLE")

    assert _names(_list(client, c1)) == ["a", "b", "c"]
    assert _names(_list(client, c1, sort="name")) == ["a", "b", "c"]
    assert _names(_list(client, c1, sort="-name")) == ["c", "b", "a"]
    # status 升序：DOWN < IDLE，同状态再按 id 稳定升序。
    assert _names(_list(client, c1, sort="status")) == ["b", "a", "c"]
    assert _names(_list(client, c1, sort="-status")) == ["a", "c", "b"]


def test_pagination_total_and_no_duplicates(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")
    for i in range(5):
        _make_resource(client, c1, f"r{i}")

    first = _list(client, c1, page=1, page_size=2)
    assert first.json()["total"] == 5
    assert _names(first) == ["r0", "r1"]
    second = _list(client, c1, page=2, page_size=2)
    assert second.json()["total"] == 5
    assert _names(second) == ["r2", "r3"]
    third = _list(client, c1, page=3, page_size=2)
    assert third.json()["total"] == 5
    assert _names(third) == ["r4"]

    combined = _names(first) + _names(second) + _names(third)
    assert combined == ["r0", "r1", "r2", "r3", "r4"]
    assert len(set(combined)) == 5

    beyond = _list(client, c1, page=4, page_size=2)
    assert beyond.status_code == 200
    assert beyond.json()["items"] == []
    assert beyond.json()["total"] == 5

    huge = _list(client, c1, page=9999, page_size=100)
    assert huge.status_code == 200
    assert huge.json()["items"] == []
    assert huge.json()["total"] == 5


# --- 搜索：名称 -------------------------------------------------------------


def test_search_by_name_weights_case_and_literals(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")
    _make_resource(client, c1, "myweb01")
    _make_resource(client, c1, "web")
    _make_resource(client, c1, "web-server")
    _make_resource(client, c1, "foo_bar")
    _make_resource(client, c1, "abc")
    _make_resource(client, c1, "100%util")

    # 权重：完全 > 前缀 > 包含。
    assert _names(_list(client, c1, q="web")) == ["web", "web-server", "myweb01"]
    # 大小写不敏感。
    assert _names(_list(client, c1, q="WEB")) == ["web", "web-server", "myweb01"]
    # 去首尾空格。
    assert _names(_list(client, c1, q="  web  ")) == [
        "web",
        "web-server",
        "myweb01",
    ]
    # ``_`` 字面量：a_c 不匹配 abc。
    assert _names(_list(client, c1, q="a_c")) == []
    # ``%`` 字面量：a%c 不匹配 abc。
    assert _names(_list(client, c1, q="a%c")) == []
    # 字面量匹配。
    assert _names(_list(client, c1, q="foo_bar")) == ["foo_bar"]
    assert _names(_list(client, c1, q="foo_")) == ["foo_bar"]
    assert _names(_list(client, c1, q="100%util")) == ["100%util"]
    # 空串 = 不搜索。
    assert _list(client, c1, q="").json()["total"] == 6
    assert _list(client, c1, q="   ").json()["total"] == 6


def test_search_by_resource_id(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")
    target = _make_resource(client, c1, "res-a").json()
    _make_resource(client, c1, "res-b")

    resp = _list(client, c1, q=str(target["id"]))
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert _names(resp) == ["res-a"]

    no_match = _list(client, c1, q="987654321")
    assert no_match.json()["items"] == []
    assert no_match.json()["total"] == 0


# --- 搜索：IP ---------------------------------------------------------------


def test_search_by_ip_within_cluster_only(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1", "Alpha")
    c2 = _make_cluster(client, "C2", "Beta")
    c3 = _make_cluster(client, "C3", "Gamma")
    seg1 = _make_segment(client, c1, "seg1", "10.0.0.0/24")
    seg2 = _make_segment(client, c2, "seg2", "10.0.0.0/24")
    a1 = _make_resource_with_ip(client, c1, "a1", seg1["id"], "10.0.0.10").json()
    _make_resource_with_ip(client, c2, "b1", seg2["id"], "10.0.0.10")

    # 完全匹配：仅本集群。
    exact = _list(client, c1, q="10.0.0.10")
    assert exact.json()["total"] == 1
    assert [i["id"] for i in exact.json()["items"]] == [a1["id"]]
    # 前缀部分匹配。
    assert _names(_list(client, c1, q="10.0.0")) == ["a1"]
    # 包含部分匹配。
    assert _names(_list(client, c1, q="0.0.1")) == ["a1"]
    # 其它集群无该 IP（c3 无资源）→ 不串数据。
    assert _list(client, c3, q="10.0.0.10").json()["items"] == []


def test_search_weight_ordering_with_ips(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")
    seg1 = _make_segment(client, c1, "seg1", "10.0.0.0/24")
    seg2 = _make_segment(client, c1, "seg2", "110.0.0.0/24")
    _make_resource_with_ip(client, c1, "contains", seg2["id"], "110.0.0.1")
    _make_resource_with_ip(client, c1, "exact", seg1["id"], "10.0.0.1")
    _make_resource_with_ip(client, c1, "prefix", seg1["id"], "10.0.0.10")

    # 完全(1) > 前缀(2) > 包含(4)。
    assert _names(_list(client, c1, q="10.0.0.1")) == [
        "exact",
        "prefix",
        "contains",
    ]


def test_search_same_weight_then_sort_then_id(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")
    seg = _make_segment(client, c1, "seg1", "10.0.0.0/24")
    _make_resource_with_ip(client, c1, "beta", seg["id"], "10.0.0.2")
    _make_resource_with_ip(client, c1, "alpha", seg["id"], "10.0.0.3")

    # 同权重（IP 前缀）再按 sort（默认 name）+ id。
    assert _names(_list(client, c1, q="10.0.0")) == ["alpha", "beta"]
    assert _names(_list(client, c1, q="10.0.0", sort="-name")) == ["beta", "alpha"]


# --- 列表列 -----------------------------------------------------------------


def test_list_columns_labels_management_ip_updated_at(
    client, add_user, login_as
) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1", "Alpha")
    seg = _make_segment(client, c1, "seg1", "192.168.1.0/24")
    with_mgmt = _make_resource_with_ip(
        client,
        c1,
        "vm1",
        seg["id"],
        "192.168.1.10",
        management=True,
        resource_type="virtual_machine",
        status="IDLE",
    ).json()
    _make_resource(client, c1, "bm1", status="DOWN")

    body = _list(client, c1, sort="name").json()
    assert body["scope"]["cluster_name"] == "Alpha"
    items = {item["name"]: item for item in body["items"]}
    vm = items["vm1"]
    assert vm["cluster_id"] == c1
    assert vm["cluster_code"] == "C1"
    assert vm["cluster_name"] == "Alpha"
    assert vm["resource_type"] == "virtual_machine"
    assert vm["resource_type_label"] == "虚拟机"
    assert vm["status"] == "IDLE"
    assert vm["status_label"] == "空闲"
    assert vm["management_ip"] == {
        "ip_id": with_mgmt["management_ip"]["ip_id"],
        "address": "192.168.1.10",
        "interface_id": with_mgmt["interfaces"][0]["id"],
        "interface_name": "eth0",
    }
    assert datetime.fromisoformat(vm["updated_at"].replace("Z", "+00:00")) is not None

    bm = items["bm1"]
    assert bm["resource_type_label"] == "裸金属"
    assert bm["status_label"] == "宕机"
    assert bm["management_ip"] is None


# --- 详情回归 ---------------------------------------------------------------


def test_detail_regression_no_ip_interface_and_management(
    client, add_user, login_as
) -> None:
    user_id = _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")
    seg = _make_segment(client, c1, "seg1", "192.168.1.0/24")

    # 无 IP 网卡 + 无管理 IP。
    plain = _make_resource(
        client,
        c1,
        "plain",
        interfaces=[{"name": "eth0", "segment_id": seg["id"], "ips": []}],
    ).json()
    detail = client.get(f"{BASE}/{plain['id']}").json()
    assert detail["interfaces"][0]["ips"] == []
    assert detail["management_ip"] is None
    assert detail["status_updated_by"] == user_id
    assert detail["status_updated_by_username"] == "root"

    # 有管理 IP。
    with_mgmt = _make_resource_with_ip(
        client, c1, "withip", seg["id"], "192.168.1.20", management=True
    ).json()
    detail2 = client.get(f"{BASE}/{with_mgmt['id']}").json()
    assert detail2["management_ip"]["address"] == "192.168.1.20"
    assert detail2["interfaces"][0]["ips"][0]["is_management"] is True


# --- 权限 -------------------------------------------------------------------


def test_permissions(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")
    _make_resource(client, c1, "r1")

    anon = TestClient(app)
    assert anon.get(BASE, params={"cluster_id": c1}).status_code == 401

    viewer = TestClient(app)
    _auth(viewer, add_user, login_as, "v1", "viewer")
    assert viewer.get(BASE, params={"cluster_id": c1}).status_code == 200

    maint = TestClient(app)
    _auth(maint, add_user, login_as, "m1", "maintainer")
    assert maint.get(BASE, params={"cluster_id": c1}).status_code == 200

    # F003 不新增写端点：GET 之外仍需 F002 权限。
    assert viewer.post(BASE, json={}).status_code in (401, 403)