"""F005 网段 API 集成测试（架构 §11，真实 PostgreSQL）。

覆盖唯一性/CIDR 规范化/重叠/字段越界/删除前置/二次确认/乐观锁/权限/审计与
资源历史/auto_assignable_count。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, NetworkSegment, ResourceHistory

PASSWORD = "Passw0rd1"
BASE = "/api/v1/network-segments"


def _auth(client, add_user, login_as, username: str, role: str):
    add_user(username, PASSWORD, role)
    assert login_as(client, username, PASSWORD).status_code == 200
    return client


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
    return client.post(BASE, json=body)


# --- 身份 / 唯一性 ----------------------------------------------------------


def test_segment_create_and_name_uniqueness(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C1")

    created = _make_segment(client, cid, name="  mgmt  ", cidr="192.168.1.5/24")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "mgmt"  # 去首尾空格
    assert body["cidr"] == "192.168.1.0/24"  # 主机位规范化
    assert body["version"] == 1
    assert body["allocated_count"] == 0
    assert body["has_overlap"] is False
    assert body["overlaps"] == []
    assert body["reserved_addresses"] == []

    # 同集群同名（区分大小写，去空格后相同）→ 409。
    dup = _make_segment(client, cid, name="mgmt", cidr="10.0.0.0/24")
    assert dup.status_code == 409
    assert dup.json()["code"] == "SEGMENT_NAME_TAKEN"

    # 区分大小写：同集群大小写不同允许。
    assert _make_segment(client, cid, name="MGMT", cidr="10.0.0.0/24").status_code == 201

    # 纯空白名称拒绝。
    blank = _make_segment(client, cid, name="   ", cidr="10.1.0.0/24")
    assert blank.status_code == 422
    assert blank.json()["errors"][0]["code"] == "NAME_FORMAT"

    # 跨集群同名允许。
    cid2 = _make_cluster(client, "C2", name="Beta")
    assert _make_segment(client, cid2, name="mgmt", cidr="10.0.0.0/24").status_code == 201


def test_cidr_normalized_unique_per_cluster(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C3")
    cid2 = _make_cluster(client, "C4", name="Beta")

    assert _make_segment(client, cid, name="a", cidr="192.168.1.0/24").status_code == 201
    # 主机位归一化后相同 → 409。
    dup = _make_segment(client, cid, name="b", cidr="192.168.1.5/24")
    assert dup.status_code == 409
    assert dup.json()["code"] == "SEGMENT_CIDR_TAKEN"

    # 跨集群相同 CIDR 允许。
    assert _make_segment(client, cid2, name="a", cidr="192.168.1.0/24").status_code == 201


def test_cidr_invalid_and_ipv6(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C5")

    for bad, code in [
        ("not-a-cidr", "CIDR_INVALID"),
        ("192.168.1.0/33", "CIDR_INVALID"),
        ("2001:db8::/32", "CIDR_NOT_IPV4"),
    ]:
        resp = _make_segment(client, cid, name=f"s{abs(hash(bad)) % 1000}", cidr=bad)
        assert resp.status_code == 422, bad
        codes = [e["code"] for e in resp.json()["errors"]]
        assert code in codes, (bad, codes)


def test_overlap_is_warning_only(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C6")

    first = _make_segment(client, cid, name="big", cidr="192.168.1.0/24").json()
    second = _make_segment(client, cid, name="small", cidr="192.168.1.128/25")
    assert second.status_code == 201
    body = second.json()
    assert body["has_overlap"] is True
    assert body["overlaps"] == [
        {"segment_id": first["id"], "name": "big", "cidr": "192.168.1.0/24"}
    ]

    # 列表也反映 has_overlap。
    listed = client.get(BASE, params={"cluster_id": cid}).json()["items"]
    by_name = {i["name"]: i for i in listed}
    assert by_name["big"]["has_overlap"] is True
    assert by_name["small"]["has_overlap"] is True


# --- 字段校验 ---------------------------------------------------------------


def test_gateway_and_auto_range_validation(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C7")

    out = _make_segment(
        client, cid, name="g1", cidr="192.168.1.0/24", gateway="10.0.0.1"
    )
    assert out.status_code == 422
    assert out.json()["errors"][0]["code"] == "GATEWAY_OUT_OF_CIDR"

    one_end = _make_segment(
        client, cid, name="g2", cidr="192.168.2.0/24", auto_alloc_start="192.168.2.10"
    )
    assert one_end.status_code == 422
    assert one_end.json()["errors"][0]["code"] == "AUTO_RANGE_INVALID"

    reversed_range = _make_segment(
        client,
        cid,
        name="g3",
        cidr="192.168.3.0/24",
        auto_alloc_start="192.168.3.30",
        auto_alloc_end="192.168.3.10",
    )
    assert reversed_range.status_code == 422
    assert reversed_range.json()["errors"][0]["code"] == "AUTO_RANGE_INVALID"

    bad_vlan = _make_segment(client, cid, name="g4", cidr="192.168.4.0/24", vlan=4095)
    assert bad_vlan.status_code == 422
    assert bad_vlan.json()["errors"][0]["code"] == "VLAN_INVALID"

    ok = _make_segment(
        client,
        cid,
        name="g5",
        cidr="192.168.5.0/24",
        gateway="192.168.5.1",
        auto_alloc_start="192.168.5.10",
        auto_alloc_end="192.168.5.20",
        vlan=100,
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["auto_alloc_enabled"] is True


def test_reserved_address_validation_and_overlap(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C8")
    seg = _make_segment(client, cid, name="r", cidr="192.168.1.0/24").json()
    sid = seg["id"]

    out = client.post(
        f"{BASE}/{sid}/reserved-addresses", json={"start_ip": "10.0.0.1"}
    )
    assert out.status_code == 422
    assert out.json()["errors"][0]["code"] == "RESERVED_OUT_OF_CIDR"

    bad_range = client.post(
        f"{BASE}/{sid}/reserved-addresses",
        json={"start_ip": "192.168.1.30", "end_ip": "192.168.1.10"},
    )
    assert bad_range.status_code == 422
    assert bad_range.json()["errors"][0]["code"] == "RESERVED_RANGE_INVALID"

    single = client.post(
        f"{BASE}/{sid}/reserved-addresses", json={"start_ip": "192.168.1.100"}
    )
    assert single.status_code == 201, single.text
    assert single.json()["is_range"] is False

    rng = client.post(
        f"{BASE}/{sid}/reserved-addresses",
        json={"start_ip": "192.168.1.110", "end_ip": "192.168.1.120"},
    )
    assert rng.status_code == 201
    assert rng.json()["is_range"] is True

    # 与既有范围重叠 → 422 RESERVED_OVERLAP。
    overlap = client.post(
        f"{BASE}/{sid}/reserved-addresses",
        json={"start_ip": "192.168.1.115", "end_ip": "192.168.1.118"},
    )
    assert overlap.status_code == 422
    assert overlap.json()["errors"][0]["code"] == "RESERVED_OVERLAP"

    # 重复单地址也视为重叠。
    dup = client.post(
        f"{BASE}/{sid}/reserved-addresses", json={"start_ip": "192.168.1.100"}
    )
    assert dup.status_code == 422
    assert dup.json()["errors"][0]["code"] == "RESERVED_OVERLAP"

    listed = client.get(f"{BASE}/{sid}/reserved-addresses").json()["items"]
    assert [r["start_ip"] for r in listed] == ["192.168.1.100", "192.168.1.110"]

    # 删除单条；不存在 → 404。
    rid = listed[0]["id"]
    assert (
        client.delete(f"{BASE}/{sid}/reserved-addresses/{rid}").status_code == 204
    )
    missing = client.delete(f"{BASE}/{sid}/reserved-addresses/999999")
    assert missing.status_code == 404
    assert missing.json()["code"] == "RESERVED_ADDRESS_NOT_FOUND"


# --- 删除前置 / 二次确认 / 乐观锁 -------------------------------------------


def test_delete_preconditions_and_confirmation(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C9")
    seg = _make_segment(
        client, cid, name="DelMe", cidr="192.168.1.0/24", gateway="192.168.1.1"
    ).json()
    sid = seg["id"]

    # confirm 不匹配 → 422 且不删除。
    mismatch = client.delete(
        f"{BASE}/{sid}", params={"confirm": "wrong", "version": 1}
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "DELETE_CONFIRMATION_MISMATCH"
    assert client.get(f"{BASE}/{sid}").status_code == 200

    # 有保留地址 → 409。
    client.post(f"{BASE}/{sid}/reserved-addresses", json={"start_ip": "192.168.1.50"})
    blocked = client.delete(f"{BASE}/{sid}", params={"confirm": "DelMe", "version": 1})
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "SEGMENT_HAS_RESERVED_ADDRESSES"

    # 删除保留地址后，网关未清 → 409。
    listed = client.get(f"{BASE}/{sid}/reserved-addresses").json()["items"]
    client.delete(f"{BASE}/{sid}/reserved-addresses/{listed[0]['id']}")
    gateway_blocked = client.delete(
        f"{BASE}/{sid}", params={"confirm": "DelMe", "version": 1}
    )
    assert gateway_blocked.status_code == 409
    assert gateway_blocked.json()["code"] == "SEGMENT_GATEWAY_NOT_CLEARED"

    # 清空网关（幂等），然后删除。
    cleared = client.delete(f"{BASE}/{sid}/gateway", params={"version": 1})
    assert cleared.status_code == 204
    assert client.delete(f"{BASE}/{sid}/gateway", params={"version": 1}).status_code == 204

    deleted = client.delete(f"{BASE}/{sid}", params={"confirm": "  DelMe  ", "version": 2})
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"{BASE}/{sid}").status_code == 404


def test_delete_confirm_case_sensitive(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C10")
    seg = _make_segment(client, cid, name="CaseSensitive", cidr="10.9.0.0/24").json()

    resp = client.delete(
        f"{BASE}/{seg['id']}",
        params={"confirm": "casesensitive", "version": 1},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "DELETE_CONFIRMATION_MISMATCH"

    assert (
        client.delete(
            f"{BASE}/{seg['id']}",
            params={"confirm": "CaseSensitive", "version": 1},
        ).status_code
        == 204
    )


def test_optimistic_lock_patch_and_delete(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C11")
    seg = _make_segment(client, cid, name="Locked", cidr="10.10.0.0/24").json()
    sid = seg["id"]

    ok = client.patch(f"{BASE}/{sid}", json={"purpose": "新用途", "version": 1})
    assert ok.status_code == 200
    assert ok.json()["version"] == 2

    stale = client.patch(f"{BASE}/{sid}", json={"purpose": "x", "version": 1})
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"

    stale_del = client.delete(
        f"{BASE}/{sid}", params={"confirm": "Locked", "version": 1}
    )
    assert stale_del.status_code == 409
    assert stale_del.json()["code"] == "VERSION_CONFLICT"

    # 无可改字段 → 400。
    noop = client.patch(f"{BASE}/{sid}", json={"version": 2})
    assert noop.status_code == 400
    assert noop.json()["errors"][0]["code"] == "NO_FIELDS"


def test_patch_cidr_narrowing_blocks_existing_reserved(
    client, add_user, login_as
) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C12")
    seg = _make_segment(client, cid, name="Narrow", cidr="192.168.1.0/24").json()
    sid = seg["id"]
    client.post(
        f"{BASE}/{sid}/reserved-addresses",
        json={"start_ip": "192.168.1.200"},
    )

    resp = client.patch(
        f"{BASE}/{sid}", json={"cidr": "192.168.1.0/25", "version": 1}
    )
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["code"] == "RESERVED_OUT_OF_CIDR"

    # CIDR 未变，保留地址仍可用。
    assert client.get(f"{BASE}/{sid}").json()["cidr"] == "192.168.1.0/24"


# --- 集群删除保护 -----------------------------------------------------------


def test_cluster_delete_blocked_by_segment(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C13", name="Protected")
    _make_segment(client, cid, name="child", cidr="10.20.0.0/24")

    resp = client.delete(
        f"/api/v1/clusters/{cid}", params={"confirm": "Protected", "version": 1}
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "CLUSTER_HAS_ASSOCIATIONS"


# --- 权限 -------------------------------------------------------------------


def test_permissions(client, add_user, login_as) -> None:
    admin = _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(admin, "C14")
    seg = _make_segment(admin, cid, name="perm", cidr="10.30.0.0/24").json()

    anon = TestClient(app)
    assert anon.get(BASE).status_code == 401
    assert anon.post(BASE, json={}).status_code == 401

    viewer = _auth(client, add_user, login_as, "v1", "viewer")
    assert viewer.get(BASE).status_code == 200
    assert viewer.get(f"{BASE}/{seg['id']}").status_code == 200
    assert _make_segment(viewer, cid, name="vseg", cidr="10.31.0.0/24").status_code == 403
    assert (
        viewer.patch(
            f"{BASE}/{seg['id']}", json={"purpose": "x", "version": 1}
        ).status_code
        == 403
    )
    assert (
        viewer.post(
            f"{BASE}/{seg['id']}/reserved-addresses",
            json={"start_ip": "10.30.0.5"},
        ).status_code
        == 403
    )
    assert (
        viewer.delete(
            f"{BASE}/{seg['id']}", params={"confirm": "perm", "version": 1}
        ).status_code
        == 403
    )

    maint = _auth(client, add_user, login_as, "m1", "maintainer")
    assert _make_segment(maint, cid, name="mseg", cidr="10.32.0.0/24").status_code == 201
    assert (
        maint.patch(
            f"{BASE}/{seg['id']}", json={"purpose": "m", "version": 1}
        ).status_code
        == 200
    )


# --- 计数 -------------------------------------------------------------------


def test_auto_assignable_count(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C15")

    # 未启用 → 0。
    disabled = _make_segment(client, cid, name="d", cidr="10.40.0.0/24").json()
    assert disabled["auto_assignable_count"] == 0

    # 启用 .10-.20（11 个），无排除 → 11。
    seg = _make_segment(
        client,
        cid,
        name="s",
        cidr="192.168.1.0/24",
        gateway="192.168.1.15",
        auto_alloc_start="192.168.1.10",
        auto_alloc_end="192.168.1.20",
    ).json()
    sid = seg["id"]
    assert seg["auto_assignable_count"] == 10  # 排除网关 .15

    # 自身保留 .12-.14 → 再减 3。
    client.post(
        f"{BASE}/{sid}/reserved-addresses",
        json={"start_ip": "192.168.1.12", "end_ip": "192.168.1.14"},
    )
    after = client.get(f"{BASE}/{sid}").json()
    assert after["auto_assignable_count"] == 7
    assert after["reserved_address_count"] == 1

    # 重叠网段 T=192.168.1.0/25 保留 .16，其网络/广播 .0/.127 不在范围。
    other = _make_segment(client, cid, name="t", cidr="192.168.1.0/25").json()
    client.post(
        f"{BASE}/{other['id']}/reserved-addresses",
        json={"start_ip": "192.168.1.16"},
    )
    recomputed = client.get(f"{BASE}/{sid}").json()
    assert recomputed["auto_assignable_count"] == 6

    # 删除重叠网段（含清空其保留）后计数恢复。
    listed = client.get(f"{BASE}/{other['id']}/reserved-addresses").json()["items"]
    client.delete(f"{BASE}/{other['id']}/reserved-addresses/{listed[0]['id']}")
    client.delete(
        f"{BASE}/{other['id']}", params={"confirm": "t", "version": 1}
    )
    restored = client.get(f"{BASE}/{sid}").json()
    assert restored["auto_assignable_count"] == 7


def test_auto_assignable_count_network_broadcast_and_small_prefixes(
    client, add_user, login_as
) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C16")

    # /24 范围 .0-.2：网络地址 .0 被排除 → 2。
    seg = _make_segment(
        client,
        cid,
        name="nb",
        cidr="192.168.9.0/24",
        auto_alloc_start="192.168.9.0",
        auto_alloc_end="192.168.9.2",
    ).json()
    assert seg["auto_assignable_count"] == 2

    # /31 两个地址均可用（无网络/广播排除）。
    p2p = _make_segment(
        client,
        cid,
        name="p2p",
        cidr="10.50.0.0/31",
        auto_alloc_start="10.50.0.0",
        auto_alloc_end="10.50.0.1",
    ).json()
    assert p2p["auto_assignable_count"] == 2

    # /32 单主机可用。
    single = _make_segment(
        client,
        cid,
        name="host",
        cidr="10.60.0.7/32",
        auto_alloc_start="10.60.0.7",
        auto_alloc_end="10.60.0.7",
    ).json()
    assert single["auto_assignable_count"] == 1


# --- 审计与资源历史 ---------------------------------------------------------


def test_audit_and_history(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C17")
    seg = _make_segment(
        client, cid, name="AuditSeg", cidr="10.70.0.0/24", gateway="10.70.0.1"
    ).json()
    sid = seg["id"]

    with SessionLocal() as db:
        row = db.scalar(
            select(AuditLog).where(
                AuditLog.target_type == "segment",
                AuditLog.target_id == str(sid),
                AuditLog.action == "segment.create",
            )
        )
        assert row is not None
        assert row.target_key_snapshot == "AuditSeg"

    # update → 审计 + 历史。
    assert (
        client.patch(f"{BASE}/{sid}", json={"purpose": "p2", "version": 1}).status_code
        == 200
    )
    rid = client.post(
        f"{BASE}/{sid}/reserved-addresses", json={"start_ip": "10.70.0.9"}
    ).json()["id"]
    client.delete(f"{BASE}/{sid}/gateway", params={"version": 2})
    client.delete(f"{BASE}/{sid}/reserved-addresses/{rid}")

    with SessionLocal() as db:
        actions = set(
            db.scalars(
                select(AuditLog.action).where(AuditLog.target_id == str(sid))
            ).all()
        )
        assert {
            "segment.create",
            "segment.update",
            "segment.reserved_address.create",
            "segment.reserved_address.delete",
            "segment.gateway.clear",
        } <= actions

        hist_actions = db.scalars(
            select(ResourceHistory.action).where(
                ResourceHistory.target_type == "segment",
                ResourceHistory.target_id == str(sid),
            )
        ).all()
        assert hist_actions and all(a == "update" for a in hist_actions)

    # delete → 审计 + 历史；业务行删除后历史仍在。
    assert (
        client.delete(f"{BASE}/{sid}", params={"confirm": "AuditSeg", "version": 3}).status_code
        == 204
    )
    with SessionLocal() as db:
        assert db.get(NetworkSegment, sid) is None
        del_hist = db.scalar(
            select(ResourceHistory).where(
                ResourceHistory.target_id == str(sid),
                ResourceHistory.action == "delete",
            )
        )
        assert del_hist is not None
        assert del_hist.target_type == "segment"
        assert del_hist.change == {"name": "AuditSeg", "cidr": "10.70.0.0/24"}
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.target_id == str(sid))
            )
            >= 6
        )


# --- 列表 / 搜索 / 分页 -----------------------------------------------------


def test_list_search_sort_pagination(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C18", name="ListCluster")

    empty = client.get(BASE, params={"cluster_id": cid})
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}

    _make_segment(client, cid, name="beta", cidr="10.80.0.0/24", purpose="用途A")
    _make_segment(client, cid, name="Alpha", cidr="10.81.0.0/24", technology="IB")

    by_name = client.get(BASE, params={"cluster_id": cid, "sort": "name"})
    assert [i["name"] for i in by_name.json()["items"]] == ["Alpha", "beta"]

    searched = client.get(BASE, params={"cluster_id": cid, "q": "10.80"})
    assert [i["name"] for i in searched.json()["items"]] == ["beta"]

    paged = client.get(BASE, params={"cluster_id": cid, "page": 2, "page_size": 1})
    assert paged.json()["total"] == 2
    assert len(paged.json()["items"]) == 1

    # 不存在的 cluster_id 返回空列表（不 404）。
    missing = client.get(BASE, params={"cluster_id": 999999})
    assert missing.status_code == 200
    assert missing.json()["items"] == []

    assert client.get(BASE, params={"sort": "bogus"}).status_code == 400
    assert client.get(BASE, params={"page_size": 101}).status_code == 400


def test_cluster_not_found_on_create(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    resp = _make_segment(client, 999999, name="x", cidr="10.90.0.0/24")
    assert resp.status_code == 404
    assert resp.json()["code"] == "CLUSTER_NOT_FOUND"


def test_purpose_technology_and_name_bounds(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cid = _make_cluster(client, "C19")

    blank_purpose = _make_segment(
        client, cid, name="p", cidr="10.91.0.0/24", purpose="   "
    )
    assert blank_purpose.status_code == 422
    assert blank_purpose.json()["code"] == "VALIDATION_ERROR"

    blank_tech = _make_segment(
        client, cid, name="t", cidr="10.92.0.0/24", technology=""
    )
    assert blank_tech.status_code == 422
    assert blank_tech.json()["code"] == "VALIDATION_ERROR"

    long_name = _make_segment(client, cid, name="n" * 129, cidr="10.93.0.0/24")
    assert long_name.status_code == 422
    assert long_name.json()["errors"][0]["code"] == "NAME_FORMAT"