"""F006 IPv4 分配与资源表单 IP 集成 API 测试（架构 §12，真实 PostgreSQL）。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AuditLog, IpAddress, Resource, ResourceHistory

PASSWORD = "Passw0rd1"
BASE = "/api/v1/resources"
SEGMENTS = "/api/v1/network-segments"


def _auth(client, add_user, login_as, username: str, role: str) -> int:
    user_id = add_user(username, PASSWORD, role)
    assert login_as(client, username, PASSWORD).status_code == 200
    return user_id


def _make_cluster(client, code: str, name: str = "Alpha") -> int:
    resp = client.post(
        "/api/v1/clusters",
        json={"code": code, "name": name, "purpose": "测试"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _make_segment(client, cluster_id: int, name="seg", cidr="192.168.1.0/24", **kw):
    body = {
        "cluster_id": cluster_id,
        "name": name,
        "cidr": cidr,
        "purpose": "管理",
        "technology": "Ethernet",
    }
    body.update(kw)
    return client.post(SEGMENTS, json=body)


def _make_resource(client, cluster_id: int, name="cn001", **kw):
    body = {"cluster_id": cluster_id, "name": name, "resource_type": "bare_metal"}
    body.update(kw)
    return client.post(BASE, json=body)


def _ips_of(body, index=0):
    return [ip["address"] for ip in body["interfaces"][index]["ips"]]


# --- 创建 / 手动 / 自动 / 管理 IP ------------------------------------------


def test_create_with_manual_auto_and_management_ip(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C1")
    seg = _make_segment(
        client,
        cid,
        cidr="192.168.1.0/24",
        gateway="192.168.1.1",
        auto_alloc_start="192.168.1.20",
        auto_alloc_end="192.168.1.30",
    ).json()

    resp = _make_resource(
        client,
        cid,
        name="cn001",
        interfaces=[
            {
                "name": "eth0",
                "segment_id": seg["id"],
                "ips": [
                    {"mode": "manual", "address": "192.168.1.10"},
                    {"mode": "auto"},
                ],
            },
            {"name": "ib0", "segment_id": None, "ips": []},
        ],
        management_ip={"interface_index": 0, "address": "192.168.1.10"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert _ips_of(body) == ["192.168.1.10", "192.168.1.20"]
    assert body["interfaces"][0]["ips"][0]["is_management"] is True
    assert body["interfaces"][1]["ips"] == []
    assert body["management_ip"] == {
        "ip_id": body["interfaces"][0]["ips"][0]["id"],
        "address": "192.168.1.10",
        "interface_id": body["interfaces"][0]["id"],
        "interface_name": "eth0",
    }
    # GET 同样带出。
    detail = client.get(f"{BASE}/{body['id']}").json()
    assert detail["management_ip"]["address"] == "192.168.1.10"
    assert len(detail["interfaces"][0]["ips"]) == 2


def test_auto_skips_allocated_and_reserved(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C2")
    seg = _make_segment(
        client,
        cid,
        cidr="192.168.1.0/24",
        auto_alloc_start="192.168.1.20",
        auto_alloc_end="192.168.1.30",
    ).json()
    sid = seg["id"]
    first = _make_resource(
        client,
        cid,
        name="cn001",
        interfaces=[
            {
                "name": "eth0",
                "segment_id": sid,
                "ips": [{"mode": "manual", "address": "192.168.1.20"}],
            }
        ],
    )
    assert first.status_code == 201, first.text
    reserved = client.post(
        f"{SEGMENTS}/{sid}/reserved-addresses", json={"start_ip": "192.168.1.21"}
    )
    assert reserved.status_code == 201, reserved.text

    second = _make_resource(
        client,
        cid,
        name="cn002",
        interfaces=[
            {"name": "eth0", "segment_id": sid, "ips": [{"mode": "auto"}]}
        ],
    )
    assert second.status_code == 201, second.text
    assert _ips_of(second.json()) == ["192.168.1.22"]


def test_manual_validation_codes(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C3")
    seg = _make_segment(
        client, cid, cidr="192.168.1.0/24", gateway="192.168.1.1"
    ).json()
    sid = seg["id"]
    client.post(f"{SEGMENTS}/{sid}/reserved-addresses", json={"start_ip": "192.168.1.50"})

    cases = [
        ("192.168.1.1", "IP_GATEWAY"),
        ("192.168.1.0", "IP_NETWORK_ADDRESS"),
        ("192.168.1.255", "IP_BROADCAST_ADDRESS"),
        ("192.168.1.50", "IP_RESERVED"),
        ("10.0.0.5", "IP_OUT_OF_SEGMENT"),
        ("not-an-ip", "IP_INVALID"),
    ]
    for address, code in cases:
        resp = _make_resource(
            client,
            cid,
            name=f"cn-{code}-{address}".replace(".", "-"),
            interfaces=[
                {
                    "name": "eth0",
                    "segment_id": sid,
                    "ips": [{"mode": "manual", "address": address}],
                }
            ],
        )
        assert resp.status_code == 422, (address, resp.text)
        codes = [e["code"] for e in resp.json()["errors"]]
        assert code in codes, (address, codes)
        with SessionLocal() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Resource)
                    .where(Resource.cluster_id == cid)
                )
                == 0
            )


def test_auto_range_not_enabled_and_exhausted(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C4")
    disabled = _make_segment(client, cid, name="nodis", cidr="10.4.0.0/24").json()
    resp = _make_resource(
        client,
        cid,
        name="auto-disabled",
        interfaces=[
            {
                "name": "eth0",
                "segment_id": disabled["id"],
                "ips": [{"mode": "auto"}],
            }
        ],
    )
    assert resp.status_code == 422
    assert "AUTO_RANGE_NOT_ENABLED" in [e["code"] for e in resp.json()["errors"]]

    tiny = _make_segment(
        client,
        cid,
        name="tiny",
        cidr="10.5.0.0/30",
        auto_alloc_start="10.5.0.1",
        auto_alloc_end="10.5.0.2",
    ).json()
    ok = _make_resource(
        client,
        cid,
        name="fill",
        interfaces=[
            {
                "name": "eth0",
                "segment_id": tiny["id"],
                "ips": [
                    {"mode": "manual", "address": "10.5.0.1"},
                    {"mode": "manual", "address": "10.5.0.2"},
                ],
            }
        ],
    )
    assert ok.status_code == 201, ok.text
    exhausted = _make_resource(
        client,
        cid,
        name="nope",
        interfaces=[
            {"name": "eth0", "segment_id": tiny["id"], "ips": [{"mode": "auto"}]}
        ],
    )
    assert exhausted.status_code == 409, exhausted.text
    assert exhausted.json()["code"] == "NO_AVAILABLE_ADDRESS"


def test_segment_not_selected(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C5")
    resp = _make_resource(
        client,
        cid,
        name="noseg",
        interfaces=[
            {
                "name": "eth0",
                "segment_id": None,
                "ips": [{"mode": "manual", "address": "10.0.0.1"}],
            }
        ],
    )
    assert resp.status_code == 422
    assert "SEGMENT_NOT_SELECTED" in [e["code"] for e in resp.json()["errors"]]


# --- 唯一 / 冲突 / 释放复用 / 原子 ------------------------------------------


def test_cluster_ip_unique_and_conflicts(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C6")
    cid2 = _make_cluster(client, "C7", name="Beta")
    seg = _make_segment(client, cid, cidr="10.6.0.0/24").json()
    seg2 = _make_segment(client, cid2, cidr="10.6.0.0/24").json()
    first = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "ib0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.6.0.10"}]}],
    )
    assert first.status_code == 201, first.text

    dup = _make_resource(
        client, cid, name="cn002",
        interfaces=[{"name": "eth0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.6.0.10"}]}],
    )
    assert dup.status_code == 409, dup.text
    body = dup.json()
    assert body["code"] == "IP_ALREADY_IN_USE"
    assert body["conflicts"][0]["resource_name"] == "cn001"
    assert body["conflicts"][0]["interface_name"] == "ib0"
    assert body["errors"][0]["field"] == "interfaces[0].ips[0].address"

    # 跨集群允许。
    other = _make_resource(
        client, cid2, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": seg2["id"], "ips": [{"mode": "manual", "address": "10.6.0.10"}]}],
    )
    assert other.status_code == 201, other.text


def test_second_ip_conflict_is_atomic(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C8")
    seg = _make_segment(client, cid, cidr="10.8.0.0/24").json()
    _make_resource(
        client, cid, name="existing",
        interfaces=[{"name": "eth0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.8.0.5"}]}],
    )
    resp = _make_resource(
        client, cid, name="cn-new",
        interfaces=[
            {"name": "eth0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.8.0.9"}]},
            {"name": "ib0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.8.0.5"}]},
        ],
    )
    assert resp.status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Resource).where(Resource.name == "cn-new")) == 0


def test_release_and_reallocate(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C9")
    seg = _make_segment(client, cid, cidr="10.9.0.0/24").json()
    sid = seg["id"]
    created = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": sid, "ips": [{"mode": "manual", "address": "10.9.0.10"}]}],
    ).json()
    ip_id = created["interfaces"][0]["ips"][0]["id"]
    deleted = client.patch(
        f"{BASE}/{created['id']}",
        json={"interfaces": [{"op": "update", "id": created["interfaces"][0]["id"], "ips": [{"op": "delete", "id": ip_id}]}], "version": 1},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["interfaces"][0]["ips"] == []

    reused = _make_resource(
        client, cid, name="cn002",
        interfaces=[{"name": "eth0", "segment_id": sid, "ips": [{"mode": "manual", "address": "10.9.0.10"}]}],
    )
    assert reused.status_code == 201, reused.text


def test_existing_unchanged_ip_not_conflict(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C10")
    seg = _make_segment(
        client, cid, cidr="10.10.0.0/24", auto_alloc_start="10.10.0.20", auto_alloc_end="10.10.0.30"
    ).json()
    sid = seg["id"]
    created = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": sid, "ips": [{"mode": "manual", "address": "10.10.0.10"}]}],
    ).json()
    iface_id = created["interfaces"][0]["id"]
    edited = client.patch(
        f"{BASE}/{created['id']}",
        json={
            "name": "cn001-renamed",
            "interfaces": [{"op": "update", "id": iface_id, "ips": [{"op": "create", "mode": "auto"}]}],
            "version": 1,
        },
    )
    assert edited.status_code == 200, edited.text
    assert _ips_of(edited.json()) == ["10.10.0.10", "10.10.0.20"]


# --- 网卡改段 / 删除 / 管理 IP ---------------------------------------------


def test_interface_segment_change_requires_ip_release(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C11")
    seg1 = _make_segment(client, cid, name="s1", cidr="10.11.0.0/24").json()
    seg2 = _make_segment(client, cid, name="s2", cidr="10.11.1.0/24").json()
    created = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": seg1["id"], "ips": [{"mode": "manual", "address": "10.11.0.10"}]}],
    ).json()
    iface = created["interfaces"][0]
    blocked = client.patch(
        f"{BASE}/{created['id']}",
        json={"interfaces": [{"op": "update", "id": iface["id"], "segment_id": seg2["id"]}], "version": 1},
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE"

    ok = client.patch(
        f"{BASE}/{created['id']}",
        json={
            "interfaces": [
                {
                    "op": "update",
                    "id": iface["id"],
                    "segment_id": seg2["id"],
                    "ips": [{"op": "delete", "id": iface["ips"][0]["id"]}],
                }
            ],
            "version": 1,
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["interfaces"][0]["segment_id"] == seg2["id"]


def test_interface_delete_with_ips_blocked(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C12")
    seg = _make_segment(client, cid, cidr="10.12.0.0/24").json()
    created = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.12.0.10"}]}],
    ).json()
    iface = created["interfaces"][0]
    blocked = client.patch(
        f"{BASE}/{created['id']}",
        json={"interfaces": [{"op": "delete", "id": iface["id"]}], "version": 1},
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "INTERFACE_HAS_IPS"

    ok = client.patch(
        f"{BASE}/{created['id']}",
        json={"interfaces": [{"op": "delete", "id": iface["id"], "ips": [{"op": "delete", "id": iface["ips"][0]["id"]}]}], "version": 1},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["interfaces"] == []


def test_management_ip_lifecycle(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C13")
    seg = _make_segment(
        client, cid, cidr="10.13.0.0/24", auto_alloc_start="10.13.0.20", auto_alloc_end="10.13.0.30"
    ).json()
    sid = seg["id"]
    created = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": sid, "ips": [{"mode": "manual", "address": "10.13.0.10"}]}],
        management_ip={"interface_index": 0, "address": "10.13.0.10"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    iface = body["interfaces"][0]
    mgmt_ip_id = iface["ips"][0]["id"]

    # 删除管理 IP 但未显式清空 → 422。
    missing = client.patch(
        f"{BASE}/{body['id']}",
        json={"interfaces": [{"op": "update", "id": iface["id"], "ips": [{"op": "delete", "id": mgmt_ip_id}]}], "version": 1},
    )
    assert missing.status_code == 422
    assert missing.json()["code"] == "MANAGEMENT_IP_REQUIRED"

    # 显式清空 + 删除 → 200。
    cleared = client.patch(
        f"{BASE}/{body['id']}",
        json={
            "interfaces": [{"op": "update", "id": iface["id"], "ips": [{"op": "delete", "id": mgmt_ip_id}]}],
            "management_ip": None,
            "version": 1,
        },
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["management_ip"] is None

    # 重选本请求新建 IP。
    reselected = client.patch(
        f"{BASE}/{body['id']}",
        json={
            "interfaces": [{"op": "update", "id": iface["id"], "ips": [{"op": "create", "mode": "auto"}]}],
            "management_ip": {"interface_index": 0, "address": "10.13.0.20"},
            "version": 2,
        },
    )
    assert reselected.status_code == 200, reselected.text
    assert reselected.json()["management_ip"]["address"] == "10.13.0.20"

    # 用 ip_id 重选既有 IP。
    current_id = reselected.json()["interfaces"][0]["ips"][0]["id"]
    existing_reselect = client.patch(
        f"{BASE}/{body['id']}",
        json={"management_ip": {"ip_id": current_id}, "version": 3},
    )
    assert existing_reselect.status_code == 200, existing_reselect.text


def test_management_ip_invalid(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C14")
    seg = _make_segment(client, cid, cidr="10.14.0.0/24").json()
    first = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.14.0.10"}]}],
    ).json()
    second = _make_resource(
        client, cid, name="cn002",
        interfaces=[{"name": "eth0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.14.0.11"}]}],
    ).json()
    other_ip_id = first["interfaces"][0]["ips"][0]["id"]
    bad = client.patch(
        f"{BASE}/{second['id']}",
        json={"management_ip": {"ip_id": other_ip_id}, "version": 1},
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "MANAGEMENT_IP_INVALID"


# --- 只读端点 / 权限 --------------------------------------------------------


def test_allocated_ips_endpoint(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C15")
    seg = _make_segment(client, cid, cidr="10.15.0.0/24").json()
    sid = seg["id"]
    created = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": sid, "ips": [{"mode": "manual", "address": "10.15.0.10"}]}],
        management_ip={"interface_index": 0, "address": "10.15.0.10"},
    ).json()

    resp = client.get(f"{SEGMENTS}/{sid}/allocated-ips")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["address"] == "10.15.0.10"
    assert item["resource_name"] == "cn001"
    assert item["interface_name"] == "eth0"
    assert item["is_management"] is True
    assert item["resource_type"] == "bare_metal"

    # 分页与 q。
    paged = client.get(f"{SEGMENTS}/{sid}/allocated-ips", params={"page": 1, "page_size": 1})
    assert paged.status_code == 200
    assert paged.json()["page_size"] == 1
    filtered = client.get(f"{SEGMENTS}/{sid}/allocated-ips", params={"q": "cn001"})
    assert filtered.json()["total"] == 1
    empty = client.get(f"{SEGMENTS}/{sid}/allocated-ips", params={"q": "nomatch"})
    assert empty.json()["items"] == []
    assert client.get(f"{SEGMENTS}/999999/allocated-ips").status_code == 404
    assert client.get(f"{SEGMENTS}/{sid}/allocated-ips", params={"page_size": 0}).status_code == 400

    # 空态。
    empty_seg = _make_segment(client, cid, name="empty", cidr="10.16.0.0/24").json()
    empty_resp = client.get(f"{SEGMENTS}/{empty_seg['id']}/allocated-ips")
    assert empty_resp.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_small_prefix_31_and_32(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C21")
    p2p = _make_segment(
        client, cid, name="p2p", cidr="10.21.0.0/31",
        auto_alloc_start="10.21.0.0", auto_alloc_end="10.21.0.1",
    ).json()
    first = _make_resource(
        client, cid, name="p2p-a",
        interfaces=[{"name": "eth0", "segment_id": p2p["id"], "ips": [{"mode": "auto"}]}],
    )
    assert first.status_code == 201, first.text
    assert _ips_of(first.json()) == ["10.21.0.0"]
    second = _make_resource(
        client, cid, name="p2p-b",
        interfaces=[{"name": "eth0", "segment_id": p2p["id"], "ips": [{"mode": "auto"}]}],
    )
    assert _ips_of(second.json()) == ["10.21.0.1"]

    single = _make_segment(
        client, cid, name="host", cidr="10.22.0.5/32",
        auto_alloc_start="10.22.0.5", auto_alloc_end="10.22.0.5",
    ).json()
    host = _make_resource(
        client, cid, name="host-a",
        interfaces=[{"name": "eth0", "segment_id": single["id"], "ips": [{"mode": "auto"}]}],
    )
    assert host.status_code == 201, host.text
    assert _ips_of(host.json()) == ["10.22.0.5"]


def test_deleted_segment_exclusions_not_applied(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C22")
    seg_a = _make_segment(
        client, cid, name="a", cidr="10.33.0.0/24",
        auto_alloc_start="10.33.0.10", auto_alloc_end="10.33.0.20",
    ).json()
    seg_b = _make_segment(client, cid, name="b", cidr="10.33.0.0/25").json()
    reserved = client.post(
        f"{SEGMENTS}/{seg_b['id']}/reserved-addresses", json={"start_ip": "10.33.0.12"}
    ).json()

    # a/b 重叠：seg_b 的保留 .12 参与 seg_a 的排除。
    _make_resource(
        client, cid, name="a1",
        interfaces=[{"name": "eth0", "segment_id": seg_a["id"], "ips": [
            {"mode": "manual", "address": "10.33.0.10"},
            {"mode": "manual", "address": "10.33.0.11"},
        ]}],
    )
    skipped = _make_resource(
        client, cid, name="a2",
        interfaces=[{"name": "eth0", "segment_id": seg_a["id"], "ips": [{"mode": "auto"}]}],
    )
    assert _ips_of(skipped.json()) == ["10.33.0.13"]

    # 删除 seg_b 的保留地址与 seg_b 本身后，.12 可被 seg_a 自动分配。
    assert client.delete(f"{SEGMENTS}/{seg_b['id']}/reserved-addresses/{reserved['id']}").status_code == 204
    assert client.delete(
        f"{SEGMENTS}/{seg_b['id']}/gateway", params={"version": 1}
    ).status_code == 204  # 幂等（无网关）
    assert client.delete(
        f"{SEGMENTS}/{seg_b['id']}", params={"confirm": "b", "version": 1}
    ).status_code == 204
    reused = _make_resource(
        client, cid, name="a3",
        interfaces=[{"name": "eth0", "segment_id": seg_a["id"], "ips": [{"mode": "auto"}]}],
    )
    assert _ips_of(reused.json()) == ["10.33.0.12"]


def test_invalid_ip_ops_and_not_found(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C23")
    seg = _make_segment(client, cid, cidr="10.23.0.0/24").json()
    created = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.23.0.10"}]}],
    ).json()
    iface_id = created["interfaces"][0]["id"]

    not_found = client.patch(
        f"{BASE}/{created['id']}",
        json={"interfaces": [{"op": "update", "id": iface_id, "ips": [{"op": "delete", "id": 999999}]}], "version": 1},
    )
    assert not_found.status_code == 422
    assert "IP_NOT_FOUND" in [e["code"] for e in not_found.json()["errors"]]

    bad_op = client.patch(
        f"{BASE}/{created['id']}",
        json={"interfaces": [{"op": "update", "id": iface_id, "ips": [{"op": "bogus"}]}], "version": 1},
    )
    assert bad_op.status_code == 400
    assert bad_op.json()["errors"][0]["code"] == "INVALID_INTERFACE_OP"

    delete_create = client.patch(
        f"{BASE}/{created['id']}",
        json={"interfaces": [{"op": "delete", "id": iface_id, "ips": [{"op": "create", "mode": "auto"}]}], "version": 1},
    )
    assert delete_create.status_code == 400


def test_create_management_ip_invalid(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C24")
    seg = _make_segment(client, cid, cidr="10.24.0.0/24").json()
    resp = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.24.0.10"}]}],
        management_ip={"interface_index": 0, "address": "10.24.0.99"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "MANAGEMENT_IP_INVALID"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Resource).where(Resource.name == "cn001")) == 0


def test_permissions(client, add_user, login_as) -> None:
    add_user("viewer1", PASSWORD, "viewer")
    assert login_as(client, "viewer1", PASSWORD).status_code == 200
    # viewer 建资源 → 403。
    denied = _make_resource(client, 1, name="nope")
    assert denied.status_code == 403
    # 未登录读 allocated-ips → 401。
    anon = TestClient(client.app)
    assert anon.get(f"{SEGMENTS}/1/allocated-ips").status_code == 401
    # 查看者读已分配 IP（需先由 admin 建数据）。
    client.cookies.clear()
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C17")
    seg = _make_segment(client, cid, cidr="10.17.0.0/24").json()
    _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": seg["id"], "ips": [{"mode": "manual", "address": "10.17.0.10"}]}],
    )
    client.cookies.clear()
    assert login_as(client, "viewer1", PASSWORD).status_code == 200
    assert client.get(f"{SEGMENTS}/{seg['id']}/allocated-ips").status_code == 200


# --- F005 网段保护 ----------------------------------------------------------


def test_segment_protections(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C18")
    seg = _make_segment(
        client, cid, cidr="10.18.0.0/24",
        gateway="10.18.0.1",
        auto_alloc_start="10.18.0.20", auto_alloc_end="10.18.0.30",
    ).json()
    sid = seg["id"]
    before = client.get(f"{SEGMENTS}/{sid}").json()["auto_assignable_count"]
    _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": sid, "ips": [{"mode": "manual", "address": "10.18.0.20"}]}],
    )
    after = client.get(f"{SEGMENTS}/{sid}").json()["auto_assignable_count"]
    assert after == before - 1
    assert client.get(f"{SEGMENTS}/{sid}").json()["allocated_count"] == 1

    # 先清空网关（F005 删除前置），再删除网段 → 409 SEGMENT_HAS_ALLOCATIONS。
    cleared = client.delete(f"{SEGMENTS}/{sid}/gateway", params={"version": 1})
    assert cleared.status_code == 204
    blocked_delete = client.delete(
        f"{SEGMENTS}/{sid}", params={"confirm": seg["name"], "version": 2}
    )
    assert blocked_delete.status_code == 409
    assert blocked_delete.json()["code"] == "SEGMENT_HAS_ALLOCATIONS"

    # 修改 CIDR → 409 CIDR_IMMUTABLE。
    cidr_edit = client.patch(
        f"{SEGMENTS}/{sid}", json={"cidr": "10.18.1.0/24", "version": 2}
    )
    assert cidr_edit.status_code == 409
    assert cidr_edit.json()["code"] == "CIDR_IMMUTABLE"


def test_reserved_and_gateway_conflicts_with_allocation(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C19")
    seg = _make_segment(client, cid, cidr="10.19.0.0/24").json()
    sid = seg["id"]
    _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": sid, "ips": [{"mode": "manual", "address": "10.19.0.10"}]}],
    )
    # 新增保留地址命中已分配 → 409。
    reserved = client.post(
        f"{SEGMENTS}/{sid}/reserved-addresses",
        json={"start_ip": "10.19.0.10", "end_ip": "10.19.0.12"},
    )
    assert reserved.status_code == 409
    assert reserved.json()["code"] == "RESERVED_ADDRESS_CONFLICTS_ALLOCATION"
    # 设置网关命中已分配 → 409。
    gateway = client.patch(
        f"{SEGMENTS}/{sid}", json={"gateway": "10.19.0.10", "version": 1}
    )
    assert gateway.status_code == 409
    assert gateway.json()["code"] == "GATEWAY_CONFLICTS_ALLOCATION"


# --- 审计 / 历史 ------------------------------------------------------------


def test_audit_and_history_include_ips_and_management(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C20")
    seg = _make_segment(
        client, cid, cidr="10.20.0.0/24", auto_alloc_start="10.20.0.20", auto_alloc_end="10.20.0.30"
    ).json()
    sid = seg["id"]
    created = _make_resource(
        client, cid, name="cn001",
        interfaces=[{"name": "eth0", "segment_id": sid, "ips": [{"mode": "manual", "address": "10.20.0.10"}]}],
        management_ip={"interface_index": 0, "address": "10.20.0.10"},
    ).json()
    iface = created["interfaces"][0]
    old_id = iface["ips"][0]["id"]
    edited = client.patch(
        f"{BASE}/{created['id']}",
        json={
            "interfaces": [{"op": "update", "id": iface["id"], "ips": [{"op": "delete", "id": old_id}, {"op": "create", "mode": "auto"}]}],
            "management_ip": {"interface_index": 0, "address": "10.20.0.20"},
            "version": 1,
        },
    )
    assert edited.status_code == 200, edited.text

    with SessionLocal() as db:
        audit_row = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "resource.update",
                AuditLog.target_type == "resource",
                AuditLog.target_id == str(created["id"]),
            )
        )
        assert audit_row is not None
        assert audit_row.change["management_ip"] == {
            "from": "10.20.0.10",
            "to": "10.20.0.20",
        }
        history = db.scalar(
            select(ResourceHistory).where(
                ResourceHistory.action == "update",
                ResourceHistory.target_type == "resource",
                ResourceHistory.target_id == str(created["id"]),
            )
        )
        assert history is not None
        updated = history.change["interfaces"]["updated"][0]
        assert updated["ips"]["created"] == [{"address": "10.20.0.20", "mode": "auto"}]
        assert updated["ips"]["deleted"] == [{"ip_id": old_id, "address": "10.20.0.10"}]
        assert history.change["management_ip"]["to"] == "10.20.0.20"

    # 删除后 IP 行真实消失、历史保留。
    latest = client.get(f"{BASE}/{created['id']}").json()
    new_ip_id = latest["interfaces"][0]["ips"][0]["id"]
    client.patch(
        f"{BASE}/{created['id']}",
        json={"interfaces": [{"op": "update", "id": iface["id"], "ips": [{"op": "delete", "id": new_ip_id}]}], "management_ip": None, "version": 2},
    )
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(IpAddress).where(IpAddress.resource_id == created["id"])) == 0
        assert db.scalar(select(func.count()).select_from(ResourceHistory).where(ResourceHistory.target_id == str(created["id"]))) >= 1