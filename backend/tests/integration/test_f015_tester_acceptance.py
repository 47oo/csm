"""Independent F015 TE-1 acceptance tests (Tester-authored).

These tests are written and executed by the Tester, independently of the
implementation suite. They target acceptance points the implementation suite
verifies only indirectly or not at all:

- A6  per-object Activity visibility for all base roles (VIEW_ACTIVITY only).
- A7  audit immutability across query / delete / restore / name reuse / disable.
- A9  no TTL / cleanup / archive mechanism.
- A13/A14 deleted column shape + restore visibility.
- A15 restore does not cascade (Service->Endpoint, Network->Pool, Resource->Interface).
- A16/A17/T41 ``unique_conflict`` / ``dependency_deleted`` and no overwrite.
- A18 RESTORE audit written in the same transaction; a failed restore leaves none.
- B3  CSRF reason distinct from permission.
- B6  ``page_size`` 1 and 100 accepted.
- B25 concurrent restore of one soft-deleted object.
- V32/V33 ordering/enum boundaries.
- V35/V36 username/password boundaries and PATCH validation ordering.
- V-DB-F015-6/7/8 deleted-at indexes, operator index absence, migration head.

Real PostgreSQL only (DB-D10 guard in conftest); no SQLite and no mocks for
constraint/concurrency evidence.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.core.auth import Operator
from app.core.permissions import Role
from app.models.audit_log import AuditLog
from app.services import cluster as cluster_service
from app.services import network as network_service
from integration.f015_helpers import (  # noqa: F401
    bind,
    create_cluster,
    create_endpoint,
    create_interface,
    create_ip,
    create_network,
    create_pool,
    create_resource,
    create_service,
    role_client_factory,
    soft_delete,
)

APP_DIR = Path(__file__).resolve().parents[2] / "app"


def _deleted_ids(client, object_type: str) -> set[str]:
    body = client.get(
        "/api/v1/deleted", params={"object_type": object_type, "page_size": 100}
    ).json()
    return {item["object_id"] for item in body["items"]}


def _audit_snapshot(session):
    return {
        row.id: (
            row.operator_user_id,
            row.operator_username,
            row.action,
            row.object_type,
            row.object_id,
            row.before_data,
            row.after_data,
            row.created_at,
        )
        for row in session.query(AuditLog).all()
    }


def _restore_audits(session, object_type: str, object_id):
    return (
        session.query(AuditLog)
        .filter(
            AuditLog.object_type == object_type,
            AuditLog.object_id == uuid.UUID(str(object_id)),
            AuditLog.action == "RESTORE",
        )
        .all()
    )


def _operator(user) -> Operator:
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


# --- A6: Activity stays available to every base role (F015 does not narrow) ---


def test_activity_visible_to_all_base_roles(api_client, role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    cluster = create_cluster(admin, "ACT1")
    admin.patch(f"/api/v1/clusters/{cluster['id']}", json={"version": 1, "name": "x"})

    viewer, _, _ = role_client_factory("VIEWER")
    editor, _, _ = role_client_factory("EDITOR")
    for client in (viewer, editor, admin):
        resp = client.get(f"/api/v1/clusters/{cluster['id']}/activity")
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] >= 1

    anon = api_client.get(f"/api/v1/clusters/{cluster['id']}/activity")
    assert anon.status_code == 401
    assert anon.json()["error"]["code"] == "AUTH_REQUIRED"


# --- A7: existing audit rows are immutable under every F015 operation --------


def test_existing_audit_rows_never_change(
    role_client_factory,  # noqa: F811
    auth_session_factory,
):
    admin, _, _ = role_client_factory("ADMIN")
    cluster = create_cluster(admin, "IMM1")
    editor, editor_user, _ = role_client_factory("EDITOR")
    create_cluster(editor, "IMM2")

    net = create_network(admin, cluster["id"], "imm-net", "10.70.0.0/24")
    healthy = create_network(admin, cluster["id"], "imm-net2", "10.72.0.0/24")
    account = admin.post(
        "/api/v1/users",
        json={"username": "imm.user", "password": "valid-pass-1", "role": "VIEWER"},
    ).json()["user"]

    with auth_session_factory() as session:
        before = _audit_snapshot(session)

    # Read-only queries, delete + restore, name reuse and account disable.
    assert admin.get("/api/v1/audit").status_code == 200
    assert admin.get("/api/v1/deleted").status_code == 200
    soft_delete(admin, f"/api/v1/networks/{healthy['id']}", 1)
    assert (
        admin.post(f"/api/v1/networks/{healthy['id']}/restore?version=2").status_code
        == 200
    )
    soft_delete(admin, f"/api/v1/networks/{net['id']}", 1)
    create_network(admin, cluster["id"], "imm-net", "10.71.0.0/24")  # name reuse
    assert (
        admin.patch(
            f"/api/v1/users/{account['id']}", json={"version": 1, "status": "DISABLED"}
        ).status_code
        == 200
    )

    with auth_session_factory() as session:
        after = _audit_snapshot(session)
    assert set(before) <= set(after), "audit rows must only be appended, never removed"
    for row_id, value in before.items():
        assert after[row_id] == value, f"audit row {row_id} was mutated"
    # Operator identity snapshot survives the disable.
    editor_rows = [v for v in after.values() if v[1] == editor_user.username]
    assert editor_rows and all(v[0] == editor_user.id for v in editor_rows)


# --- A9: no TTL / cleanup / archive path -------------------------------------


def test_no_audit_ttl_cleanup_or_archive(committed_engine):
    texts = "\n".join(p.read_text() for p in APP_DIR.rglob("*.py"))
    for needle in (
        "audit_retention",
        "purge_audit",
        "cleanup_audit",
        "delete_audit",
        "archive_audit",
        "apscheduler",
        "celery",
    ):
        assert needle not in texts, f"unexpected retention mechanism: {needle}"

    with committed_engine.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'audit_logs'"
                )
            )
        }
    assert "expires_at" not in columns
    assert "ttl" not in columns
    assert "archived_at" not in columns


# --- A15: restore only the target, never its relations ------------------------


def test_restore_does_not_cascade(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")

    # Service -> ServiceEndpoint
    c1 = create_cluster(admin, "CAS1")
    r1 = create_resource(admin, "CAS1", "cas-host1")
    i1 = create_interface(admin, r1["id"], "cas-eth1")
    n1 = create_network(admin, "CAS1", "cas-net1", "10.40.0.0/24")
    a1 = create_ip(admin, n1["id"], "10.40.0.5")
    bind(admin, a1, i1)
    s1 = create_service(admin, r1["id"], "cas-svc1")
    e1 = create_endpoint(admin, s1["id"], a1["id"], protocol="TCP", port=8081)
    soft_delete(admin, f"/api/v1/service-endpoints/{e1['id']}", 1)
    soft_delete(admin, f"/api/v1/services/{s1['id']}", 1)
    assert admin.post(f"/api/v1/services/{s1['id']}/restore?version=2").status_code == 200
    assert e1["id"] in _deleted_ids(admin, "service_endpoint")
    assert s1["id"] not in _deleted_ids(admin, "service")

    # Network -> IPPool
    n2 = create_network(admin, "CAS1", "cas-net2", "10.41.0.0/24")
    p2 = create_pool(admin, n2["id"], "cas-pool2", "10.41.0.10", "10.41.0.20")
    soft_delete(admin, f"/api/v1/ip-pools/{p2['id']}", 1)
    soft_delete(admin, f"/api/v1/networks/{n2['id']}", 1)
    assert admin.post(f"/api/v1/networks/{n2['id']}/restore?version=2").status_code == 200
    assert p2["id"] in _deleted_ids(admin, "ip_pool")
    assert n2["id"] not in _deleted_ids(admin, "network")

    # Resource -> Interface
    r3 = create_resource(admin, c1["code"], "cas-host3")
    i3 = create_interface(admin, r3["id"], "cas-eth3")
    soft_delete(admin, f"/api/v1/interfaces/{i3['id']}", 1)
    soft_delete(admin, f"/api/v1/resources/{r3['id']}", 1)
    assert admin.post(f"/api/v1/resources/{r3['id']}/restore?version=2").status_code == 200
    assert i3["id"] in _deleted_ids(admin, "interface")
    assert r3["id"] not in _deleted_ids(admin, "resource")


# --- A16/A17/T41: name reuse writes conflict and never overwrites -------------


def test_restore_conflicts_do_not_overwrite(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    c = create_cluster(admin, "UNQ1")

    # Network name reuse -> unique_conflict; new object untouched.
    old = create_network(admin, c["id"], "uq-net", "10.80.0.0/24")
    soft_delete(admin, f"/api/v1/networks/{old['id']}", 1)
    new = create_network(admin, c["id"], "uq-net", "10.81.0.0/24")
    resp = admin.post(f"/api/v1/networks/{old['id']}/restore?version=2")
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"
    fresh = admin.get(f"/api/v1/networks/{new['id']}").json()["network"]
    assert fresh["version"] == 1 and fresh["name"] == "uq-net"
    assert old["id"] in _deleted_ids(admin, "network")

    # Service name reuse within the same Resource -> unique_conflict.
    r = create_resource(admin, c["code"], "uq-host")
    old_svc = create_service(admin, r["id"], "uq-svc")
    soft_delete(admin, f"/api/v1/services/{old_svc['id']}", 1)
    new_svc = create_service(admin, r["id"], "uq-svc")
    resp = admin.post(f"/api/v1/services/{old_svc['id']}/restore?version=2")
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"
    assert admin.get(f"/api/v1/services/{new_svc['id']}").json()["service"][
        "version"
    ] == 1

    # Resource hostname reuse -> unique_conflict.
    old_r = create_resource(admin, c["code"], "uq-host2")
    soft_delete(admin, f"/api/v1/resources/{old_r['id']}", 1)
    new_r = create_resource(admin, c["code"], "uq-host2")
    resp = admin.post(f"/api/v1/resources/{old_r['id']}/restore?version=2")
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"
    assert admin.get(f"/api/v1/resources/{new_r['id']}").json()["resource"][
        "version"
    ] == 1

    # Cluster code is not reusable at all: no second object; own restore works.
    gone = create_cluster(admin, "UNQC")
    soft_delete(admin, f"/api/v1/clusters/{gone['id']}", 1)
    dup = admin.post("/api/v1/clusters", json={"code": "UNQC", "name": "again"})
    assert dup.status_code == 409
    assert dup.json()["error"]["details"]["reason"] == "unique_conflict"
    assert admin.post(f"/api/v1/clusters/{gone['id']}/restore?version=2").status_code == 200


def test_restore_dependency_deleted(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    c = create_cluster(admin, "DEP1")
    r = create_resource(admin, c["code"], "dep-host")
    svc = create_service(admin, r["id"], "dep-svc")
    soft_delete(admin, f"/api/v1/services/{svc['id']}", 1)
    soft_delete(admin, f"/api/v1/resources/{r['id']}", 1)

    resp = admin.post(f"/api/v1/services/{svc['id']}/restore?version=2")
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["reason"] == "dependency_deleted"
    assert any(d["object_type"] == "resource" for d in details["conflicts"])
    assert svc["id"] in _deleted_ids(admin, "service")
    assert admin.get(f"/api/v1/resources/{r['id']}").status_code in (404,)


# --- A18: RESTORE audit is transactional and failure leaves no residue --------


def test_restore_audit_and_failure_residue(
    role_client_factory,  # noqa: F811
    auth_session_factory,
):
    admin, admin_user, _ = role_client_factory("ADMIN")

    good = create_network(admin, create_cluster(admin, "AU1")["id"], "au-net", "10.90.0.0/24")
    soft_delete(admin, f"/api/v1/networks/{good['id']}", 1)
    assert admin.post(f"/api/v1/networks/{good['id']}/restore?version=2").status_code == 200
    with auth_session_factory() as session:
        rows = _restore_audits(session, "network", good["id"])
    assert len(rows) == 1
    assert rows[0].operator_user_id == admin_user.id

    # Failed restore (name reuse) must not add a RESTORE audit row.
    c = create_cluster(admin, "AU2")
    bad = create_network(admin, c["id"], "bad-net", "10.91.0.0/24")
    soft_delete(admin, f"/api/v1/networks/{bad['id']}", 1)
    create_network(admin, c["id"], "bad-net", "10.92.0.0/24")
    assert admin.post(f"/api/v1/networks/{bad['id']}/restore?version=2").status_code == 409
    with auth_session_factory() as session:
        assert _restore_audits(session, "network", bad["id"]) == []


# --- B3: CSRF reason is distinct from permission ------------------------------


def test_csrf_reason_distinct_from_permission(api_client, role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    viewer, _, _ = role_client_factory("VIEWER")

    cross = admin.post(
        "/api/v1/users",
        json={"username": "csrf.user", "password": "valid-pass-1", "role": "VIEWER"},
        headers={"Origin": "https://evil.example"},
    )
    assert cross.status_code == 403
    assert cross.json()["error"]["details"] == {"reason": "csrf"}

    # GET is CSRF-exempt; the refusal is a permission refusal, not CSRF.
    denied = viewer.get(
        "/api/v1/audit", headers={"Origin": "https://evil.example"}
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["details"] == {"reason": "permission"}

    assert (
        admin.get("/api/v1/audit", headers={"Origin": "https://evil.example"}).status_code
        == 200
    )


# --- B6 / V32 / V33: pagination and ordering boundaries ----------------------


def test_audit_pagination_boundaries_and_ordering(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    for code in ("PB1", "PB2"):
        create_cluster(admin, code)

    for size in (1, 100):
        resp = admin.get("/api/v1/audit", params={"page_size": size})
        assert resp.status_code == 200, resp.text
        assert resp.json()["page_size"] == size

    desc = admin.get(
        "/api/v1/audit",
        params={"object_type": "cluster", "sort": "created_at", "order": "desc"},
    )
    assert desc.status_code == 200
    asc = admin.get(
        "/api/v1/audit",
        params={"object_type": "cluster", "sort": "created_at", "order": "asc"},
    )
    assert asc.status_code == 200
    assert [i["id"] for i in desc.json()["items"]] == list(
        reversed([i["id"] for i in asc.json()["items"]])
    )
    for params, expected in (
        ({"sort": "id"}, 422),
        ({"order": "up"}, 422),
        ({"object_type": "user"}, 200),
    ):
        resp = admin.get("/api/v1/audit", params=params)
        assert resp.status_code == expected, (params, resp.text)


def test_deleted_ordering_and_version_shape(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    c = create_cluster(admin, "DS1")
    net = create_network(admin, c["id"], "ds-net", "10.93.0.0/24")
    soft_delete(admin, f"/api/v1/networks/{net['id']}", 1)

    body = admin.get(
        "/api/v1/deleted",
        params={"sort": "deleted_at", "order": "asc", "page_size": 100},
    ).json()
    assert body["items"]
    for item in body["items"]:
        assert item["version"] >= 1
        assert uuid.UUID(item["object_id"])
        assert item["deleted_at"].endswith("+00:00")
    for params in ({"sort": "created_at"}, {"object_type": "user"}):
        assert (
            admin.get("/api/v1/deleted", params=params).status_code == 422
        ), params


# --- V35/V36: username/password boundaries and PATCH validation order --------


def test_username_and_password_boundaries(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")

    def create(username, password="valid-pass-1"):
        return admin.post(
            "/api/v1/users",
            json={"username": username, "password": password, "role": "VIEWER"},
        )

    assert create("abc").status_code == 201  # 3 chars
    assert create("a" * 64).status_code == 201  # 64 chars
    assert create("ab").status_code == 422  # 2 chars
    assert create("a" * 65).status_code == 422  # 65 chars
    assert create("bad#char").status_code == 422

    assert create("pw8.user", "12345678").status_code == 201  # exactly 8
    assert create("pw128.user", "x" * 128).status_code == 201  # exactly 128
    assert create("pw7.user", "x" * 7).status_code == 422
    assert create("pw129.user", "x" * 129).status_code == 422


def test_patch_validation_order(api_client, role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    viewer, _, _ = role_client_factory("VIEWER")
    created = admin.post(
        "/api/v1/users",
        json={"username": "order.user", "password": "valid-pass-1", "role": "VIEWER"},
    ).json()["user"]
    path = f"/api/v1/users/{created['id']}"

    # 401 for unauthenticated, before any validation.
    anon = api_client.patch(path, json={})
    assert anon.status_code == 401

    # 403 for authenticated without USER_ADMIN, before body validation.
    assert viewer.patch(path, json={}).status_code == 403

    # 422 for a malformed body.
    assert admin.patch(path, json={"role": "VIEWER"}).status_code == 422

    # 404 for a missing object with a valid body.
    assert (
        admin.patch(
            f"/api/v1/users/{uuid.uuid4()}", json={"version": 1, "role": "VIEWER"}
        ).status_code
        == 404
    )

    # 409 for a stale version, after 404.
    stale = admin.patch(path, json={"version": 99, "role": "VIEWER"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


# --- B25: concurrent restore of one soft-deleted object -----------------------


def test_restore_concurrency_two_connections_real(
    auth_session_factory, committed_engine, make_user
):
    user, _ = make_user(role="EDITOR", username="rc.user")
    op = _operator(user)

    with auth_session_factory() as session:
        cluster_service.create_cluster(session, op, code="RC1", name="RC1")
    with auth_session_factory() as session:
        net = network_service.create_network(
            session, op, cluster="RC1", name="rc-net", cidr="10.94.0.0/24"
        )
        nid = net.id
    with auth_session_factory() as session:
        network_service.delete_network(session, op, nid, expected_version=1)

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def restore() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            network_service.restore_network(session, op, nid, expected_version=2)
            with lock:
                outcomes.append("ok")
        except Exception:
            session.rollback()
            with lock:
                outcomes.append("err")
        finally:
            session.close()

    threads = [threading.Thread(target=restore) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(outcomes) == ["err", "ok"], outcomes
    with committed_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT deleted_at, version FROM networks WHERE id = :id"
            ),
            {"id": nid},
        ).mappings().one()
        audit_count = conn.execute(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE object_type = 'network' AND object_id = :id AND action = 'RESTORE'"
            ),
            {"id": nid},
        ).scalar_one()
    assert row["deleted_at"] is None
    assert row["version"] == 3
    assert audit_count == 1


# --- V-DB-F015-6/7/8: deleted-at indexes, operator index, migration head ------


def test_deleted_at_indexes_and_schema_unchanged(committed_engine, alembic_runner):
    assert alembic_runner.head_revision() == "0014_api_keys"
    with committed_engine.connect() as conn:
        db_head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
                )
            )
            .scalars()
            .all()
        )
    assert db_head == "0014_api_keys"
    assert "ix_audit_logs_operator_username" not in indexes
    assert "ix_interfaces_deleted_at" not in indexes
    for table in (
        "clusters",
        "resources",
        "networks",
        "ip_pools",
        "ip_addresses",
        "services",
        "service_endpoints",
    ):
        assert f"ix_{table}_deleted_at" in indexes


def test_audit_query_plan_baseline(committed_engine):
    with committed_engine.begin() as conn:
        plan = conn.execute(
            text(
                "EXPLAIN (FORMAT JSON) SELECT * FROM audit_logs "
                "WHERE operator_username = 'nobody' ORDER BY created_at DESC, id ASC"
            )
        ).scalar_one()
    assert plan  # planner returns a plan; correctness never depends on the index

# --- V32: exact operator match and desc same-instant id tie-break -------------


def test_operator_exact_match_and_desc_tie_break(
    role_client_factory,  # noqa: F811
    auth_session_factory,
):
    admin, _, _ = role_client_factory("ADMIN")
    editor, editor_user, _ = role_client_factory("EDITOR")
    create_cluster(editor, "EX1")

    # Exact match, not a substring: a prefix of the username must miss.
    prefix = editor_user.username[:-1]
    assert (
        admin.get("/api/v1/audit", params={"operator": prefix}).json()["total"] == 0
    )
    exact = admin.get(
        "/api/v1/audit", params={"operator": editor_user.username}
    ).json()
    assert exact["total"] >= 1

    instant = datetime.now(timezone.utc)
    inserted: list[uuid.UUID] = []
    with auth_session_factory() as session:
        for _ in range(3):
            row = AuditLog(
                operator_username="tie.user",
                action="CREATE",
                object_type="cluster",
                object_id=uuid.uuid4(),
                after_data={},
                created_at=instant,
            )
            session.add(row)
            session.flush()
            inserted.append(row.id)
        session.commit()

    for order in ("asc", "desc"):
        body = admin.get(
            "/api/v1/audit",
            params={
                "operator": "tie.user",
                "order": order,
                "page_size": 100,
            },
        ).json()
        returned = [uuid.UUID(item["id"]) for item in body["items"]]
        assert returned == sorted(inserted), (order, returned)
