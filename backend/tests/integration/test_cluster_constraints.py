"""F003 database constraint / trigger / migration tests (V12/V13, B34-B42).

Real PostgreSQL only (DB-D10): SQLite cannot prove CHECK/UNIQUE/FK/UUID/trigger
behaviour. Raw SQL is used deliberately so the evidence does not depend on ORM
validation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

CONSTRAINT_NAMES = {
    "clusters": {
        "pk_clusters",
        "uq_clusters_code_key",
        "ck_clusters_code_not_blank",
        "ck_clusters_code_trimmed",
        "ck_clusters_code_no_ws_control",
        "ck_clusters_code_length",
        "ck_clusters_code_key_not_blank",
        "ck_clusters_code_key_length",
        "ck_clusters_code_key_matches",
        "ck_clusters_name_not_blank",
        "ck_clusters_name_trimmed",
        "ck_clusters_name_no_control",
        "ck_clusters_status",
        "ck_clusters_metadata_object",
        "ck_clusters_version",
    },
    "audit_logs": {
        "pk_audit_logs",
        "fk_audit_logs_operator_user_id_users",
        "ck_audit_logs_operator_username_not_blank",
        "ck_audit_logs_action",
        "ck_audit_logs_at_least_one_snapshot",
        "ck_audit_logs_before_data_object",
        "ck_audit_logs_after_data_object",
    },
}

INDEX_NAMES = {
    "ix_clusters_status",
    "ix_clusters_deleted_at",
    "ix_audit_logs_object_type_object_id",
    "ix_audit_logs_operator_user_id",
    "ix_audit_logs_created_at",
}

TRIGGER_NAMES = {"trg_clusters_code_immutable", "trg_audit_logs_append_only"}


def _expect_violation(engine, sql: str, params: dict | None = None) -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(sql), params or {})


def _tables(engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


def insert_cluster(conn, **cols):
    columns = {"code": "C", "code_key": "C", "name": "n"}
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(
            f"INSERT INTO clusters ({names}) VALUES ({placeholders}) RETURNING id"
        ),
        columns,
    ).scalar_one()


# --- V12 / B34-B39: clusters constraints ------------------------------------


def test_uuid_default_and_required_columns(committed_engine):
    with committed_engine.begin() as conn:
        cluster_id = insert_cluster(conn)
        assert isinstance(cluster_id, uuid.UUID)
        status, version, meta = conn.execute(
            text("SELECT status, version, metadata FROM clusters WHERE id = :id"),
            {"id": cluster_id},
        ).one()
        assert status == "ACTIVE"
        assert version == 1
        assert meta == {}


def test_code_key_matches_and_format_checks(committed_engine):
    engine = committed_engine
    # ck_clusters_code_key_matches
    _expect_violation(
        engine,
        "INSERT INTO clusters (code, code_key, name) VALUES ('ABC', 'XYZ', 'n')",
    )
    # code not blank / trimmed / no whitespace-control / length
    _expect_violation(
        engine, "INSERT INTO clusters (code, code_key, name) VALUES ('', '', 'n')"
    )
    _expect_violation(
        engine, "INSERT INTO clusters (code, code_key, name) VALUES (' A', ' A', 'n')"
    )
    _expect_violation(
        engine, "INSERT INTO clusters (code, code_key, name) VALUES ('A B', 'A B', 'n')"
    )
    _expect_violation(
        engine,
        "INSERT INTO clusters (code, code_key, name) VALUES (E'A\\u0001', E'A\\u0001', 'n')",
    )
    # code_key not blank / length
    _expect_violation(
        engine, "INSERT INTO clusters (code, code_key, name) VALUES ('A', '', 'n')"
    )
    # CJK is accepted (D01 §5.1)
    with engine.begin() as conn:
        assert insert_cluster(conn, code="山河3", code_key="山河3", name="n")
    # F003-REV-1: code_key folding is locale-independent ASCII-only translate();
    # non-ASCII code points are preserved, not Unicode upper-cased.
    with engine.begin() as conn:
        assert insert_cluster(conn, code="straße", code_key="STRAßE", name="n")
        assert insert_cluster(conn, code="ﬁle", code_key="ﬁLE", name="n")
    _expect_violation(
        engine,
        "INSERT INTO clusters (code, code_key, name) VALUES ('straße', 'STRASSE', 'n')",
    )
    _expect_violation(
        engine,
        "INSERT INTO clusters (code, code_key, name) VALUES ('ﬁle', 'FILE', 'n')",
    )


def test_name_status_metadata_version_checks(committed_engine):
    engine = committed_engine
    _expect_violation(
        engine, "INSERT INTO clusters (code, code_key, name) VALUES ('A', 'A', '')"
    )
    _expect_violation(
        engine, "INSERT INTO clusters (code, code_key, name) VALUES ('A', 'A', ' n ')"
    )
    _expect_violation(
        engine,
        "INSERT INTO clusters (code, code_key, name) VALUES ('A', 'A', E'b\\u0001')",
    )
    _expect_violation(
        engine,
        "INSERT INTO clusters (code, code_key, name, status) VALUES ('A','A','n','BOGUS')",
    )
    _expect_violation(
        engine,
        "INSERT INTO clusters (code, code_key, name, version) VALUES ('A','A','n',0)",
    )
    _expect_violation(
        engine,
        "INSERT INTO clusters (code, code_key, name, metadata) "
        "VALUES ('A','A','n','[]'::jsonb)",
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clusters (code, code_key, name, metadata) "
                "VALUES ('OK','OK','n','{\"x\": 1}'::jsonb)"
            )
        )


def test_code_key_full_unique_includes_soft_deleted(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clusters (code, code_key, name, deleted_at) "
                "VALUES ('N96P', 'N96P', 'n', now())"
            )
        )
    # same key on a second (undeleted) row must fail: the index is full, not partial
    _expect_violation(
        engine,
        "INSERT INTO clusters (code, code_key, name) VALUES ('n96p', 'N96P', 'n')",
    )
    with engine.connect() as conn:
        indexdef = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname='public' AND indexname='uq_clusters_code_key'"
            )
        ).scalar_one()
    assert "deleted_at" not in indexdef.lower()


def test_code_is_immutable_trigger(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cluster_id = insert_cluster(conn, code="N96P", code_key="N96P", name="n")
    _expect_violation(
        engine,
        "UPDATE clusters SET code = 'OTHER', code_key = 'OTHER' WHERE id = :id",
        {"id": cluster_id},
    )
    _expect_violation(
        engine,
        "UPDATE clusters SET code_key = 'OTHER' WHERE id = :id",
        {"id": cluster_id},
    )
    # name/status/deleted_at changes are permitted
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE clusters SET name = 'renamed' WHERE id = :id"),
            {"id": cluster_id},
        )


# --- V12 / B36-B38: audit_logs constraints ----------------------------------


def test_audit_action_and_snapshot_checks(committed_engine):
    engine = committed_engine
    object_id = uuid.uuid4()
    base = (
        "INSERT INTO audit_logs "
        "(operator_username, action, object_type, object_id, after_data) "
        "VALUES ('system', :action, 'cluster', :oid, '{}'::jsonb)"
    )
    _expect_violation(engine, base, {"action": "PURGE", "oid": object_id})
    _expect_violation(engine, base, {"action": "delete", "oid": object_id})
    _expect_violation(
        engine,
        "INSERT INTO audit_logs (operator_username, action, object_type, object_id) "
        "VALUES ('system','CREATE','cluster',:oid)",
        {"oid": object_id},
    )
    _expect_violation(
        engine,
        "INSERT INTO audit_logs "
        "(operator_username, action, object_type, object_id, before_data, after_data) "
        "VALUES ('system','CREATE','cluster',:oid,'[]'::jsonb,'{}'::jsonb)",
        {"oid": object_id},
    )
    with engine.begin() as conn:
        conn.execute(text(base), {"action": "CREATE", "oid": object_id})


def test_audit_is_append_only(committed_engine):
    engine = committed_engine
    object_id = uuid.uuid4()
    with engine.begin() as conn:
        audit_id = conn.execute(
            text(
                "INSERT INTO audit_logs "
                "(operator_username, action, object_type, object_id, after_data) "
                "VALUES ('system','CREATE','cluster',:oid,'{}'::jsonb) RETURNING id"
            ),
            {"oid": object_id},
        ).scalar_one()
    _expect_violation(
        engine,
        "UPDATE audit_logs SET action = 'UPDATE' WHERE id = :id",
        {"id": audit_id},
    )
    _expect_violation(engine, "DELETE FROM audit_logs WHERE id = :id", {"id": audit_id})


def test_audit_operator_fk_is_restrict(committed_engine, make_user):
    engine = committed_engine
    user, _ = make_user(role="ADMIN")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_logs "
                "(operator_user_id, operator_username, action, object_type, object_id, after_data) "
                "VALUES (:uid, :uname, 'CREATE', 'cluster', :oid, '{}'::jsonb)"
            ),
            {"uid": user.id, "uname": user.username, "oid": uuid.uuid4()},
        )
    _expect_violation(engine, "DELETE FROM users WHERE id = :id", {"id": user.id})
    # system/CLI operators may be null
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_logs "
                "(operator_user_id, operator_username, action, object_type, object_id, after_data) "
                "VALUES (NULL, 'system', 'CREATE', 'cluster', :oid, '{}'::jsonb)"
            ),
            {"oid": uuid.uuid4()},
        )
    # confdeltype is RESTRICT, not CASCADE
    with engine.connect() as conn:
        confdeltype = conn.execute(
            text(
                "SELECT confdeltype FROM pg_constraint "
                "WHERE conname = 'fk_audit_logs_operator_user_id_users'"
            )
        ).scalar_one()
    assert confdeltype == "r"


# --- V12/B34-B38: object catalogue ------------------------------------------


def test_constraints_indexes_triggers_exist(committed_engine):
    engine = committed_engine
    with engine.connect() as conn:
        for table, expected in CONSTRAINT_NAMES.items():
            found = set(
                conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint c "
                        "JOIN pg_class t ON c.conrelid = t.oid "
                        "WHERE t.relname = :table"
                    ),
                    {"table": table},
                ).scalars()
            )
            assert expected <= found, (table, expected - found)

        indexes = set(
            conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            ).scalars()
        )
        assert INDEX_NAMES <= indexes

        triggers = set(
            conn.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars()
        )
        assert TRIGGER_NAMES <= triggers

        # The deprecated ASCII-only format CHECK from architecture DR-24 is gone (I-1).
        assert "ck_clusters_code_key_format" not in set(
            conn.execute(text("SELECT conname FROM pg_constraint")).scalars()
        )


# --- V13/B40/B42: migration ------------------------------------------------


def test_clusters_migration_up_down_up(pg_engine, alembic_runner):
    head = alembic_runner.head_revision()
    assert head == "0003_clusters_audit"
    with pg_engine.connect() as conn:
        versions = list(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        )
    assert versions == [head]
    assert {"clusters", "audit_logs"} <= _tables(pg_engine)

    alembic_runner.downgrade("0002_users_sessions")
    remaining = _tables(pg_engine)
    assert "clusters" not in remaining
    assert "audit_logs" not in remaining
    assert "users" in remaining and "user_sessions" in remaining
    with pg_engine.connect() as conn:
        assert list(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        ) == ["0002_users_sessions"]

    alembic_runner.upgrade("head")
    assert {"clusters", "audit_logs"} <= _tables(pg_engine)
    with pg_engine.connect() as conn:
        assert list(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        ) == [head]