"""F017 independent Tester acceptance tests (TD-1 V14/V15, B5/B6/B10/B13/B15-B19).

These complement ``test_api_keys.py`` with the TD-1 items that were not directly
asserted by the developer's suite: auth-response equivalence (V14), read-only /
logout no-op (V15/B17), status derivation REVOKED>EXPIRED (B5), the
``expires_at <= now`` boundary (B6), concurrent creation uniqueness (B10),
non-Bearer Authorization fall-through (B13), re-enable semantics under the
default F017-OPEN-1 resolution (B15), create does not mutate the account (B16),
response/log credential scrubbing (A5/DR-310) and the authentication query plan.

Real PostgreSQL + real HTTP via the production app; no Mock/SQLite evidence.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from integration.api_keys_helpers import bearer_client, create_key  # noqa: F401
from integration.f015_helpers import role_client_factory  # noqa: F401


# --- local helpers ------------------------------------------------------------


def _insert_key(
    auth_session_factory,
    *,
    user_id,
    label: str = "tester",
    created_delta_days: float = -1,
    expires_delta_days: float = 90,
    revoked_at=None,
):
    """Insert an ``api_keys`` row directly to reach expired/revoked states."""
    from app.core.security import hash_api_key
    from app.models.api_key import ApiKey

    plaintext = "csm_ak_" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    with auth_session_factory() as session:
        row = ApiKey(
            user_id=user_id,
            label=label,
            key_hash=hash_api_key(plaintext),
            created_by=user_id,
            created_at=now + timedelta(days=created_delta_days),
            expires_at=now + timedelta(days=expires_delta_days),
            revoked_at=revoked_at,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row, plaintext


def _make_editor(auth_session_factory, username: str):
    from app.core.permissions import Role
    from app.core.security import hash_password
    from app.models.user import User, UserStatus

    with auth_session_factory() as session:
        user = User(
            username=username,
            password_hash=hash_password("user-pass-123"),
            role=Role.EDITOR.value,
            status=UserStatus.ACTIVE.value,
            version=1,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


# --- B5 / B6: status derivation ----------------------------------------------


def test_status_derivation_revoked_priority_and_expiry_boundary(
    role_client_factory, auth_session_factory
):  # noqa: F811
    """B5/B6: REVOKED > EXPIRED; ``expires_at <= now`` is EXPIRED."""
    admin, _, _ = role_client_factory("ADMIN")
    bound = _make_editor(auth_session_factory, "ak.tester.status")

    # Both revoked and expired -> REVOKED wins.
    revoked_expired, _ = _insert_key(
        auth_session_factory,
        user_id=bound.id,
        label="revoked-and-expired",
        created_delta_days=-3,
        expires_delta_days=-2,
        revoked_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    # Expired, never revoked.
    expired, _ = _insert_key(
        auth_session_factory,
        user_id=bound.id,
        label="only-expired",
        created_delta_days=-2,
        expires_delta_days=-1,
    )
    # Active (well in the future).
    active, _ = _insert_key(
        auth_session_factory,
        user_id=bound.id,
        label="still-active",
        created_delta_days=-1,
        expires_delta_days=30,
    )

    detail = admin.get(f"/api/v1/api-keys/{revoked_expired.id}").json()["api_key"]
    assert detail["status"] == "REVOKED"

    revoked_list = admin.get(
        "/api/v1/api-keys", params={"status": "REVOKED", "page_size": 100}
    ).json()
    revoked_ids = {item["id"] for item in revoked_list["items"]}
    assert str(revoked_expired.id) in revoked_ids
    assert str(expired.id) not in revoked_ids

    expired_list = admin.get(
        "/api/v1/api-keys", params={"status": "EXPIRED", "page_size": 100}
    ).json()
    expired_ids = {item["id"] for item in expired_list["items"]}
    assert str(expired.id) in expired_ids
    assert str(revoked_expired.id) not in expired_ids

    active_list = admin.get(
        "/api/v1/api-keys", params={"status": "ACTIVE", "page_size": 100}
    ).json()
    active_ids = {item["id"] for item in active_list["items"]}
    assert str(active.id) in active_ids


def test_expires_at_equals_now_is_expired(
    auth_app, role_client_factory, auth_session_factory
):  # noqa: F811
    """B6: a key whose ``expires_at`` has just passed is EXPIRED and rejected."""
    admin, _, _ = role_client_factory("ADMIN")
    bound = _make_editor(auth_session_factory, "ak.tester.boundary")
    key, plaintext = _insert_key(
        auth_session_factory,
        user_id=bound.id,
        label="just-expired",
        created_delta_days=-1,
        expires_delta_days=0,
    )
    # Move expires_at to 1s in the past (created_at kept in the past).
    from app.models.api_key import ApiKey

    with auth_session_factory() as session:
        row = session.get(ApiKey, key.id)
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

    detail = admin.get(f"/api/v1/api-keys/{key.id}").json()["api_key"]
    assert detail["status"] == "EXPIRED"

    with bearer_client(auth_app, plaintext) as client:
        assert client.get("/api/v1/auth/me").status_code == 401


# --- V14: auth error equivalence ---------------------------------------------


def test_auth_error_responses_are_equivalent_and_401_before_403(
    auth_app, role_client_factory, auth_session_factory
):  # noqa: F811
    """V14/B11: every unusable credential yields the identical 401 envelope."""
    admin, _, _ = role_client_factory("ADMIN")
    bound = _make_editor(auth_session_factory, "ak.tester.equivalent")
    active, active_plaintext = _insert_key(
        auth_session_factory, user_id=bound.id, label="active"
    )
    revoked, revoked_plaintext = _insert_key(
        auth_session_factory,
        user_id=bound.id,
        label="revoked",
        revoked_at=datetime.now(timezone.utc),
    )
    expired, expired_plaintext = _insert_key(
        auth_session_factory,
        user_id=bound.id,
        label="expired",
        created_delta_days=-2,
        expires_delta_days=-1,
    )

    disabled = _make_editor(auth_session_factory, "ak.tester.disabled")
    disabled_key, disabled_plaintext = _insert_key(
        auth_session_factory, user_id=disabled.id, label="disabled-bound"
    )
    from app.models.user import User, UserStatus

    with auth_session_factory() as session:
        row = session.get(User, disabled.id)
        row.status = UserStatus.DISABLED.value
        session.commit()

    expected = {
        "error": {
            "code": "AUTH_REQUIRED",
            "message": "Authentication required",
            "details": {},
        }
    }
    with TestClient(auth_app) as client:
        responses = {
            "missing": client.get("/api/v1/auth/me"),
            "empty_bearer": client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer "}
            ),
            "no_prefix": client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-key"}
            ),
            "unknown_hash": client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer csm_ak_{uuid.uuid4().hex}"},
            ),
            "revoked": client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {revoked_plaintext}"},
            ),
            "expired": client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {expired_plaintext}"},
            ),
            "disabled_account": client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {disabled_plaintext}"},
            ),
            # Invalid key on an ADMIN-only endpoint -> 401 before 403.
            "invalid_on_admin": client.get(
                "/api/v1/api-keys",
                headers={"Authorization": "Bearer csm_ak_bogus"},
            ),
        }

    for name, resp in responses.items():
        assert resp.status_code == 401, (name, resp.status_code, resp.text)
        assert resp.json() == expected, name

    # The valid key still authenticates (control case).
    with bearer_client(auth_app, active_plaintext) as client:
        assert client.get("/api/v1/auth/me").status_code == 200
    del active, revoked, expired, disabled_key


# --- B13: non-Bearer Authorization is ignored --------------------------------


def test_non_bearer_authorization_falls_back_to_cookie(auth_app, make_user):  # noqa: F811
    """B13: ``Authorization: Basic`` is ignored; the cookie still authenticates."""
    user, password = make_user(role="EDITOR", username="ak.tester.basic")
    with TestClient(auth_app) as client:
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": user.username, "password": password},
            ).status_code
            == 200
        )
        client.headers.update({"Authorization": "Basic dXNlcjpwYXNz"})
        me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["user"]["username"] == "ak.tester.basic"


# --- B12: Bearer priority over a cookie --------------------------------------


def test_bearer_priority_over_cookie(auth_app, role_client_factory, make_user):  # noqa: F811
    """B12: valid Bearer wins; invalid Bearer does not fall back to a valid cookie."""
    admin, _, _ = role_client_factory("ADMIN")
    key_user = make_user(role="EDITOR", username="ak.tester.bearer")[0]
    key = create_key(
        admin, bound_user_id=str(key_user.id), label="bearer-priority"
    ).json()["api_key"]

    cookie_user, cookie_password = make_user(role="VIEWER", username="ak.tester.cookie")
    with TestClient(auth_app) as client:
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": cookie_user.username, "password": cookie_password},
            ).status_code
            == 200
        )
        # Valid Bearer + other-account cookie -> Bearer identity.
        client.headers.update({"Authorization": f"Bearer {key['plaintext']}"})
        assert client.get("/api/v1/auth/me").json()["user"]["username"] == "ak.tester.bearer"
        # Invalid Bearer + valid cookie -> 401 (no cookie fallback).
        client.headers.update({"Authorization": "Bearer csm_ak_invalid"})
        assert client.get("/api/v1/auth/me").status_code == 401


# --- B15: re-enable semantics (default F017-OPEN-1 resolution) ---------------


def test_reenable_account_restores_unrevoked_key(
    auth_app, role_client_factory, auth_session_factory
):  # noqa: F811
    """B15: disabled -> 401; re-enabled -> un-revoked key usable, revoked stays dead."""
    admin, _, _ = role_client_factory("ADMIN")
    bound = _make_editor(auth_session_factory, "ak.tester.reenable")
    usable = create_key(admin, bound_user_id=str(bound.id), label="reusable").json()[
        "api_key"
    ]
    revoked = create_key(admin, bound_user_id=str(bound.id), label="dead").json()[
        "api_key"
    ]
    assert admin.post(f"/api/v1/api-keys/{revoked['id']}/revoke").status_code == 200

    from app.models.user import User, UserStatus

    def set_status(status: str):
        with auth_session_factory() as session:
            row = session.get(User, bound.id)
            row.status = status
            session.commit()

    set_status(UserStatus.DISABLED.value)
    with bearer_client(auth_app, usable["plaintext"]) as client:
        assert client.get("/api/v1/auth/me").status_code == 401

    set_status(UserStatus.ACTIVE.value)
    with bearer_client(auth_app, usable["plaintext"]) as client:
        assert client.get("/api/v1/auth/me").status_code == 200
    with bearer_client(auth_app, revoked["plaintext"]) as client:
        assert client.get("/api/v1/auth/me").status_code == 401

    # Re-enabling does not silently revoke the key.
    from app.models.api_key import ApiKey

    with auth_session_factory() as session:
        row = session.get(ApiKey, uuid.UUID(usable["id"]))
        assert row.revoked_at is None


# --- B16: create does not mutate the account ---------------------------------


def test_create_does_not_change_account(auth_session_factory, role_client_factory):  # noqa: F811
    """B16: creating a key must not change user status/version/updated_at."""
    admin, _, _ = role_client_factory("ADMIN")
    bound = _make_editor(auth_session_factory, "ak.tester.immutable")

    from app.models.user import User

    def snapshot():
        with auth_session_factory() as session:
            row = session.get(User, bound.id)
            return (row.status, row.version, row.updated_at)

    before = snapshot()
    assert create_key(admin, bound_user_id=str(bound.id), label="no-mutate").status_code == 201
    assert snapshot() == before


# --- B10: concurrent creation uniqueness -------------------------------------


def test_concurrent_create_produces_distinct_hashes(
    committed_engine, auth_session_factory
):
    """B10: concurrent creates yield distinct hashes; DB unique index is the backstop."""
    from sqlalchemy.orm import sessionmaker

    from app.core.auth import Operator
    from app.core.permissions import Role
    from app.services import api_key as svc

    bound = _make_editor(auth_session_factory, "ak.tester.concurrent")
    factory = sessionmaker(
        bind=committed_engine, autoflush=False, expire_on_commit=False, future=True
    )
    operator = Operator(user_id=bound.id, username=bound.username, role=Role.ADMIN)

    results: list[tuple[str, str]] = []
    errors: list[Exception] = []

    def create():
        try:
            with factory() as session:
                key, _u, _c, plaintext = svc.create_api_key(
                    session,
                    operator,
                    user_id=bound.id,
                    label="concurrent",
                    validity_days=90,
                )
                results.append((key.key_hash, plaintext))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=create) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    assert len(results) == 5
    hashes = [h for h, _ in results]
    assert len(set(hashes)) == 5
    # Each stored hash is the digest of a distinct plaintext.
    assert {h for h, _ in results} == {
        hashlib.sha256(pt.encode()).hexdigest() for _, pt in results
    }


# --- V15 / B17: read-only endpoints have no side effects ---------------------


def test_read_only_endpoints_have_no_write_side_effects(
    auth_app, role_client_factory, auth_session_factory
):  # noqa: F811
    """V15/B17: list/detail/logout do not change api_keys or audit_logs rows."""
    from app.models.api_key import ApiKey
    from app.models.audit_log import AuditLog

    admin, _, _ = role_client_factory("ADMIN")
    bound = _make_editor(auth_session_factory, "ak.tester.readonly")
    created = create_key(admin, bound_user_id=str(bound.id), label="ro-key").json()[
        "api_key"
    ]

    def counts():
        with auth_session_factory() as session:
            return (
                session.execute(select(func.count()).select_from(ApiKey)).scalar_one(),
                session.execute(select(func.count()).select_from(AuditLog)).scalar_one(),
            )

    before = counts()
    assert admin.get("/api/v1/api-keys", params={"page_size": 100}).status_code == 200
    assert admin.get(f"/api/v1/api-keys/{created['id']}").status_code == 200
    assert counts() == before

    # logout carries an API Key: harmless no-op, the key remains usable.
    with bearer_client(auth_app, created["plaintext"]) as client:
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 200
    assert counts() == before


# --- A5 / DR-310: response and log scrubbing ---------------------------------


def test_sensitive_fields_cover_api_key_material():
    from app.core.logging import SENSITIVE_FIELDS

    required = {
        "api_key",
        "api_key_hash",
        "key_hash",
        "plaintext",
        "bearer",
        "authorization",
    }
    assert required <= SENSITIVE_FIELDS


def test_responses_and_logs_never_expose_plaintext_or_hash(
    role_client_factory, auth_session_factory, caplog
):  # noqa: F811
    """A5/V5: 201 is the only place the plaintext appears; logs are clean."""
    admin, _, _ = role_client_factory("ADMIN")
    bound = _make_editor(auth_session_factory, "ak.tester.scrub")

    with caplog.at_level(logging.DEBUG):
        created = create_key(admin, bound_user_id=str(bound.id), label="scrub-key")
        assert created.status_code == 201
        plaintext = created.json()["api_key"]["plaintext"]
        key_id = created.json()["api_key"]["id"]
        stored_hash = hashlib.sha256(plaintext.encode()).hexdigest()

        # Every other export must be clean.
        exports = [
            admin.get("/api/v1/api-keys", params={"page_size": 100}).text,
            admin.get(f"/api/v1/api-keys/{key_id}").text,
            admin.post(f"/api/v1/api-keys/{key_id}/revoke").text,
            admin.post("/api/v1/api-keys", json={"user_id": "bad", "label": ""}).text,
        ]

    for body in exports:
        assert plaintext not in body
        assert stored_hash not in body
        assert "key_hash" not in body

    log_text = caplog.text
    assert plaintext not in log_text
    assert stored_hash not in log_text

    with auth_session_factory() as session:
        from app.models.api_key import ApiKey

        row = session.get(ApiKey, uuid.UUID(key_id))
        assert row.key_hash == stored_hash
        assert row.key_hash != plaintext


def test_database_has_no_plaintext_column(committed_engine):
    """T-DB-1: ``api_keys`` stores only key_hash (no plaintext column)."""
    from sqlalchemy import text

    with committed_engine.connect() as conn:
        columns = {
            c
            for c in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'api_keys' AND table_schema = 'public'"
                )
            ).scalars()
        }
    assert "key_hash" in columns
    assert "plaintext" not in columns
    assert "api_key" not in columns


# --- B2 / B18: concurrency and audit atomicity -------------------------------


def test_concurrent_revoke_yields_single_success(
    auth_app, role_client_factory, auth_session_factory, committed_engine
):  # noqa: F811
    """B2/B18: two concurrent revokes -> exactly one 200 and one 409."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from app.core.auth import Operator
    from app.core.permissions import Role
    from app.services import api_key as svc

    admin, admin_user, _ = role_client_factory("ADMIN")
    bound = _make_editor(auth_session_factory, "ak.tester.racerevoke")
    key = create_key(admin, bound_user_id=str(bound.id), label="race").json()["api_key"]
    operator = Operator(
        user_id=admin_user.id, username=admin_user.username, role=Role.ADMIN
    )
    factory = sessionmaker(
        bind=committed_engine, autoflush=False, expire_on_commit=False, future=True
    )

    from app.core.errors import Conflict

    outcomes: list[str] = []

    def revoke():
        try:
            with factory() as session:
                svc.revoke_api_key(session, operator, uuid.UUID(key["id"]))
                outcomes.append("ok")
        except Conflict:
            outcomes.append("conflict")

    threads = [threading.Thread(target=revoke) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(outcomes) == ["conflict", "ok"], outcomes
    # Exactly one UPDATE audit row for the api_key (no duplicate on the loser).
    with committed_engine.connect() as conn:
        audit_count = conn.execute(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE object_type = 'api_key' AND object_id = :oid AND action = 'UPDATE'"
            ),
            {"oid": uuid.UUID(key["id"])},
        ).scalar_one()
    assert audit_count == 1


def test_failed_create_leaves_zero_residue(
    auth_app, role_client_factory, auth_session_factory
):  # noqa: F811
    """B18: a rejected create writes no ``api_keys`` or ``audit_logs`` row."""
    from app.models.api_key import ApiKey
    from app.models.audit_log import AuditLog

    admin, _, _ = role_client_factory("ADMIN")

    def counts():
        with auth_session_factory() as session:
            return (
                session.execute(select(func.count()).select_from(ApiKey)).scalar_one(),
                session.execute(select(func.count()).select_from(AuditLog)).scalar_one(),
            )

    before = counts()
    assert (
        admin.post(
            "/api/v1/api-keys",
            json={"user_id": str(uuid.uuid4()), "label": "ghost"},
        ).status_code
        == 422
    )
    assert counts() == before


# --- V-DB-F017-6/9: authentication query plan --------------------------------


def test_auth_lookup_uses_unique_key_hash_index(committed_engine, make_user):
    """The SHA-256 equality lookup can use ``uq_api_keys_key_hash``."""
    from sqlalchemy import text

    user, _ = make_user(role="EDITOR", username="ak.tester.plan")
    with committed_engine.begin() as conn:
        for i in range(50):
            conn.execute(
                text(
                    "INSERT INTO api_keys (user_id, label, key_hash, created_by, expires_at) "
                    "VALUES (:uid, :label, :hash, :uid, now() + interval '1 day')"
                ),
                {"uid": user.id, "label": f"plan-{i}", "hash": f"{i:064x}"},
            )
        conn.execute(text("ANALYZE api_keys"))
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in conn.execute(
                text(
                    "EXPLAIN SELECT id FROM api_keys WHERE key_hash = :hash"
                ),
                {"hash": f"{7:064x}"},
            )
        )
    assert "uq_api_keys_key_hash" in plan, plan