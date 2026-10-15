"""F018 global search field-combination display — associated data (Contract §2.9).

Covers TD-1 verification items V1–V10 and edge cases B1–B10, B13, B20, B21 that
are observable on the backend. Requires a real PostgreSQL database via
``TEST_DATABASE_URL`` (DB-D10 guard in ``conftest``): ``COLLATE "C"`` ordering,
``inet`` numeric ordering and soft-delete filtering are only meaningful there.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


# --- helpers -----------------------------------------------------------------


def _login_client(app, make_user, role: str):
    user, password = make_user(role=role)
    client = TestClient(app)
    client.__enter__()
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return client, user, password


@pytest.fixture
def role_client_factory(auth_app, make_user):
    clients: list[TestClient] = []

    def _make(role: str):
        client, user, password = _login_client(auth_app, make_user, role)
        clients.append(client)
        return client, user, password

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


def _cluster(client, code="C1", name="Cluster"):
    resp = client.post("/api/v1/clusters", json={"code": code, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster"]


def _resource(client, cluster, hostname="host1", **overrides):
    body = {"cluster": cluster, "hostname": hostname, "resource_type": "BARE_METAL"}
    body.update(overrides)
    resp = client.post("/api/v1/resources", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _service(client, resource, name="ssh"):
    resp = client.post("/api/v1/services", json={"resource": resource, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["service"]


def _network(client, cluster, name="net", cidr="10.0.0.0/8"):
    resp = client.post(
        "/api/v1/networks", json={"cluster": cluster, "name": name, "cidr": cidr}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["network"]


def _interface(client, resource, name="eth0", interface_type="OTHER"):
    resp = client.post(
        "/api/v1/interfaces",
        json={"resource": resource, "name": name, "interface_type": interface_type},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["interface"]


def _ip(client, network, address):
    resp = client.post(
        "/api/v1/ip-addresses", json={"network": network, "address": address}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["ip_address"]


def _bind(client, ip, interface, version=1):
    resp = client.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": version, "interface": interface["id"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["ip_address"]


def _delete_ip(client, ip, version=1):
    resp = client.delete(
        f"/api/v1/ip-addresses/{ip['id']}", params={"version": version}
    )
    assert resp.status_code == 204, resp.text


def _delete_interface(client, interface, version=1):
    resp = client.delete(
        f"/api/v1/interfaces/{interface['id']}", params={"version": version}
    )
    assert resp.status_code == 204, resp.text


def _delete_resource(client, resource, version=1):
    resp = client.delete(
        f"/api/v1/resources/{resource['id']}", params={"version": version}
    )
    assert resp.status_code == 204, resp.text


def _search(client, q, **params):
    return client.get("/api/v1/search", params={"q": q, **params})


def _resource_row(client, hostname, **params):
    body = _search(client, hostname, **params).json()
    rows = [i for i in body["items"] if i["object_type"] == "resource"]
    assert len(rows) == 1, body
    return rows[0]


def _related_names(related):
    return [(r["interface"]["name"], r["ip_address"]["address"]) for r in related]


# --- V1 / A1 / V13 / V14: fixed superset, non-resource rows null -------------


def test_resource_row_related_superset(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="gpu0701")
    net = _network(editor, c1["code"], name="ib", cidr="10.10.0.0/16")
    iface = _interface(
        editor, res["id"], name="ib0", interface_type="PHYSICAL"
    )
    ip = _ip(editor, net["id"], "10.10.1.9")
    _bind(editor, ip, iface)

    item = _resource_row(editor, "gpu0701")
    resource = item["resource"]
    assert resource["related_total"] == 1
    assert resource["related"] == [
        {
            "id": ip["id"],
            "interface": {
                "id": iface["id"],
                "name": "ib0",
                "interface_type": "PHYSICAL",
            },
            "ip_address": {"id": ip["id"], "address": "10.10.1.9"},
            "network": {"id": net["id"], "name": "ib"},
        }
    ]
    # Fixed superset: resource row always carries the two fields.
    assert "related" in resource and "related_total" in resource


def test_non_resource_rows_have_null_related(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="svc-host")
    _service(editor, res["id"], name="websvc")
    net = _network(editor, c1["code"], name="mgmt", cidr="10.0.0.0/24")
    iface = _interface(editor, res["id"], name="eth0")
    ip = _ip(editor, net["id"], "10.0.0.5")
    _bind(editor, ip, iface)

    # service row embeds resource; related must stay null (A12/V14).
    service_item = _search(editor, "websvc").json()["items"][0]
    assert service_item["object_type"] == "service"
    assert service_item["resource"]["related"] is None
    assert service_item["resource"]["related_total"] is None

    # ip_address row embeds resource; related must stay null (A12/V14).
    ip_item = _search(editor, "10.0.0.5").json()["items"][0]
    assert ip_item["object_type"] == "ip_address"
    assert ip_item["resource"]["related"] is None
    assert ip_item["resource"]["related_total"] is None


# --- V2 / B1 / B2: deterministic ordering ------------------------------------


def test_related_ordering_collate_c_and_inet_numeric(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="order-host")
    net = _network(editor, c1["code"], name="data", cidr="10.0.0.0/8")
    eth2 = _interface(editor, res["id"], name="eth2")
    eth10 = _interface(editor, res["id"], name="eth10")
    # Byte order: "eth10" < "eth2"; numeric order: 10.10.1.9 < 10.10.1.10 < 10.10.2.1.
    _bind(editor, _ip(editor, net["id"], "10.10.2.1"), eth2)
    _bind(editor, _ip(editor, net["id"], "10.10.1.10"), eth2)
    _bind(editor, _ip(editor, net["id"], "10.10.1.9"), eth10)

    expected = [
        ("eth10", "10.10.1.9"),
        ("eth2", "10.10.1.10"),
        ("eth2", "10.10.2.1"),
    ]
    for _ in range(3):  # repeat: stable full order (A2)
        item = _resource_row(editor, "order-host")
        assert _related_names(item["resource"]["related"]) == expected


# --- V3 / B4: limit 10 + pre-truncation total --------------------------------


def test_related_limit_and_total(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="many-host")
    net = _network(editor, c1["code"], name="net", cidr="10.10.0.0/16")
    iface = _interface(editor, res["id"], name="eth0")
    for octet in range(1, 24):  # 23 bound IPs
        _bind(editor, _ip(editor, net["id"], f"10.10.0.{octet}"), iface)

    resource = _resource_row(editor, "many-host")["resource"]
    assert resource["related_total"] == 23
    assert len(resource["related"]) == 10
    # Numeric order => first ten are .1 .. .10 (string order would differ).
    assert [r["ip_address"]["address"] for r in resource["related"]] == [
        f"10.10.0.{n}" for n in range(1, 11)
    ]


@pytest.mark.parametrize("count", [10, 11])
def test_related_limit_boundary(role_client_factory, count):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname=f"bound-{count}")
    net = _network(editor, c1["code"], name="net", cidr="10.20.0.0/16")
    iface = _interface(editor, res["id"], name="eth0")
    for octet in range(1, count + 1):
        _bind(editor, _ip(editor, net["id"], f"10.20.0.{octet}"), iface)

    resource = _resource_row(editor, f"bound-{count}")["resource"]
    assert resource["related_total"] == count
    assert len(resource["related"]) == min(count, 10)


# --- V4 / A4: each bound IP is one row, no dup/missing -----------------------


def test_two_interfaces_two_ips_each(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="quad-host")
    net = _network(editor, c1["code"], name="net", cidr="10.30.0.0/16")
    iface_a = _interface(editor, res["id"], name="eth0")
    iface_b = _interface(editor, res["id"], name="eth1")
    for address in ("10.30.0.1", "10.30.0.2"):
        _bind(editor, _ip(editor, net["id"], address), iface_a)
    for address in ("10.30.0.3", "10.30.0.4"):
        _bind(editor, _ip(editor, net["id"], address), iface_b)

    related = _resource_row(editor, "quad-host")["resource"]["related"]
    assert len(related) == 4
    ids = [r["id"] for r in related]
    assert len(set(ids)) == 4
    assert sorted(_related_names(related)) == [
        ("eth0", "10.30.0.1"),
        ("eth0", "10.30.0.2"),
        ("eth1", "10.30.0.3"),
        ("eth1", "10.30.0.4"),
    ]


# --- V5 / B3: no associations ------------------------------------------------


def test_no_interface_is_empty(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    _resource(editor, c1["code"], hostname="empty-host")

    resource = _resource_row(editor, "empty-host")["resource"]
    assert resource["related"] == []
    assert resource["related_total"] == 0


def test_interface_without_ip_is_empty(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="iface-empty-host")
    _interface(editor, res["id"], name="eth0")

    resource = _resource_row(editor, "iface-empty-host")["resource"]
    assert resource["related"] == []
    assert resource["related_total"] == 0


# --- V7 / B6 / B7 / B8 / B19: soft-delete inheritance ------------------------


def test_deleted_association_exclude_include_only(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin, code="C1")
    res = _resource(admin, c1["code"], hostname="sd-host")
    net = _network(admin, c1["code"], name="net", cidr="10.40.0.0/16")
    iface = _interface(admin, res["id"], name="eth0")
    live = _bind(admin, _ip(admin, net["id"], "10.40.0.1"), iface)
    doomed = _bind(admin, _ip(admin, net["id"], "10.40.0.2"), iface)
    _delete_ip(admin, doomed, version=doomed["version"])

    # exclude: deleted association hidden, and not counted in the total.
    excluded = _resource_row(admin, "sd-host")["resource"]
    assert [r["id"] for r in excluded["related"]] == [live["id"]]
    assert excluded["related_total"] == 1

    # No VIEW_DELETED -> include/only is 403 permission (unchanged).
    forbidden = _search(viewer, "sd-host", deleted="include")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["details"] == {"reason": "permission"}

    # include shows undeleted + deleted (B7).
    included = _resource_row(admin, "sd-host", deleted="include")["resource"]
    assert {r["id"] for r in included["related"]} == {live["id"], doomed["id"]}
    assert included["related_total"] == 2

    # only: the result row itself must be deleted (row semantics). Association
    # filtering treats only like include (no filter), so the live IP bound to
    # the now-deleted Interface and the deleted IP both still surface.
    _delete_ip(admin, live, version=live["version"])
    _delete_interface(admin, iface, version=iface["version"])
    _delete_resource(admin, res, version=res["version"])
    only = _resource_row(admin, "sd-host", deleted="only")["resource"]
    assert {r["id"] for r in only["related"]} == {live["id"], doomed["id"]}
    assert only["related_total"] == 2
    # The live Network association is still shown: ``only`` does not restrict
    # associations to deleted-only (B7).
    assert {r["network"]["id"] for r in only["related"]} == {net["id"]}


def test_deleted_association_restore_reappears(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    res = _resource(admin, c1["code"], hostname="restore-host")
    net = _network(admin, c1["code"], name="net", cidr="10.50.0.0/16")
    iface = _interface(admin, res["id"], name="eth0")
    ip = _bind(admin, _ip(admin, net["id"], "10.50.0.1"), iface)
    _delete_ip(admin, ip, version=ip["version"])
    assert _resource_row(admin, "restore-host")["resource"]["related_total"] == 0

    resp = admin.post(
        f"/api/v1/ip-addresses/{ip['id']}/restore", params={"version": ip["version"] + 1}
    )
    assert resp.status_code == 200, resp.text
    restored = _resource_row(admin, "restore-host")["resource"]
    assert restored["related_total"] == 1
    assert [r["id"] for r in restored["related"]] == [ip["id"]]


# --- V8 / B9: unbound IP never appears but is still searchable ---------------


def test_unbound_ip_not_in_related_but_searchable(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    _resource(editor, c1["code"], hostname="unbound-host")
    net = _network(editor, c1["code"], name="net", cidr="10.60.0.0/16")
    _ip(editor, net["id"], "10.60.0.99")  # interface_id IS NULL

    resource = _resource_row(editor, "unbound-host")["resource"]
    assert resource["related"] == []
    assert resource["related_total"] == 0

    item = _search(editor, "10.60.0.99").json()["items"][0]
    assert item["object_type"] == "ip_address"
    assert item["ip_address"]["interface"] is None
    assert item["resource"] is None


# --- B5: same (name, address) tie-break by ip id ASC -------------------------


def test_same_name_and_address_tiebreak_by_id(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    res = _resource(admin, c1["code"], hostname="tie-host")
    net = _network(admin, c1["code"], name="net", cidr="10.70.0.0/16")

    first_iface = _interface(admin, res["id"], name="eth0")
    first_ip = _bind(admin, _ip(admin, net["id"], "10.70.0.5"), first_iface)
    # Release the name/address, then recreate the same (name, address) pair.
    _delete_ip(admin, first_ip, version=first_ip["version"])
    _delete_interface(admin, first_iface, version=first_iface["version"])
    second_iface = _interface(admin, res["id"], name="eth0")
    second_ip = _bind(admin, _ip(admin, net["id"], "10.70.0.5"), second_iface)

    related = _resource_row(admin, "tie-host", deleted="include")["resource"][
        "related"
    ]
    assert len(related) == 2
    assert _related_names(related) == [("eth0", "10.70.0.5"), ("eth0", "10.70.0.5")]
    got = [r["id"] for r in related]
    expected = [
        str(x)
        for x in sorted(
            [uuid.UUID(first_ip["id"]), uuid.UUID(second_ip["id"])]
        )
    ]
    assert got == expected


# --- B10: non-ASCII names, verbatim, deterministic ---------------------------


def test_non_ascii_names_are_verbatim(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="cn-host")
    net = _network(editor, c1["code"], name="管理网 络", cidr="10.80.0.0/16")
    iface = _interface(editor, res["id"], name="网卡甲")
    ip = _ip(editor, net["id"], "10.80.0.1")
    _bind(editor, ip, iface)

    related = _resource_row(editor, "cn-host")["resource"]["related"]
    assert _related_names(related) == [("网卡甲", "10.80.0.1")]
    assert related[0]["network"]["name"] == "管理网 络"


# --- B21: interface_type is echoed from the authoritative seven values -------


@pytest.mark.parametrize(
    "interface_type",
    ["PHYSICAL", "VIRTUAL", "BOND", "BRIDGE", "VLAN", "LOOPBACK", "OTHER"],
)
def test_interface_type_echoed(role_client_factory, interface_type):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code=f"C-{interface_type}")
    res = _resource(editor, c1["code"], hostname=f"type-{interface_type}")
    net = _network(editor, c1["code"], name="net", cidr="10.90.0.0/16")
    iface = _interface(
        editor, res["id"], name="eth0", interface_type=interface_type
    )
    _bind(editor, _ip(editor, net["id"], "10.90.0.1"), iface)

    related = _resource_row(editor, f"type-{interface_type}")["resource"]["related"]
    assert related[0]["interface"]["interface_type"] == interface_type


# --- V9 / B13 / V17: no change to result set, dedup, order, total ------------


def test_related_does_not_change_result_set(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    plain = _resource(editor, c1["code"], hostname="rs-1-plain")
    rich = _resource(editor, c1["code"], hostname="rs-2-rich")
    net = _network(editor, c1["code"], name="net", cidr="10.100.0.0/16")
    iface = _interface(editor, rich["id"], name="eth0")
    for octet in range(1, 24):
        _bind(editor, _ip(editor, net["id"], f"10.100.0.{octet}"), iface)

    body = _search(editor, "rs-").json()
    assert body["total"] == 2
    # Only one typed row per resource; association never adds rows.
    assert len(body["items"]) == 2
    assert {i["object_type"] for i in body["items"]} == {"resource"}
    assert sorted(i["id"] for i in body["items"]) == sorted(
        [plain["id"], rich["id"]]
    )
    # related_total is per-resource, unrelated to top-level total (V17).
    rich_row = [i for i in body["items"] if i["id"] == rich["id"]][0]
    assert rich_row["resource"]["related_total"] == 23
    assert body["total"] == 2


def test_pagination_associations_are_page_scoped(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["code"], name="net", cidr="10.110.0.0/16")
    expected: dict[str, list[str]] = {}
    for index in range(3):
        res = _resource(editor, c1["code"], hostname=f"pg-{index}")
        iface = _interface(editor, res["id"], name="eth0")
        addresses = [f"10.110.{index}.{n}" for n in range(1, index + 2)]
        for address in addresses:
            _bind(editor, _ip(editor, net["id"], address), iface)
        expected[res["id"]] = addresses

    seen: set[str] = set()
    for page in (1, 2, 3):
        body = _search(editor, "pg-", page=page, page_size=1).json()
        assert body["total"] == 3
        assert len(body["items"]) == 1
        item = body["items"][0]
        resource = item["resource"]
        assert [r["ip_address"]["address"] for r in resource["related"]] == (
            expected[item["id"]]
        )
        seen.add(item["id"])
    assert len(seen) == 3


# --- V10 / B11 / B12: read-only, no audit, idempotent -----------------------


def test_related_search_is_idempotent_and_writes_no_audit(
    role_client_factory, auth_session_factory
):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="ro-host")
    net = _network(editor, c1["code"], name="net", cidr="10.120.0.0/16")
    iface = _interface(editor, res["id"], name="eth0")
    _bind(editor, _ip(editor, net["id"], "10.120.0.1"), iface)

    with auth_session_factory() as session:
        before = session.execute(
            text("SELECT count(*) FROM audit_logs")
        ).scalar_one()

    first = _search(editor, "ro-host")
    second = _search(editor, "ro-host")
    assert first.status_code == 200
    assert first.json() == second.json()  # idempotent

    with auth_session_factory() as session:
        after = session.execute(text("SELECT count(*) FROM audit_logs")).scalar_one()
    assert after == before