"""F015 real-PostgreSQL constraint/trigger/migration evidence (V-DB-F015-1..5).

SQLite/Mock cannot prove append-only triggers, FK RESTRICT, column types or the
migration head; this module uses raw SQL against the real test database.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from integration.f015_helpers import role_client_factory  # noqa: F401


def _expect_dbapi_error(engine, sql: str, params: dict | None = None) -> None:
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text(sql), params or {})


# --- V-DB-F015-1 / I-1: append-only trigger ----------------------------------


def test_audit_logs_append_only(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        audit_id = conn.execute(
            text(
                "INSERT INTO audit_logs "
                "(operator_username, action, object_type, object_id, after_data) "
                "VALUES ('system','CREATE','cluster',:oid,'{}'::jsonb) RETURNING id"
            ),
            {"oid": uuid.uuid4()},
        ).scalar_one()

    _expect_dbapi_error(
        engine,
        "UPDATE audit_logs SET action = 'UPDATE' WHERE id = :id",
        {"id": audit_id},
    )
    _expect_dbapi_error(
        engine, "DELETE FROM audit_logs WHERE id = :id", {"id": audit_id}
    )


# --- V-DB-F015-2 / DB-D27: FK RESTRICT + snapshot constraints ----------------


def test_audit_operator_fk_restrict_and_snapshot_constraints(
    committed_engine, make_user
):
    engine = committed_engine
    user, _ = make_user(role="ADMIN", username="fk.user")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_logs "
                "(operator_user_id, operator_username, action, object_type, object_id, after_data) "
                "VALUES (:uid, :uname, 'CREATE', 'cluster', :oid, '{}'::jsonb)"
            ),
            {"uid": user.id, "uname": user.username, "oid": uuid.uuid4()},
        )
    _expect_dbapi_error(engine, "DELETE FROM users WHERE id = :id", {"id": user.id})

    # At least one snapshot is required and snapshots must be JSON objects.
    _expect_dbapi_error(
        engine,
        "INSERT INTO audit_logs (operator_username, action, object_type, object_id) "
        "VALUES ('system','CREATE','cluster',:oid)",
        {"oid": uuid.uuid4()},
    )
    _expect_dbapi_error(
        engine,
        "INSERT INTO audit_logs "
        "(operator_username, action, object_type, object_id, after_data) "
        "VALUES ('system','CREATE','cluster',:oid,'[]'::jsonb)",
        {"oid": uuid.uuid4()},
    )
    # Action CHECK is limited to the registered set.
    _expect_dbapi_error(
        engine,
        "INSERT INTO audit_logs "
        "(operator_username, action, object_type, object_id, after_data) "
        "VALUES ('system','PURGE','cluster',:oid,'{}'::jsonb)",
        {"oid": uuid.uuid4()},
    )


# --- V-DB-F015-3 / DB-D167: object_type is varchar(64) with no enum CHECK -----


def test_audit_object_type_accepts_user_without_enum_check(committed_engine):
    engine = committed_engine
    with engine.connect() as conn:
        data_type, length = conn.execute(
            text(
                "SELECT data_type, character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_name = 'audit_logs' AND column_name = 'object_type'"
            )
        ).one()
    assert data_type == "character varying"
    assert length == 64

    with engine.begin() as conn:
        for object_type, action in (("user", "CREATE"), ("user", "UPDATE")):
            conn.execute(
                text(
                    "INSERT INTO audit_logs "
                    "(operator_username, action, object_type, object_id, after_data) "
                    "VALUES ('system', :action, :object_type, :oid, "
                    "'{\"username\":\"x\",\"role\":\"VIEWER\",\"status\":\"ACTIVE\"}'::jsonb)"
                ),
                {"action": action, "object_type": object_type, "oid": uuid.uuid4()},
            )
        # No enum CHECK: an arbitrary future type is still accepted.
        conn.execute(
            text(
                "INSERT INTO audit_logs "
                "(operator_username, action, object_type, object_id, after_data) "
                "VALUES ('system','CREATE','future.type',:oid,'{}'::jsonb)"
            ),
            {"oid": uuid.uuid4()},
        )


# --- DB-D16: users lifecycle columns and uniqueness ---------------------------


def test_users_has_no_soft_delete_and_username_unique(committed_engine):
    engine = committed_engine
    with engine.connect() as conn:
        user_columns = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'users'"
                )
            )
            .scalars()
            .all()
        )
        audit_columns = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'audit_logs'"
                )
            )
            .scalars()
            .all()
        )
    assert "deleted_at" not in user_columns
    assert "version" in user_columns and "status" in user_columns
    assert "deleted_at" not in audit_columns
    assert "version" not in audit_columns

    with engine.connect() as conn:
        unique = conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'users'::regclass AND contype = 'u'"
            )
        ).scalars().all()
    # The UniqueConstraint gets the F001 naming convention name.
    assert any("username" in name for name in unique)

    # No append-only trigger protects user_sessions (disable must delete them).
    with engine.connect() as conn:
        session_triggers = conn.execute(
            text(
                "SELECT tgname FROM pg_trigger "
                "WHERE tgrelid = 'user_sessions'::regclass AND NOT tgisinternal"
            )
        ).scalars().all()
    assert list(session_triggers) == []


# --- V-DB-F015-4/5 / DB-D171: no new migration/index ---------------------------


def test_no_new_schema_or_operator_username_index(committed_engine, alembic_runner):
    engine = committed_engine
    assert alembic_runner.head_revision() == "0014_api_keys"

    with engine.connect() as conn:
        db_head = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        forbidden = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "AND indexname = 'ix_audit_logs_operator_username'"
            )
        ).scalar_one_or_none()
        existing = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'audit_logs'"
                )
            )
            .scalars()
            .all()
        )
        deleted_at_indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' "
                    "AND indexname LIKE 'ix_%_deleted_at'"
                )
            )
            .scalars()
            .all()
        )
    assert db_head == "0014_api_keys"
    assert forbidden is None
    assert {
        "ix_audit_logs_object_type_object_id",
        "ix_audit_logs_operator_user_id",
        "ix_audit_logs_created_at",
    } <= existing
    assert "ix_interfaces_deleted_at" not in deleted_at_indexes
    for table in (
        "clusters",
        "resources",
        "networks",
        "ip_pools",
        "ip_addresses",
        "services",
        "service_endpoints",
    ):
        assert f"ix_{table}_deleted_at" in deleted_at_indexes


# --- V-ST-1/V25: no audit mutation or registration routes --------------------


def test_route_catalogue_has_no_mutation_or_registration(auth_app):
    routes = {
        (route.path, method)
        for route in auth_app.routes
        for method in getattr(route, "methods", set()) or set()
    }
    mutating = {"POST", "PUT", "PATCH", "DELETE"}
    for path, method in routes:
        if path == "/api/v1/audit":
            assert method not in mutating, (path, method)
        assert "register" not in path and "signup" not in path
        if path.startswith("/api/v1/users"):
            assert not (method == "DELETE"), (path, method)
            assert "password" not in path and "reset" not in path