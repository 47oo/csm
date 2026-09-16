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

MIGRATION_HEAD = "0003_f002_bare_metals"

SKIP_REASON = "未配置 PostgreSQL 测试库：设置 CSM_TEST_DATABASE_URL 后重跑。"


#: 破坏性 reset 的显式豁免开关。仅供一次性容器 / CI 等确知可丢弃的库使用。
DESTRUCTIVE_RESET_OPT_IN = "CSM_ALLOW_DESTRUCTIVE_TEST_RESET"


def get_dsn() -> str | None:
    """返回**显式**测试库 DSN。

    刻意**不**回退到 ``CSM_DATABASE_URL``：``reset_schema`` 会执行
    ``DROP SCHEMA ... CASCADE``，一旦回退到开发库或真实库就会造成不可恢复的
    数据丢失（``AGENTS.md`` §6）。测试库必须由使用者显式指定。
    """
    return os.environ.get("CSM_TEST_DATABASE_URL")


def assert_safe_to_reset(dsn: str) -> None:
    """防御性检查：拒绝对疑似非测试库执行破坏性 reset。

    纵深防御 —— 即使调用方错误地传入了应用库 DSN，也在 ``DROP`` 之前终止。
    """
    if os.environ.get(DESTRUCTIVE_RESET_OPT_IN) == "1":
        return
    app_dsn = os.environ.get("CSM_DATABASE_URL")
    if app_dsn and dsn == app_dsn:
        raise AssertionError(
            "拒绝对 CSM_DATABASE_URL 指向的库执行 DROP SCHEMA（可能造成不可恢复的数据丢失）。"
            "请设置独立的 CSM_TEST_DATABASE_URL；"
            f"确需在可丢弃的库上执行时，设置 {DESTRUCTIVE_RESET_OPT_IN}=1。"
        )


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
    assert_safe_to_reset(dsn)
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
