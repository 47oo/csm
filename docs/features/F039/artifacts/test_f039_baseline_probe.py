"""F039 baseline probe (TEST evidence) — start_commit f66d1f3 code only.

Runs the **same** fixture, counter and measurement functions as
``integration/test_f039_query_count.py`` against the pre-F039 services
(``dashboard.py`` blob f0ca4d28…, ``ip_capacity.py`` blob 7e01365c…, both equal
to ``git rev-parse f66d1f3:backend/app/services/*``). It only *records* the
counts (no ``K`` assertion): the post-implementation run must be compared with
these numbers, and the A1 criterion must be provably false here.
"""

from __future__ import annotations

from integration.test_f039_query_count import (  # noqa: F401
    NETWORK_AXIS,
    POOL_AXIS,
    _cluster,
    _network,
    _pool,
    _q_http,
    _q_svc,
    _seed_network_axis,
    role_client_factory,
)


def test_baseline_network_axis(role_client_factory, auth_session_factory, committed_engine):
    client, _, _ = role_client_factory("EDITOR", username="f039.base.n")
    _seed_network_axis(client)
    observed = {}
    http = {}
    for page_size in (1, 10, NETWORK_AXIS):
        observed[page_size] = _q_svc(committed_engine, auth_session_factory, page_size)[0]
        http[page_size] = _q_http(committed_engine, client, page_size)[0]
    print("F039-BASELINE-N-AXIS", observed)
    print("F039-BASELINE-HTTP", http)
    print("F039-BASELINE-DELTA", {k: http[k] - observed[k] for k in observed})
    assert observed[1] != observed[NETWORK_AXIS]


def test_baseline_pool_axis(role_client_factory, auth_session_factory, committed_engine):
    client, _, _ = role_client_factory("EDITOR", username="f039.base.p")
    cluster = _cluster(client, code="C1")
    network = _network(
        client, cluster["code"], name="n1", cidr="10.0.0.0/24", gateway="10.0.0.1"
    )
    observed = {}
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
        observed[pool_count] = _q_svc(committed_engine, auth_session_factory, 1)[0]
    print("F039-BASELINE-P-AXIS", observed)
    assert len(set(observed.values())) > 1


def test_baseline_capacity_endpoint(role_client_factory, auth_session_factory, committed_engine):
    from integration.test_f039_query_count import _count_selects

    client, _, _ = role_client_factory("EDITOR", username="f039.base.e")
    cluster = _cluster(client, code="C1")
    network = _network(
        client, cluster["code"], name="n1", cidr="10.0.0.0/24", gateway="10.0.0.1"
    )
    http_observed = {}
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
        http_observed[pool_count] = len(statements)
    print("F039-BASELINE-F010-HTTP", http_observed)
