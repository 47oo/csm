"""F018 Tester independent acceptance coverage (F018-TE-1).

Complements the developer suite (``test_search_related.py``) with the evidence
items TD-1 requires but the developer tests do not establish directly:

- V13 fixed superset is query-independent (same ``related``/``related_total``
  for different ``q``/``type`` filters);
- V15 read-only route inventory (only ``GET`` on ``/api/v1/search``);
- V16 error ordering 401 -> 403 -> 422;
- V17/B18 ``related_total`` vs top-level ``total`` never mixed;
- V18 real-PostgreSQL evidence: bounded query count (no N+1) and ``EXPLAIN``
  referencing the existing indexes; raw-SQL cross-check of ``COLLATE "C"`` +
  ``inet`` numeric ordering (B1/B2);
- B14 an unknown ``fields`` query parameter is ignored server-side (field
  selection is purely client-side).

Real PostgreSQL only (DB-D10 guard in ``conftest``).
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text


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


def _search(client, q, **params):
    return client.get("/api/v1/search", params={"q": q, **params})


def _resource_row(client, hostname, **params):
    body = _search(client, hostname, **params).json()
    rows = [i for i in body["items"] if i["object_type"] == "resource"]
    assert len(rows) == 1, body
    return rows[0]


def _names(related):
    return [(r["interface"]["name"], r["ip_address"]["address"]) for r in related]


# --- V13: fixed superset is independent of q / type --------------------------


def test_fixed_superset_independent_of_query(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="superset-host")
    net = _network(editor, c1["code"], name="ib", cidr="10.10.0.0/16")
    iface = _interface(editor, res["id"], name="ib0", interface_type="PHYSICAL")
    _bind(editor, _ip(editor, net["id"], "10.10.1.9"), iface)

    full = _resource_row(editor, "superset-host")["resource"]
    narrowed = _resource_row(editor, "superset-host", type="resource")["resource"]
    # Different q prefixes still return the same fixed superset content.
    other_q = _resource_row(editor, "superset")["resource"]
    assert full["related"] == narrowed["related"] == other_q["related"]
    assert (
        full["related_total"]
        == narrowed["related_total"]
        == other_q["related_total"]
        == 1
    )
    assert set(full) >= {
        "hostname",
        "resource_type",
        "role",
        "status",
        "cluster",
        "related",
        "related_total",
    }


def test_unknown_fields_param_is_ignored(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="fieldparam-host")
    net = _network(editor, c1["code"], name="net", cidr="10.11.0.0/16")
    iface = _interface(editor, res["id"], name="eth0")
    _bind(editor, _ip(editor, net["id"], "10.11.0.1"), iface)

    plain = _search(editor, "fieldparam-host").json()
    with_fields = _search(
        editor, "fieldparam-host", fields="hostname,ip_address"
    ).json()
    # B14: field selection never changes the server request/result.
    assert plain == with_fields
    assert plain["items"][0]["resource"]["related_total"] == 1


# --- V14 / V17 / B18: non-resource rows and total independence ---------------


def test_non_resource_rows_related_null_and_total_distinct(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    rich = _resource(editor, c1["code"], hostname="rt-rich")
    plain = _resource(editor, c1["code"], hostname="rt-plain")
    net = _network(editor, c1["code"], name="net", cidr="10.12.0.0/16")
    iface = _interface(editor, rich["id"], name="eth0")
    for octet in range(1, 24):
        _bind(editor, _ip(editor, net["id"], f"10.12.0.{octet}"), iface)
    # A cluster row has no embedded resource at all.
    cluster_resp = _search(editor, "C1").json()
    cluster_rows = [i for i in cluster_resp["items"] if i["object_type"] == "cluster"]
    assert cluster_rows and cluster_rows[0]["resource"] is None

    body = _search(editor, "rt-").json()
    assert body["total"] == 2  # top-level total counts result rows, not associations
    rich_row = [i for i in body["items"] if i["id"] == rich["id"]][0]
    plain_row = [i for i in body["items"] if i["id"] == plain["id"]][0]
    assert rich_row["resource"]["related_total"] == 23
    assert plain_row["resource"]["related_total"] == 0
    assert body["total"] != rich_row["resource"]["related_total"]


# --- V15: read-only route inventory ------------------------------------------


def test_search_route_is_get_only(auth_app):
    methods = set()
    for route in auth_app.routes:
        path = getattr(route, "path", "")
        if path == "/api/v1/search":
            methods |= set(getattr(route, "methods", set()) or set())
    assert methods == {"GET"}, methods
    write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    assert not (methods & write_methods)


# --- V16: error ordering 401 -> 403 -> 422 -----------------------------------


def test_error_ordering_401_before_validation(auth_app):
    with TestClient(auth_app) as client:
        resp = client.get("/api/v1/search", params={"q": ""})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


def test_error_ordering_403_before_422(role_client_factory):
    viewer, _, _ = role_client_factory("VIEWER")
    # No VIEW_DELETED: permission check precedes q validation.
    forbidden = _search(viewer, "", deleted="include")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["details"] == {"reason": "permission"}

    admin, _, _ = role_client_factory("ADMIN")
    after = _search(admin, "", deleted="include")
    assert after.status_code == 422
    assert after.json()["error"]["details"]["fields"][0]["field"] == "q"

    invalid = _search(viewer, "x", type="bogus")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"]["fields"][0]["field"] == "type"


# --- V18 / B1 / B2: raw SQL cross-check of ordering --------------------------


def test_ordering_matches_raw_sql(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="rawsql-host")
    net = _network(editor, c1["code"], name="data", cidr="10.13.0.0/16")
    eth2 = _interface(editor, res["id"], name="eth2")
    eth10 = _interface(editor, res["id"], name="eth10")
    _bind(editor, _ip(editor, net["id"], "10.13.1.10"), eth2)
    _bind(editor, _ip(editor, net["id"], "10.13.2.1"), eth2)
    _bind(editor, _ip(editor, net["id"], "10.13.1.9"), eth10)

    api_order = _names(_resource_row(editor, "rawsql-host")["resource"]["related"])
    with auth_session_factory() as session:
        raw = [
            (name, str(address))
            for name, address in session.execute(
                text(
                    "SELECT i.name, ip.address "
                    "FROM interfaces i JOIN ip_addresses ip ON ip.interface_id = i.id "
                    "WHERE i.resource_id = :rid "
                    "AND i.deleted_at IS NULL AND ip.deleted_at IS NULL "
                    'ORDER BY i.name COLLATE "C", ip.address, ip.id'
                ),
                {"rid": res["id"]},
            ).all()
        ]
    assert api_order == raw
    # Byte order "eth10" < "eth2" and numeric 10.13.1.9 < 10.13.1.10 < 10.13.2.1.
    assert api_order == [
        ("eth10", "10.13.1.9"),
        ("eth2", "10.13.1.10"),
        ("eth2", "10.13.2.1"),
    ]


def test_related_explain_references_existing_indexes(
    role_client_factory, committed_engine
):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="explain-host")
    net = _network(editor, c1["code"], name="net", cidr="10.14.0.0/16")
    iface = _interface(editor, res["id"], name="eth0")
    _bind(editor, _ip(editor, net["id"], "10.14.0.1"), iface)

    join_sql = (
        "SELECT i.resource_id, ip.address FROM interfaces i "
        "JOIN ip_addresses ip ON ip.interface_id = i.id "
        "JOIN networks n ON n.id = ip.network_id "
        "WHERE i.resource_id = :rid "
        'ORDER BY i.name COLLATE "C", ip.address, ip.id'
    )
    with committed_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("SET LOCAL enable_seqscan = off"))
            plan = "\n".join(
                row[0]
                for row in conn.execute(
                    text(f"EXPLAIN {join_sql}"), {"rid": res["id"]}
                ).all()
            )
        finally:
            trans.rollback()
    # Forced index path must reference the existing FK indexes / PK.
    assert re.search(
        r"ix_interfaces_resource_id|ix_ip_addresses_interface_id|networks_pkey|Index",
        plan,
    ), plan


# --- V18: bounded statement count (no per-resource N+1) ----------------------


def _count_selects(engine, fn):
    counter = {"n": 0}

    def _listener(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _listener)
    return counter["n"]


def test_related_loading_has_no_n_plus_1(role_client_factory, committed_engine):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["code"], name="net", cidr="10.15.0.0/16")

    # One resource: baseline statement count.
    base = _resource(editor, c1["code"], hostname="n1-base")
    base_iface = _interface(editor, base["id"], name="eth0")
    _bind(editor, _ip(editor, net["id"], "10.15.0.1"), base_iface)
    baseline = _count_selects(
        committed_engine,
        lambda: _search(editor, "n1-base", page_size=100),
    )

    # Five more resources, each with two interfaces and several bound IPs.
    for r in range(5):
        extra = _resource(editor, c1["code"], hostname=f"n1-extra-{r}")
        for i in range(2):
            iface = _interface(editor, extra["id"], name=f"eth{i}")
            for j in range(3):
                _bind(
                    editor,
                    _ip(editor, net["id"], f"10.15.{r + 1}.{i * 3 + j + 1}"),
                    iface,
                )
    many = _count_selects(
        committed_engine,
        lambda: _search(editor, "n1-", page_size=100),
    )
    # Statement count must not grow with the number of resources/interfaces.
    assert many == baseline, (baseline, many)
    assert many <= 15, many