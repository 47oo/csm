"""F039 A1/A2/A4/A5/A8 — Dashboard capacity batching (real PostgreSQL).

Counting method (F039 architecture §4 / TD-F039 §1.1): ``before_cursor_execute``
on the engine, counting only statements whose first keyword is ``SELECT``
(``BEGIN`` / ``COMMIT`` / ``SAVEPOINT`` / DDL / DML never enter the count). The
listener is removed in ``finally`` so no later test inherits it.

Two measurement points, both counting a **single** call:
* ``q_svc(N)``  = ``dashboard_service.get_dashboard(session, page=1, page_size=N)``
  — excludes authentication and §23.2 scope resolution (main criterion);
* ``q_http(N)`` = ``GET /api/v1/dashboard?page_size=N`` — adds a constant
  per-request overhead ``C``; the HTTP criterion is the difference
  ``q_http(N) - q_svc(N) == C`` for every ``N``.

``K`` is the pinned literal measured on the implementation (architecture §4
fixes it after the implementation round, hard cap ``<= 20``); it is **not**
derived from a formula in ``N`` and must never be relaxed to make a run green.

Module boundary (architecture §7): this module must not touch the §23.2 scope
symbols — the scope-dependent acceptance case (A3) lives in
``test_f039_scope.py`` under ``pytest.mark.real_scope`` (guard:
``test_f030_test_harness.py``).
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event, select, text

from app.models.network import Network
from app.services import dashboard as dashboard_service
from app.services import ip_capacity
from integration.f015_helpers import role_client_factory  # noqa: F401

# --- measurement -------------------------------------------------------------

K = 11  # measured on the F039 implementation (dashboard: 8 fixed + 3 batch)
K_MAX = 20  # architecture §4 absolute cap; never raised to make a run pass

NETWORK_AXIS = 50
POOL_AXIS = 5  # AUTO pool counts 0..4


@contextmanager
def _count_selects(engine):
    """Count ``SELECT`` statements issued through ``engine`` inside the block."""
    statements: list[tuple[str, Any]] = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _listener)


def _q_svc(engine, session_factory, page_size: int) -> tuple[int, dict[str, Any]]:
    """Count the aggregate path's statements for one dashboard page."""
    with session_factory() as session:
        with _count_selects(engine) as statements:
            body = dashboard_service.get_dashboard(
                session, page=1, page_size=page_size
            )
    return len(statements), body


def _q_http(engine, client, page_size: int) -> tuple[int, dict[str, Any]]:
    """Count the statements of one ``GET /api/v1/dashboard`` request."""
    with _count_selects(engine) as statements:
        response = client.get(
            "/api/v1/dashboard", params={"page": 1, "page_size": page_size}
        )
    assert response.status_code == 200, response.text
    return len(statements), response.json()


# --- real-API fixture helpers (same shape as test_dashboard.py) --------------


def _cluster(client, code="C1", name="Cluster", **overrides):
    body = {"code": code, "name": name}
    body.update(overrides)
    resp = client.post("/api/v1/clusters", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster"]


def _network(client, cluster, name="net", cidr="10.0.0.0/24", **overrides):
    body = {"cluster": cluster, "name": name, "cidr": cidr}
    body.update(overrides)
    resp = client.post("/api/v1/networks", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["network"]


def _pool(client, network, name="pool", start="10.0.0.1", end="10.0.0.9", **overrides):
    body = {
        "network": network,
        "name": name,
        "start_address": start,
        "end_address": end,
    }
    body.update(overrides)
    resp = client.post("/api/v1/ip-pools", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["ip_pool"]


def _ip(client, network, address, **overrides):
    body = {"network": network, "address": address}
    body.update(overrides)
    resp = client.post("/api/v1/ip-addresses", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["ip_address"]


def _seed_network_axis(client) -> dict[str, Any]:
    """1 Cluster + 50 Networks, each 1 RESERVED + 2 AUTO pools + 4 unbound IPs.

    Deterministic (no random seed): ``10.{i}.0.0/24``, gateway ``.1``,
    RESERVED ``.2-.10``, AUTO ``.100-.120`` and ``.130-.140``, IPs
    ``.100/.101/.130`` (in pools) and ``.200`` (outside every pool).
    """
    cluster = _cluster(client, code="C1")
    for index in range(NETWORK_AXIS):
        prefix = f"10.{index}.0"
        network = _network(
            client,
            cluster["code"],
            name=f"net-{index}",
            cidr=f"{prefix}.0/24",
            gateway=f"{prefix}.1",
        )
        _pool(
            client,
            network["id"],
            name=f"res-{index}",
            start=f"{prefix}.2",
            end=f"{prefix}.10",
            allocation_mode="RESERVED",
        )
        for suffix, (start, end) in (("a", ("100", "120")), ("b", ("130", "140"))):
            _pool(
                client,
                network["id"],
                name=f"auto-{suffix}-{index}",
                start=f"{prefix}.{start}",
                end=f"{prefix}.{end}",
                allocation_mode="AUTO",
            )
        for host in ("100", "101", "130", "200"):
            _ip(client, network["id"], f"{prefix}.{host}")
    return cluster


# --- A1: bounded query count -------------------------------------------------


def test_a1_query_count_constant_across_network_count(
    role_client_factory, auth_session_factory, committed_engine
):
    """``q_svc(1) == q_svc(10) == q_svc(50) == K`` and ``K <= 20`` (A1)."""
    client, _, _ = role_client_factory("EDITOR", username="f039.a1n")
    _seed_network_axis(client)

    observed: dict[int, int] = {}
    for page_size in (1, 10, NETWORK_AXIS):
        count, body = _q_svc(committed_engine, auth_session_factory, page_size)
        observed[page_size] = count
        assert body["networks"]["total"] == NETWORK_AXIS
        assert len(body["networks"]["items"]) == page_size
        assert body["counts"]["networks"] == NETWORK_AXIS
        first = body["networks"]["items"][0]
        assert first["capacity"] == {
            "allocatable_total": 244,
            "occupied": 4,
            "remaining": 240,
        }
        assert len(first["auto_pools"]) == 2

    print("F039-A1-N-AXIS", observed)
    assert observed == {1: K, 10: K, NETWORK_AXIS: K}, observed
    assert observed[NETWORK_AXIS] <= K_MAX


def test_a1_query_count_constant_across_auto_pool_count(
    role_client_factory, auth_session_factory, committed_engine
):
    """Appending AUTO pools does not add statements (A1, pool axis)."""
    client, _, _ = role_client_factory("EDITOR", username="f039.a1p")
    cluster = _cluster(client, code="C1")
    network = _network(
        client, cluster["code"], name="n1", cidr="10.0.0.0/24", gateway="10.0.0.1"
    )

    observed: dict[int, int] = {}
    for pool_count in range(0, POOL_AXIS):
        if pool_count:
            start = 100 + (pool_count - 1) * 10
            _pool(
                client,
                network["id"],
                name=f"auto-{pool_count}",
                start=f"10.0.0.{start}",
                end=f"10.0.0.{start + 9}",
                allocation_mode="AUTO",
            )
        count, body = _q_svc(committed_engine, auth_session_factory, 1)
        row = body["networks"]["items"][0]
        assert len(row["auto_pools"]) == pool_count, (pool_count, row["auto_pools"])
        observed[pool_count] = count

    print("F039-A1-P-AXIS", observed)
    assert set(observed.values()) == {K}, observed
    assert max(observed.values()) <= K_MAX


def test_a1_http_overhead_is_constant(
    role_client_factory, auth_session_factory, committed_engine
):
    """``q_http(N) - q_svc(N) == C`` for every ``N`` (A1, HTTP path)."""
    client, _, _ = role_client_factory("EDITOR", username="f039.a1h")
    _seed_network_axis(client)

    deltas: dict[int, int] = {}
    http_counts: dict[int, int] = {}
    for page_size in (1, 10, NETWORK_AXIS):
        service_count, service_body = _q_svc(
            committed_engine, auth_session_factory, page_size
        )
        http_count, http_body = _q_http(committed_engine, client, page_size)
        assert http_body["counts"] == service_body["counts"]
        deltas[page_size] = http_count - service_count
        http_counts[page_size] = http_count

    print("F039-A1-HTTP", deltas, http_counts)
    assert len(set(deltas.values())) == 1, deltas
    overhead = deltas[NETWORK_AXIS]
    assert 0 <= overhead < K_MAX, deltas
    assert http_counts[NETWORK_AXIS] == K + overhead
    assert http_counts[NETWORK_AXIS] <= K_MAX + overhead


def test_a1_capacity_endpoint_statement_count_unchanged(
    role_client_factory, committed_engine
):
    """F010 ``GET /networks/{id}/capacity`` statement count is not increased.

    The endpoint calls ``network_capacity`` / ``auto_pools_capacity`` without a
    context, so F039 must not add statements to it (architecture §2/§10).
    Measured literals: ``6 / 7 / 8`` for 0 / 1 / 2 AUTO pools at the HTTP level
    (request authentication + route lookup + ``4 + P`` service statements).
    The start_commit tree (f66d1f3) was measured with the same probe and gives
    the same ``{0: 6, 1: 7, 2: 8}``, so the count is unchanged, and it still
    grows by exactly 1 per AUTO pool (the F039 batch path is not used here).
    """
    client, _, _ = role_client_factory("EDITOR", username="f039.a1e")
    cluster = _cluster(client, code="C1")
    network = _network(
        client, cluster["code"], name="n1", cidr="10.0.0.0/24", gateway="10.0.0.1"
    )
    observed: dict[int, int] = {}
    for pool_count in range(0, 3):
        if pool_count:
            start = 100 + (pool_count - 1) * 10
            _pool(
                client,
                network["id"],
                name=f"auto-{pool_count}",
                start=f"10.0.0.{start}",
                end=f"10.0.0.{start + 9}",
                allocation_mode="AUTO",
            )
        with _count_selects(committed_engine) as statements:
            response = client.get(f"/api/v1/networks/{network['id']}/capacity")
        assert response.status_code == 200, response.text
        observed[pool_count] = len(statements)
    print("F039-A1-F010", observed)
    assert observed == {0: 6, 1: 7, 2: 8}, observed


# --- A2: §20 capacity equivalence with F010 ----------------------------------


def _capacity_of(client, network_id: str) -> dict[str, Any]:
    resp = client.get(f"/api/v1/networks/{network_id}/capacity")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _assert_row_matches_endpoint(row: dict[str, Any], endpoint: dict[str, Any]) -> None:
    """Item-by-item equality with ``GET /networks/{id}/capacity`` (A2)."""
    assert row["capacity"] == {
        key: endpoint["network_capacity"][key]
        for key in ("allocatable_total", "occupied", "remaining")
    }
    # Pools are matched by id (order asserted separately below).
    assert {
        (block["ip_pool"]["id"], block["allocatable_total"], block["occupied"],
         block["remaining"], block["ip_pool"]["name"],
         block["ip_pool"]["start_address"], block["ip_pool"]["end_address"])
        for block in row["auto_pools"]
    } == {
        (block["ip_pool"]["id"], block["allocatable_total"], block["occupied"],
         block["remaining"], block["ip_pool"]["name"],
         block["ip_pool"]["start_address"], block["ip_pool"]["end_address"])
        for block in endpoint["auto_pools"]
    }
    assert [block["ip_pool"]["id"] for block in row["auto_pools"]] == [
        block["ip_pool"]["id"] for block in endpoint["auto_pools"]
    ]


def test_a2_capacity_matches_endpoint_and_literals(
    role_client_factory, auth_session_factory
):
    """A2/T32 matrix, double-proved by the endpoint *and* hard-coded literals."""
    client, _, _ = role_client_factory("EDITOR", username="f039.a2")
    cluster = _cluster(client, code="C1")
    cases: dict[str, dict[str, Any]] = {}

    # (a) gateway inside the RESERVED range is de-duplicated: 254 - 10 = 244.
    dedup = _network(
        client, cluster["code"], name="dedup", cidr="10.10.0.0/24",
        gateway="10.10.0.1",
    )
    _pool(
        client, dedup["id"], name="res", start="10.10.0.1", end="10.10.0.10",
        allocation_mode="RESERVED",
    )
    cases["dedup"] = {
        "network": dedup,
        "capacity": {"allocatable_total": 244, "occupied": 0, "remaining": 244},
        "pools": {},
    }

    # (b) AUTO pool |range ∩ allocatable| = 11; unbound IP and out-of-pool
    # manual IP both occupy the Network.
    auto = _network(
        client, cluster["code"], name="auto", cidr="10.11.0.0/24",
        gateway="10.11.0.1",
    )
    _pool(
        client, auto["id"], name="res", start="10.11.0.2", end="10.11.0.10",
        allocation_mode="RESERVED",
    )
    auto_pool = _pool(
        client, auto["id"], name="auto", start="10.11.0.100", end="10.11.0.110",
        allocation_mode="AUTO",
    )
    _ip(client, auto["id"], "10.11.0.100")  # unbound, inside the pool
    _ip(client, auto["id"], "10.11.0.200")  # manual, outside every pool
    cases["auto"] = {
        "network": auto,
        "capacity": {"allocatable_total": 244, "occupied": 2, "remaining": 242},
        "pools": {
            auto_pool["id"]: {
                "allocatable_total": 11,
                "occupied": 1,
                "remaining": 10,
            }
        },
    }

    # (c) INACTIVE Network: capacity is *not* zeroed (no status predicate).
    # The row is created ACTIVE (allocation is refused on an INACTIVE Network,
    # 409 ``network_inactive``) and switched afterwards.
    inactive = _network(
        client, cluster["code"], name="inactive", cidr="10.12.0.0/24",
        gateway="10.12.0.1",
    )
    _pool(
        client, inactive["id"], name="res", start="10.12.0.2", end="10.12.0.10",
        allocation_mode="RESERVED",
    )
    inactive_pool = _pool(
        client, inactive["id"], name="auto", start="10.12.0.100",
        end="10.12.0.110", allocation_mode="AUTO",
    )
    _ip(client, inactive["id"], "10.12.0.100")
    deactivated = client.patch(
        f"/api/v1/networks/{inactive['id']}",
        json={"version": inactive["version"], "status": "INACTIVE"},
    )
    assert deactivated.status_code == 200, deactivated.text
    cases["inactive"] = {
        "network": deactivated.json()["network"],
        "status": "INACTIVE",
        "capacity": {"allocatable_total": 244, "occupied": 1, "remaining": 243},
        "pools": {
            inactive_pool["id"]: {
                "allocatable_total": 11,
                "occupied": 1,
                "remaining": 10,
            }
        },
    }

    # (d) §11.1 disabled range: base usable is empty.
    disabled = _network(client, cluster["code"], name="disabled", cidr="240.0.0.0/24")
    cases["disabled"] = {
        "network": disabled,
        "capacity": {"allocatable_total": 0, "occupied": 0, "remaining": 0},
        "pools": {},
    }

    # (e) /31 and /32 boundaries (§11.1: both / the single address usable).
    slash31 = _network(client, cluster["code"], name="slash31", cidr="10.13.0.0/31")
    cases["slash31"] = {
        "network": slash31,
        "capacity": {"allocatable_total": 2, "occupied": 0, "remaining": 2},
        "pools": {},
    }
    slash32 = _network(client, cluster["code"], name="slash32", cidr="10.13.1.1/32")
    cases["slash32"] = {
        "network": slash32,
        "capacity": {"allocatable_total": 1, "occupied": 0, "remaining": 1},
        "pools": {},
    }

    with auth_session_factory() as session:
        audit_before = session.execute(
            text("SELECT count(*) FROM audit_logs")
        ).scalar_one()

    by_name = {
        row["network"]["name"]: row
        for row in client.get(
            "/api/v1/dashboard", params={"page_size": 100}
        ).json()["networks"]["items"]
    }
    assert set(by_name) == set(cases), by_name.keys()

    for name, case in cases.items():
        row = by_name[name]
        endpoint = _capacity_of(client, case["network"]["id"])
        _assert_row_matches_endpoint(row, endpoint)
        assert row["capacity"] == case["capacity"], (name, row["capacity"])
        assert row["network"]["id"] == case["network"]["id"]
        assert row["network"]["status"] == case.get(
            "status", case["network"].get("status", "ACTIVE")
        )
        assert {
            block["ip_pool"]["id"]: {
                key: block[key]
                for key in ("allocatable_total", "occupied", "remaining")
            }
            for block in row["auto_pools"]
        } == case["pools"], name

    with auth_session_factory() as session:
        audit_after = session.execute(
            text("SELECT count(*) FROM audit_logs")
        ).scalar_one()
    assert audit_after == audit_before  # read-only endpoints, no audit writes


def test_a2_pool_occupancy_follows_current_address(
    role_client_factory, auth_session_factory
):
    """Pool occupancy counts by current address, not by allocation source (A2)."""
    client, _, _ = role_client_factory("EDITOR", username="f039.a2c")
    cluster = _cluster(client, code="C1")
    network = _network(
        client, cluster["code"], name="n1", cidr="10.14.0.0/24",
        gateway="10.14.0.1",
    )
    auto_pool = _pool(
        client, network["id"], name="auto", start="10.14.0.100",
        end="10.14.0.110", allocation_mode="AUTO",
    )
    manual_pool = _pool(
        client, network["id"], name="manual", start="10.14.0.200",
        end="10.14.0.210", allocation_mode="MANUAL",
    )
    address = _ip(client, network["id"], "10.14.0.100")
    with auth_session_factory() as session:
        # The allocation-source FK now points at the MANUAL pool while the
        # address still lives inside the AUTO range (F039 A2 / AP-F039-4).
        session.execute(
            text("UPDATE ip_addresses SET ip_pool_id = :pool WHERE id = :id"),
            {"pool": uuid.UUID(manual_pool["id"]), "id": uuid.UUID(address["id"])},
        )
        session.commit()

    row = client.get("/api/v1/dashboard").json()["networks"]["items"][0]
    endpoint = _capacity_of(client, network["id"])
    _assert_row_matches_endpoint(row, endpoint)
    blocks = {
        block["ip_pool"]["id"]: block for block in row["auto_pools"]
    }
    assert set(blocks) == {auto_pool["id"]}
    assert blocks[auto_pool["id"]]["occupied"] == 1
    assert row["capacity"]["occupied"] == 1


# --- A4: negative remaining --------------------------------------------------


def test_a4_negative_remaining_is_returned_verbatim(
    role_client_factory, auth_session_factory
):
    """``remaining`` may be negative and is never clamped (A4)."""
    client, _, _ = role_client_factory("EDITOR", username="f039.a4")
    cluster = _cluster(client, code="C1")
    network = _network(client, cluster["code"], name="n1", cidr="10.0.0.0/30")
    with auth_session_factory() as session:
        session.execute(
            text(
                "INSERT INTO ip_addresses (network_id, cluster_id, address) "
                "VALUES (:n, :c, '10.0.0.1'), (:n, :c, '10.0.0.2')"
            ),
            {"n": uuid.UUID(network["id"]), "c": uuid.UUID(cluster["id"])},
        )
        session.execute(
            text("UPDATE networks SET gateway = '10.0.0.1' WHERE id = :id"),
            {"id": uuid.UUID(network["id"])},
        )
        session.commit()

    row = client.get("/api/v1/dashboard").json()["networks"]["items"][0]
    endpoint = _capacity_of(client, network["id"])
    assert row["capacity"] == {
        "allocatable_total": 1,
        "occupied": 2,
        "remaining": -1,
    }
    assert row["capacity"]["remaining"] == endpoint["network_capacity"]["remaining"]
    assert row["capacity"]["remaining"] < 0


# --- A5: response surface ----------------------------------------------------


def test_a5_response_surface_matches_golden_body(role_client_factory):
    """Field names/types/values/order unchanged: full literal comparison (A5)."""
    client, _, _ = role_client_factory("EDITOR", username="f039.a5")
    cluster = _cluster(client, code="C1")
    network = _network(
        client, cluster["code"], name="n1", cidr="10.10.0.0/24",
        gateway="10.10.0.1",
    )
    _pool(
        client, network["id"], name="res", start="10.10.0.2", end="10.10.0.10",
        allocation_mode="RESERVED",
    )
    pool = _pool(
        client, network["id"], name="auto", start="10.10.0.100",
        end="10.10.0.110", allocation_mode="AUTO",
    )
    _ip(client, network["id"], "10.10.0.100")
    _ip(client, network["id"], "10.10.0.200")

    response = client.get("/api/v1/dashboard", params={"page": 1, "page_size": 20})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "counts": {
            "clusters": 1,
            "resources": 0,
            "bare_metal": 0,
            "virtual_machines": 0,
            "networks": 1,
        },
        "networks": {
            "items": [
                {
                    "network": {
                        "id": network["id"],
                        "name": "n1",
                        "cidr": "10.10.0.0/24",
                        "status": "ACTIVE",
                        "auto_allocate": False,
                        "cluster": {
                            "id": cluster["id"],
                            "code": "C1",
                            "name": "Cluster",
                        },
                    },
                    "capacity": {
                        "allocatable_total": 244,
                        "occupied": 2,
                        "remaining": 242,
                    },
                    "auto_pools": [
                        {
                            "ip_pool": {
                                "id": pool["id"],
                                "name": "auto",
                                "start_address": "10.10.0.100",
                                "end_address": "10.10.0.110",
                            },
                            "allocatable_total": 11,
                            "occupied": 1,
                            "remaining": 10,
                        }
                    ],
                }
            ],
            "page": 1,
            "page_size": 20,
            "total": 1,
        },
    }


def test_a5_pagination_and_counts_ordering(role_client_factory):
    """``items`` order (created_at desc, id asc) and pagination (A5)."""
    client, _, _ = role_client_factory("EDITOR", username="f039.a5p")
    cluster = _cluster(client, code="C1")
    created = [
        _network(client, cluster["code"], name=f"n{index}", cidr=f"10.0.{index}.0/24")
        for index in range(3)
    ]

    first = client.get(
        "/api/v1/dashboard", params={"page": 1, "page_size": 2}
    ).json()
    second = client.get(
        "/api/v1/dashboard", params={"page": 2, "page_size": 2}
    ).json()

    assert first["counts"] == second["counts"]
    assert first["networks"]["total"] == second["networks"]["total"] == 3
    assert (first["networks"]["page"], first["networks"]["page_size"]) == (1, 2)
    assert (second["networks"]["page"], second["networks"]["page_size"]) == (2, 2)
    assert len(first["networks"]["items"]) == 2
    assert len(second["networks"]["items"]) == 1
    # created_at DESC, id ASC == reverse creation order for distinct times.
    assert [
        row["network"]["id"]
        for row in first["networks"]["items"] + second["networks"]["items"]
    ] == [network["id"] for network in reversed(created)]
    # same set of keys on every row
    keys = {tuple(sorted(row)) for row in first["networks"]["items"]}
    assert keys == {("auto_pools", "capacity", "network")}


def test_a5_error_semantics(role_client_factory, auth_app):
    """``401 -> 422 -> 200`` ordering and unchanged error envelopes (A5)."""
    from fastapi.testclient import TestClient

    with TestClient(auth_app) as anonymous:
        unauthenticated = anonymous.get("/api/v1/dashboard")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json() == {
        "error": {
            "code": "AUTH_REQUIRED",
            "message": "Authentication required",
            "details": {},
        }
    }

    client, _, _ = role_client_factory("EDITOR", username="f039.a5e")
    for params in ({"page": 0}, {"page_size": 101}, {"page_size": 0}):
        invalid = client.get("/api/v1/dashboard", params=params)
        assert invalid.status_code == 422, (params, invalid.text)
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
        assert invalid.json()["error"]["message"] == "Validation error"
        assert "fields" in invalid.json()["error"]["details"]

    assert client.get("/api/v1/dashboard").status_code == 200
    assert (
        client.get("/api/v1/dashboard", params={"deleted": "include"}).status_code
        == 200
    )


# --- A8: EXPLAIN + single formula source -------------------------------------


def _plan_nodes(node: dict[str, Any], collected: list[dict[str, Any]]) -> None:
    collected.append(node)
    for child in node.get("Plans", []):
        _plan_nodes(child, collected)


def _explain(connection, statement: str, parameters: Any, *, force_index: bool):
    """Return ``(plan, nodes)`` for one statement (optionally with seqscan off)."""
    if force_index:
        connection.exec_driver_sql("SET LOCAL enable_seqscan = off")
    rows = connection.exec_driver_sql(
        "EXPLAIN (FORMAT JSON) " + statement, parameters or {}
    ).scalar_one()
    plan = rows[0]
    nodes: list[dict[str, Any]] = []
    _plan_nodes(plan["Plan"], nodes)
    return plan, nodes


def test_a8_batch_statements_have_index_paths(
    role_client_factory, auth_session_factory, committed_engine
):
    """3 batch statements; index paths exist, no sequential-scan degradation (A8)."""
    client, _, _ = role_client_factory("EDITOR", username="f039.a8")
    cluster = _cluster(client, code="C1")
    for index in range(2):
        network = _network(
            client, cluster["code"], name=f"n{index}", cidr=f"10.20.{index}.0/24",
            gateway=f"10.20.{index}.1",
        )
        _pool(
            client, network["id"], name="res", start=f"10.20.{index}.2",
            end=f"10.20.{index}.10", allocation_mode="RESERVED",
        )
        _pool(
            client, network["id"], name="auto", start=f"10.20.{index}.100",
            end=f"10.20.{index}.110", allocation_mode="AUTO",
        )
        _ip(client, network["id"], f"10.20.{index}.100")

    with auth_session_factory() as session:
        networks = list(
            session.execute(select(Network).order_by(Network.name)).scalars().all()
        )
        with _count_selects(committed_engine) as statements:
            context = ip_capacity.load_capacity_context(session, networks)
        assert len(statements) == 3, [stmt for stmt, _ in statements]
        assert set(context.reserved) == {network.id for network in networks}
        assert sum(len(pools) for pools in context.auto_pools.values()) == 2
        assert context.occupied == {network.id: 1 for network in networks}

        existing: dict[str, set[str]] = {}
        for table in ("ip_pools", "ip_addresses", "networks"):
            existing[table] = set(
                session.execute(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE schemaname = 'public' AND tablename = :table"
                    ),
                    {"table": table},
                )
                .scalars()
                .all()
            )

    connection = committed_engine.connect()
    try:
        foreign: set[str] = set()
        for index, (statement, parameters) in enumerate(statements, start=1):
            raw_plan, raw = _explain(
                connection, statement, parameters, force_index=False
            )
            forced_plan, forced = _explain(
                connection, statement, parameters, force_index=True
            )
            connection.rollback()
            # No index degradation: with sequential scans disabled every scan
            # must still be reachable through an index (architecture §3).
            scan_types = {node["Node Type"] for node in forced}
            assert not any(scan.startswith("Seq Scan") for scan in scan_types), (
                statement,
                scan_types,
            )
            assert any("Index" in scan for scan in scan_types), (statement, scan_types)
            for node in forced:
                name = node.get("Index Name")
                if name is None:
                    continue
                for table in ("ip_pools", "ip_addresses", "networks"):
                    if name in existing[table]:
                        break
                else:
                    foreign.add(name)
            print(
                "F039-EXPLAIN",
                statement.split("FROM")[0].strip()[:40],
                "raw=", sorted({n["Node Type"] for n in raw}),
                "forced=", sorted(
                    {n["Node Type"] for n in forced}
                ),
                "indexes=", sorted(
                    {n["Index Name"] for n in forced if n.get("Index Name")}
                ),
            )
            print(f"F039-EXPLAIN-SQL-{index}", " ".join(statement.split()))
            print(f"F039-EXPLAIN-RAW-{index}", json.dumps(raw_plan, sort_keys=True))
            print(f"F039-EXPLAIN-FORCED-{index}", json.dumps(forced_plan, sort_keys=True))
        assert foreign == set(), foreign
    finally:
        connection.close()


def test_a8_dashboard_has_no_address_arithmetic():
    """``dashboard.py`` still delegates to the single formula source (A8/N2)."""
    from pathlib import Path

    source = (
        Path(dashboard_service.__file__).read_text(encoding="utf-8")
    )
    code_lines = [
        line
        for line in source.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    body = "\n".join(code_lines)
    for forbidden in (
        "subtract_intervals",
        "intersect_with_range",
        "base_usable_intervals",
        "interval_length",
        "allocatable_intervals_for",
        "remaining =",
    ):
        assert forbidden not in body, forbidden
    assert "ip_capacity.network_capacity(" in body
    assert "ip_capacity.auto_pools_capacity(" in body
    assert "load_capacity_context(" in body
