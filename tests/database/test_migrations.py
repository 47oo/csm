"""T1 — Alembic migration 可应用 / 可重复应用 / 可从空库重建。"""

from __future__ import annotations

from sqlalchemy import text

from tests.database.helpers import (
    alembic_current,
    reset_schema,
    run_alembic,
    table_names,
    upgrade_to_head,
)


def test_migration_applies_repeats_and_rebuilds(database_url):
    engine = reset_schema(database_url)

    # 空库 → 应用
    assert run_alembic("upgrade", "head", dsn=database_url).returncode == 0
    assert {
        "clusters",
        "users",
        "sessions",
        "bare_metals",
        "virtual_machines",
        "network_interfaces",
    } <= table_names(engine)
    assert alembic_current(database_url) == "0005_f004_network_interfaces"

    # 重复应用 → no-op，无错误
    assert run_alembic("upgrade", "head", dsn=database_url).returncode == 0
    assert alembic_current(database_url) == "0005_f004_network_interfaces"

    # 可从空库重建（downgrade base → upgrade head）
    assert run_alembic("downgrade", "base", dsn=database_url).returncode == 0
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.clusters')")).scalar()
    assert exists is None

    assert run_alembic("upgrade", "head", dsn=database_url).returncode == 0
    assert {
        "clusters",
        "users",
        "sessions",
        "bare_metals",
        "virtual_machines",
        "network_interfaces",
    } <= table_names(engine)
    engine.dispose()


def test_f004_downgrade_to_0004_drops_nic_and_preserves_existing(database_url):
    """V-13：``alembic downgrade 0004_f006_virtual_machines`` 后 ``network_interfaces``
    被删、既有表（含 ``virtual_machines``）完好；再次 ``upgrade head`` 可重建。"""
    engine = upgrade_to_head(database_url)
    try:
        assert (
            run_alembic("downgrade", "0004_f006_virtual_machines", dsn=database_url).returncode == 0
        )
        assert alembic_current(database_url) == "0004_f006_virtual_machines"
        with engine.connect() as conn:
            nic = conn.execute(text("SELECT to_regclass('public.network_interfaces')")).scalar()
        assert nic is None, "downgrade 后 network_interfaces 必须被删除"
        assert {
            "clusters",
            "users",
            "sessions",
            "bare_metals",
            "virtual_machines",
        } <= table_names(engine)

        assert run_alembic("upgrade", "head", dsn=database_url).returncode == 0
        assert "network_interfaces" in table_names(engine)
        assert alembic_current(database_url) == "0005_f004_network_interfaces"
    finally:
        engine.dispose()


def test_f006_downgrade_to_0003_drops_vm_and_preserves_existing(database_url):
    """V-12：``alembic downgrade 0003_f002_bare_metals`` 后 ``virtual_machines`` 被删、
    既有表完好；再次 ``upgrade head`` 可重建。"""
    engine = upgrade_to_head(database_url)
    try:
        assert run_alembic("downgrade", "0003_f002_bare_metals", dsn=database_url).returncode == 0
        assert alembic_current(database_url) == "0003_f002_bare_metals"
        with engine.connect() as conn:
            vm = conn.execute(text("SELECT to_regclass('public.virtual_machines')")).scalar()
        assert vm is None, "downgrade 后 virtual_machines 必须被删除"
        assert {"clusters", "users", "sessions", "bare_metals"} <= table_names(engine)

        assert run_alembic("upgrade", "head", dsn=database_url).returncode == 0
        assert "virtual_machines" in table_names(engine)
        assert alembic_current(database_url) == "0005_f004_network_interfaces"
    finally:
        engine.dispose()


def test_f006_alembic_check_reports_no_schema_drift(database_url):
    """V-13：``alembic check`` 无 schema 漂移（ORM 模型与 migration 一致）。"""
    engine = upgrade_to_head(database_url)
    try:
        result = run_alembic("check", dsn=database_url)
        assert result.returncode == 0, f"alembic check 发现漂移：\n{result.stdout}\n{result.stderr}"
    finally:
        engine.dispose()
