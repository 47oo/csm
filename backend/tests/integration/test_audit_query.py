"""F015 audit query integration tests (A1-A11, I-1/I-2/I-13, B1/B4-B11/B27-B28).

Real PostgreSQL via the ``auth_app``/``auth_session_factory`` fixtures; the app
is the production ``create_app`` with only ``get_db`` overridden.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from integration.f015_helpers import create_cluster, role_client_factory  # noqa: F401


def _count_audit(session) -> int:
    return int(session.execute(select(func.count()).select_from(AuditLog)).scalar_one())


# --- A1/I-11: permission matrix and 401-before-403 ---------------------------


def test_audit_permissions(api_client, role_client_factory):  # noqa: F811
    anon = api_client.get("/api/v1/audit")
    assert anon.status_code == 401
    assert anon.json()["error"]["code"] == "AUTH_REQUIRED"

    # 401 precedes query validation (invalid enum still 401 when unauthenticated).
    anon_bad = api_client.get("/api/v1/audit", params={"object_type": "bogus"})
    assert anon_bad.status_code == 401

    viewer, _, _ = role_client_factory("VIEWER")
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")

    for client in (viewer, editor):
        resp = client.get("/api/v1/audit")
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["details"] == {"reason": "permission"}

    assert admin.get("/api/v1/audit").status_code == 200


# --- A3/B4: AND filters -------------------------------------------------------


def test_filters_are_and_combined(role_client_factory):  # noqa: F811
    admin, admin_user, _ = role_client_factory("ADMIN")
    editor, editor_user, _ = role_client_factory("EDITOR")

    cluster = create_cluster(admin, "AF1")
    other = create_cluster(editor, "AF2")
    resp = admin.patch(
        f"/api/v1/clusters/{cluster['id']}",
        json={"version": 1, "name": "renamed"},
    )
    assert resp.status_code == 200

    # object_type + object_id isolates one object's rows (CREATE + UPDATE).
    scoped = admin.get(
        "/api/v1/audit",
        params={"object_type": "cluster", "object_id": cluster["id"]},
    ).json()
    assert scoped["total"] == 2
    assert {item["action"] for item in scoped["items"]} == {"CREATE", "UPDATE"}
    assert all(item["object_id"] == cluster["id"] for item in scoped["items"])

    # + action narrows further.
    only_update = admin.get(
        "/api/v1/audit",
        params={
            "object_type": "cluster",
            "object_id": cluster["id"],
            "action": "UPDATE",
        },
    ).json()
    assert only_update["total"] == 1
    assert only_update["items"][0]["action"] == "UPDATE"

    # Operator filter hits only the editor's row.
    by_operator = admin.get(
        "/api/v1/audit", params={"operator": editor_user.username}
    ).json()
    assert by_operator["total"] >= 1
    assert all(
        item["operator_username"] == editor_user.username
        for item in by_operator["items"]
    )
    assert str(editor_user.id) in {
        item["operator_user_id"] for item in by_operator["items"]
    }
    assert all(item["object_id"] != cluster["id"] for item in by_operator["items"])
    assert other["id"] in {item["object_id"] for item in by_operator["items"]}


def test_operator_normalisation_and_bounds(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    editor, editor_user, _ = role_client_factory("EDITOR")
    create_cluster(editor, "OP1")

    normalized = admin.get(
        "/api/v1/audit",
        params={"operator": f"  {editor_user.username.upper()}  "},
    ).json()
    assert normalized["total"] >= 1

    assert (
        admin.get("/api/v1/audit", params={"operator": "nobody"}).json()["total"] == 0
    )

    blank = admin.get("/api/v1/audit", params={"operator": "   "})
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "VALIDATION_ERROR"

    too_long = admin.get("/api/v1/audit", params={"operator": "x" * 65})
    assert too_long.status_code == 422


def test_invalid_query_parameters(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")

    object_id = str(uuid.uuid4())
    # object_id without object_type -> 422
    assert (
        admin.get("/api/v1/audit", params={"object_id": object_id}).status_code == 422
    )
    # non-UUID object_id -> 422
    assert (
        admin.get(
            "/api/v1/audit",
            params={"object_type": "cluster", "object_id": "not-a-uuid"},
        ).status_code
        == 422
    )
    for params in (
        {"object_type": "bogus"},
        {"action": "NOPE"},
        {"created_from": "not-a-date"},
        {"sort": "id"},
        {"order": "sideways"},
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
    ):
        resp = admin.get("/api/v1/audit", params=params)
        assert resp.status_code == 422, (params, resp.text)
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- A3/B5: closed time interval ---------------------------------------------


def test_time_interval_is_closed(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    cluster = create_cluster(admin, "TI1")

    scoped = admin.get(
        "/api/v1/audit",
        params={"object_type": "cluster", "object_id": cluster["id"]},
    ).json()
    target = scoped["items"][0]
    created_at = target["created_at"]

    same_instant = admin.get(
        "/api/v1/audit",
        params={"created_from": created_at, "created_to": created_at},
    ).json()
    assert any(item["id"] == target["id"] for item in same_instant["items"])

    # Inclusive lower bound excludes earlier rows, inclusive upper excludes later.
    earlier = (
        datetime.fromisoformat(created_at) - timedelta(seconds=1)
    ).isoformat()
    narrower = admin.get(
        "/api/v1/audit",
        params={"created_from": earlier, "created_to": created_at},
    ).json()
    assert any(item["id"] == target["id"] for item in narrower["items"])

    inverted = admin.get(
        "/api/v1/audit",
        params={"created_from": created_at, "created_to": earlier},
    )
    assert inverted.status_code == 422

    # Naive ISO-8601 is accepted and treated as UTC.
    naive = created_at.replace("+00:00", "")
    accepted = admin.get(
        "/api/v1/audit", params={"created_from": naive, "created_to": naive}
    )
    assert accepted.status_code == 200


# --- A4/B6/B8: pagination, empty result --------------------------------------


def test_pagination_and_empty_result(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    for code in ("PG1", "PG2", "PG3"):
        create_cluster(admin, code)

    first = admin.get(
        "/api/v1/audit", params={"object_type": "cluster", "page": 1, "page_size": 2}
    ).json()
    second = admin.get(
        "/api/v1/audit", params={"object_type": "cluster", "page": 2, "page_size": 2}
    ).json()
    assert first["page"] == 1 and first["page_size"] == 2
    assert second["page"] == 2
    assert first["total"] == second["total"] == 3
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert not ({item["id"] for item in first["items"]} & {
        item["id"] for item in second["items"]
    })

    empty = admin.get(
        "/api/v1/audit",
        params={"object_type": "cluster", "object_id": str(uuid.uuid4())},
    ).json()
    assert empty["total"] == 0
    assert empty["items"] == []
    assert empty["page"] == 1 and empty["page_size"] == 20


# --- A15/B7: ordering and same-timestamp id tie-break ------------------------


def test_same_timestamp_orders_by_id_ascending(
    role_client_factory,  # noqa: F811
    auth_session_factory,
):
    admin, _, _ = role_client_factory("ADMIN")
    instant = datetime.now(timezone.utc) - timedelta(minutes=5)
    inserted: list[uuid.UUID] = []
    with auth_session_factory() as session:
        for _ in range(3):
            row = AuditLog(
                operator_username="system",
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

    body = admin.get(
        "/api/v1/audit",
        params={
            "created_from": instant.isoformat(),
            "created_to": instant.isoformat(),
            "order": "asc",
        },
    ).json()
    returned = [uuid.UUID(item["id"]) for item in body["items"]]
    assert returned == sorted(inserted)


# --- A5/B9: read-only and idempotent -----------------------------------------


def test_audit_query_is_read_only_and_idempotent(
    role_client_factory,  # noqa: F811
    auth_session_factory,
):
    admin, _, _ = role_client_factory("ADMIN")
    create_cluster(admin, "RO1")

    with auth_session_factory() as session:
        before = _count_audit(session)

    first = admin.get("/api/v1/audit")
    second = admin.get("/api/v1/audit")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()

    with auth_session_factory() as session:
        assert _count_audit(session) == before


# --- A8/A30/B11: no mutation / clear endpoints --------------------------------


def test_no_audit_mutation_endpoints(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    for method in ("put", "patch", "delete"):
        resp = getattr(admin, method)("/api/v1/audit")
        assert resp.status_code in (404, 405), (method, resp.status_code)
    for path in ("/api/v1/audit/clear", f"/api/v1/audit/{uuid.uuid4()}"):
        assert admin.delete(path).status_code in (404, 405)
        assert admin.post(path).status_code in (404, 405)


# --- A2/A10/A11/I-2/I-4/B27/B28: field shape & account history ---------------


def test_audit_row_shape_and_account_snapshots(
    role_client_factory,  # noqa: F811
    auth_session_factory,
):
    admin, admin_user, _ = role_client_factory("ADMIN")
    created = admin.post(
        "/api/v1/users",
        json={"username": "shape.user", "password": "shape-pass-1", "role": "EDITOR"},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["user"]["id"]

    rows = admin.get(
        "/api/v1/audit", params={"object_type": "user", "object_id": user_id}
    ).json()["items"]
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == {
        "id",
        "action",
        "object_type",
        "object_id",
        "operator_user_id",
        "operator_username",
        "before_data",
        "after_data",
        "created_at",
    }
    assert row["action"] == "CREATE"
    assert row["operator_user_id"] == str(admin_user.id)
    assert row["operator_username"] == admin_user.username
    assert row["before_data"] is None
    assert set(row["after_data"]) == {"username", "role", "status"}
    assert row["after_data"]["username"] == "shape.user"
    assert row["created_at"].endswith("+00:00")

    # No credential material anywhere in the account audit trail.
    with auth_session_factory() as session:
        snapshots = session.execute(
            select(AuditLog.before_data, AuditLog.after_data).where(
                AuditLog.object_type == "user"
            )
        ).all()
    for before, after in snapshots:
        for snapshot in (before, after):
            if snapshot:
                assert set(snapshot) <= {"username", "role", "status"}

    # Disable the account and confirm the existing audit row is untouched and
    # the historical identity still resolves.
    disabled = admin.patch(
        f"/api/v1/users/{user_id}", json={"version": 1, "status": "DISABLED"}
    )
    assert disabled.status_code == 200

    unchanged = admin.get(
        "/api/v1/audit", params={"object_type": "user", "object_id": user_id}
    ).json()["items"]
    create_row = next(item for item in unchanged if item["action"] == "CREATE")
    assert create_row == row

    by_operator = admin.get(
        "/api/v1/audit", params={"operator": admin_user.username}
    ).json()
    assert by_operator["total"] >= 1