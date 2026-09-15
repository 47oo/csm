"""T1 — Alembic migration 可应用 / 可重复应用 / 可从空库重建。"""

from __future__ import annotations

from sqlalchemy import text

from tests.database.helpers import (
    alembic_current,
    reset_schema,
    run_alembic,
    table_names,
)


def test_migration_applies_repeats_and_rebuilds(database_url):
    engine = reset_schema(database_url)

    # 空库 → 应用
    assert run_alembic("upgrade", "head", dsn=database_url).returncode == 0
    assert "clusters" in table_names(engine)
    assert alembic_current(database_url) == "0001_f012_baseline"

    # 重复应用 → no-op，无错误
    assert run_alembic("upgrade", "head", dsn=database_url).returncode == 0
    assert alembic_current(database_url) == "0001_f012_baseline"

    # 可从空库重建（downgrade base → upgrade head）
    assert run_alembic("downgrade", "base", dsn=database_url).returncode == 0
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.clusters')")).scalar()
    assert exists is None

    assert run_alembic("upgrade", "head", dsn=database_url).returncode == 0
    assert "clusters" in table_names(engine)
    engine.dispose()
