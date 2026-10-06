"""Health endpoint integration tests (TD-2 V1/B7/B8).

- liveness must NOT touch the database;
- readiness executes SELECT 1;
- readiness returns 503 with a fixed body when the database is unreachable.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.db import get_db
from app.main import create_app


def test_liveness_does_not_touch_db():
    app = create_app()

    def _forbidden_dependency():
        raise AssertionError("liveness must not touch the database")
        yield  # pragma: no cover - generator marker

    app.dependency_overrides[get_db] = _forbidden_dependency
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "csm-backend"}


def test_readiness_ok_against_real_db(db_session):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "db": "up"}


def test_readiness_returns_503_when_db_unreachable():
    app = create_app()
    # Port 1 is guaranteed closed -> immediate connection refusal.
    bad_engine = create_engine(
        "postgresql+psycopg://csm:csm@127.0.0.1:1/csm",
        poolclass=NullPool,
        connect_args={"connect_timeout": 2},
        future=True,
    )
    BadSession = sessionmaker(bind=bad_engine)

    def _bad_db():
        session = BadSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _bad_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health/ready")
    finally:
        bad_engine.dispose()

    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "not_ready", "db": "down"}
    # Credential boundary: the error body must not leak the connection string.
    assert "postgresql" not in response.text
    assert "csm:csm" not in response.text