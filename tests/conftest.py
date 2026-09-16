"""共享测试夹具。"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from tests.database.helpers import raw_connection_dsn, require_dsn, upgrade_to_head

# 一个不会真正连上的 DSN：用于不触发数据库访问的测试（参数校验、路由隔离）。
OFFLINE_DSN = "postgresql+psycopg://nobody:nobody@127.0.0.1:1/none"

#: ``auth_client`` / ``auth_client_and_raw`` 夹具建立的账号（口令满足 R-AUTH-004）。
AUTH_USERNAME = "auth-user"
AUTH_PASSWORD = "auth-password-123"


@pytest.fixture
def database_url() -> str:
    """可用的 PostgreSQL DSN；未配置时 skip（不伪造通过）。"""
    return require_dsn()


def _client(environment: str, dsn: str) -> TestClient:
    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(environment=environment, database_url=dsn))
    return TestClient(app, raise_server_exceptions=False)


def create_user(dsn: str, username: str, password: str, *, active: bool = True) -> int:
    """通过应用服务建立账号（绕过 HTTP，但不复制业务规则）。"""
    from app.auth import service
    from app.config import Settings
    from app.db.session import create_db_engine, create_session_factory
    from app.models.user import User

    engine = create_db_engine(Settings(environment="test", database_url=dsn))
    try:
        with create_session_factory(engine)() as session:
            result = service.create_initial_admin(session, username, password)
            if not active:
                session.execute(update(User).where(User.username == username).values(active=False))
            session.commit()
            return result.user_id
    finally:
        engine.dispose()


def login(client: TestClient, username: str = AUTH_USERNAME, password: str = AUTH_PASSWORD):
    """登录并断言成功。"""
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response


@pytest.fixture
def offline_client() -> Iterator[TestClient]:
    """dev 配置、不访问数据库的客户端（无 Cookie）。"""
    with _client("dev", OFFLINE_DSN) as client:
        yield client


@pytest.fixture
def app_client(database_url: str) -> Iterator[TestClient]:
    """dev 配置、已迁移数据库、**未认证**（无 Cookie）的客户端。"""
    engine = upgrade_to_head(database_url)
    try:
        with _client("dev", database_url) as client:
            yield client
    finally:
        engine.dispose()


@pytest.fixture
def app_client_and_raw(
    database_url: str,
) -> Iterator[tuple[TestClient, psycopg.Connection]]:
    """已迁移数据库的 **未认证** 客户端 + **绕过应用层**的原始 psycopg 连接。"""
    engine = upgrade_to_head(database_url)
    try:
        with _client("dev", database_url) as client:
            with psycopg.connect(raw_connection_dsn(database_url)) as conn:
                conn.autocommit = True
                yield client, conn
    finally:
        engine.dispose()


@pytest.fixture
def auth_client(database_url: str) -> Iterator[TestClient]:
    """已迁移数据库 + 已建立账号 + 已登录（携带会话 Cookie）的客户端。"""
    engine = upgrade_to_head(database_url)
    create_user(database_url, AUTH_USERNAME, AUTH_PASSWORD)
    try:
        with _client("dev", database_url) as client:
            login(client)
            yield client
    finally:
        engine.dispose()


@pytest.fixture
def auth_client_and_raw(
    database_url: str,
) -> Iterator[tuple[TestClient, psycopg.Connection]]:
    """已登录客户端 + **绕过应用层**的原始 psycopg 连接。"""
    engine = upgrade_to_head(database_url)
    create_user(database_url, AUTH_USERNAME, AUTH_PASSWORD)
    try:
        with _client("dev", database_url) as client:
            with psycopg.connect(raw_connection_dsn(database_url)) as conn:
                conn.autocommit = True
                login(client)
                yield client, conn
    finally:
        engine.dispose()
