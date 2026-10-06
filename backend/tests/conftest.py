"""Pytest fixtures for the CSM backend test suite.

Integration fixtures require a real PostgreSQL instance through
``TEST_DATABASE_URL`` (database design DB-D10). SQLite is never used as
constraint/extension/migration/concurrency evidence.

Fixture layering:
- session: rebuild ``public`` schema, run ``alembic upgrade head``;
- function: outer transaction + savepoint, rollback after each test;
- concurrency: real commits, teardown TRUNCATE (excluding ``alembic_version``).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _require_test_database_url() -> str:
    """Return TEST_DATABASE_URL after applying the DB-D10 safety guards."""
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL is not set; integration tests require a real PostgreSQL database"
        )
    database = make_url(url).database or ""
    assert "test" in database.lower(), (
        f"refusing to run integration tests against non-test database {database!r} (DB-D10 guard)"
    )
    production = os.environ.get("DATABASE_URL", "").strip()
    assert url != production, "TEST_DATABASE_URL must differ from DATABASE_URL (DB-D10 guard)"
    return url


class AlembicRunner:
    """Run Alembic commands against a specific database URL."""

    def __init__(self, url: str) -> None:
        self.url = url

    def _config(self):
        from alembic.config import Config

        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        cfg.set_main_option("sqlalchemy.url", self.url)
        return cfg

    def _prepare(self) -> None:
        # env.py reads the URL from Settings; point it at the test DB and
        # invalidate the settings cache so the override takes effect.
        from app.core.config import get_settings

        os.environ["DATABASE_URL"] = self.url
        get_settings.cache_clear()

    def upgrade(self, revision: str = "head") -> None:
        from alembic import command

        self._prepare()
        command.upgrade(self._config(), revision)

    def downgrade(self, revision: str = "base") -> None:
        from alembic import command

        self._prepare()
        command.downgrade(self._config(), revision)

    def head_revision(self) -> str:
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(self._config())
        return script.get_current_head()


def _recreate_public_schema(url: str) -> None:
    admin = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT", future=True)
    try:
        with admin.connect() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _require_test_database_url()


@pytest.fixture(scope="session")
def alembic_runner(test_database_url: str) -> AlembicRunner:
    return AlembicRunner(test_database_url)


@pytest.fixture(scope="session")
def pg_engine(test_database_url: str):
    """Session engine bound to a freshly migrated real PostgreSQL test DB."""
    _recreate_public_schema(test_database_url)
    AlembicRunner(test_database_url).upgrade("head")

    engine = create_engine(test_database_url, poolclass=NullPool, future=True)
    try:
        yield engine
    finally:
        engine.dispose()
        # Leave no residual objects for the next run (V4).
        _recreate_public_schema(test_database_url)


@pytest.fixture
def db_session(pg_engine):
    """Function-scoped session wrapped in an outer transaction + savepoint."""
    connection = pg_engine.connect()
    transaction = connection.begin()
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def committed_engine(pg_engine):
    """Engine for tests that must perform real commits (V7/B5/B6).

    Teardown TRUNCATEs every non-``alembic_version`` table and drops test-only
    probe tables so repeated runs leave no residue.
    """
    yield pg_engine
    with pg_engine.begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        if tables:
            quoted = ", ".join(f'public."{t}"' for t in tables)
            conn.execute(text(f"TRUNCATE TABLE {quoted}"))
        for table in tables:
            if table.startswith("_f001"):
                conn.execute(text(f'DROP TABLE IF EXISTS public."{table}"'))