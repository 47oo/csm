"""F004 database constraint / trigger / migration tests (V13, B7/B8/B12-B14/B37-B45).

Real PostgreSQL only (DB-D10): SQLite cannot prove CHECK/UNIQUE/FK/UUID/trigger
behaviour. Raw SQL is used deliberately so the evidence does not depend on ORM
validation.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

CONSTRAINT_NAMES = {
    "resources": {
        "pk_resources",
        "fk_resources_cluster_id_clusters",
        "ck_resources_hostname_not_blank",
        "ck_resources_hostname_trimmed",
        "ck_resources_hostname_no_ws_control",
        "ck_resources_hostname_length",
        "ck_resources_hostname_ascii_lower",
        "ck_resources_hostname_key_not_blank",
        "ck_resources_hostname_key_length",
        "ck_resources_hostname_key_matches",
        "ck_resources_resource_type",
        "ck_resources_role",
        "ck_resources_status",
        "ck_resources_metadata_object",
        "ck_resources_version",
    }
}

RESOURCE_INDEX_NAMES = {
    "uq_resources_cluster_id_hostname_key",
    "ix_resources_cluster_id",
    "ix_resources_resource_type",
    "ix_resources_role",
    "ix_resources_status",
    "ix_resources_deleted_at",
    "ix_resources_hostname_key",
}

TRIGGER_NAMES = {"trg_resources_immutable_fields"}


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


def insert_cluster(conn, **cols) -> uuid.UUID:
    columns = {"code": "C", "code_key": "C", "name": "n"}
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(f"INSERT INTO clusters ({names}) VALUES ({placeholders}) RETURNING id"),
        columns,
    ).scalar_one()


def insert_resource(conn, cluster_id: uuid.UUID, **cols) -> uuid.UUID:
    columns = {
        "cluster_id": cluster_id,
        "hostname": "h",
        "hostname_key": "h",
        "resource_type": "BARE_METAL",
    }
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = []
    params: dict = {}
    for name, value in columns.items():
        if name == "metadata" and isinstance(value, (dict, list)):
            params[name] = json.dumps(value)
            placeholders.append(f"CAST(:{name} AS jsonb)")
        else:
            params[name] = value
            placeholders.append(f":{name}")
    return conn.execute(
        text(
            f"INSERT INTO resources ({names}) VALUES ({', '.join(placeholders)}) "
            "RETURNING id"
        ),
        params,
    ).scalar_one()


# --- V13: constraints --------------------------------------------------------


def test_resource_defaults_and_uuid(committed_engine):
    with committed_engine.begin() as conn:
        cluster_id = insert_cluster(conn)
        resource_id = insert_resource(conn, cluster_id, hostname="cn001", hostname_key="cn001")
        assert isinstance(resource_id, uuid.UUID)
        role, status, meta, version, deleted = conn.execute(
            text("SELECT role, status, metadata, version, deleted_at FROM resources WHERE id = :id"),
            {"id": resource_id},
        ).one()
        assert role == "OTHER"
        assert status == "UNKNOWN"
        assert meta == {}
        assert version == 1
        assert deleted is None


def test_hostname_checks(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cluster_id = insert_cluster(conn)

    # not blank / trimmed / internal whitespace / control / length
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
        "VALUES (:cid, '', '', 'BARE_METAL')",
        {"cid": cluster_id},
    )
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
        "VALUES (:cid, ' h', ' h', 'BARE_METAL')",
        {"cid": cluster_id},
    )
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
        "VALUES (:cid, 'c n', 'c n', 'BARE_METAL')",
        {"cid": cluster_id},
    )
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
        "VALUES (:cid, E'bad\\u0001x', E'bad\\u0001x', 'BARE_METAL')",
        {"cid": cluster_id},
    )
    # ASCII upper-case storage is rejected by ck_resources_hostname_ascii_lower
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
        "VALUES (:cid, 'CN001', 'cn001', 'BARE_METAL')",
        {"cid": cluster_id},
    )
    # key mismatch rejected by ck_resources_hostname_key_matches
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
        "VALUES (:cid, 'cn001', 'other', 'BARE_METAL')",
        {"cid": cluster_id},
    )
    # length 1 / 253 accepted, 254 rejected at the column/CHECK
    with engine.begin() as conn:
        insert_resource(conn, cluster_id, hostname="a", hostname_key="a")
        insert_resource(conn, cluster_id, hostname="b" * 253, hostname_key="b" * 253)
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            insert_resource(conn, cluster_id, hostname="c" * 254, hostname_key="c" * 254)


def test_hostname_unicodedata_ascii_only(committed_engine):
    """DB-D36: translate(btrim(...)) folds ASCII only; non-ASCII kept verbatim."""
    engine = committed_engine
    with engine.begin() as conn:
        cluster_id = insert_cluster(conn)
        insert_resource(conn, cluster_id, hostname="straße", hostname_key="straße")
        insert_resource(conn, cluster_id, hostname="ﬁle", hostname_key="ﬁle")
        insert_resource(conn, cluster_id, hostname="山河3", hostname_key="山河3")
        # CN001 would store lower-case, key lower-case; translate is consistent
        insert_resource(conn, cluster_id, hostname="cn001", hostname_key="cn001")
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
        "VALUES (:cid, 'straße', 'STRASSE', 'BARE_METAL')",
        {"cid": cluster_id},
    )
    # ck_resources_hostname_key_matches uses translate(), never lower()
    with engine.connect() as conn:
        definition = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_resources_hostname_key_matches'"
            )
        ).scalar_one()
    assert "translate(" in definition
    assert "lower(" not in definition


def test_enum_metadata_version_checks(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cluster_id = insert_cluster(conn)

    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
        "VALUES (:cid, 'h1', 'h1', 'STORAGE')",
        {"cid": cluster_id},
    )
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type, role) "
        "VALUES (:cid, 'h2', 'h2', 'BARE_METAL', 'BOGUS')",
        {"cid": cluster_id},
    )
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type, status) "
        "VALUES (:cid, 'h3', 'h3', 'BARE_METAL', 'RUNNING')",
        {"cid": cluster_id},
    )
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type, version) "
        "VALUES (:cid, 'h4', 'h4', 'BARE_METAL', 0)",
        {"cid": cluster_id},
    )
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type, metadata) "
        "VALUES (:cid, 'h5', 'h5', 'BARE_METAL', '[]'::jsonb)",
        {"cid": cluster_id},
    )
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type, metadata) "
        "VALUES (:cid, 'h6', 'h6', 'BARE_METAL', '\"x\"'::jsonb)",
        {"cid": cluster_id},
    )
    with engine.begin() as conn:
        insert_resource(
            conn,
            cluster_id,
            hostname="ok1",
            hostname_key="ok1",
            metadata={"x": 1},
            role="GPU",
            status="IDLE",
        )


# --- V13/B37/B38: partial unique --------------------------------------------


def test_partial_unique_index_semantics(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        c1 = insert_cluster(conn, code="C1", code_key="C1", name="c1")
        c2 = insert_cluster(conn, code="C2", code_key="C2", name="c2")
        insert_resource(conn, c1, hostname="cn001", hostname_key="cn001")

    # duplicate undeleted in same cluster rejected
    _expect_violation(
        engine,
        "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
        "VALUES (:cid, 'cn001', 'cn001', 'BARE_METAL')",
        {"cid": c1},
    )
    # cross-cluster same hostname allowed
    with engine.begin() as conn:
        insert_resource(conn, c2, hostname="cn001", hostname_key="cn001")
    # soft-deleted row releases the key -> same key can be inserted again
    with engine.begin() as conn:
        deleted_id = insert_resource(
            conn, c1, hostname="cn002", hostname_key="cn002"
        )
        conn.execute(
            text("UPDATE resources SET deleted_at = now() WHERE id = :id"),
            {"id": deleted_id},
        )
        insert_resource(conn, c1, hostname="cn002", hostname_key="cn002")

    with engine.connect() as conn:
        indexdef = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname='public' "
                "AND indexname='uq_resources_cluster_id_hostname_key'"
            )
        ).scalar_one()
    assert "deleted_at IS NULL" in indexdef
    assert "UNIQUE" in indexdef.upper()


def test_no_pg_trgm_gin_on_resources(committed_engine):
    with committed_engine.connect() as conn:
        gin_indexes = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname='public' AND tablename='resources' "
                "AND indexdef ILIKE '%USING gin%'"
            )
        ).scalars().all()
    assert gin_indexes == []


# --- V13/B13/B14: immutable trigger -----------------------------------------


def test_immutable_fields_trigger(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        c1 = insert_cluster(conn, code="C1", code_key="C1", name="c1")
        c2 = insert_cluster(conn, code="C2", code_key="C2", name="c2")
        resource_id = insert_resource(conn, c1)

    _expect_violation(
        engine,
        "UPDATE resources SET cluster_id = :c2 WHERE id = :id",
        {"c2": c2, "id": resource_id},
    )
    _expect_violation(
        engine,
        "UPDATE resources SET resource_type = 'VIRTUAL_MACHINE' WHERE id = :id",
        {"id": resource_id},
    )
    # soft-delete / mutable fields are permitted
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE resources SET hostname='renamed', hostname_key='renamed', "
                "role='GPU', status='IDLE', deleted_at=now() WHERE id = :id"
            ),
            {"id": resource_id},
        )


def test_fk_cluster_restrict(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        c1 = insert_cluster(conn, code="C1", code_key="C1", name="c1")
        insert_resource(conn, c1)
    _expect_violation(engine, "DELETE FROM clusters WHERE id = :id", {"id": c1})
    with engine.connect() as conn:
        confdeltype = conn.execute(
            text(
                "SELECT confdeltype FROM pg_constraint "
                "WHERE conname = 'fk_resources_cluster_id_clusters'"
            )
        ).scalar_one()
    assert confdeltype == "r"


# --- V13/B45: soft-delete filter on relationship load ------------------------


def test_soft_delete_filter_applies_to_relationship(committed_engine):
    """with_loader_criteria(include_aliases=True) hides a soft-deleted cluster."""
    from app.models.cluster import Cluster
    from app.models.resource import Resource
    from sqlalchemy.orm import selectinload

    with committed_engine.begin() as conn:
        c1 = insert_cluster(conn, code="C1", code_key="C1", name="c1")
        insert_resource(conn, c1, hostname="cn001", hostname_key="cn001")
        # Bypass the API reference check to soft-delete the owning cluster.
        conn.execute(
            text("UPDATE clusters SET deleted_at = now() WHERE id = :id"), {"id": c1}
        )

    factory = sessionmaker(bind=committed_engine, expire_on_commit=False, future=True)
    with factory() as session:
        resource = session.execute(
            select(Resource).options(selectinload(Resource.cluster))
        ).scalars().one()
        # The relationship loader is filtered by the same criteria -> None.
        assert resource.cluster is None
        assert resource.cluster_id == c1


# --- V13/B44: object catalogue and migration --------------------------------


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
        assert RESOURCE_INDEX_NAMES <= indexes

        triggers = set(
            conn.execute(
                text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
            ).scalars()
        )
        assert TRIGGER_NAMES <= triggers


def test_resources_migration_up_down_up(pg_engine, alembic_runner):
    head = alembic_runner.head_revision()
    assert head >= "0004_resources"
    with pg_engine.connect() as conn:
        versions = list(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        )
    assert versions == [head]
    assert "resources" in _tables(pg_engine)

    alembic_runner.downgrade("0003_clusters_audit")
    remaining = _tables(pg_engine)
    assert "resources" not in remaining
    # F003 objects survive the downgrade
    assert {"clusters", "audit_logs"} <= remaining
    with pg_engine.connect() as conn:
        assert list(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        ) == ["0003_clusters_audit"]

    alembic_runner.upgrade("head")
    assert {"resources", "clusters", "audit_logs"} <= _tables(pg_engine)
    with pg_engine.connect() as conn:
        assert list(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        ) == [head]