"""Shared fixtures/helpers for the F041 candidate-completeness tests.

Not a test module (no ``test_`` prefix). It provides:

* deterministic bulk seeding (``INSERT ... SELECT generate_series``) of
  ≥101 Clusters and ≥101 same-Cluster ``BARE_METAL`` Hosts, so the object
  pickers must be able to reach candidates whose *server-side* sort rank is
  ≥101 (TD-F041-1 §1.5, ON-3);
* ``rank_by_server_order`` — derives the 1-based rank of a target object by
  walking the **existing** list endpoint with ``page_size=100``, so no rank,
  UUID or ``created_at`` value is hard-coded (TD §1.6 判定口径);
* small database helpers used to cross-check "the server accepted the
  submission" (rows in ``resources`` / ``virtual_machine_details``) and
  "candidate reads have no write side effect" (``audit_logs`` count).

Seeding writes go straight to the dedicated test database (`csm_f037_test`,
guarded by ``tests/conftest.py``); every row satisfies the existing CHECK/FK
constraints, and cleanup relies on the existing ``committed_engine`` teardown
(TRUNCATE of every non-``alembic_version`` table). No production code and no
schema is touched (F041 architecture DR-F041-09 / §4).
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

# Bulk fixture size: 150 so that two far-from-boundary targets exist (rank 110
# for "search -> select -> submit", rank 120 for "change host") and page=2 is a
# full 50-row window (TD-F041-1 §1.5).
BULK_CLUSTER_COUNT = 150
BULK_HOST_COUNT = 150

CLUSTER_PREFIX = "F41C"
HOST_PREFIX = "f41n"

# Existing list endpoints only — F041 adds no endpoint/parameter (N1/A11).
RESOURCES = "/api/v1/resources"
CLUSTERS = "/api/v1/clusters"

# Candidate query parameter sets, exactly as architecture §1.2 defines them.
HOST_CANDIDATE_PARAMS = {
    "type": "BARE_METAL",
    "page": 1,
    "page_size": 100,
    "sort": "hostname",
    "order": "asc",
}
CLUSTER_CANDIDATE_PARAMS = {
    "page": 1,
    "page_size": 100,
    "sort": "code",
    "order": "asc",
}


def cluster_code(index: int, prefix: str = CLUSTER_PREFIX) -> str:
    return f"{prefix}-{index:04d}"


def host_name(index: int, prefix: str = HOST_PREFIX) -> str:
    return f"{prefix}-{index:04d}"


# --- bulk seeding (real PostgreSQL, test database only) ----------------------


def seed_clusters(engine, count: int = BULK_CLUSTER_COUNT, prefix: str = CLUSTER_PREFIX) -> None:
    """Insert ``count`` Clusters ``<prefix>-0001..`` with deterministic keys.

    ``code_key`` mirrors ``translate(code, 'a-z', 'A-Z')`` (the migration CHECK),
    so ``sort=code`` order equals the code order.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clusters (code, code_key, name, status) "
                "SELECT :prefix || '-' || lpad(g::text, 4, '0'), "
                "       :prefix || '-' || lpad(g::text, 4, '0'), "
                "       'F041 bulk cluster ' || g, "
                "       'ACTIVE' "
                "FROM generate_series(1, :count) AS g"
            ),
            {"prefix": prefix, "count": count},
        )


def seed_bare_metal_hosts(
    engine,
    cluster: str,
    count: int = BULK_HOST_COUNT,
    prefix: str = HOST_PREFIX,
) -> None:
    """Insert ``count`` ``BARE_METAL`` Hosts ``<prefix>-0001..`` into ``cluster``.

    ``hostname_key`` mirrors ``translate(btrim(hostname), 'A-Z', 'a-z')``, so
    ``sort=hostname`` order equals the hostname order.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO resources "
                "  (cluster_id, hostname, hostname_key, resource_type, role, status) "
                "SELECT (SELECT id FROM clusters WHERE code = :cluster), "
                "       :prefix || '-' || lpad(g::text, 4, '0'), "
                "       :prefix || '-' || lpad(g::text, 4, '0'), "
                "       'BARE_METAL', 'COMPUTE', 'IDLE' "
                "FROM generate_series(1, :count) AS g"
            ),
            {"cluster": cluster, "prefix": prefix, "count": count},
        )


def seed_cluster_with_hosts(
    engine,
    code: str,
    host_count: int,
    host_prefix: str,
    name: str = "F041 bulk cluster",
) -> None:
    """Insert one Cluster (API-equivalent columns) plus ``host_count`` Hosts."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clusters (code, code_key, name, status) "
                "VALUES (:code, :code_key, :name, 'ACTIVE')"
            ),
            {"code": code, "code_key": code.upper(), "name": name},
        )
    seed_bare_metal_hosts(engine, code, count=host_count, prefix=host_prefix)


# --- server-ordered rank / page helpers -------------------------------------


def _get(client, path: str, params: dict) -> dict:
    resp = client.get(path, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def page_of(client, path: str, params: dict | None = None) -> dict:
    """One list request with the given parameters (defaults: candidate page 1)."""
    return _get(client, path, dict(params or {}))


def items_of(client, path: str, params: dict | None = None) -> list[dict]:
    return page_of(client, path, params)["items"]


def rank_by_server_order(
    client,
    path: str,
    params: dict,
    target_id: str,
    page_size: int = 100,
    max_pages: int = 50,
) -> int | None:
    """1-based rank of ``target_id`` in the server's own list ordering.

    Walks the existing list endpoint page by page (``page_size`` capped at the
    contract limit) in the given ``sort``/``order``; returns ``None`` when the
    target is not in the visible result set at all.
    """
    seen = 0
    for page in range(1, max_pages + 1):
        query = dict(params)
        query.update({"page": page, "page_size": page_size})
        body = _get(client, path, query)
        items = body["items"]
        for offset, item in enumerate(items):
            if item["id"] == target_id:
                return seen + offset + 1
        seen += len(items)
        if not items or seen >= body["total"]:
            return None
    return None


def id_by_query(client, path: str, params: dict, q: str) -> str:
    """Resolve the target id via server-side search (never a hard-coded UUID)."""
    query = dict(params)
    query["q"] = q
    body = _get(client, path, query)
    assert body["total"] == 1, (q, body["total"])
    return body["items"][0]["id"]


def first_page_ids(client, path: str, params: dict) -> list[str]:
    query = dict(params)
    query.update({"page": 1, "page_size": 100})
    return [item["id"] for item in _get(client, path, query)["items"]]


# --- database cross-checks --------------------------------------------------


def table_count(session, table: str) -> int:
    return int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def resource_cluster_id(session, resource_id: str) -> uuid.UUID:
    return session.execute(
        text("SELECT cluster_id FROM resources WHERE id = :id"),
        {"id": uuid.UUID(str(resource_id))},
    ).scalar_one()


def vm_host_resource_id(session, resource_id: str) -> uuid.UUID:
    return session.execute(
        text("SELECT host_resource_id FROM virtual_machine_details WHERE resource_id = :id"),
        {"id": uuid.UUID(str(resource_id))},
    ).scalar_one()


def field_names(resp) -> list[str]:
    """Extract ``error.details.fields[*].field`` from an error envelope."""
    return [
        field.get("field")
        for field in resp.json().get("error", {}).get("details", {}).get("fields", [])
    ]
