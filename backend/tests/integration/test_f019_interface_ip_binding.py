"""F019 接口侧选择并绑定 IP — 独立集成测试（Tester，TEST 模式）。

验证 `docs/features/F019/product.md` AC1–AC7、`requirements-v3.md` revision 6
§13.4（T54–T58）与 `architecture.md` DR-332–DR-345。F019 是纯前端编排，本模块
在**真实 PostgreSQL** 上独立验证被复用的 F010 `GET /api/v1/ip-addresses` 与
`PATCH /api/v1/ip-addresses/{id}` 的可观察服务端语义（候选过滤、逐条绑定与
Audit、部分成功、并发 409、权限、软删、只读无副作用、不回归）。前端机制级
（跨页多选、串行不重试、汇总、门控）由 `scripts/smoke-client.mjs` IP-F1–F8
独立覆盖，不在此重复。

依赖真实 PostgreSQL（`TEST_DATABASE_URL`，DB-D10 guard）。helper 复用
`integration.test_ip_addresses`（_cluster/_network/_pool/_resource/_interface/
_ip/_allocate/_auto/_operator）与 `conftest` 的 `role_client_factory`、
`auth_session_factory`、`auth_app`。
"""

from __future__ import annotations

import threading
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core.errors import VersionConflict
from app.models.audit_log import AuditLog
from app.services import ip_address as ip_address_service
from app.services import ip_address_reference
from integration.test_ip_addresses import (  # noqa: F401  (reused helpers)
    _allocate,
    _auto,
    _cluster,
    _interface,
    _ip,
    _network,
    _operator,
    _pool,
    _resource,
    role_client_factory,
)

# --- F019-local helpers ------------------------------------------------------


def _bind(client, ip_id: str, version: int, interface_id: str | None):
    """PATCH {version, interface}（F010 §6.5，恰前端提交载荷，exclude_unset）。"""
    body = {"version": version, "interface": interface_id}
    return client.patch(f"/api/v1/ip-addresses/{ip_id}", json=body)


def _candidates(client, cluster_id: str, **params):
    """F019 候选口径查询（DR-332）：cluster_id + bound=false + deleted=exclude。"""
    query = {
        "cluster_id": cluster_id,
        "bound": "false",
        "deleted": "exclude",
        **params,
    }
    return client.get("/api/v1/ip-addresses", params=query)


def _ip_update_audits(session, ip_id: str) -> int:
    return session.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.object_type == "ip_address",
            AuditLog.object_id == uuid.UUID(ip_id),
            AuditLog.action == "UPDATE",
        )
    ).scalar_one()


def _ip_address_audits(session) -> int:
    return session.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.object_type == "ip_address")
    ).scalar_one()


def _raw_ip_row(session, ip_id: str):
    return session.execute(
        text(
            "SELECT interface_id, version, address, network_id, cluster_id "
            "FROM ip_addresses WHERE id = :id"
        ),
        {"id": uuid.UUID(ip_id)},
    ).one()


# --- T01/AC1: 候选过滤（同 Cluster / 未绑定 / 未删） --------------------------


def test_candidate_filtering_same_cluster_unbound_undeleted(role_client_factory):
    """F019-T01/AC1/T54/B14：候选仅同 Cluster、未绑定、未删。

    跨 Cluster / 已绑定 / 已删 IP 不出现；服务端过滤为唯一权威（前端不复制规则）。
    """
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1", name="C1")
    c2 = _cluster(admin, code="C2", name="C2")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    n2 = _network(admin, c2["id"], name="n2", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")

    unbound = _ip(admin, n1["id"], "10.0.0.10")
    bound = _ip(admin, n1["id"], "10.0.0.11")
    assert _bind(admin, bound["id"], 1, if1["id"]).status_code == 200
    released = _ip(admin, n1["id"], "10.0.0.12")
    assert admin.delete(
        f"/api/v1/ip-addresses/{released['id']}", params={"version": 1}
    ).status_code == 204
    foreign = _ip(admin, n2["id"], "10.0.0.13")

    resp = _candidates(admin, c1["id"])
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert unbound["id"] in ids
    assert bound["id"] not in ids  # 已绑定其它接口
    assert released["id"] not in ids  # 已删
    assert foreign["id"] not in ids  # 跨 Cluster
    assert resp.json()["total"] == 1

    # 跨 Cluster 的候选查询只返回该 Cluster 的未绑定未删 IP
    other = _candidates(admin, c2["id"])
    assert {item["id"] for item in other.json()["items"]} == {foreign["id"]}

    # q 搜索作用于地址子串（服务端过滤，不改候选口径）；无匹配为空集
    hit = _candidates(admin, c1["id"], q=".10")
    assert {item["id"] for item in hit.json()["items"]} == {unbound["id"]}
    miss = _candidates(admin, c1["id"], q=".99")
    assert miss.json()["total"] == 0 and miss.json()["items"] == []


def test_candidate_empty_state_and_pagination_boundary(role_client_factory):
    """F019-T04/AC4/T56：空候选 total=0；分页 total>items 不静默截断；越界 422。"""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")

    empty = _candidates(admin, c1["id"])
    assert empty.status_code == 200
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []

    # 3 个候选，page_size=2 → total=3、items=2（显式截断，客户端据 total>items 提示）
    for octet in (10, 11, 12):
        _ip(admin, n1["id"], f"10.0.0.{octet}")
    page = _candidates(admin, c1["id"], page=1, page_size=2, sort="address", order="asc")
    body = page.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert [i["address"] for i in body["items"]] == ["10.0.0.10", "10.0.0.11"]
    assert _candidates(admin, c1["id"], page_size=101).status_code == 422


# --- T02/AC2: 多选逐条绑定关系一致 + 各 1 行 UPDATE Audit --------------------


def test_multi_bind_relationship_and_audit(
    role_client_factory, auth_session_factory
):
    """F019-T02/AC2/T55/DR-339：逐条绑定关系一致；各恰 1 行 ip_address UPDATE Audit。"""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")

    ip_a = _ip(admin, n1["id"], "10.0.0.10")
    ip_b = _ip(admin, n1["id"], "10.0.0.11")
    ip_c = _ip(admin, n1["id"], "10.0.0.12")

    # 逐条串行 PATCH（提交顺序与 address 无关，服务端逐条独立处理）
    for ip in (ip_a, ip_b, ip_c):
        resp = _bind(admin, ip["id"], 1, if1["id"])
        assert resp.status_code == 200, resp.text
        assert resp.json()["ip_address"]["interface"]["id"] == if1["id"]
        assert resp.json()["ip_address"]["version"] == 2

    # 关系与提交一致：详情与 interface_id 过滤查询都能核对
    bound = admin.get("/api/v1/ip-addresses", params={"interface_id": if1["id"]})
    assert bound.status_code == 200
    got = {item["id"] for item in bound.json()["items"]}
    assert got == {ip_a["id"], ip_b["id"], ip_c["id"]}

    # 各恰 1 行 UPDATE Audit（绑定只产生 UPDATE，不产生 CREATE/DELETE）
    with auth_session_factory() as session:
        for ip in (ip_a, ip_b, ip_c):
            assert _ip_update_audits(session, ip["id"]) == 1
        actions = session.execute(
            select(AuditLog.action).where(AuditLog.object_type == "ip_address")
        ).scalars().all()
    assert actions.count("UPDATE") == 3
    assert actions.count("CREATE") == 3


# --- T03/AC3: 部分成功（409 + 422 + 404 + 成功混合，逐条结果） ---------------


def test_partial_success_mixed_statuses(role_client_factory):
    """F019-T03/AC3/T55：混合 409/422/404/成功，逐条独立结果，成功项不阻断其余。"""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    c2 = _cluster(admin, code="C2")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    n2 = _network(admin, c2["id"], name="n2", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")
    foreign_r = _resource(admin, c2["id"], hostname="h2")
    foreign_if = _interface(admin, foreign_r["id"], name="eth0")

    ok_ip = _ip(admin, n1["id"], "10.0.0.10")
    stale_ip = _ip(admin, n1["id"], "10.0.0.11")
    gone_ip = _ip(admin, n1["id"], "10.0.0.12")
    admin.delete(f"/api/v1/ip-addresses/{gone_ip['id']}", params={"version": 1})
    # 软删接口（合法存在但不可绑定）
    soft_iface = _interface(admin, r1["id"], name="eth9")
    assert admin.delete(
        f"/api/v1/interfaces/{soft_iface['id']}", params={"version": 1}
    ).status_code == 204

    # 逐条模拟前端提交（每项恰一次），混合结果：
    # 成功 / 409 VERSION_CONFLICT（stale version）/ 404（已删 IP）/ 422（软删接口）
    r_ok = _bind(admin, ok_ip["id"], 1, if1["id"])
    r_stale = _bind(admin, stale_ip["id"], 99, if1["id"])
    r_gone = _bind(admin, gone_ip["id"], 1, if1["id"])
    r_soft = _bind(admin, stale_ip["id"], 1, soft_iface["id"])

    assert r_ok.status_code == 200, r_ok.text
    assert r_stale.status_code == 409 and r_stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert r_gone.status_code == 404
    assert r_soft.status_code == 422
    assert r_soft.json()["error"]["details"]["fields"][0]["field"] == "interface"

    # 部分成功不整体成功：成功项已绑定，失败项保持未绑定
    assert admin.get(f"/api/v1/ip-addresses/{ok_ip['id']}").json()["ip_address"][
        "interface"
    ]["id"] == if1["id"]
    assert admin.get(f"/api/v1/ip-addresses/{stale_ip['id']}").json()["ip_address"][
        "interface"
    ] is None
    # 跨 Cluster 接口同样是 422 field=interface
    cross = _bind(admin, stale_ip["id"], 1, foreign_if["id"])
    assert cross.status_code == 422
    assert cross.json()["error"]["details"]["fields"][0]["field"] == "interface"


# --- T05/T11/AC5: 权限 401 先于 403；绑定不改 address/network/占用 -----------


def test_permissions_401_before_403_and_viewer_403(
    role_client_factory, auth_app
):
    """F019-T05/T11/AC5/T57：未认证 401 先于权限；VIEWER 候选可读、绑定 403。"""
    admin, _, _ = role_client_factory("ADMIN")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")
    ip = _ip(admin, n1["id"], "10.0.0.10")

    # 未认证：PATCH 绑定 → 401（先于 403）；候选 GET → 401
    with TestClient(auth_app) as anon:
        anon_patch = anon.patch(
            f"/api/v1/ip-addresses/{ip['id']}",
            json={"version": 1, "interface": if1["id"]},
        )
        assert anon_patch.status_code == 401, anon_patch.text
        assert anon_patch.json()["error"]["code"] == "AUTH_REQUIRED"
        assert anon.get("/api/v1/ip-addresses").status_code == 401

    # VIEWER：候选 READ 可读；绑定 WRITE → 403（服务端权威，隐藏入口不替代鉴权）
    assert _candidates(viewer, c1["id"]).status_code == 200
    forbidden = _bind(viewer, ip["id"], 1, if1["id"])
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["details"]["reason"] == "permission"


def test_binding_preserves_address_network_and_occupancy(
    role_client_factory, auth_session_factory
):
    """F019-T05/AC5/T57：绑定只改 interface 关系；address/network/占用不变。"""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")
    ip = _ip(admin, n1["id"], "10.0.0.10")

    before = admin.get(f"/api/v1/ip-addresses/{ip['id']}").json()["ip_address"]
    cap_before = admin.get(f"/api/v1/networks/{n1['id']}/capacity").json()

    assert _bind(admin, ip["id"], 1, if1["id"]).status_code == 200

    after = admin.get(f"/api/v1/ip-addresses/{ip['id']}").json()["ip_address"]
    assert after["address"] == before["address"]
    assert after["network"] == before["network"]
    assert after["cluster"] == before["cluster"]
    # 占用不变（绑定前后该 Network 的 occupied 一致；地址仍被占用不可再分配）
    cap_after = admin.get(f"/api/v1/networks/{n1['id']}/capacity").json()
    assert cap_after["network_capacity"]["occupied"] == cap_before["network_capacity"]["occupied"]
    assert _allocate(admin, n1["id"], "10.0.0.10").status_code == 409


def test_binding_does_not_trigger_reference_rejection(
    role_client_factory, monkeypatch
):
    """F019-T05/AC5/T57：绑定未被引用的候选不触发 Endpoint 引用拒绝；引用检查器仍
    对已引用 IP 的解绑生效（回归 F010 §16/§21 语义）。

    说明：F010 `update_ip_address` 在任何 interface 变更（含绑定）时调用引用检查器；
    本测试以「仅对已引用 IP 返回引用」的检查器证明：对无引用的候选，绑定照常成功
    （不误触发 reference_exists）；对确有引用的 IP，解绑仍被 409 阻止。
    """
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")

    referenced = _ip(admin, n1["id"], "10.0.0.10")
    fresh = _ip(admin, n1["id"], "10.0.0.11")
    assert _bind(admin, referenced["id"], 1, if1["id"]).status_code == 200

    refs = [{"object_type": "service_endpoint", "object_id": str(uuid.uuid4()), "label": "ssh:22"}]
    monkeypatch.setattr(
        ip_address_reference,
        "_CHECKERS",
        [
            lambda db, ip_id: list(refs)
            if str(ip_id) == referenced["id"]
            else []
        ],
    )

    # 解绑已引用 IP → 409 reference_exists（引用检查器生效）
    unbind = _bind(admin, referenced["id"], 2, None)
    assert unbind.status_code == 409, unbind.text
    assert unbind.json()["error"]["details"]["reason"] == "reference_exists"

    # 绑定未被引用的候选 → 200（绑定不触发引用拒绝，AC5）
    ok = _bind(admin, fresh["id"], 1, if1["id"])
    assert ok.status_code == 200, ok.text
    assert ok.json()["ip_address"]["interface"]["id"] == if1["id"]


# --- T06/T08/AC6: 并发同 version 恰一成功一 409，无重复绑定 -------------------


def test_concurrent_binding_same_version_one_wins(
    auth_session_factory, role_client_factory
):
    """F019-T06/T08/AC6/T58/DR-342：Barrier + 两独立会话同 version 绑定同一候选，
    恰一成功一 VersionConflict；raw SQL 核对唯一绑定与 version 递增（无重复绑定）。"""
    admin, user, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    iface = _interface(admin, r1["id"], name="eth0")
    ip = _ip(admin, n1["id"], "10.0.0.10")
    operator = _operator(user)
    ip_id = uuid.UUID(ip["id"])
    iface_id = uuid.UUID(iface["id"])

    barrier = threading.Barrier(2)
    results: list[object] = []

    def patch() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            ip_address_service.update_ip_address(
                session,
                operator,
                ip_id,
                expected_version=1,
                changes={"interface": iface_id},
            )
            results.append("bound")
        except VersionConflict as exc:
            session.rollback()
            results.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=patch) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    winners = [r for r in results if isinstance(r, str)]
    conflicts = [r for r in results if isinstance(r, VersionConflict)]
    assert len(winners) == 1, results
    assert len(conflicts) == 1, results

    with auth_session_factory() as session:
        row = _raw_ip_row(session, ip["id"])
    assert str(row[0]) == iface["id"]  # 唯一绑定
    assert row[1] == 2  # version 恰递增一次（无丢失更新）

    listed = admin.get("/api/v1/ip-addresses", params={"interface_id": iface["id"]})
    assert [i["id"] for i in listed.json()["items"]] == [ip["id"]]


# --- T09/B10-B12: 已删 IP 404、软删接口 422、跨 Cluster 422 --------------------


def test_deleted_ip_soft_deleted_interface_cross_cluster(role_client_factory):
    """F019-T09/B10-B12/DR-336/DR-338：已删 IP 404；软删接口 422；跨 Cluster 422。"""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    c2 = _cluster(admin, code="C2")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    n2 = _network(admin, c2["id"], name="n2", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")
    soft_iface = _interface(admin, r1["id"], name="eth1")
    foreign_r = _resource(admin, c2["id"], hostname="h2")
    foreign_if = _interface(admin, foreign_r["id"], name="eth0")

    gone = _ip(admin, n1["id"], "10.0.0.10")
    assert admin.delete(
        f"/api/v1/ip-addresses/{gone['id']}", params={"version": 1}
    ).status_code == 204
    assert _bind(admin, gone["id"], 2, if1["id"]).status_code == 404

    assert admin.delete(
        f"/api/v1/interfaces/{soft_iface['id']}", params={"version": 1}
    ).status_code == 204
    live = _ip(admin, n1["id"], "10.0.0.11")
    soft = _bind(admin, live["id"], 1, soft_iface["id"])
    assert soft.status_code == 422
    assert soft.json()["error"]["details"]["fields"][0]["field"] == "interface"

    cross = _bind(admin, live["id"], 1, foreign_if["id"])
    assert cross.status_code == 422
    assert cross.json()["error"]["details"]["fields"][0]["field"] == "interface"


# --- T07/AC7: 创建失败无绑定；创建成功绑定失败保留 Interface ------------------


def test_create_failure_no_binding_and_bind_failure_keeps_interface(
    role_client_factory
):
    """F019-T07/AC7/§13.4/DR-341：接口创建失败不产生绑定；创建成功而绑定失败时
    Interface 保留、逐条提示失败（不级联删除、不静默成功）。"""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if0 = _interface(admin, r1["id"], name="eth0")  # 占位，制造创建失败
    ip = _ip(admin, n1["id"], "10.0.0.10")

    # 创建失败（同资源同名 → 409 unique_conflict）：不产生任何绑定
    dup = admin.post("/api/v1/interfaces", json={"resource": r1["id"], "name": "eth0"})
    assert dup.status_code == 409
    assert admin.get(f"/api/v1/ip-addresses/{ip['id']}").json()["ip_address"][
        "interface"
    ] is None

    # 创建成功
    if1 = _interface(admin, r1["id"], name="eth1")
    # 绑定失败（stale version → 409 VERSION_CONFLICT）
    failed = _bind(admin, ip["id"], 99, if1["id"])
    assert failed.status_code == 409

    # Interface 保留（未删除、version 未变），IP 仍未绑定
    kept = admin.get(f"/api/v1/interfaces/{if1['id']}")
    assert kept.status_code == 200
    assert kept.json()["interface"]["deleted_at"] is None
    assert admin.get(f"/api/v1/ip-addresses/{ip['id']}").json()["ip_address"][
        "interface"
    ] is None

    # 用正确 version 重试绑定 → 成功（保留的 Interface 可正常绑定）
    assert _bind(admin, ip["id"], 1, if1["id"]).status_code == 200


# --- T12/DR-339: 只读无副作用 ------------------------------------------------


def test_read_only_no_side_effects(role_client_factory, auth_session_factory):
    """F019-T12/DR-339：候选 / 已绑定列表查询只读，无 Audit、无 version 变更。"""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")
    ip = _ip(admin, n1["id"], "10.0.0.10")
    assert _bind(admin, ip["id"], 1, if1["id"]).status_code == 200

    with auth_session_factory() as session:
        audits_before = _ip_address_audits(session)
    version_before = admin.get(f"/api/v1/ip-addresses/{ip['id']}").json()["ip_address"][
        "version"
    ]

    _candidates(admin, c1["id"])
    _candidates(admin, c1["id"], q=".10", page=1, page_size=50)
    admin.get("/api/v1/ip-addresses", params={"interface_id": if1["id"], "deleted": "exclude"})

    with auth_session_factory() as session:
        assert _ip_address_audits(session) == audits_before  # 只读不产生 Audit
        row = _raw_ip_row(session, ip["id"])
    assert row[1] == version_before  # version 不变


# --- T13/DR-340: 无新端点 / 参数 / 契约 --------------------------------------


def test_no_new_endpoint_params_or_contract(role_client_factory):
    """F019-T13/DR-340：仅复用既有 GET/PATCH；无新端点；未列参数忽略；载荷恰
    {version, interface}。"""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")
    ip = _ip(admin, n1["id"], "10.0.0.10")

    # 不存在新的接口侧 IP 端点
    assert admin.get(f"/api/v1/interfaces/{if1['id']}/ip-addresses").status_code == 404
    assert admin.get(f"/api/v1/interfaces/{if1['id']}/bind-ip").status_code == 404

    # 未列参数被忽略（Contract §4）：候选查询仍 200
    assert _candidates(admin, c1["id"], unknown_param="x").status_code == 200

    # 绑定载荷恰 {version, interface}（exclude_unset）成功
    ok = admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": 1, "interface": if1["id"]},
    )
    assert ok.status_code == 200
    assert ok.json()["ip_address"]["interface"]["id"] == if1["id"]


# --- 不回归：IP 侧分配 / 解绑 / 转移 / 释放 / 容量；F007 接口 ------------------


def test_no_regression_ip_side_flows(role_client_factory):
    """不回归（真 PG）：手动/自动分配、解绑、转移、释放、容量口径在 F019 后不变。"""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24", auto_allocate=True)
    pool = _pool(admin, n1["id"], name="a", start="10.0.0.10", end="10.0.0.20",
                 allocation_mode="AUTO")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")
    if2 = _interface(admin, r1["id"], name="eth1")

    manual = _ip(admin, n1["id"], "10.0.0.30")
    auto = _auto(admin, n1["id"], pool["id"])
    assert auto.status_code == 201, auto.text
    auto_ip = auto.json()["ip_address"]

    # 绑定 → 转移 → 解绑（IP 侧关系编辑）
    assert _bind(admin, manual["id"], 1, if1["id"]).status_code == 200
    moved = _bind(admin, manual["id"], 2, if2["id"])
    assert moved.status_code == 200
    assert moved.json()["ip_address"]["interface"]["id"] == if2["id"]
    unbound = _bind(admin, manual["id"], 3, None)
    assert unbound.status_code == 200
    assert unbound.json()["ip_address"]["interface"] is None

    # 释放需 RELEASE_IP（ADMIN 可）；释放后可复用
    assert admin.delete(
        f"/api/v1/ip-addresses/{auto_ip['id']}", params={"version": 1}
    ).status_code == 204
    assert _allocate(admin, n1["id"], auto_ip["address"]).status_code == 201

    # 容量口径：绑定不改变占用（manual 仍占用）
    cap = admin.get(f"/api/v1/networks/{n1['id']}/capacity").json()
    assert cap["network_capacity"]["occupied"] >= 1


def test_no_regression_interface_reference_and_list(role_client_factory):
    """不回归（F007）：接口列表/创建正常；绑定 IP 后的接口软删仍被引用阻止。"""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(admin, c1["id"], hostname="h1")
    if1 = _interface(admin, r1["id"], name="eth0")
    ip = _ip(admin, n1["id"], "10.0.0.10")

    listed = admin.get("/api/v1/interfaces", params={"resource_id": r1["id"]})
    assert listed.status_code == 200
    assert {i["id"] for i in listed.json()["items"]} == {if1["id"]}

    assert _bind(admin, ip["id"], 1, if1["id"]).status_code == 200
    blocked = admin.delete(f"/api/v1/interfaces/{if1['id']}", params={"version": 1})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["reason"] == "reference_exists"
    assert blocked.json()["error"]["details"]["references"][0]["object_type"] == "ip_address"