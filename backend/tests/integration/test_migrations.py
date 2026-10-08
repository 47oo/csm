"""Migration baseline integration tests (TD-2 V2/V3/V3b, B1–B4).

Requires a real PostgreSQL database; uses the session ``pg_engine`` fixture.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _declared_baseline_extensions() -> set[str]:
    path = BACKEND_DIR / "alembic" / "versions" / "0001_baseline.py"
    spec = importlib.util.spec_from_file_location("_f001_baseline", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name for name, _schema in module.EXTENSIONS}


def _extensions(engine) -> set[str]:
    with engine.connect() as conn:
        return set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())


def _alembic_versions(engine) -> list[str]:
    with engine.connect() as conn:
        return list(conn.execute(text("SELECT version_num FROM alembic_version")).scalars())


def test_upgrade_downgrade_upgrade_is_consistent(pg_engine, alembic_runner):
    """V2/B1: up -> down -> up converges to the same head; downgrade is asymmetric."""
    head = alembic_runner.head_revision()
    assert _alembic_versions(pg_engine) == [head]

    alembic_runner.downgrade("base")
    # DB-D4: downgrade removes the alembic version row but NOT the extension.
    assert _alembic_versions(pg_engine) == []
    after_down = _extensions(pg_engine)
    assert "pg_trgm" in after_down, "pg_trgm must survive baseline downgrade (DB-D4)"
    # F008 0008 enables btree_gist and its downgrade intentionally does not drop
    # it (same asymmetry as F001 DB-D4), so it survives a full downgrade.
    assert "btree_gist" in after_down, "btree_gist survives the 0008 downgrade (DB-D94)"

    alembic_runner.upgrade("head")
    assert _alembic_versions(pg_engine) == [head]
    assert "pg_trgm" in _extensions(pg_engine)
    assert "btree_gist" in _extensions(pg_engine)


def test_upgrade_is_idempotent(pg_engine, alembic_runner):
    """B2: running upgrade head twice is a no-op that keeps a single head."""
    head = alembic_runner.head_revision()
    alembic_runner.upgrade("head")
    alembic_runner.upgrade("head")
    assert _alembic_versions(pg_engine) == [head]


def test_extension_set_matches_baseline_declaration(pg_engine):
    """V3/A1: baseline declares pg_trgm; F008 0008 additionally enables btree_gist."""
    declared = _declared_baseline_extensions()
    assert declared == {"pg_trgm"}

    present = _extensions(pg_engine)
    assert "pg_trgm" in present
    # Declared baseline extensions are a subset of installed ones; the only
    # extra entries are PG default/plpgsql and pre-existing trusted extensions.
    assert declared <= present
    # btree_gist is enabled by migration 0008 (F008), not by the baseline (DB-D2).
    assert "btree_gist" in present, "0008 must enable btree_gist (DB-D88)"


def test_downgrade_non_asymmetry_is_documented(pg_engine, alembic_runner):
    """B4: after downgrade base, no business tables and version table is empty."""
    alembic_runner.downgrade("base")
    assert _alembic_versions(pg_engine) == []
    with pg_engine.connect() as conn:
        tables = set(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
    assert not (tables - {"alembic_version"}), f"unexpected business tables: {tables}"
    alembic_runner.upgrade("head")


def test_trusted_extension_installed_by_non_superuser(pg_engine):
    """V3b: confirm DB-D11 trusted-extension assumption when role is non-superuser.

    The pg_trgm migration already ran in the session fixture. When connected as
    a superuser this check is not meaningful and is skipped; when the role is a
    plain database owner the presence of pg_trgm proves the trusted install path.
    """
    with pg_engine.connect() as conn:
        is_superuser = conn.execute(
            text("SELECT current_setting('is_superuser')")
        ).scalar()
        role = conn.execute(text("SELECT current_user")).scalar()
        if is_superuser == "on":
            pytest.skip(
                f"connected role {role!r} is superuser; run against a non-superuser "
                "DB owner to exercise V3b (DB-D11)"
            )
    assert "pg_trgm" in _extensions(pg_engine)