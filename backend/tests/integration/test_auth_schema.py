"""F002 database-constraint and migration integration tests (TD-2 V9, B15-B21).

All assertions run against a real PostgreSQL database; SQLite would not prove
CHECK / UUID-default / FK / index behaviour.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$c29tZWhhc2g"

_counter = 0


def _unique_username(prefix: str = "user") -> str:
    global _counter
    _counter += 1
    return f"{prefix}{_counter:03d}"


def _insert_user(conn, username: str, **overrides) -> None:
    values = {
        "username": username,
        "password_hash": VALID_HASH,
        "role": "VIEWER",
        "status": "ACTIVE",
        "version": 1,
    }
    values.update(overrides)
    conn.execute(
        text(
            "INSERT INTO users (username, password_hash, role, status, version) "
            "VALUES (:username, :password_hash, :role, :status, :version)"
        ),
        values,
    )


def _create_user(engine, username: str | None = None, **overrides) -> uuid.UUID:
    chosen = username or _unique_username()
    with engine.begin() as conn:
        _insert_user(conn, chosen, **overrides)
        return conn.execute(
            text("SELECT id FROM users WHERE username = :u"), {"u": chosen}
        ).scalar()


def _expect_integrity_error(engine, username: str | None = None, **overrides) -> None:
    chosen = username or _unique_username("reject")
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_user(conn, chosen, **overrides)


# --- B15 users CHECK ---------------------------------------------------------


def test_users_check_rejects_invalid_role_status_version(committed_engine):
    _expect_integrity_error(committed_engine, role="SUPERUSER")
    _expect_integrity_error(committed_engine, status="BOGUS")
    _expect_integrity_error(committed_engine, version=0)

    for role in ("VIEWER", "EDITOR", "ADMIN"):
        assert _create_user(committed_engine, role=role) is not None
    for status in ("ACTIVE", "DISABLED"):
        assert _create_user(committed_engine, status=status) is not None


# --- B16 username normalization / uniqueness ---------------------------------


def test_username_format_and_uniqueness(committed_engine):
    _expect_integrity_error(committed_engine, username="Admin")
    _expect_integrity_error(committed_engine, username="ab")
    _expect_integrity_error(committed_engine, username="bad name")

    taken = _unique_username()
    _create_user(committed_engine, username=taken)
    _expect_integrity_error(committed_engine, username=taken)


def test_username_normalization_service():
    from app.services.auth import is_valid_username, normalize_username

    assert normalize_username("  Admin  ") == "admin"
    assert is_valid_username(normalize_username("Admin.User-1"))
    assert not is_valid_username(normalize_username("ab"))
    assert not is_valid_username(normalize_username("bad name"))


# --- B18 UUID default & extensions -------------------------------------------


def test_uuid_defaults_and_no_pgcrypto(committed_engine):
    user_id = _create_user(committed_engine)
    assert isinstance(user_id, uuid.UUID)

    token_hash = hashlib.sha256(b"uuid-default-token").hexdigest()
    with committed_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_sessions (user_id, token_hash, expires_at) "
                "VALUES (:user_id, :token_hash, now() + interval '1 hour')"
            ),
            {"user_id": user_id, "token_hash": token_hash},
        )
        session_id = conn.execute(
            text("SELECT id FROM user_sessions WHERE token_hash = :t"),
            {"t": token_hash},
        ).scalar()
    assert isinstance(session_id, uuid.UUID)

    with committed_engine.connect() as conn:
        extensions = set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())
    assert "pgcrypto" not in extensions
    assert "uuid-ossp" not in extensions


# --- B19 FK ON DELETE RESTRICT -----------------------------------------------


def test_fk_restrict_blocks_user_delete(committed_engine):
    user_id = _create_user(committed_engine)
    token_hash = hashlib.sha256(b"fk-restrict-token").hexdigest()
    with committed_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_sessions (user_id, token_hash, expires_at) "
                "VALUES (:user_id, :token_hash, now() + interval '1 hour')"
            ),
            {"user_id": user_id, "token_hash": token_hash},
        )

    with pytest.raises(IntegrityError):
        with committed_engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})

    # Both rows survive the rejected delete.
    with committed_engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM users WHERE id = :id"), {"id": user_id}
        ).scalar() == 1
        assert conn.execute(
            text("SELECT count(*) FROM user_sessions WHERE user_id = :id"),
            {"id": user_id},
        ).scalar() == 1

    # Without sessions the delete succeeds.
    with committed_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM user_sessions WHERE user_id = :id"), {"id": user_id}
        )
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


# --- B20 indexes / unique constraints ----------------------------------------


def test_indexes_and_unique_constraints_exist(pg_engine, committed_engine):
    inspector = inspect(pg_engine)
    index_names = {idx["name"] for idx in inspector.get_indexes("user_sessions")}
    assert {"ix_user_sessions_user_id", "ix_user_sessions_expires_at"} <= index_names

    assert "uq_users_username" in {
        c["name"] for c in inspector.get_unique_constraints("users")
    }
    assert "uq_user_sessions_token_hash" in {
        c["name"] for c in inspector.get_unique_constraints("user_sessions")
    }

    with pg_engine.connect() as conn:
        constraints = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'users'::regclass"
                )
            ).scalars()
        )
        session_constraints = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'user_sessions'::regclass"
                )
            ).scalars()
        )
    assert {
        "pk_users",
        "uq_users_username",
        "ck_users_username_format",
        "ck_users_role",
        "ck_users_status",
        "ck_users_version",
        "ck_users_password_hash_nonempty",
    } <= constraints
    assert {
        "pk_user_sessions",
        "uq_user_sessions_token_hash",
        "fk_user_sessions_user_id_users",
        "ck_user_sessions_token_hash_format",
        "ck_user_sessions_expires_after_created",
    } <= session_constraints
    assert (
        conn_fk_ondelete(pg_engine) == "r"
    ), "fk_user_sessions_user_id_users must be ON DELETE RESTRICT (confdeltype 'r')"


def conn_fk_ondelete(engine) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT confdeltype FROM pg_constraint "
                "WHERE conname = 'fk_user_sessions_user_id_users'"
            )
        ).scalar()


def test_duplicate_token_hash_rejected(committed_engine):
    user_id = _create_user(committed_engine)
    token_hash = hashlib.sha256(b"dup-token").hexdigest()
    with committed_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_sessions (user_id, token_hash, expires_at) "
                "VALUES (:u, :t, now() + interval '1 hour')"
            ),
            {"u": user_id, "t": token_hash},
        )
    with pytest.raises(IntegrityError):
        with committed_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_sessions (user_id, token_hash, expires_at) "
                    "VALUES (:u, :t, now() + interval '1 hour')"
                ),
                {"u": user_id, "t": token_hash},
            )


# --- B21 remaining CHECKs and migration reversibility ------------------------


def test_remaining_check_constraints(committed_engine):
    user_id = _create_user(committed_engine)

    # token_hash must be 64 lowercase hex.
    with pytest.raises(IntegrityError):
        with committed_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_sessions (user_id, token_hash, expires_at) "
                    "VALUES (:u, 'not-a-hash', now() + interval '1 hour')"
                ),
                {"u": user_id},
            )

    # expires_at must be strictly after created_at.
    with pytest.raises(IntegrityError):
        with committed_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_sessions (user_id, token_hash, expires_at) "
                    "VALUES (:u, :t, now() - interval '1 hour')"
                ),
                {"u": user_id, "t": hashlib.sha256(b"past").hexdigest()},
            )

    # password_hash must not be blank.
    _expect_integrity_error(committed_engine, password_hash="   ")


def test_migration_0002_is_reversible(pg_engine, alembic_runner):
    head = alembic_runner.head_revision()
    with pg_engine.connect() as conn:
        assert list(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        ) == [head]
    alembic_runner.upgrade("head")

    def table_names() -> set[str]:
        with pg_engine.connect() as conn:
            return set(
                conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).scalars()
            )

    assert {"users", "user_sessions"} <= table_names()

    alembic_runner.downgrade("0001_baseline")
    remaining = table_names()
    assert "users" not in remaining
    assert "user_sessions" not in remaining
    with pg_engine.connect() as conn:
        assert set(
            conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars()
        ) == {"0001_baseline"}

    alembic_runner.upgrade("head")
    assert {"users", "user_sessions"} <= table_names()
    with pg_engine.connect() as conn:
        assert set(
            conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars()
        ) == {head}