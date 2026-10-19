"""F022 Resource 详情页 IP Addresses 区域 — 独立集成测试（Tester，TEST 模式）。

验证 `docs/features/F022/product.md` A1–A7、`requirements-v3.md` revision 7
§18/§32/§13/§14/§12/§21/§23 与 `architecture.md` DR-382–DR-400。

F022 是**纯前端只读聚合**（Backend / Database / Contract NOT_REQUIRED）：前端按
DR-382 逐接口查询——先 `GET /api/v1/interfaces?resource_id&deleted=exclude&
sort=name&order=asc` 取未删接口，再对每个未删接口 `GET /api/v1/ip-addresses?
interface_id&deleted=exclude&sort=address&order=asc` 取已绑定未删 IP，合并排序。

本模块在**真实 PostgreSQL**上独立验证被复用的 F007 §4/§6.1 与 F010 §3/§4/§5/
§6.1 的可观察服务端语义：接口/IP 软删口径、逐接口绑定关系、可见集合、排序、
只读无副作用、角色一致、无新端点。前端机制级（查询串、合并、比较器、边界、
部分失败、标签）由 `scripts/smoke-client.mjs` M1–M7 独立覆盖，不在此重复。

依赖真实 PostgreSQL（`TEST_DATABASE_URL`，DB-D10 guard）。helper 复用
`integration.test_ip_addresses`（_cluster/_network/_resource/_interface/_ip/
_allocate/role_client_factory）与 `conftest` 的 `auth_session_factory`。
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text

from app.models.audit_log import AuditLog
from integration.test_ip_addresses import (  # noqa: F401  (reused helpers/fixtures)
    _allocate,
    _cluster,
    _interface,
    _ip,
    _network,
    _resource,
    role_client_factory,
)

# --- helpers -----------------------------------------------------------------


def _bind(client, ip_id: str, version: int, interface_id: str | None):
    """PATCH {version, interface}（F010 §6.5，恰前端提交载荷，exclude_unset）。"""
    return client.patch(
        f"/api/v1/ip-addresses/{ip_id}",
        json={"version": version, "interface": interface_id},
    )


def _list_resource_interfaces(client, resource_id: str, **params):
    """F022 接口查询口径（DR-382）：resource_id + deleted=exclude + sort=name。"""
    query = {
        "resource_id": resource_id,
        "deleted": "exclude",
        "sort": "name",
        "order": "asc",
        "page_size": 100,
        **params,
    }
    return client.get("/api/v1/interfaces", params=query)


def _list_interface_ips(client, interface_id: str, **params):
    """逐接口已绑定 IP 查询口径（DR-382/DR-388，复用 F019 buildInterfaceBoundIpsQuery）。"""
    query = {
        "interface_id": interface_id,
        "deleted": "exclude",
        "sort": "address",
        "order": "asc",
        "page": 1,
        "page_size": 100,
        **params,
    }
    return client.get("/api/v1/ip-addresses", params=query)


def _ip_sort_key(address: str) -> tuple[int, ...]:
    """IPv4 数值排序键（镜像前端 compareResourceIpAddressesAscending 语义）。"""
    return tuple(int(part) for part in address.split("."))


def _frontend_visible_rows(client, resource_id: str) -> list[dict[str, str]]:
    """模拟 F022 前端算法：未删接口 → 逐接口未删 IP → 合并按总序排序（DR-385）。"""
    resp = _list_resource_interfaces(client, resource_id)
    assert resp.status_code == 200, resp.text
    rows: list[dict[str, str]] = []
    for iface in resp.json()["items"]:
        data = _list_interface_ips(client, iface["id"])
        assert data.status_code == 200, data.text
        for ip in data.json()["items"]:
            rows.append(
                {"interface": iface["name"], "address": ip["address"], "id": ip["id"]}
            )
    # interface.name 码序 → IP 数值 ASC → id ASC（Python str 码序与 JS 对 ASCII 一致）
    rows.sort(key=lambda r: (r["interface"], _ip_sort_key(r["address"]), r["id"]))
    return rows


def _build_fixture(admin, session):
    """构建 P1 夹具（C1/R；I1/I2 未删、I3 软删；a1–a3→I1、a4→I2、a5 未绑定、
    a6 已删绑 I1、a7 绑软删 I3）。返回命名 ID 字典。

    a7 绑到软删 I3：接口带未删 IP 引用时服务端软删会被 409 阻止（F007 DR-80/82），
    故先用 API 绑定 a7→I3，再以 SQL 将 I3 置为软删，构造「绑定到已软删 Interface
    的 IP」这一读取侧防御场景（前端只查未删接口，天然不出现，DR-391）。
    """
    c1 = _cluster(admin, code="C1", name="C1")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    r = _resource(admin, c1["id"], hostname="h1")

    i1 = _interface(admin, r["id"], name="eth0")
    i2 = _interface(admin, r["id"], name="ib0")
    i3 = _interface(admin, r["id"], name="old0")

    # I1：a1/a2/a3（乱序地址，跨数值/字符串序差异：9 < 10 < 100）
    a1 = _ip(admin, n1["id"], "10.0.0.10", description="primary")
    a2 = _ip(admin, n1["id"], "10.0.0.9")
    a3 = _ip(admin, n1["id"], "10.0.0.100")
    for ip in (a1, a2, a3):
        resp = _bind(admin, ip["id"], 1, i1["id"])
        assert resp.status_code == 200, resp.text

    # I2：a4
    a4 = _ip(admin, n1["id"], "10.0.0.50")
    assert _bind(admin, a4["id"], 1, i2["id"]).status_code == 200

    # a5：未绑定（不应出现）
    a5 = _ip(admin, n1["id"], "10.0.0.200")

    # a6：绑定 I1 后软删（不应出现）
    a6 = _ip(admin, n1["id"], "10.0.0.77")
    bound6 = _bind(admin, a6["id"], 1, i1["id"])
    assert bound6.status_code == 200, bound6.text
    deleted = admin.delete(
        f"/api/v1/ip-addresses/{a6['id']}",
        params={"version": bound6.json()["ip_address"]["version"]},
    )
    assert deleted.status_code == 204, deleted.text

    # a7：绑定 I3 后（SQL）软删 I3（不应出现）
    a7 = _ip(admin, n1["id"], "10.0.0.88")
    assert _bind(admin, a7["id"], 1, i3["id"]).status_code == 200
    session.execute(
        text("UPDATE interfaces SET deleted_at = now() WHERE id = :id"),
        {"id": uuid.UUID(i3["id"])},
    )
    session.commit()

    return {
        "c1": c1,
        "n1": n1,
        "r": r,
        "i1": i1,
        "i2": i2,
        "i3": i3,
        "a1": a1,
        "a2": a2,
        "a3": a3,
        "a4": a4,
        "a5": a5,
        "a6": a6,
        "a7": a7,
    }


def _audit_count(session, object_type: str) -> int:
    return session.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.object_type == object_type)
    ).scalar_one()


def _raw_version(session, table: str, row_id: str) -> int:
    return session.execute(
        text(f"SELECT version FROM {table} WHERE id = :id"),  # noqa: S608 (fixed table names)
        {"id": uuid.UUID(row_id)},
    ).scalar_one()


# --- P1：夹具构造 ------------------------------------------------------------


def test_p01_fixture_construction(role_client_factory, auth_session_factory):
    """P1：夹具可构造——I3 软删（接口 exclude 后不可见），a6 软删，a7 绑软删 I3。"""
    admin, _, _ = role_client_factory("ADMIN")
    with auth_session_factory() as session:
        fx = _build_fixture(admin, session)

    # 未删接口 = I1/I2；I3 已被软删（deleted=only 可见）
    live = _list_resource_interfaces(admin, fx["r"]["id"]).json()
    assert {i["id"] for i in live["items"]} == {fx["i1"]["id"], fx["i2"]["id"]}
    only = _list_resource_interfaces(admin, fx["r"]["id"], deleted="only").json()
    assert {i["id"] for i in only["items"]} == {fx["i3"]["id"]}

    # a6 已软删（详情 deleted=true）；a7 仍绑 I3
    gone = admin.get(f"/api/v1/ip-addresses/{fx['a6']['id']}", params={"deleted": "true"})
    assert gone.status_code == 200
    assert gone.json()["ip_address"]["deleted_at"] is not None
    a7 = admin.get(f"/api/v1/ip-addresses/{fx['a7']['id']}").json()["ip_address"]
    assert a7["interface"]["id"] == fx["i3"]["id"]


# --- P2：接口列表 exclude 仅 I1/I2 -------------------------------------------


def test_p02_interface_list_deleted_exclude(role_client_factory, auth_session_factory):
    """P2/DR-382/DR-391/A4：接口查询 deleted=exclude 仅返回 I1/I2，软删 I3 不出现。

    服务端过滤为唯一权威；前端据该结果逐接口取 IP，故绑定到软删 I3 的 a7
    不会被查询。
    """
    admin, _, _ = role_client_factory("ADMIN")
    with auth_session_factory() as session:
        fx = _build_fixture(admin, session)

    resp = _list_resource_interfaces(admin, fx["r"]["id"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert [i["name"] for i in body["items"]] == ["eth0", "ib0"]  # sort=name asc
    ids = {i["id"] for i in body["items"]}
    assert ids == {fx["i1"]["id"], fx["i2"]["id"]}
    assert fx["i3"]["id"] not in ids


# --- P3：逐接口 IP 查询（I1→a1–a3、I2→a4；a6 不出现） ------------------------


def test_p03_per_interface_ip_queries(role_client_factory, auth_session_factory):
    """P3/DR-382/DR-388/A1/A4：I1 返回 a1–a3、I2 返回 a4（address 升序）；软删 a6 不出现。"""
    admin, _, _ = role_client_factory("ADMIN")
    with auth_session_factory() as session:
        fx = _build_fixture(admin, session)

    i1 = _list_interface_ips(admin, fx["i1"]["id"])
    assert i1.status_code == 200, i1.text
    i1_items = i1.json()["items"]
    # address 数值升序：a2(.9) < a1(.10) < a3(.100)（非字符串序）
    assert [ip["id"] for ip in i1_items] == [fx["a2"]["id"], fx["a1"]["id"], fx["a3"]["id"]]
    assert {ip["id"] for ip in i1_items} == {fx["a1"]["id"], fx["a2"]["id"], fx["a3"]["id"]}
    assert fx["a6"]["id"] not in {ip["id"] for ip in i1_items}  # 已删 IP 不出现
    # A1 字段最小集：network{name,cidr}；manual IP 的 ip_pool=null（前端映射「池外（手动）」）
    a1 = next(ip for ip in i1_items if ip["id"] == fx["a1"]["id"])
    assert a1["address"] == "10.0.0.10"
    assert a1["network"]["name"] == "n1" and a1["network"]["cidr"] == "10.0.0.0/24"
    assert a1["interface"]["name"] == "eth0"
    assert a1["ip_pool"] is None
    assert a1["description"] == "primary"
    assert "cluster" not in a1 or a1["cluster"] is not None  # cluster 只在响应可用，不进入列

    i2 = _list_interface_ips(admin, fx["i2"]["id"])
    assert i2.status_code == 200, i2.text
    assert [ip["id"] for ip in i2.json()["items"]] == [fx["a4"]["id"]]
    assert i2.json()["total"] == 1


# --- P4：合并可见集合 = {a1,a2,a3,a4} -----------------------------------------


def test_p04_merged_visible_set(role_client_factory, auth_session_factory):
    """P4/DR-384/DR-385：按前端算法合并后可见集合 = {a1,a2,a3,a4}。

    a5（未绑定）、a6（已删 IP）、a7（绑软删接口）均不出现。
    """
    admin, _, _ = role_client_factory("ADMIN")
    with auth_session_factory() as session:
        fx = _build_fixture(admin, session)

    rows = _frontend_visible_rows(admin, fx["r"]["id"])
    ids = {row["id"] for row in rows}
    assert ids == {fx["a1"]["id"], fx["a2"]["id"], fx["a3"]["id"], fx["a4"]["id"]}
    assert fx["a5"]["id"] not in ids  # 未绑定
    assert fx["a6"]["id"] not in ids  # 已删 IP
    assert fx["a7"]["id"] not in ids  # 绑软删 Interface


# --- P5：确定性全序排序 -------------------------------------------------------


def test_p05_deterministic_ordering(role_client_factory, auth_session_factory):
    """P5/DR-385/A2：interface.name ASC → IP 数值 ASC → id ASC。"""
    admin, _, _ = role_client_factory("ADMIN")
    with auth_session_factory() as session:
        fx = _build_fixture(admin, session)

    rows = _frontend_visible_rows(admin, fx["r"]["id"])
    got = [(row["interface"], row["address"]) for row in rows]
    assert got == [
        ("eth0", "10.0.0.9"),
        ("eth0", "10.0.0.10"),
        ("eth0", "10.0.0.100"),
        ("ib0", "10.0.0.50"),
    ]
    assert [row["id"] for row in rows] == [
        fx["a2"]["id"],
        fx["a1"]["id"],
        fx["a3"]["id"],
        fx["a4"]["id"],
    ]


# --- P6：只读无副作用（audit_logs / version 不变） ---------------------------


def test_p06_read_only_no_side_effects(role_client_factory, auth_session_factory):
    """P6/DR-390/§22/§23：接口/IP 查询只读，不产生 Audit，不改 IP/接口 version。"""
    admin, _, _ = role_client_factory("ADMIN")
    with auth_session_factory() as session:
        fx = _build_fixture(admin, session)

    with auth_session_factory() as session:
        ip_audits_before = _audit_count(session, "ip_address")
        iface_audits_before = _audit_count(session, "interface")
    with auth_session_factory() as session:
        ip_versions_before = {
            key: _raw_version(session, "ip_addresses", fx[key]["id"])
            for key in ("a1", "a2", "a3", "a4")
        }
        iface_versions_before = {
            key: _raw_version(session, "interfaces", fx[key]["id"])
            for key in ("i1", "i2", "i3")
        }

    # 执行 F022 全部读取路径
    _list_resource_interfaces(admin, fx["r"]["id"])
    _list_interface_ips(admin, fx["i1"]["id"])
    _list_interface_ips(admin, fx["i2"]["id"])
    _frontend_visible_rows(admin, fx["r"]["id"])

    with auth_session_factory() as session:
        assert _audit_count(session, "ip_address") == ip_audits_before
        assert _audit_count(session, "interface") == iface_audits_before
        ip_versions_after = {
            key: _raw_version(session, "ip_addresses", fx[key]["id"])
            for key in ("a1", "a2", "a3", "a4")
        }
        iface_versions_after = {
            key: _raw_version(session, "interfaces", fx[key]["id"])
            for key in ("i1", "i2", "i3")
        }
    assert ip_versions_after == ip_versions_before
    assert iface_versions_after == iface_versions_before


# --- P7：角色一致（VIEWER/EDITOR/ADMIN） -------------------------------------


def test_p07_role_consistency(role_client_factory, auth_session_factory):
    """P7/DR-390/A5/§23：VIEWER / EDITOR / ADMIN 的接口与 IP 可见集合一致（READ）。"""
    admin, _, _ = role_client_factory("ADMIN")
    viewer, _, _ = role_client_factory("VIEWER")
    editor, _, _ = role_client_factory("EDITOR")
    with auth_session_factory() as session:
        fx = _build_fixture(admin, session)

    sets = {}
    for role, client in (("ADMIN", admin), ("EDITOR", editor), ("VIEWER", viewer)):
        ifaces = _list_resource_interfaces(client, fx["r"]["id"])
        assert ifaces.status_code == 200, f"{role}: {ifaces.text}"
        iface_ids = {i["id"] for i in ifaces.json()["items"]}
        rows = _frontend_visible_rows(client, fx["r"]["id"])
        sets[role] = (frozenset(iface_ids), frozenset(row["id"] for row in rows))

    assert sets["ADMIN"] == sets["EDITOR"] == sets["VIEWER"]
    assert sets["VIEWER"][1] == {
        fx["a1"]["id"],
        fx["a2"]["id"],
        fx["a3"]["id"],
        fx["a4"]["id"],
    }


# --- P9：无新端点 / 参数 ------------------------------------------------------


def test_p09_no_new_endpoints_or_params(role_client_factory, auth_session_factory):
    """P9/DR-394：仅复用既有 F007/F010 GET；拟新增的资源级 IP 路径均应 404。"""
    admin, _, _ = role_client_factory("ADMIN")
    with auth_session_factory() as session:
        fx = _build_fixture(admin, session)
    rid = fx["r"]["id"]
    iid = fx["i1"]["id"]

    for path in (
        f"/api/v1/resources/{rid}/ip-addresses",
        f"/api/v1/resources/{rid}/ips",
        f"/api/v1/interfaces/{iid}/ip-addresses",
        f"/api/v1/interfaces/{iid}/bind-ip",
    ):
        assert admin.get(path).status_code == 404, path

    # 既有端点：未列参数被忽略（F007/F010 §4），查询仍 200
    assert _list_resource_interfaces(admin, rid, unknown_param="x").status_code == 200
    assert _list_interface_ips(admin, iid, unknown_param="x").status_code == 200