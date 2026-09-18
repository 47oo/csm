"""G2 / Q8 / NQ-1：数据库结构 guard（绕过应用层，直接断言迁移后的实际 Schema）。

- ``clusters`` 的 CHECK 约束集合**恰为** ``{ck_clusters_name_no_slash}``：
  防止「顺手」新增 ``name <> ''`` / 长度 / ``trim`` CHECK。
- ``clusters`` 的列集合**恰为** ``{id, name, created_at, updated_at, deleted_at}``：
  防止新增状态 / 位置 / 预留列。

这两条把 ``undefined_constraints`` 的「不实现」变成可失败的测试。
"""

from __future__ import annotations


def test_g2_check_constraint_set_is_exactly_slash_guard(raw_conn):
    checks = {
        row[0]
        for row in raw_conn.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'clusters'::regclass AND contype = 'c'"
        ).fetchall()
    }
    assert checks == {"ck_clusters_name_no_slash"}


def test_g2_column_set_is_exactly_expected(raw_conn):
    columns = {
        row[0]
        for row in raw_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'clusters'"
        ).fetchall()
    }
    assert columns == {"id", "name", "created_at", "updated_at", "deleted_at"}
