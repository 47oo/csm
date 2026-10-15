"""F017 migration ``0014_api_keys`` up/down/up evidence (V-DB-F017-1/B22).

Real PostgreSQL only. Downgrades exactly one revision to ``0013_search_indexes``
(not all the way to base) to prove the F017 delta is reversibly confined, then
restores head.
"""

from __future__ import annotations

from sqlalchemy import text


def _tables(engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


def _audit_columns(engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'audit_logs' AND table_schema = 'public'"
                )
            ).scalars()
        )


def _check_constraints(engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'public.audit_logs'::regclass AND contype = 'c'"
                )
            ).scalars()
        )


def _single_head(alembic_runner) -> str:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_runner._config())
    heads = list(script.get_heads())
    assert len(heads) == 1, heads
    return heads[0]


def test_f017_0014_downgrade_and_reupgrade_is_confined(pg_engine, alembic_runner):
    """V-DB-F017-1/B22: down to 0013 drops only F017 objects; up restores them."""
    assert _single_head(alembic_runner) == "0014_api_keys"
    assert "api_keys" in _tables(pg_engine)
    assert "api_key_label" in _audit_columns(pg_engine)
    assert "ck_audit_logs_api_key_label_not_blank" in _check_constraints(pg_engine)

    alembic_runner.downgrade("0013_search_indexes")

    assert "api_keys" not in _tables(pg_engine)
    assert "api_key_label" not in _audit_columns(pg_engine)
    assert "ck_audit_logs_api_key_label_not_blank" not in _check_constraints(pg_engine)
    # Pre-existing audit tables survive the narrow downgrade.
    assert "audit_logs" in _tables(pg_engine)
    assert "users" in _tables(pg_engine)
    with pg_engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == "0013_search_indexes"

    alembic_runner.upgrade("head")

    assert "api_keys" in _tables(pg_engine)
    assert "api_key_label" in _audit_columns(pg_engine)
    assert "ck_audit_logs_api_key_label_not_blank" in _check_constraints(pg_engine)
    assert _single_head(alembic_runner) == "0014_api_keys"