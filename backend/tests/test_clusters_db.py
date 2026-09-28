"""F001 数据库约束与 append-only 测试（数据库设计 §7，真实 PostgreSQL）。"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import engine


def _insert_cluster(conn, code: str, name: str, purpose: str = "p") -> int:
    return conn.execute(
        text(
            "INSERT INTO clusters (code, name, purpose) "
            "VALUES (:c, :n, :p) RETURNING id"
        ),
        {"c": code, "n": name, "p": purpose},
    ).scalar_one()


def _insert_user(conn, username: str) -> int:
    return conn.execute(
        text(
            "INSERT INTO users (username, role, status) "
            "VALUES (:u, 'viewer', 'enabled') RETURNING id"
        ),
        {"u": username},
    ).scalar_one()


def test_code_key_generated_and_unique() -> None:
    with engine.begin() as conn:
        _insert_cluster(conn, "N96P", "n1")
        row = conn.execute(
            text("SELECT code_key FROM clusters WHERE code='N96P'")
        ).scalar_one()
        assert row == "N96P"

    # 大小写等价冲突（生成列唯一）。
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_cluster(conn, "n96p", "n2")


def test_code_trim_and_format_checks() -> None:
    # code 必须等于 btrim(code)。
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_cluster(conn, " AB ", "trimmed")

    # code_key 格式：非 [A-Z0-9] 被拒。
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_cluster(conn, "ab!", "banged")

    # 超长（>32）被拒。
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_cluster(conn, "A" * 33, "toolong")


def test_name_format_and_case_sensitive_unique() -> None:
    with engine.begin() as conn:
        _insert_cluster(conn, "K1", "ABC")
        _insert_cluster(conn, "K2", "abc")  # 区分大小写，允许
        _insert_cluster(conn, "K3", "集群_01")  # 中文与下划线允许

    for bad in ["a b", "bad!", "ＡＢ"]:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert_cluster(conn, "KX", bad)

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_cluster(conn, "K4", "ABC")


def test_purpose_check() -> None:
    for bad in ["", "   ", "x" * 201]:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert_cluster(conn, "PP", "pname", bad)


def test_reserved_cluster_codes_append_only() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO reserved_cluster_codes (code_key) VALUES ('KEEP1')")
        )

    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE reserved_cluster_codes SET code_key='CHANGED' "
                    "WHERE code_key='KEEP1'"
                )
            )
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM reserved_cluster_codes WHERE code_key='KEEP1'")
            )

    with engine.begin() as conn:
        assert conn.execute(
            text(
                "SELECT count(*) FROM reserved_cluster_codes WHERE code_key='KEEP1'"
            )
        ).scalar_one() == 1

    # 格式约束。
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO reserved_cluster_codes (code_key) VALUES ('bad!')")
            )


def test_resource_history_append_only_and_action_check() -> None:
    with engine.begin() as conn:
        entry_id = conn.execute(
            text(
                "INSERT INTO resource_history "
                "(actor_username_snapshot, target_type, target_id, action) "
                "VALUES ('system', 'cluster', '1', 'delete') RETURNING id"
            )
        ).scalar_one()

    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE resource_history SET action='update' WHERE id=:i"),
                {"i": entry_id},
            )
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM resource_history WHERE id=:i"), {"i": entry_id}
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO resource_history "
                    "(actor_username_snapshot, target_type, action) "
                    "VALUES ('system', 'cluster', 'create')"
                )
            )


def test_resource_history_actor_set_null_preserves_row() -> None:
    with engine.begin() as conn:
        user_id = _insert_user(conn, "actoruser")
        entry_id = conn.execute(
            text(
                "INSERT INTO resource_history "
                "(actor_user_id, actor_username_snapshot, target_type, target_id, action) "
                "VALUES (:u, 'actoruser', 'cluster', '9', 'update') RETURNING id"
            ),
            {"u": user_id},
        ).scalar_one()

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id=:i"), {"i": user_id})
        row = conn.execute(
            text(
                "SELECT actor_user_id, actor_username_snapshot "
                "FROM resource_history WHERE id=:i"
            ),
            {"i": entry_id},
        ).one()
        assert row.actor_user_id is None
        assert row.actor_username_snapshot == "actoruser"