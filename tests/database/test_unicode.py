"""T7（数据库侧）— 中文写入 / 读出 / 等值比较往返（UTF-8）。"""

from __future__ import annotations

CHINESE_NAME = "高性能计算集群-A"


def test_chinese_roundtrip_and_equality(raw_conn):
    raw_conn.execute("INSERT INTO clusters (name) VALUES (%s)", (CHINESE_NAME,))

    fetched = raw_conn.execute(
        "SELECT name FROM clusters WHERE name = %s AND deleted_at IS NULL",
        (CHINESE_NAME,),
    ).fetchone()

    assert fetched is not None, "按字面值等值比较应命中"
    assert fetched[0] == CHINESE_NAME
    assert raw_conn.execute("SELECT %s::text", (CHINESE_NAME,)).fetchone()[0] == CHINESE_NAME


def test_database_encoding_is_utf8(raw_conn):
    encoding = raw_conn.execute(
        "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname = current_database()"
    ).fetchone()[0]
    assert encoding == "UTF8"
