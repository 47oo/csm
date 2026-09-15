"""数据库测试辅助：DSN 解析、Alembic 调用、原始连接。

所有数据库级断言都**绕过应用层**，直接对 PostgreSQL 执行 SQL（§21 / 架构
Test Work）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import Engine, create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[2]

MIGRATION_HEAD = "0001_f012_baseline"

SKIP_REASON = "未配置 PostgreSQL 测试库：设置 CSM_TEST_DATABASE_URL（或 CSM_DATABASE_URL）后重跑。"


def get_dsn() -> str | None:
    return os.environ.get("CSM_TEST_DATABASE_URL") or os.environ.get("CSM_DATABASE_URL")


def require_dsn() -> str:
    """返回 DSN，若不可用则跳过（不伪造通过）。"""
    import pytest

    dsn = get_dsn()
    if not dsn:
        pytest.skip(SKIP_REASON)
    try:
        engine = create_engine(dsn)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"{SKIP_REASON}（连接失败：{exc}）")
    return dsn


def raw_connection_dsn(dsn: str) -> str:
    """把 SQLAlchemy URL 转成 psycopg 可直接使用的 URL。"""
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def run_alembic(*args: str, dsn: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CSM_DATABASE_URL"] = dsn
    env["CSM_ENVIRONMENT"] = "test"
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def alembic_current(dsn: str) -> str | None:
    engine = create_engine(dsn)
    with engine.connect() as conn:
        try:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:  # noqa: BLE001
            version = None
    engine.dispose()
    return version


def reset_schema(dsn: str) -> Engine:
    engine = create_engine(dsn)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    return engine


def upgrade_to_head(dsn: str) -> Engine:
    engine = reset_schema(dsn)
    result = run_alembic("upgrade", "head", dsn=dsn)
    if result.returncode != 0:  # pragma: no cover - 失败时给出诊断
        raise AssertionError(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")
    return engine


def table_names(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalars()
        return set(rows)
