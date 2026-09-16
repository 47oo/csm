"""F014 数据库结构 guard（G-1 / G-4 / T-11-DB）。

绕过应用层直接对 PostgreSQL 断言：不存在 ``ON DELETE CASCADE`` 外键；认证表
（``users`` / ``sessions``）无 ``deleted_at`` 列（AC-05 / AC-13）。
"""

from __future__ import annotations


def test_g1_no_cascade_foreign_keys(raw_conn):
    """G-1 / R-DELETE-005：数据库中不存在 confdeltype='c'（CASCADE）的外键。"""
    cascades = raw_conn.execute(
        "SELECT conrelid::regclass::text, conname FROM pg_constraint "
        "WHERE contype = 'f' AND confdeltype = 'c'"
    ).fetchall()
    assert cascades == [], f"禁止 ON DELETE CASCADE 外键：{cascades}"


def test_g1_all_foreign_keys_are_restrict_or_no_action(raw_conn):
    types = {
        row[0]
        for row in raw_conn.execute(
            "SELECT confdeltype FROM pg_constraint WHERE contype = 'f'"
        ).fetchall()
    }
    assert types <= {"r", "a", "n"}, f"外键删除策略必须为 RESTRICT / NO ACTION，实际：{types}"


def test_g4_auth_tables_have_no_deleted_at(raw_conn):
    """G-4 / T-11 / AC-13：非资源表不获得软删语义。"""
    for table in ("users", "sessions"):
        columns = {
            row[0]
            for row in raw_conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            ).fetchall()
        }
        assert "deleted_at" not in columns
