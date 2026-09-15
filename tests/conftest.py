"""共享测试夹具。"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.database.helpers import raw_connection_dsn, require_dsn, upgrade_to_head

# 一个不会真正连上的 DSN：用于不触发数据库访问的测试（参数校验、路由隔离）。
OFFLINE_DSN = "postgresql+psycopg://nobody:nobody@127.0.0.1:1/none"


@pytest.fixture
def database_url() -> str:
    """可用的 PostgreSQL DSN；未配置时 skip（不伪造通过）。"""
    return require_dsn()


def _client(environment: str, dsn: str) -> TestClient:
    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(environment=environment, database_url=dsn))
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def offline_client() -> Iterator[TestClient]:
    """dev 配置、不访问数据库的客户端（参数校验 / 404 隔离测试用）。"""
    with _client("dev", OFFLINE_DSN) as client:
        yield client


@pytest.fixture
def app_client(database_url: str) -> Iterator[TestClient]:
    """dev 配置、已迁移数据库的客户端。"""
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
    """已迁移数据库的 dev 客户端 + **绕过应用层**的原始 psycopg 连接。

    用于 AC-07 / A08：由测试直接在数据层预置 ``deleted_at`` 非空行，
    再断言 API 读取路径的排除行为。
    """
    engine = upgrade_to_head(database_url)
    try:
        with _client("dev", database_url) as client:
            with psycopg.connect(raw_connection_dsn(database_url)) as conn:
                conn.autocommit = True
                yield client, conn
    finally:
        engine.dispose()
