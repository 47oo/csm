"""Independent F011 TE-1 verification tests (Tester-authored).

These tests are written and executed by the Tester, independently of the
implementation report's numbers. They deliberately target the acceptance points
that the implementation suite covers only indirectly:

- B26 audit same-transaction rollback for CREATE/UPDATE/DELETE/RESTORE;
- B33 optimistic lock across two real committed sessions (service layer);
- B34 restore vs concurrent recreate (real partial-unique arbitration);
- A1 Unicode Cc/Cf rejection at the API boundary (and the documented DB
  ASCII-only backstop divergence);
- A1 name length 1-255 / internal ordinary spaces not collapsed;
- A16 application ``name_key`` vs DB ``translate(btrim(name))`` consistency;
- A12 unauthenticated 401 before permission;
- A14 ``sort=name`` orders by ``name_key``.

Real PostgreSQL only (``TEST_DATABASE_URL`` / DB-D10 guard in conftest); no
SQLite and no mocks for constraint/concurrency evidence.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.auth import Operator
from app.core.errors import VersionConflict
from app.core.permissions import Role
from app.services import service as service_service
from app.services import cluster as cluster_service
from app.services import resource as resource_service

# --- helpers -----------------------------------------------------------------


def _operator(user) -> Operator:
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


@pytest.fixture
def role_client_factory(auth_app, make_user):
    clients: list[TestClient] = []

    def _make(role: str):
        user, password = make_user(role=role)
        client = TestClient(auth_app)
        client.__enter__()
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": user.username, "password": password},
        )
        assert resp.status_code == 200, resp.text
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


def _cluster(client, code="TC1"):
    resp = client.post(
        "/api/v1/clusters", json={"code": code, "name": f"cluster {code}"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster"]


def _resource(client, cluster, hostname="th1"):
    resp = client.post(
        "/api/v1/resources",
        json={
            "cluster": cluster,
            "hostname": hostname,
            "resource_type": "BARE_METAL",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _service(client, resource, name="ssh", **overrides):
    body = {"resource": resource, "name": name}
    body.update(overrides)
    resp = client.post("/api/v1/services", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["service"]


def _seed_resource_via_services(auth_session_factory, op, code="TSEED", host="tseed"):
    with auth_session_factory() as session:
        cluster_service.create_cluster(session, op, code=code, name=code)
    with auth_session_factory() as session:
        resource = resource_service.create_resource(
            session,
            op,
            cluster=code,
            hostname=host,
            resource_type="BARE_METAL",
        )
        return resource.id


# --- A1: Unicode Cc/Cf rejected at the API boundary ---------------------------


def test_unicode_control_and_format_rejected_api(role_client_factory):
    admin = role_client_factory("ADMIN")
    resource = _resource(admin, _cluster(admin)["code"])

    # \x00 is Cc; \u200b / \ufeff / \u00ad are Cf (format). All must be 422 at
    # the API even though the DB CHECK is an ASCII-only backstop (DB-D130).
    for bad in ("a\x00b", "a\u200bb", "\ufeffx", "a\u00adb"):
        resp = admin.post(
            "/api/v1/services", json={"resource": resource["id"], "name": bad}
        )
        assert resp.status_code == 422, (bad, resp.text)
        fields = resp.json()["error"]["details"]["fields"]
        assert fields[0]["field"] == "name", (bad, fields)

    # No partial row is left behind for the rejected names.
    listed = admin.get("/api/v1/services", params={"page_size": 100}).json()
    assert listed["total"] == 0


def test_db_name_control_backstop_is_ascii_only(committed_engine):
    """Documented divergence: the DB backstop only rejects ASCII cntrl chars."""
    engine = committed_engine
    with engine.begin() as conn:
        cid = conn.execute(
            text(
                "INSERT INTO clusters (code, code_key, name) "
                "VALUES ('TCF', 'TCF', 'tcf') RETURNING id"
            )
        ).scalar_one()
        rid = conn.execute(
            text(
                "INSERT INTO resources (cluster_id, hostname, hostname_key, "
                "resource_type) VALUES (:cid, 'cfh', 'cfh', 'BARE_METAL') "
                "RETURNING id"
            ),
            {"cid": cid},
        ).scalar_one()
    # Unicode Cf is accepted by the DB (ASCII [[:cntrl:]] backstop only).
    with engine.begin() as conn:
        sid = conn.execute(
            text(
                "INSERT INTO services (resource_id, name, name_key) "
                "VALUES (:rid, :name, :name) RETURNING id"
            ),
            {"rid": rid, "name": "a\u200bb"},
        ).scalar_one()
    assert sid is not None
    # An ASCII control character is rejected by the DB backstop (own txn so the
    # abort does not poison the accepted-row transaction).
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO services (resource_id, name, name_key) "
                    "VALUES (:rid, :name, :name)"
                ),
                {"rid": rid, "name": "a\x01b"},
            )


# --- A1: length + internal ordinary spaces ------------------------------------


def test_name_length_and_internal_spaces_api(role_client_factory):
    admin = role_client_factory("ADMIN")
    resource = _resource(admin, _cluster(admin)["code"])

    # 255 code points accepted; 256 rejected with field="name".
    ok = _service(admin, resource["id"], name="x" * 255)
    assert ok["name"] == "x" * 255

    too_long = admin.post(
        "/api/v1/services", json={"resource": resource["id"], "name": "y" * 256}
    )
    assert too_long.status_code == 422
    assert too_long.json()["error"]["details"]["fields"][0]["field"] == "name"

    # Internal ordinary spaces are preserved verbatim (not collapsed).
    spaced = _service(admin, resource["id"], name="web  1")
    assert spaced["name"] == "web  1"


# --- A16: application name_key == DB translate(btrim(name)) -------------------


def test_name_key_app_db_consistency_api_to_db(role_client_factory, committed_engine):
    admin = role_client_factory("ADMIN")
    resource = _resource(admin, _cluster(admin)["code"])
    created = _service(admin, resource["id"], name="İstanbul ß")

    with committed_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT name, name_key, "
                "translate(btrim(name), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                "'abcdefghijklmnopqrstuvwxyz') AS expected "
                "FROM services WHERE id = :id"
            ),
            {"id": uuid.UUID(created["id"])},
        ).mappings().one()
    # Only ASCII A-Z folds; İ/ß stay verbatim in both application and DB.
    assert row["name_key"] == row["expected"] == "İstanbul ß"


# --- A12: unauthenticated is 401 before any permission check ------------------


def test_unauthenticated_401(auth_app):
    with TestClient(auth_app) as client:
        assert client.get("/api/v1/services").status_code == 401
        assert client.get("/api/v1/services?deleted=include").status_code == 401
        assert (
            client.post(
                "/api/v1/services",
                json={"resource": str(uuid.uuid4()), "name": "x"},
            ).status_code
            == 401
        )


# --- A14: sort=name orders by the normalisation key --------------------------


def test_sort_name_uses_name_key(role_client_factory):
    admin = role_client_factory("ADMIN")
    resource = _resource(admin, _cluster(admin)["code"])
    # Display order would be B, C, a (ASCII); name_key order is a, B, C.
    for name in ("B", "a", "C"):
        _service(admin, resource["id"], name=name)

    resp = admin.get(
        "/api/v1/services",
        params={"sort": "name", "order": "asc", "page_size": 100},
    )
    assert resp.status_code == 200, resp.text
    assert [item["name"] for item in resp.json()["items"]] == ["a", "B", "C"]


# --- B26: audit same-transaction rollback (all four actions) ------------------


def test_audit_failure_rolls_back_all_service_writes(
    auth_session_factory, make_user, monkeypatch
):
    from app.services import audit as audit_service

    user, _ = make_user(role="EDITOR")
    op = _operator(user)
    rid = _seed_resource_via_services(auth_session_factory, op)

    def boom(*args, **kwargs):
        raise RuntimeError("audit failure injected")

    # CREATE: no service row survives.
    monkeypatch.setattr(audit_service, "record", boom)
    with auth_session_factory() as session:
        with pytest.raises(RuntimeError):
            service_service.create_service(
                session, op, resource=str(rid), name="create-rb"
            )
        session.rollback()
    with auth_session_factory() as session:
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM services WHERE resource_id = :rid "
                    "AND name = 'create-rb'"
                ),
                {"rid": rid},
            ).scalar_one()
            == 0
        )

    # Set up one live and one soft-deleted service with the audit intact.
    monkeypatch.undo()
    with auth_session_factory() as session:
        live = service_service.create_service(
            session, op, resource=str(rid), name="live-rb"
        )
        live_id = live.id
    with auth_session_factory() as session:
        gone = service_service.create_service(
            session, op, resource=str(rid), name="gone-rb"
        )
        gone_id = gone.id
    with auth_session_factory() as session:
        service_service.delete_service(session, op, gone_id, expected_version=1)

    # UPDATE: value and version unchanged.
    monkeypatch.setattr(audit_service, "record", boom)
    with auth_session_factory() as session:
        with pytest.raises(RuntimeError):
            service_service.update_service(
                session,
                op,
                live_id,
                expected_version=1,
                changes={"status": "RUNNING"},
            )
        session.rollback()
    with auth_session_factory() as session:
        row = session.execute(
            text("SELECT status, version FROM services WHERE id = :id"),
            {"id": live_id},
        ).mappings().one()
        assert row["status"] == "UNKNOWN" and row["version"] == 1

    # DELETE: stays undeleted.
    with auth_session_factory() as session:
        with pytest.raises(RuntimeError):
            service_service.delete_service(
                session, op, live_id, expected_version=1
            )
        session.rollback()
    with auth_session_factory() as session:
        assert (
            session.execute(
                text("SELECT deleted_at FROM services WHERE id = :id"),
                {"id": live_id},
            ).scalar_one()
            is None
        )

    # RESTORE: stays soft-deleted.
    with auth_session_factory() as session:
        with pytest.raises(RuntimeError):
            service_service.restore_service(
                session, op, gone_id, expected_version=2
            )
        session.rollback()
    with auth_session_factory() as session:
        assert (
            session.execute(
                text("SELECT deleted_at FROM services WHERE id = :id"),
                {"id": gone_id},
            ).scalar_one()
            is not None
        )


# --- B33: optimistic lock across two real sessions ---------------------------


def test_optimistic_lock_two_sessions(auth_session_factory, make_user):
    user, _ = make_user(role="EDITOR")
    op = _operator(user)
    rid = _seed_resource_via_services(auth_session_factory, op, code="TLOCK", host="tlock")

    with auth_session_factory() as session:
        created = service_service.create_service(
            session, op, resource=str(rid), name="lock-svc"
        )
        sid = created.id

    first = auth_session_factory()
    second = auth_session_factory()
    try:
        service_service.update_service(
            first, op, sid, expected_version=1, changes={"status": "RUNNING"}
        )
        with pytest.raises(VersionConflict) as exc:
            service_service.update_service(
                second, op, sid, expected_version=1, changes={"status": "STOPPED"}
            )
        assert exc.value.details == {"current_version": 2}
        second.rollback()
    finally:
        first.close()
        second.close()

    with auth_session_factory() as verify:
        final = service_service.get_service(verify, sid)
        assert final.version == 2
        assert final.status == "RUNNING"


# --- B34: restore vs concurrent recreate (real partial-unique arbitration) ----


def test_restore_vs_recreate_concurrency(auth_session_factory, committed_engine, make_user):
    user, _ = make_user(role="EDITOR")
    op = _operator(user)
    rid = _seed_resource_via_services(auth_session_factory, op, code="TRACE", host="trace")

    with auth_session_factory() as session:
        created = service_service.create_service(
            session, op, resource=str(rid), name="race"
        )
        sid = created.id
    with auth_session_factory() as session:
        service_service.delete_service(session, op, sid, expected_version=1)

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def restorer() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            service_service.restore_service(
                session, op, sid, expected_version=2
            )
            with lock:
                outcomes.append("restore-ok")
        except Exception:
            session.rollback()
            with lock:
                outcomes.append("restore-error")
        finally:
            session.close()

    def recreator() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            service_service.create_service(
                session, op, resource=str(rid), name="race"
            )
            with lock:
                outcomes.append("create-ok")
        except Exception:
            session.rollback()
            with lock:
                outcomes.append("create-error")
        finally:
            session.close()

    threads = [threading.Thread(target=restorer), threading.Thread(target=recreator)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    # The partial unique index admits at most one undeleted "race" row.
    with committed_engine.connect() as conn:
        undeleted = conn.execute(
            text(
                "SELECT count(*) FROM services WHERE resource_id = :rid "
                "AND name_key = 'race' AND deleted_at IS NULL"
            ),
            {"rid": rid},
        ).scalar_one()
    assert undeleted == 1, outcomes
    assert sorted(o.split("-")[1] for o in outcomes) == ["error", "ok"], outcomes


# --- A10/V21: public register_service_reference_checker hook ------------------


def test_public_service_reference_register_hook(role_client_factory, monkeypatch):
    """F012 will call the public registration API; prove it drives DELETE."""
    from app.services import service_reference

    admin = role_client_factory("ADMIN")
    resource = _resource(admin, _cluster(admin)["code"])
    created = _service(admin, resource["id"], name="hook")

    # Isolate the registry through the public registration API only.
    monkeypatch.setattr(service_reference, "_CHECKERS", [])

    def checker(db, service_id):
        return [
            {
                "object_type": "service_endpoint",
                "object_id": str(uuid.uuid4()),
                "label": "tcp/443",
            }
        ]

    service_reference.register_service_reference_checker(checker)
    blocked = admin.delete(
        f"/api/v1/services/{created['id']}", params={"version": 1}
    )
    assert blocked.status_code == 409, blocked.text
    details = blocked.json()["error"]["details"]
    assert details["reason"] == "reference_exists"
    assert details["references"][0]["object_type"] == "service_endpoint"

    # Empty registry lets the delete through (default F011 behaviour).
    monkeypatch.setattr(service_reference, "_CHECKERS", [])
    ok = admin.delete(f"/api/v1/services/{created['id']}", params={"version": 1})
    assert ok.status_code == 204, ok.text


# --- A13/B25/B16: UPDATE audit before/after snapshot content -----------------


def test_update_audit_snapshot_content(role_client_factory, committed_engine):
    admin = role_client_factory("ADMIN")
    resource = _resource(admin, _cluster(admin)["code"])
    created = _service(admin, resource["id"], name="aud", metadata={"a": 1})
    patched = admin.patch(
        f"/api/v1/services/{created['id']}",
        json={
            "version": created["version"],
            "status": "RUNNING",
            "metadata": {"c": 3},
        },
    )
    assert patched.status_code == 200, patched.text

    with committed_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT before_data, after_data FROM audit_logs "
                "WHERE object_type = 'service' AND object_id = :id "
                "AND action = 'UPDATE'"
            ),
            {"id": uuid.UUID(created["id"])},
        ).mappings().one()
    assert set(row["before_data"].keys()) == {
        "resource_id",
        "name",
        "status",
        "description",
        "metadata",
    }
    assert row["before_data"]["status"] == "UNKNOWN"
    assert row["before_data"]["metadata"] == {"a": 1}
    assert row["after_data"]["status"] == "RUNNING"
    # Whole-value replacement is reflected (old key 'a' is gone).
    assert row["after_data"]["metadata"] == {"c": 3}


# --- V27/B38: read-only endpoints have no write side effects -----------------


def test_read_only_has_no_side_effects(role_client_factory, committed_engine):
    admin = role_client_factory("ADMIN")
    resource = _resource(admin, _cluster(admin)["code"])
    created = _service(admin, resource["id"], name="ro")

    with committed_engine.connect() as conn:
        audit_before = conn.execute(
            text("SELECT count(*) FROM audit_logs")
        ).scalar_one()

    assert admin.get("/api/v1/services").status_code == 200
    assert admin.get(f"/api/v1/services/{created['id']}").status_code == 200
    assert (
        admin.get(f"/api/v1/services/{created['id']}/activity").status_code == 200
    )

    with committed_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT status, version, metadata, deleted_at FROM services "
                "WHERE id = :id"
            ),
            {"id": uuid.UUID(created["id"])},
        ).mappings().one()
        audit_after = conn.execute(
            text("SELECT count(*) FROM audit_logs")
        ).scalar_one()
    assert row["status"] == "UNKNOWN" and row["version"] == 1
    assert row["deleted_at"] is None
    assert audit_after == audit_before