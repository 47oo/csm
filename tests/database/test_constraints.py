"""T3 / T4 / T5 / T6 — 直接对数据库执行 SQL 的约束断言。

这些测试**绕过应用层**（不用应用 session / service），证明约束来自数据库而非
应用逻辑（§21 / §22）。
"""

from __future__ import annotations

import psycopg
import pytest


def test_t3_case_sensitive_values_coexist(raw_conn):
    """T3：cluster-a 与 Cluster-A 可共存；等值比较为 false。"""
    raw_conn.execute("INSERT INTO clusters (name) VALUES ('cluster-a')")
    raw_conn.execute("INSERT INTO clusters (name) VALUES ('Cluster-A')")

    assert raw_conn.execute("SELECT ('cluster-a' = 'Cluster-A')").fetchone()[0] is False

    names = {
        row[0]
        for row in raw_conn.execute(
            "SELECT name FROM clusters WHERE deleted_at IS NULL ORDER BY name"
        ).fetchall()
    }
    assert names == {"cluster-a", "Cluster-A"}


def test_t4_active_duplicate_rejected_with_23505(raw_conn):
    """T4：活跃同名第二行 → SQLSTATE 23505。"""
    raw_conn.execute("INSERT INTO clusters (name) VALUES ('cluster-a')")
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        raw_conn.execute("INSERT INTO clusters (name) VALUES ('cluster-a')")
    assert excinfo.value.sqlstate == "23505"


def test_t5_soft_deleted_name_can_be_recreated(raw_conn):
    """T5：软删后同名可重建；已删行不出现在活跃查询。"""
    raw_conn.execute("INSERT INTO clusters (name) VALUES ('cluster-a')")
    raw_conn.execute(
        "UPDATE clusters SET deleted_at = now() WHERE name = 'cluster-a' AND deleted_at IS NULL"
    )
    # 已删不占唯一性 → 可重建同名
    raw_conn.execute("INSERT INTO clusters (name) VALUES ('cluster-a')")

    active = raw_conn.execute(
        "SELECT count(*) FROM clusters WHERE name = 'cluster-a' AND deleted_at IS NULL"
    ).fetchone()[0]
    assert active == 1

    total = raw_conn.execute("SELECT count(*) FROM clusters WHERE name = 'cluster-a'").fetchone()[0]
    assert total == 2  # 历史保留

    # 活跃查询看不到已删行
    active_names = [
        row[0]
        for row in raw_conn.execute("SELECT name FROM clusters WHERE deleted_at IS NULL").fetchall()
    ]
    assert active_names == ["cluster-a"]


def test_t6_slash_in_name_rejected_with_23514(raw_conn):
    """T6：name 含 / → SQLSTATE 23514（R-CLUSTER-005 数据库层）。"""
    with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        raw_conn.execute("INSERT INTO clusters (name) VALUES ('a/b')")
    assert excinfo.value.sqlstate == "23514"
