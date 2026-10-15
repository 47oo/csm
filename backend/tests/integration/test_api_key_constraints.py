"""F017 real-PostgreSQL constraint/index/migration evidence (V-DB-F017-1..10).

SQLite/Mock cannot prove CHECK/UNIQUE/FK, the append-only trigger interaction or
the migration head; this module uses raw SQL against the real test database.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

VALID_HASH = "a" * 64


def _expect_dbapi_error(engine, sql: str, params: dict | None = None) -> None:
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text(sql), params or {})


# --- V-DB-F017-2 / DB-D305/306/307: CHECK constraints -------------------------


def test_api_key_check_constraints(committed_engine, make_user):
    engine = committed_engine
    user, _ = make_user(role="ADMIN", username="ak.constraints")

    # Invalid key_hash format / length.
    for bad_hash in ("z" * 64, "A" * 64, "abc", "a" * 63):
        _expect_dbapi_error(
            engine,
            "INSERT INTO api_keys (user_id, label, key_hash, created_by, expires_at) "
            "VALUES (:uid, 'ci', :hash, :uid, now() + interval '1 day')",
            {"uid": user.id, "hash": bad_hash},
        )

    # Blank label.
    _expect_dbapi_error(
        engine,
        "INSERT INTO api_keys (user_id, label, key_hash, created_by, expires_at) "
        "VALUES (:uid, '   ', :hash, :uid, now() + interval '1 day')",
        {"uid": user.id, "hash": VALID_HASH},
    )

    # expires_at <= created_at and over the 365d + 5min backstop.
    _expect_dbapi_error(
        engine,
        "INSERT INTO api_keys (user_id, label, key_hash, created_by, created_at, expires_at) "
        "VALUES (:uid, 'ci', :hash, :uid, now(), now() - interval '1 hour')",
        {"uid": user.id, "hash": "b" * 64},
    )
    _expect_dbapi_error(
        engine,
        "INSERT INTO api_keys (user_id, label, key_hash, created_by, created_at, expires_at) "
        "VALUES (:uid, 'ci', :hash, :uid, now(), now() + interval '366 days')",
        {"uid": user.id, "hash": "c" * 64},
    )

    # revoked_at before created_at.
    _expect_dbapi_error(
        engine,
        "INSERT INTO api_keys (user_id, label, key_hash, created_by, created_at, expires_at, revoked_at) "
        "VALUES (:uid, 'ci', :hash, :uid, now(), now() + interval '1 day', now() - interval '1 hour')",
        {"uid": user.id, "hash": "d" * 64},
    )

    # Valid boundaries: 365 days, revoked_at == created_at, 255-char label.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO api_keys (user_id, label, key_hash, created_by, created_at, expires_at) "
                "VALUES (:uid, 'boundary', :hash, :uid, now(), now() + interval '365 days')"
            ),
            {"uid": user.id, "hash": "e" * 64},
        )
        conn.execute(
            text(
                "INSERT INTO api_keys (user_id, label, key_hash, created_by, created_at, expires_at, revoked_at) "
                "VALUES (:uid, 'revoked-now', :hash, :uid, now(), now() + interval '1 day', now())"
            ),
            {"uid": user.id, "hash": "f" * 64},
        )
        conn.execute(
            text(
                "INSERT INTO api_keys (user_id, label, key_hash, created_by, expires_at) "
                "VALUES (:uid, :label, :hash, :uid, now() + interval '1 day')"
            ),
            {"uid": user.id, "label": "x" * 255, "hash": "1" * 64},
        )


# --- V-DB-F017-3 / DB-D304: UNIQUE key_hash ----------------------------------


def test_api_key_key_hash_unique(committed_engine, make_user):
    engine = committed_engine
    user, _ = make_user(role="ADMIN", username="ak.unique")
    _insert_key_row(engine, user.id, "a" * 64)
    _expect_dbapi_error(
        engine,
        "INSERT INTO api_keys (user_id, label, key_hash, created_by, expires_at) "
        "VALUES (:uid, 'dup', :hash, :uid, now() + interval '1 day')",
        {"uid": user.id, "hash": "a" * 64},
    )


# --- V-DB-F017-4 / DB-D303: FK RESTRICT --------------------------------------


def test_api_key_fk_restrict(committed_engine, make_user):
    engine = committed_engine
    user, _ = make_user(role="ADMIN", username="ak.fk")
    _insert_key_row(engine, user.id, "b" * 64)
    _expect_dbapi_error(engine, "DELETE FROM users WHERE id = :id", {"id": user.id})


# --- V-DB-F017-5: audit_logs.api_key_label + append-only ---------------------


def test_audit_api_key_label_column_and_append_only(committed_engine, make_user):
    engine = committed_engine
    user, _ = make_user(role="ADMIN", username="ak.audit")

    # NULL is allowed; empty/blank is rejected by the nullable-safe CHECK.
    with engine.begin() as conn:
        audit_id = conn.execute(
            text(
                "INSERT INTO audit_logs "
                "(operator_user_id, operator_username, api_key_label, action, object_type, object_id, after_data) "
                "VALUES (:uid, :uname, NULL, 'CREATE', 'api_key', :oid, '{}'::jsonb) RETURNING id"
            ),
            {"uid": user.id, "uname": user.username, "oid": uuid.uuid4()},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO audit_logs "
                "(operator_username, api_key_label, action, object_type, object_id, after_data) "
                "VALUES ('system', 'ci-key', 'UPDATE', 'api_key', :oid, '{}'::jsonb)"
            ),
            {"oid": uuid.uuid4()},
        )
    for blank in ("", "   "):
        _expect_dbapi_error(
            engine,
            "INSERT INTO audit_logs "
            "(operator_username, api_key_label, action, object_type, object_id, after_data) "
            "VALUES ('system', :label, 'CREATE', 'api_key', :oid, '{}'::jsonb)",
            {"label": blank, "oid": uuid.uuid4()},
        )

    # append-only trigger still rejects UPDATE / DELETE after the column add.
    _expect_dbapi_error(
        engine, "UPDATE audit_logs SET api_key_label = 'x' WHERE id = :id", {"id": audit_id}
    )
    _expect_dbapi_error(engine, "DELETE FROM audit_logs WHERE id = :id", {"id": audit_id})

    # object_type='api_key' is accepted by the un-constrained varchar(64) column.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_logs "
                "(operator_username, action, object_type, object_id, after_data) "
                "VALUES ('system', 'CREATE', 'api_key', :oid, '{}'::jsonb)"
            ),
            {"oid": uuid.uuid4()},
        )


# --- V-DB-F017-7: gen_random_uuid() default ----------------------------------


def test_api_key_id_defaults_to_uuid(committed_engine, make_user):
    engine = committed_engine
    user, _ = make_user(role="ADMIN", username="ak.uuid")
    with engine.begin() as conn:
        new_id = conn.execute(
            text(
                "INSERT INTO api_keys (user_id, label, key_hash, created_by, expires_at) "
                "VALUES (:uid, 'gen', :hash, :uid, now() + interval '1 day') RETURNING id"
            ),
            {"uid": user.id, "hash": "9" * 64},
        ).scalar_one()
    assert isinstance(new_id, uuid.UUID)


# --- V-DB-F017-9: indexes / no extra indexes ---------------------------------


def test_api_key_indexes(committed_engine):
    engine = committed_engine
    with engine.connect() as conn:
        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'api_keys'"
                )
            )
            .scalars()
            .all()
        )
    assert {"ix_api_keys_user_id", "ix_api_keys_created_by"} <= indexes
    assert not any("expires" in name for name in indexes)
    assert not any("label" in name for name in indexes)


# --- V-DB-F017-1: migration column presence ----------------------------------


def test_migration_adds_audit_column(committed_engine):
    engine = committed_engine
    with engine.connect() as conn:
        columns = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'audit_logs' AND table_schema = 'public'"
                )
            )
            .scalars()
            .all()
        )
    assert "api_key_label" in columns
    # F017 adds no deleted_at/version/last_used_at to api_keys.
    with engine.connect() as conn:
        key_columns = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'api_keys' AND table_schema = 'public'"
                )
            )
            .scalars()
            .all()
        )
    assert key_columns == {
        "id",
        "user_id",
        "label",
        "key_hash",
        "created_by",
        "created_at",
        "expires_at",
        "revoked_at",
    }


def _insert_key_row(engine, user_id, key_hash: str, label: str = "ci"):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO api_keys (user_id, label, key_hash, created_by, expires_at) "
                "VALUES (:uid, :label, :hash, :uid, now() + interval '1 day')"
            ),
            {"uid": user_id, "label": label, "hash": key_hash},
        )