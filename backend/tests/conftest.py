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


# --- F002 authentication fixtures -----------------------------------------
# These reuse the real PostgreSQL ``committed_engine`` (no SQLite) and the
# production ``create_app`` + ``require_permission`` dependency. Only the DB
# dependency is overridden so routes talk to the test database.


@pytest.fixture
def auth_session_factory(committed_engine):
    """Session factory bound to the real test database (commits persist)."""
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(
        bind=committed_engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )


@pytest.fixture
def auth_app(auth_session_factory, request):
    """Production app with ``get_db`` overridden to the test database.

    Pre-F027 suites assume non-ADMIN users can see every Cluster.  F027 changes
    that rule, so those suites run with an explicit unrestricted scope override;
    the F026/F027 suites exercise the real ``get_access_scope`` dependency.  This
    is a test-only compatibility shim and never changes production behavior.
    """
    from app.core.access_scope import AccessScope, get_access_scope
    from app.core.db import get_db
    from app.main import create_app

    app = create_app()
    path = str(getattr(request.node, "fspath", "")).replace("\\", "/")
    legacy_scope = "tests/integration" in path and not path.endswith(
        ("test_cluster_authorizations.py", "test_f027_access_scope.py")
    )

    def _override():
        session = auth_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override
    if legacy_scope:
        app.dependency_overrides[get_access_scope] = lambda: AccessScope(
            unrestricted=True, cluster_ids=frozenset()
        )
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def api_client(auth_app):
    """ASGI test client (cookies preserved across requests)."""
    from fastapi.testclient import TestClient

    with TestClient(auth_app) as client:
        yield client


@pytest.fixture
def bootstrap_admin(auth_session_factory):
    """Run the production bootstrap CLI against the test database."""
    from app.cli.bootstrap_admin import run as bootstrap_run
    from app.core.config import Settings

    def _run(username: str = "admin", password: str = "admin-pass-123", expect: int = 0):
        settings = Settings(
            _env_file=None,
            initial_admin_username=username,
            initial_admin_password=password,
        )
        code = bootstrap_run(settings=settings, session_factory=auth_session_factory)
        assert code == expect, f"bootstrap exit code {code} != expected {expect}"
        return settings

    return _run


@pytest.fixture
def make_user(auth_session_factory):
    """Factory inserting a role/status user with a real argon2id hash."""
    from app.core.permissions import Role
    from app.core.security import hash_password
    from app.models.user import User, UserStatus
    from app.services.auth import normalize_username

    def _make(
        role: str = "VIEWER",
        status: str = "ACTIVE",
        username: str | None = None,
        password: str = "user-pass-123",
    ):
        normalized = normalize_username(username or f"{role.lower()}-user")
        with auth_session_factory() as session:
            user = User(
                username=normalized,
                password_hash=hash_password(password),
                role=Role(role).value,
                status=UserStatus(status).value,
                version=1,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user, password

    return _make


@pytest.fixture
def login(api_client):
    """POST /auth/login helper."""

    def _login(username: str, password: str):
        return api_client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )

    return _login
