"""Pure-logic smoke tests (SQLite / no DB).

These are NEVER evidence for PostgreSQL constraints, extensions, migrations or
concurrency. They only assert importability and basic wiring.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.smoke


def test_app_exposes_health_liveness_without_db():
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "csm-backend"}


def test_v1_prefix_is_centralised():
    from app.api.v1.router import api_v1_router

    assert api_v1_router.prefix == "/api/v1"
    paths = {route.path for route in api_v1_router.routes}
    assert "/api/v1/health" in paths
    assert "/api/v1/health/ready" in paths


def test_naming_convention_matches_db_d6():
    from app.models.base import NAMING_CONVENTION

    assert NAMING_CONVENTION["pk"] == "pk_%(table_name)s"
    assert NAMING_CONVENTION["fk"] == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}


def test_settings_read_env(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    settings = Settings(_env_file=None)
    assert settings.database_url.endswith("/db")
    assert settings.db_pool_size == 7
    assert "statement_timeout" in settings.db_connect_options
    assert "lock_timeout" in settings.db_connect_options