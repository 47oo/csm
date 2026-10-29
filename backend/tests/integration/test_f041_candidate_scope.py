"""F041 candidate completeness — module B (§23.2 row-level scope; real scope).

Covers TD-F041-1 §1.6 cases I-11, I-12, I-13 (VIEW_DELETED part) and I-15 under
the **production** access scope: candidates come from the existing list
endpoints, whose ``items`` *and* ``total`` share one scope predicate, so the
truncation hint (`total` vs loaded rows) can only ever count visible objects.

This module declares ``pytest.mark.real_scope`` (see ``tests/conftest.py`` and
``test_f030_test_harness.py``): without it the assertions would run against the
legacy unrestricted shim and say nothing about §23.2.
"""

from __future__ import annotations

import pytest

from integration.f015_helpers import create_cluster, role_client_factory  # noqa: F401
from integration.f041_helpers import (
    CLUSTERS,
    CLUSTER_CANDIDATE_PARAMS,
    HOST_CANDIDATE_PARAMS,
    RESOURCES,
    cluster_code,
    field_names,
    page_of,
    seed_bare_metal_hosts,
    seed_clusters,
)

pytestmark = pytest.mark.real_scope

VISIBLE_COUNT = 3
TOTAL_CLUSTERS = 120
VISIBLE_HOSTS = 120
HIDDEN_HOSTS = 30


def _grant(admin, user_id, cluster_id) -> None:
    resp = admin.post(
        f"/api/v1/users/{user_id}/cluster-authorizations",
        json={"cluster_id": str(cluster_id)},
    )
    assert resp.status_code == 201, resp.text


@pytest.fixture
def scoped(committed_engine, role_client_factory):
    """120 Clusters; C1 has 120 Hosts, the ungranted C4 has 30; EDITOR gets C1..C3."""
    seed_clusters(committed_engine, count=TOTAL_CLUSTERS)
    seed_bare_metal_hosts(committed_engine, cluster_code(1), count=VISIBLE_HOSTS)
    seed_bare_metal_hosts(
        committed_engine, cluster_code(4), count=HIDDEN_HOSTS, prefix="f41u"
    )

    admin, _, _ = role_client_factory("ADMIN", username="f041.b.admin")
    editor, editor_user, _ = role_client_factory("EDITOR", username="f041.b.editor")

    granted = []
    for index in range(1, VISIBLE_COUNT + 1):
        body = page_of(admin, CLUSTERS, {"q": cluster_code(index), "page_size": 100})
        assert body["total"] == 1, (index, body["total"])
        cluster_id = body["items"][0]["id"]
        _grant(admin, editor_user.id, cluster_id)
        granted.append({"id": cluster_id, "code": cluster_code(index)})

    return {"admin": admin, "editor": editor, "granted": granted}


def test_i11_editor_candidates_and_total_count_only_visible_objects(scoped):
    """I-11/A6: `total`/`items` cover only granted Clusters (3 of 120)."""
    editor = scoped["editor"]
    granted = scoped["granted"]

    clusters = page_of(editor, CLUSTERS, CLUSTER_CANDIDATE_PARAMS)
    assert clusters["total"] == VISIBLE_COUNT, clusters["total"]
    assert [item["id"] for item in clusters["items"]] == [c["id"] for c in granted]
    assert len(clusters["items"]) == clusters["total"]  # no truncation semantics

    hidden = page_of(editor, CLUSTERS, {**CLUSTER_CANDIDATE_PARAMS, "q": cluster_code(10)})
    assert hidden["total"] == 0 and hidden["items"] == []
    assert cluster_code(10) not in str(hidden)

    visible = page_of(
        editor, CLUSTERS, {**CLUSTER_CANDIDATE_PARAMS, "q": cluster_code(2).lower()}
    )
    assert visible["total"] == 1
    assert visible["items"][0]["id"] == granted[1]["id"]

    hosts = page_of(
        editor, RESOURCES, {**HOST_CANDIDATE_PARAMS, "cluster_id": granted[0]["id"]}
    )
    assert hosts["total"] == VISIBLE_HOSTS, hosts["total"]
    assert len(hosts["items"]) == 100
    assert hosts["total"] > len(hosts["items"])

    # unscoped candidate read: the 30 Hosts of the ungranted Cluster are invisible
    unscoped = {k: v for k, v in HOST_CANDIDATE_PARAMS.items() if k != "cluster_id"}
    everything = page_of(editor, RESOURCES, unscoped)
    assert everything["total"] == VISIBLE_HOSTS, everything["total"]

    admin_everything = page_of(scoped["admin"], RESOURCES, unscoped)
    assert admin_everything["total"] == VISIBLE_HOSTS + HIDDEN_HOSTS, admin_everything["total"]


def test_i12_editor_write_into_ungranted_cluster_is_rejected(scoped):
    """I-12/A6/A10: out-of-scope Cluster reference stays 422 `cluster` (no leak)."""
    editor = scoped["editor"]
    resp = editor.post(
        "/api/v1/resources",
        json={
            "cluster": cluster_code(10),
            "hostname": "f41-out-of-scope-host",
            "resource_type": "BARE_METAL",
        },
    )
    assert resp.status_code == 422, resp.text
    assert field_names(resp)[0] == "cluster"
    assert cluster_code(10) not in resp.text


def test_i13_editor_cannot_request_deleted_objects(scoped):
    """I-13/A5/A10: `deleted=include` needs VIEW_DELETED -> 403 for an EDITOR."""
    editor = scoped["editor"]
    for path in (RESOURCES, CLUSTERS):
        resp = editor.get(path, params={"deleted": "include", "page_size": 100})
        assert resp.status_code == 403, (path, resp.text)
        assert resp.json()["error"]["code"] == "FORBIDDEN"
        assert resp.json()["error"]["details"]["reason"] == "permission"

        only = editor.get(path, params={"deleted": "only", "page_size": 100})
        assert only.status_code == 403, (path, only.text)


def test_i15_truncation_inputs_are_scoped(scoped):
    """I-15/A9: `total > items.length == page_size` holds and counts visible rows only."""
    editor = scoped["editor"]
    hosts = page_of(
        editor,
        RESOURCES,
        {**HOST_CANDIDATE_PARAMS, "cluster_id": scoped["granted"][0]["id"]},
    )
    assert hosts["total"] == VISIBLE_HOSTS
    assert len(hosts["items"]) == hosts["page_size"] == 100
    assert hosts["total"] > len(hosts["items"])  # -> the picker shows a truncation hint

    clusters = page_of(editor, CLUSTERS, CLUSTER_CANDIDATE_PARAMS)
    assert clusters["total"] == len(clusters["items"]) == VISIBLE_COUNT  # no hint
