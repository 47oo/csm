"""F041 candidate completeness — module A (real PostgreSQL, production app).

Covers TD-F041-1 §1.6 cases I-01..I-10, I-13 (anonymous/VIEWER part),
I-14, I-16, I-17: candidate search over the **existing** list endpoints
(``GET /api/v1/resources`` with ``cluster_id``/``type``/``q``/``page``/
``page_size``/``sort``/``order``; ``GET /api/v1/clusters``), the ≥101 rank
judgement, the submission-accepted facts (HTTP 201 + response + DB row + T19
audit) and the unchanged rejection semantics.

This module deliberately does **not** declare ``pytest.mark.real_scope``: it
runs under the legacy unrestricted AccessScope shim (``tests/conftest.py``), so
it says nothing about §23.2 row-level scope — that is
``test_f041_candidate_scope.py`` (module B, ``real_scope``).

F041 adds no endpoint, query parameter or error code (A11): every assertion
below goes through production code that already existed at ``d5c0a4c``.
"""

from __future__ import annotations

import uuid

import pytest

from integration.f015_helpers import (  # noqa: F401
    create_cluster,
    create_resource,
    role_client_factory,
)
from integration.f041_helpers import (
    CLUSTERS,
    CLUSTER_CANDIDATE_PARAMS,
    HOST_CANDIDATE_PARAMS,
    RESOURCES,
    cluster_code,
    field_names,
    first_page_ids,
    host_name,
    id_by_query,
    page_of,
    rank_by_server_order,
    resource_cluster_id,
    seed_bare_metal_hosts,
    seed_clusters,
    table_count,
    vm_host_resource_id,
)


@pytest.fixture
def seeded(committed_engine):
    """150 Clusters + 150 same-Cluster BARE_METAL Hosts (deterministic names)."""
    seed_clusters(committed_engine)
    seed_bare_metal_hosts(committed_engine, cluster_code(1))
    return committed_engine


@pytest.fixture
def admin(role_client_factory):
    client, user, _ = role_client_factory("ADMIN", username="f041.a.admin")
    return client


def _c1_id(client) -> str:
    return id_by_query(client, CLUSTERS, CLUSTER_CANDIDATE_PARAMS, cluster_code(1))


def _host_params(cluster_id: str) -> dict:
    return {**HOST_CANDIDATE_PARAMS, "cluster_id": cluster_id}


# --- A1 / I-01..I-03: rank >= 101 exists and is reachable by server search ----


def test_i01_host_rank_beyond_first_page_is_searchable(seeded, admin):
    """I-01: host sorted at rank >= 101 is not on page 1 but is found by `q`."""
    cluster_id = _c1_id(admin)
    params = _host_params(cluster_id)
    target_id = id_by_query(admin, RESOURCES, params, host_name(110))

    page1 = page_of(admin, RESOURCES, {**params, "page": 1, "page_size": 100})
    assert page1["total"] == 150, page1["total"]
    assert target_id not in [item["id"] for item in page1["items"]]
    assert len(page1["items"]) <= 100

    rank = rank_by_server_order(admin, RESOURCES, params, target_id)
    assert rank is not None and rank >= 101, rank

    found = page_of(admin, RESOURCES, {**params, "q": host_name(110)})
    assert found["total"] >= 1
    assert found["items"][0]["id"] == target_id
    assert found["items"][0]["hostname"] == host_name(110)
    assert len(found["items"]) <= 100


def test_i02_cluster_rank_beyond_first_page_is_searchable(seeded, admin):
    """I-02: cluster sorted at rank >= 101 is not on page 1 but is found by `q`."""
    target_id = id_by_query(admin, CLUSTERS, CLUSTER_CANDIDATE_PARAMS, cluster_code(110))

    page1 = page_of(admin, CLUSTERS, CLUSTER_CANDIDATE_PARAMS)
    assert page1["total"] == 150, page1["total"]
    assert target_id not in [item["id"] for item in page1["items"]]

    rank = rank_by_server_order(admin, CLUSTERS, CLUSTER_CANDIDATE_PARAMS, target_id)
    assert rank is not None and rank >= 101, rank

    found = page_of(admin, CLUSTERS, {**CLUSTER_CANDIDATE_PARAMS, "q": cluster_code(110)})
    assert found["total"] == 1
    assert found["items"][0]["id"] == target_id
    assert found["items"][0]["code"] == cluster_code(110)


def test_i03_candidate_response_respects_single_page_limit(seeded, admin):
    """I-03/A2: the successful candidate response reports page=1, page_size=100."""
    cluster_id = _c1_id(admin)
    body = page_of(admin, RESOURCES, {**_host_params(cluster_id), "q": host_name(110)})
    assert body["page"] == 1
    assert body["page_size"] == 100
    assert len(body["items"]) <= 100

    full = page_of(admin, RESOURCES, _host_params(cluster_id))
    assert full["page_size"] == 100
    assert len(full["items"]) == 100  # total=150 > single-page limit
    assert full["total"] == 150

    clusters = page_of(admin, CLUSTERS, CLUSTER_CANDIDATE_PARAMS)
    assert clusters["page"] == 1 and clusters["page_size"] == 100
    assert len(clusters["items"]) == 100 and clusters["total"] == 150


def test_i04_page_size_above_contract_limit_is_rejected(seeded, admin):
    """I-04/A2/N4: `page_size` > 100 stays a 422; 100 stays accepted."""
    for path in (RESOURCES, CLUSTERS):
        over = admin.get(path, params={"page": 1, "page_size": 101})
        assert over.status_code == 422, (path, over.status_code, over.text[:200])
        assert over.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "page_size" in field_names(over)

        ok = admin.get(path, params={"page": 1, "page_size": 100})
        assert ok.status_code == 200
        assert ok.json()["page_size"] == 100

    # page bound is still 1-based and validated
    zero = admin.get(RESOURCES, params={"page": 0, "page_size": 100})
    assert zero.status_code == 422


# --- A1 / I-05..I-07: the server accepts a rank >= 101 selection -------------


def test_i05_create_resource_in_rank_110_cluster_is_accepted(seeded, admin, auth_session_factory):
    """I-05/A1: a Cluster found only at rank >= 101 is accepted on submit (DB row)."""
    params = CLUSTER_CANDIDATE_PARAMS
    target_id = id_by_query(admin, CLUSTERS, params, cluster_code(110))
    page1_ids = first_page_ids(admin, CLUSTERS, params)
    assert target_id not in page1_ids

    resp = admin.post(
        "/api/v1/resources",
        json={
            "cluster": cluster_code(110),
            "hostname": "f41-target-cluster-host",
            "resource_type": "BARE_METAL",
        },
    )
    assert resp.status_code == 201, resp.text
    resource = resp.json()["resource"]
    assert resource["cluster"]["id"] == target_id

    detail = admin.get(f"/api/v1/resources/{resource['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["resource"]["cluster"]["id"] == target_id

    with auth_session_factory() as session:
        assert str(resource_cluster_id(session, resource["id"])) == target_id


def test_i06_create_vm_on_rank_110_host_is_accepted(seeded, admin, auth_session_factory):
    """I-06/A1: a Host found only at rank >= 101 is accepted on submit (DB row)."""
    cluster_id = _c1_id(admin)
    params = _host_params(cluster_id)
    host_id = id_by_query(admin, RESOURCES, params, host_name(110))
    assert host_id not in first_page_ids(admin, RESOURCES, params)

    resp = admin.post(
        "/api/v1/resources",
        json={
            "cluster": cluster_code(1),
            "hostname": "f41-vm-1",
            "resource_type": "VIRTUAL_MACHINE",
            "virtual_machine": {"host_resource_id": host_id},
        },
    )
    assert resp.status_code == 201, resp.text
    vm = resp.json()["resource"]
    assert vm["virtual_machine"]["host_resource_id"] == host_id
    assert vm["virtual_machine"]["host"]["hostname"] == host_name(110)

    detail = admin.get(f"/api/v1/resources/{vm['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["resource"]["virtual_machine"]["host_resource_id"] == host_id

    with auth_session_factory() as session:
        assert str(vm_host_resource_id(session, vm["id"])) == host_id


def test_i07_rehost_from_rank_110_to_rank_120_records_t19_audit(
    seeded, admin, auth_session_factory
):
    """I-07/A16/T19: re-selecting another late-rank Host updates + audits before/after."""
    cluster_id = _c1_id(admin)
    params = _host_params(cluster_id)
    first_host = id_by_query(admin, RESOURCES, params, host_name(110))
    second_host = id_by_query(admin, RESOURCES, params, host_name(120))
    assert first_host != second_host

    created = admin.post(
        "/api/v1/resources",
        json={
            "cluster": cluster_code(1),
            "hostname": "f41-vm-rehost",
            "resource_type": "VIRTUAL_MACHINE",
            "virtual_machine": {"host_resource_id": first_host},
        },
    )
    assert created.status_code == 201, created.text
    vm_id = created.json()["resource"]["id"]

    patched = admin.patch(
        f"/api/v1/resources/{vm_id}",
        json={"version": 1, "virtual_machine": {"host_resource_id": second_host}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["resource"]["virtual_machine"]["host_resource_id"] == second_host
    assert patched.json()["resource"]["virtual_machine"]["host"]["hostname"] == host_name(120)

    with auth_session_factory() as session:
        assert str(vm_host_resource_id(session, vm_id)) == second_host

    activity = admin.get(f"/api/v1/resources/{vm_id}/activity")
    assert activity.status_code == 200, activity.text
    rows = activity.json()["items"]
    assert [row["action"] for row in rows] == ["CREATE", "UPDATE"], rows
    update = rows[1]
    assert update["after_data"]["virtual_machine"]["host_resource_id"] == second_host
    assert update["before_data"]["virtual_machine"]["host_resource_id"] == first_host


# --- A2/A5 / I-08: existing filters still shape the candidate set ------------


def test_i08_cluster_and_type_filters_bound_the_candidate_set(seeded, admin):
    """I-08: `cluster_id` + `type=BARE_METAL` exclude other clusters and VMs."""
    cluster_id = _c1_id(admin)
    other = create_cluster(admin, "F41C-OTHER", "F041 other cluster")
    other_bare = create_resource(admin, other["code"], "f41-other-host")

    bare_c1 = id_by_query(admin, RESOURCES, _host_params(cluster_id), host_name(1))
    vm_resp = admin.post(
        "/api/v1/resources",
        json={
            "cluster": cluster_code(1),
            "hostname": "f41-vm-filter",
            "resource_type": "VIRTUAL_MACHINE",
            "virtual_machine": {"host_resource_id": bare_c1},
        },
    )
    assert vm_resp.status_code == 201, vm_resp.text
    vm_id = vm_resp.json()["resource"]["id"]

    candidates = page_of(admin, RESOURCES, _host_params(cluster_id))
    assert candidates["total"] == 150, candidates["total"]
    assert all(item["resource_type"] == "BARE_METAL" for item in candidates["items"])
    assert all(item["cluster"]["id"] == cluster_id for item in candidates["items"])
    assert vm_id not in [item["id"] for item in candidates["items"]]
    assert other_bare["id"] not in [item["id"] for item in candidates["items"]]

    # same cluster without the type filter really contains the VM -> the type
    # filter is what keeps it out of the candidate set
    everything = page_of(
        admin, RESOURCES, {"cluster_id": cluster_id, "page": 1, "page_size": 100}
    )
    assert everything["total"] == 151, everything["total"]


# --- A5 / I-09..I-10: soft delete is excluded and rejected on submit ---------


def test_i09_soft_deleted_objects_are_not_candidates(seeded, admin):
    """I-09/A5: soft-deleted Host/Cluster are unreachable by default (exclude)."""
    cluster_id = _c1_id(admin)
    params = _host_params(cluster_id)
    victim_id = id_by_query(admin, RESOURCES, params, host_name(115))
    deleted = admin.delete(f"/api/v1/resources/{victim_id}", params={"version": 1})
    assert deleted.status_code == 204, deleted.text

    scoped_params = dict(params)
    scoped_params["q"] = host_name(115)
    after = page_of(admin, RESOURCES, scoped_params)
    assert after["total"] == 0 and after["items"] == []

    # explicit/default exclude agree: the deleted row is not silently included
    default_ids = first_page_ids(admin, RESOURCES, params)
    explicit_ids = first_page_ids(admin, RESOURCES, {**params, "deleted": "exclude"})
    assert default_ids == explicit_ids
    assert victim_id not in default_ids

    # ADMIN (VIEW_DELETED) can still see it only when asking for it
    included = page_of(admin, RESOURCES, {**params, "q": host_name(115), "deleted": "include"})
    assert included["total"] == 1
    assert included["items"][0]["id"] == victim_id

    # a soft-deleted Cluster leaves the Cluster candidate set the same way
    doomed = create_cluster(admin, "F41C-DOOMED", "F041 doomed cluster")
    assert admin.delete(f"/api/v1/clusters/{doomed['id']}", params={"version": 1}).status_code == 204
    gone = page_of(admin, CLUSTERS, {**CLUSTER_CANDIDATE_PARAMS, "q": "F41C-DOOMED"})
    assert gone["total"] == 0 and gone["items"] == []


def test_i10_submit_with_soft_deleted_host_is_rejected(seeded, admin):
    """I-10/A5/A10: the picker cannot smuggle a soft-deleted Host past the server."""
    cluster_id = _c1_id(admin)
    host_id = id_by_query(admin, RESOURCES, _host_params(cluster_id), host_name(116))
    assert admin.delete(f"/api/v1/resources/{host_id}", params={"version": 1}).status_code == 204

    resp = admin.post(
        "/api/v1/resources",
        json={
            "cluster": cluster_code(1),
            "hostname": "f41-vm-deleted-host",
            "resource_type": "VIRTUAL_MACHINE",
            "virtual_machine": {"host_resource_id": host_id},
        },
    )
    assert resp.status_code == 422, resp.text
    assert field_names(resp)[0] == "virtual_machine.host_resource_id"


# --- A10 / I-13..I-14: unchanged rejection semantics -------------------------


def test_i13_auth_and_permission_errors_precede_candidate_semantics(
    seeded, admin, role_client_factory
):
    """I-13: 401 for anonymous, 403 for a read-only role, 404 for unknown ids."""
    from fastapi.testclient import TestClient

    # anonymous: authentication is evaluated before query validation
    anonymous = TestClient(admin.app, raise_server_exceptions=False)
    anonymous.__enter__()
    try:
        resp = anonymous.get(RESOURCES, params={"page_size": 101})
        assert resp.status_code == 401, resp.text
        assert resp.json()["error"]["code"] == "AUTH_REQUIRED"
        resp = anonymous.get(CLUSTERS)
        assert resp.status_code == 401, resp.text
    finally:
        anonymous.__exit__(None, None, None)

    viewer, _, _ = role_client_factory("VIEWER", username="f041.a.viewer")
    resp = viewer.post("/api/v1/resources", json={"unknown": 1})
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "FORBIDDEN"
    assert resp.json()["error"]["details"]["reason"] == "permission"

    # read-only roles still get candidates (READ), with no write side effect
    assert viewer.get(RESOURCES, params={"page_size": 1}).status_code == 200

    missing = admin.get(f"{CLUSTERS}/{uuid.uuid4()}")
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_i14_invalid_host_references_keep_their_existing_errors(seeded, admin):
    """I-14/A10: cross-Cluster / VM-typed / unknown Host stay 422; name clash 409."""
    cluster_id = _c1_id(admin)
    params = _host_params(cluster_id)
    other = create_cluster(admin, "F41C-OTHER", "F041 other cluster")
    other_bare = create_resource(admin, other["code"], "f41-other-host")
    bare_c1 = id_by_query(admin, RESOURCES, params, host_name(1))

    vm = admin.post(
        "/api/v1/resources",
        json={
            "cluster": cluster_code(1),
            "hostname": "f41-vm-typed",
            "resource_type": "VIRTUAL_MACHINE",
            "virtual_machine": {"host_resource_id": bare_c1},
        },
    )
    assert vm.status_code == 201, vm.text
    vm_id = vm.json()["resource"]["id"]

    cases = {
        "cross-cluster": other_bare["id"],
        "vm-typed": vm_id,
        "unknown": str(uuid.uuid4()),
    }
    for label, host_id in cases.items():
        resp = admin.post(
            "/api/v1/resources",
            json={
                "cluster": cluster_code(1),
                "hostname": f"f41-vm-{label}",
                "resource_type": "VIRTUAL_MACHINE",
                "virtual_machine": {"host_resource_id": host_id},
            },
        )
        assert resp.status_code == 422, (label, resp.text)
        assert field_names(resp)[0] == "virtual_machine.host_resource_id", label

    conflict = admin.post(
        "/api/v1/resources",
        json={
            "cluster": cluster_code(1),
            "hostname": host_name(1),
            "resource_type": "BARE_METAL",
        },
    )
    assert conflict.status_code == 409, conflict.text
    error = conflict.json()["error"]
    assert error["code"] == "CONFLICT"
    assert error["details"]["reason"] == "unique_conflict"
    assert error["details"]["field"] == "hostname"


# --- A12 / I-16: `q` is still a case-insensitive substring -----------------


def test_i16_q_stays_case_insensitive_substring(seeded, admin):
    """I-16/A12: literal/case/middle-substring `q`; candidate == list semantics."""
    cluster_id = _c1_id(admin)
    params = _host_params(cluster_id)

    exact = page_of(admin, RESOURCES, {**params, "q": host_name(110)})
    upper = page_of(admin, RESOURCES, {**params, "q": host_name(110).upper()})
    middle = page_of(admin, RESOURCES, {**params, "q": "n-0110"})
    for body in (exact, upper, middle):
        assert body["total"] == 1, body["total"]
        assert body["items"][0]["hostname"] == host_name(110)

    broad = page_of(admin, RESOURCES, {**params, "q": "n-01"})
    assert broad["total"] >= 10, broad["total"]
    assert all("n-01" in item["hostname"] for item in broad["items"])

    # Clusters: `q` matches code or name, still ILIKE
    by_code = page_of(admin, CLUSTERS, {**CLUSTER_CANDIDATE_PARAMS, "q": cluster_code(110).lower()})
    assert by_code["total"] == 1
    assert by_code["items"][0]["code"] == cluster_code(110)
    by_middle = page_of(admin, CLUSTERS, {**CLUSTER_CANDIDATE_PARAMS, "q": "bulk cluster 11"})
    assert by_middle["total"] >= 1

    # the candidate request and a same-parameter list page agree on `total`
    candidate = page_of(admin, RESOURCES, {**params, "q": "n-01"})
    plain = page_of(
        admin,
        RESOURCES,
        {
            "cluster_id": cluster_id,
            "type": "BARE_METAL",
            "q": "n-01",
            "page": 1,
            "page_size": 100,
        },
    )
    assert candidate["total"] == plain["total"]


# --- A15 / I-17: candidate reads have no write side effect -----------------


def test_i17_candidate_reads_write_no_audit(seeded, admin, auth_session_factory):
    """I-17/A15 (§22): reading candidates never appends audit rows."""
    cluster_id = _c1_id(admin)
    host_params = _host_params(cluster_id)

    with auth_session_factory() as session:
        before_audit = table_count(session, "audit_logs")
        before_resources = table_count(session, "resources")

    for _ in range(5):
        assert page_of(admin, RESOURCES, host_params)["total"] == 150
        assert page_of(admin, RESOURCES, {**host_params, "q": host_name(110)})["total"] == 1
        assert page_of(admin, CLUSTERS, CLUSTER_CANDIDATE_PARAMS)["total"] == 150

    with auth_session_factory() as session:
        assert table_count(session, "audit_logs") == before_audit
        assert table_count(session, "resources") == before_resources
