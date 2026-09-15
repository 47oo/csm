"""数据库测试夹具：迁移后的库 + 原始 psycopg 连接（绕开应用层）。"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from tests.database.helpers import raw_connection_dsn, upgrade_to_head


@pytest.fixture
def migrated_database(database_url: str) -> Iterator[str]:
    engine = upgrade_to_head(database_url)
    try:
        yield database_url
    finally:
        engine.dispose()


@pytest.fixture
def raw_conn(migrated_database: str) -> Iterator[psycopg.Connection]:
    """原始数据库连接，不经过 SQLAlchemy / 应用 session。"""
    with psycopg.connect(raw_connection_dsn(migrated_database)) as conn:
        conn.autocommit = True
        yield conn
