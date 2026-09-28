"""F002 资源 API 集成测试（架构 §10，真实 PostgreSQL）。

覆盖唯一性/同名新增/只读字段/网卡显式增改删/整单原子/删除前置/乐观锁/
权限/审计与资源历史/网段与集群删除保护。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, NetworkInterface, Resource, ResourceHistory

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


# --- 创建 / 唯一性 / 同名新增 ------------------------------------------------


def test_create_and_name_uniqueness(client, add_user, login_as) -> None:
    admin_id = _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C1")
    c2 = _make_cluster(client, "C2", name="Beta")

    created = _make_resource(client, c1, name="  cn001  ")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "cn001"  # 去首尾空格
    assert body["status"] == "ALLOC"  # 默认
    assert body["resource_type"] == "bare_metal"
    assert body["version"] == 1
    assert body["interfaces"] == []
    assert body["status_updated_by"] == admin_id
    assert body["cluster_id"] == c1
    assert body["cluster_code"] == "C1"
    assert body["cluster_name"] == "Alpha"
    resource_id = body["id"]

    # 同集群同名 → 409 + existing_resource_id/type，不创建第二条。
    dup = _make_resource(client, c1, name="cn001")
    assert dup.status_code == 409
    assert dup.json()["code"] == "RESOURCE_NAME_EXISTS"
    assert dup.json()["existing_resource_id"] == resource_id
    assert dup.json()["existing_resource_type"] == "bare_metal"
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Resource)
                .where(Resource.cluster_id == c1, Resource.name == "cn001")
            )
            == 1
        )

    # 区分大小写：同集群 CN001 允许。
    assert _make_resource(client, c1, name="CN001").status_code == 201

    # 裸金属与 VM 统一判重。
    assert _make_resource(client, c1, name="vmx").status_code == 201
    vm_dup = _make_resource(
        client, c1, name="vmx", resource_type="virtual_machine"
    )
    assert vm_dup.status_code == 409
    assert vm_dup.json()["code"] == "RESOURCE_NAME_EXISTS"
    assert vm_dup.json()["existing_resource_type"] == "bare_metal"

    # 跨集群同名允许。
    assert _make_resource(client, c2, name="cn001").status_code == 201

    # 纯空白 / 超长名称拒绝。
    blank = _make_resource(client, c1, name="   ")
    assert blank.status_code == 422
    assert blank.json()["errors"][0]["code"] == "NAME_FORMAT"
    long_name = _make_resource(client, c1, name="x" * 129)
    assert long_name.status_code == 422
    assert long_name.json()["errors"][0]["code"] == "NAME_FORMAT"

    # 非法类型 / 状态。
    bad_type = _make_resource(client, c1, name="bt", resource_type="container")
    assert bad_type.status_code == 422
    assert bad_type.json()["errors"][0]["code"] == "RESOURCE_TYPE_INVALID"
    bad_status = _make_resource(client, c1, name="bs", status="BUSY")
    assert bad_status.status_code == 422
    assert bad_status.json()["errors"][0]["code"] == "STATUS_INVALID"

    # 集群不存在 → 404。
    missing = _make_resource(client, 999999, name="ghost")
    assert missing.status_code == 404
    assert missing.json()["code"] == "CLUSTER_NOT_FOUND"


# --- 只读字段 / NO_FIELDS ---------------------------------------------------


def test_readonly_fields_and_no_fields(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C3")
    c2 = _make_cluster(client, "C4", name="Beta")
    resource = _make_resource(client, c1, name="ro").json()
    rid = resource["id"]

    type_immutable = client.patch(
        f"{BASE}/{rid}",
        json={"resource_type": "virtual_machine", "version": 1},
    )
    assert type_immutable.status_code == 400
    assert type_immutable.json()["code"] == "INVALID_REQUEST"
    assert type_immutable.json()["errors"][0]["code"] == "RESOURCE_TYPE_IMMUTABLE"

    cluster_immutable = client.patch(
        f"{BASE}/{rid}", json={"cluster_id": c2, "version": 1}
    )
    assert cluster_immutable.status_code == 400
    assert cluster_immutable.json()["errors"][0]["code"] == "RESOURCE_CLUSTER_IMMUTABLE"

    # 只读字段传相同值 + 无可改字段 → NO_FIELDS（版本不变）。
    no_fields = client.patch(
        f"{BASE}/{rid}",
        json={"resource_type": "bare_metal", "cluster_id": c1, "version": 1},
    )
    assert no_fields.status_code == 400
    assert no_fields.json()["errors"][0]["code"] == "NO_FIELDS"

    only_version = client.patch(f"{BASE}/{rid}", json={"version": 1})
    assert only_version.status_code == 400
    assert only_version.json()["errors"][0]["code"] == "NO_FIELDS"

    # 相同只读值 + 可改字段：容忍只读字段并生效。
    ok = client.patch(
        f"{BASE}/{rid}",
        json={"resource_type": "bare_metal", "cluster_id": c1, "name": "ro2", "version": 1},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["name"] == "ro2"
    assert ok.json()["version"] == 2


# --- 网卡增 / 改 / 删 / 省略 ------------------------------------------------


def test_interface_crud_and_omitted(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C5")
    seg = _make_segment(client, c1, name="mgmt", cidr="192.168.1.0/24").json()
    seg_id = seg["id"]

    created = _make_resource(
        client,
        c1,
        name="srv1",
        interfaces=[
            {"name": "  eth0  ", "segment_id": seg_id},
            {"name": "ib0"},
        ],
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert [i["name"] for i in body["interfaces"]] == ["eth0", "ib0"]
    eth0 = body["interfaces"][0]
    assert eth0["segment_id"] == seg_id
    assert eth0["segment"] == {
        "id": seg_id,
        "name": "mgmt",
        "cidr": "192.168.1.0/24",
        "purpose": "管理",
        "technology": "Ethernet",
        "vlan": None,
        "gateway": None,
    }
    assert body["interfaces"][1]["segment_id"] is None
    assert body["interfaces"][1]["segment"] is None
    ib0_id = body["interfaces"][1]["id"]
    eth0_id = eth0["id"]
    rid = body["id"]

    # 省略 interfaces：网卡未修改（仅状态变更）。
    status_only = client.patch(
        f"{BASE}/{rid}", json={"status": "DOWN", "version": 1}
    )
    assert status_only.status_code == 200, status_only.text
    assert status_only.json()["status"] == "DOWN"
    assert [i["name"] for i in status_only.json()["interfaces"]] == ["eth0", "ib0"]

    # 显式增 / 改 / 删。
    edited = client.patch(
        f"{BASE}/{rid}",
        json={
            "interfaces": [
                {"op": "create", "name": "ib1", "segment_id": None},
                {"op": "update", "id": eth0_id, "name": "eth1"},
                {"op": "delete", "id": ib0_id},
            ],
            "version": 2,
        },
    )
    assert edited.status_code == 200, edited.text
    names = [i["name"] for i in edited.json()["interfaces"]]
    assert names == ["eth1", "ib1"]
    # eth1 保留原网段（update 省略 segment_id=不修改）。
    eth1 = next(i for i in edited.json()["interfaces"] if i["name"] == "eth1")
    assert eth1["segment_id"] == seg_id

    # interfaces=[]：不改动网卡（与名称变更同次提交）。
    empty = client.patch(
        f"{BASE}/{rid}", json={"name": "srv1b", "interfaces": [], "version": 3}
    )
    assert empty.status_code == 200, empty.text
    assert [i["name"] for i in empty.json()["interfaces"]] == ["eth1", "ib1"]

    # 清空网段（显式 null）。
    clear = client.patch(
        f"{BASE}/{rid}",
        json={"interfaces": [{"op": "update", "id": eth0_id, "segment_id": None}], "version": 4},
    )
    assert clear.status_code == 200, clear.text
    cleared = next(i for i in clear.json()["interfaces"] if i["id"] == eth0_id)
    assert cleared["segment_id"] is None

    # update/delete 非本资源网卡 → 422 INTERFACE_NOT_FOUND。
    not_found = client.patch(
        f"{BASE}/{rid}",
        json={"interfaces": [{"op": "delete", "id": 999999}], "version": 5},
    )
    assert not_found.status_code == 422
    assert not_found.json()["errors"][0]["code"] == "INTERFACE_NOT_FOUND"

    # 非法 op → 400 INVALID_INTERFACE_OP。
    bad_op = client.patch(
        f"{BASE}/{rid}",
        json={"interfaces": [{"op": "upsert", "name": "x"}], "version": 5},
    )
    assert bad_op.status_code == 400
    assert bad_op.json()["errors"][0]["code"] == "INVALID_INTERFACE_OP"


def test_payload_duplicate_interface_name(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C6")

    dup_create = _make_resource(
        client,
        c1,
        name="dup1",
        interfaces=[{"name": "eth0"}, {"name": " eth0 "}],
    )
    assert dup_create.status_code == 422
    assert dup_create.json()["code"] == "VALIDATION_ERROR"
    err = dup_create.json()["errors"][0]
    assert err["code"] == "INTERFACE_NAME_DUPLICATE_IN_PAYLOAD"
    assert err["field"] == "interfaces[1].name"

    resource = _make_resource(client, c1, name="dup2").json()
    dup_patch = client.patch(
        f"{BASE}/{resource['id']}",
        json={
            "interfaces": [
                {"op": "create", "name": "ib0"},
                {"op": "create", "name": "ib0"},
            ],
            "version": 1,
        },
    )
    assert dup_patch.status_code == 422
    assert dup_patch.json()["errors"][0]["code"] == "INTERFACE_NAME_DUPLICATE_IN_PAYLOAD"


def test_interface_name_taken_against_existing(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C7")
    resource = _make_resource(
        client, c1, name="taken", interfaces=[{"name": "eth0"}]
    ).json()

    conflict = client.patch(
        f"{BASE}/{resource['id']}",
        json={
            "interfaces": [{"op": "create", "name": "eth0"}],
            "version": 1,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "INTERFACE_NAME_TAKEN"


def test_interface_name_swap_in_single_patch(client, add_user, login_as) -> None:
    """F002-R-06：同一 PATCH 内互换两个接口名（终态合法）可保存。

    逐条 UPDATE 的中间态会瞬时重名，依赖 deferrable 唯一约束在提交时统一判定。
    """
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C18")
    resource = _make_resource(
        client, c1, name="swap", interfaces=[{"name": "eth0"}, {"name": "eth1"}]
    ).json()
    rid = resource["id"]
    by_name = {i["name"]: i for i in resource["interfaces"]}
    eth0_id = by_name["eth0"]["id"]
    eth1_id = by_name["eth1"]["id"]

    swapped = client.patch(
        f"{BASE}/{rid}",
        json={
            "interfaces": [
                {"op": "update", "id": eth0_id, "name": "eth1"},
                {"op": "update", "id": eth1_id, "name": "eth0"},
            ],
            "version": 1,
        },
    )
    assert swapped.status_code == 200, swapped.text
    body = swapped.json()
    assert body["version"] == 2
    assert {i["id"]: i["name"] for i in body["interfaces"]} == {
        eth0_id: "eth1",
        eth1_id: "eth0",
    }

    # 落库终态正确。
    detail = client.get(f"{BASE}/{rid}").json()
    assert {i["id"]: i["name"] for i in detail["interfaces"]} == {
        eth0_id: "eth1",
        eth1_id: "eth0",
    }


def test_interface_name_swap_terminal_conflict(client, add_user, login_as) -> None:
    """F002-R-06：终态冲突（eth0→eth1 而 eth1 不变）仍返回 409 且无残留。"""
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C19")
    resource = _make_resource(
        client,
        c1,
        name="swap-bad",
        interfaces=[{"name": "eth0"}, {"name": "eth1"}],
    ).json()
    rid = resource["id"]
    by_name = {i["name"]: i for i in resource["interfaces"]}

    conflict = client.patch(
        f"{BASE}/{rid}",
        json={
            "interfaces": [
                {"op": "update", "id": by_name["eth0"]["id"], "name": "eth1"}
            ],
            "version": 1,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "INTERFACE_NAME_TAKEN"

    # 整单回滚：名称与版本不变。
    detail = client.get(f"{BASE}/{rid}").json()
    assert detail["version"] == 1
    assert {i["name"] for i in detail["interfaces"]} == {"eth0", "eth1"}


def test_resource_name_conflict_fallback_includes_existing(
    client, add_user, login_as, monkeypatch
) -> None:
    """F002-R-07：并发/兜底命中 uq_resources_cluster_name 时带扩展成员。

    模拟前置查重与插入之间的并发窗口（前置查重未命中），由 DB 唯一约束兜底
    触发 23505，验证 ``existing_resource_id``/``existing_resource_type`` 回填。
    """
    import app.resources.router as resources_router

    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C20")
    existing = _make_resource(client, c1, name="fallback").json()

    monkeypatch.setattr(
        resources_router, "find_by_cluster_name", lambda *a, **k: None
    )

    dup = _make_resource(client, c1, name="fallback")
    assert dup.status_code == 409, dup.text
    body = dup.json()
    assert body["code"] == "RESOURCE_NAME_EXISTS"
    assert body["existing_resource_id"] == existing["id"]
    assert body["existing_resource_type"] == "bare_metal"


# --- 网段校验 ---------------------------------------------------------------


def test_segment_validation(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C8")
    c2 = _make_cluster(client, "C9", name="Beta")
    other_seg = _make_segment(client, c2, name="other", cidr="10.0.0.0/24").json()

    missing = _make_resource(
        client, c1, name="m1", interfaces=[{"name": "eth0", "segment_id": 999999}]
    )
    assert missing.status_code == 422
    assert missing.json()["errors"][0]["code"] == "INTERFACE_SEGMENT_INVALID"
    assert missing.json()["errors"][0]["field"] == "interfaces[0].segment_id"

    mismatch = _make_resource(
        client,
        c1,
        name="m2",
        interfaces=[{"name": "eth0", "segment_id": other_seg["id"]}],
    )
    assert mismatch.status_code == 422
    assert (
        mismatch.json()["errors"][0]["code"] == "INTERFACE_SEGMENT_CLUSTER_MISMATCH"
    )


# --- 整单原子 ---------------------------------------------------------------


def test_atomic_no_residue(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C10")

    failed = _make_resource(
        client,
        c1,
        name="atomic1",
        interfaces=[
            {"name": "eth0"},
            {"name": "eth1", "segment_id": 999999},
        ],
    )
    assert failed.status_code == 422
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Resource)
                .where(Resource.name == "atomic1")
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(NetworkInterface)
                .where(NetworkInterface.name.in_(["eth0", "eth1"]))
            )
            == 0
        )

    # PATCH 整单原子：第二张网卡失败 → 第一张与资源变更均不生效。
    resource = _make_resource(
        client, c1, name="atomic2", interfaces=[{"name": "eth0"}]
    ).json()
    patch_failed = client.patch(
        f"{BASE}/{resource['id']}",
        json={
            "name": "atomic2-renamed",
            "interfaces": [
                {"op": "create", "name": "ib1"},
                {"op": "create", "name": "ib2", "segment_id": 999999},
            ],
            "version": 1,
        },
    )
    assert patch_failed.status_code == 422
    with SessionLocal() as db:
        row = db.get(Resource, resource["id"])
        assert row is not None
        assert row.name == "atomic2"
        assert row.version == 1
        names = set(
            db.scalars(
                select(NetworkInterface.name).where(
                    NetworkInterface.resource_id == resource["id"]
                )
            ).all()
        )
        assert names == {"eth0"}


# --- 删除前置 / 二次确认 / 乐观锁 -------------------------------------------


def test_delete_preconditions_and_confirmation(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C11")
    resource = _make_resource(
        client, c1, name="DelMe", interfaces=[{"name": "eth0"}]
    ).json()
    rid = resource["id"]
    iface_id = resource["interfaces"][0]["id"]

    blocked = client.delete(
        f"{BASE}/{rid}", params={"confirm": "DelMe", "version": 1}
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "RESOURCE_HAS_INTERFACES"

    # 逐项删除网卡。
    removed = client.patch(
        f"{BASE}/{rid}",
        json={"interfaces": [{"op": "delete", "id": iface_id}], "version": 1},
    )
    assert removed.status_code == 200

    mismatch = client.delete(
        f"{BASE}/{rid}", params={"confirm": "delme", "version": 2}
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "DELETE_CONFIRMATION_MISMATCH"
    assert client.get(f"{BASE}/{rid}").status_code == 200

    stale = client.delete(
        f"{BASE}/{rid}", params={"confirm": "DelMe", "version": 1}
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"

    deleted = client.delete(
        f"{BASE}/{rid}", params={"confirm": "  DelMe  ", "version": 2}
    )
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"{BASE}/{rid}").status_code == 404

    # 删除后名称可复用。
    assert _make_resource(client, c1, name="DelMe").status_code == 201


def test_optimistic_lock_patch(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C12")
    resource = _make_resource(client, c1, name="Locked").json()
    rid = resource["id"]

    ok = client.patch(f"{BASE}/{rid}", json={"name": "Locked2", "version": 1})
    assert ok.status_code == 200
    assert ok.json()["version"] == 2

    stale = client.patch(f"{BASE}/{rid}", json={"name": "Locked3", "version": 1})
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"


def test_status_refresh_bq_aa(client, add_user, login_as) -> None:
    admin_id = _auth(client, add_user, login_as, "root", "admin")
    maint_id = add_user("m1", PASSWORD, "maintainer")
    c1 = _make_cluster(client, "C13")
    resource = _make_resource(client, c1, name="status", status="IDLE").json()
    rid = resource["id"]
    assert resource["status_updated_by"] == admin_id

    maint = TestClient(app)
    assert maint.post(
        "/api/v1/auth/login", json={"username": "m1", "password": PASSWORD}
    ).status_code == 200

    # 非状态编辑：不刷新 status_updated_by/at。
    before = resource["status_updated_at"]
    renamed = maint.patch(f"{BASE}/{rid}", json={"name": "status2", "version": 1})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["status_updated_by"] == admin_id
    assert renamed.json()["status_updated_at"] == before
    assert renamed.json()["status_updated_by_username"] == "root"

    # 状态变更：刷新为操作者。
    changed = maint.patch(f"{BASE}/{rid}", json={"status": "DOWN", "version": 2})
    assert changed.status_code == 200, changed.text
    assert changed.json()["status_updated_by"] == maint_id
    assert changed.json()["status_updated_by_username"] == "m1"
    assert changed.json()["status_updated_at"] != before


# --- 权限 -------------------------------------------------------------------


def test_permissions(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C14")
    resource = _make_resource(client, c1, name="perm").json()
    rid = resource["id"]

    anon = TestClient(app)
    assert anon.get(f"{BASE}/{rid}").status_code == 401
    assert anon.post(BASE, json={}).status_code == 401
    assert anon.patch(f"{BASE}/{rid}", json={"version": 1}).status_code == 401
    assert anon.delete(
        f"{BASE}/{rid}", params={"confirm": "perm", "version": 1}
    ).status_code == 401

    viewer = TestClient(app)
    _auth(viewer, add_user, login_as, "v1", "viewer")
    assert viewer.get(f"{BASE}/{rid}").status_code == 200
    assert _make_resource(viewer, c1, name="vres").status_code == 403
    assert (
        viewer.patch(f"{BASE}/{rid}", json={"name": "x", "version": 1}).status_code
        == 403
    )
    assert (
        viewer.delete(
            f"{BASE}/{rid}", params={"confirm": "perm", "version": 1}
        ).status_code
        == 403
    )

    maint = TestClient(app)
    _auth(maint, add_user, login_as, "m1", "maintainer")
    assert _make_resource(maint, c1, name="mres").status_code == 201
    assert (
        maint.patch(f"{BASE}/{rid}", json={"name": "perm2", "version": 1}).status_code
        == 200
    )


# --- 审计与资源历史 ---------------------------------------------------------


def test_audit_and_history(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C15")
    resource = _make_resource(
        client, c1, name="AuditRes", interfaces=[{"name": "eth0"}]
    ).json()
    rid = resource["id"]
    iface_id = resource["interfaces"][0]["id"]

    with SessionLocal() as db:
        create_audit = db.scalar(
            select(AuditLog).where(
                AuditLog.target_type == "resource",
                AuditLog.target_id == str(rid),
                AuditLog.action == "resource.create",
            )
        )
        assert create_audit is not None
        assert create_audit.target_key_snapshot == "AuditRes"

    # update：审计 + 历史，change 含 interfaces 增删。
    edited = client.patch(
        f"{BASE}/{rid}",
        json={
            "interfaces": [
                {"op": "create", "name": "ib1"},
                {"op": "delete", "id": iface_id},
            ],
            "version": 1,
        },
    )
    assert edited.status_code == 200, edited.text

    with SessionLocal() as db:
        update_audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "resource.update",
                AuditLog.target_id == str(rid),
            )
        )
        assert update_audit is not None
        assert update_audit.target_type == "resource"

        history = db.scalar(
            select(ResourceHistory).where(
                ResourceHistory.action == "update",
                ResourceHistory.target_type == "resource",
                ResourceHistory.target_id == str(rid),
            )
        )
        assert history is not None
        assert history.target_key_snapshot == "AuditRes"
        assert history.change["interfaces"]["created"] == [
            {"name": "ib1", "segment_id": None, "ips": []}
        ]
        assert history.change["interfaces"]["deleted"] == [
            {"id": iface_id, "name": "eth0", "ips": []}
        ]

    # 删除前先删网卡，再真实删除；历史保留。
    ib1_id = edited.json()["interfaces"][0]["id"]
    assert (
        client.patch(
            f"{BASE}/{rid}",
            json={"interfaces": [{"op": "delete", "id": ib1_id}], "version": 2},
        ).status_code
        == 200
    )
    deleted = client.delete(
        f"{BASE}/{rid}", params={"confirm": "AuditRes", "version": 3}
    )
    assert deleted.status_code == 204, deleted.text

    with SessionLocal() as db:
        assert db.get(Resource, rid) is None
        delete_history = db.scalar(
            select(ResourceHistory).where(
                ResourceHistory.action == "delete",
                ResourceHistory.target_type == "resource",
                ResourceHistory.target_id == str(rid),
            )
        )
        assert delete_history is not None
        delete_audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "resource.delete",
                AuditLog.target_id == str(rid),
            )
        )
        assert delete_audit is not None


# --- 删除保护行为侧 ---------------------------------------------------------


def test_segment_delete_protection(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C16")
    seg = _make_segment(client, c1, name="Protected", cidr="192.168.9.0/24").json()
    resource = _make_resource(
        client,
        c1,
        name="prot",
        interfaces=[{"name": "eth0", "segment_id": seg["id"]}],
    ).json()

    blocked = client.delete(
        f"{SEGMENTS}/{seg['id']}", params={"confirm": "Protected", "version": 1}
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "SEGMENT_HAS_INTERFACES"

    # 逐项删除网卡后，网段可删。
    client.patch(
        f"{BASE}/{resource['id']}",
        json={
            "interfaces": [
                {"op": "delete", "id": resource["interfaces"][0]["id"]}
            ],
            "version": 1,
        },
    )
    assert (
        client.delete(
            f"{SEGMENTS}/{seg['id']}", params={"confirm": "Protected", "version": 1}
        ).status_code
        == 204
    )


def test_cluster_delete_protection(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    c1 = _make_cluster(client, "C17", name="ProtectedCluster")
    _make_resource(client, c1, name="incluster")

    blocked = client.delete(
        f"/api/v1/clusters/{c1}",
        params={"confirm": "ProtectedCluster", "version": 1},
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "CLUSTER_HAS_ASSOCIATIONS"