"""G-C / T-14 —— 认证表结构 guard 与大小写敏感唯一性（绕过应用层）。

这些断言直接对 PostgreSQL 执行 SQL，证明约束 / 结构来自数据库而非应用逻辑。
"""

from __future__ import annotations

import psycopg
import pytest

EXPECTED_USERS_COLUMNS = {
    "id",
    "username",
    "password_hash",
    "active",
    "created_at",
    "updated_at",
}
EXPECTED_SESSIONS_COLUMNS = {
    "id",
    "user_id",
    "token_hash",
    "created_at",
    "expires_at",
    "last_seen_at",
}


def _columns(raw_conn, table: str) -> set[str]:
    return {
        row[0]
        for row in raw_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    }


# --------------------------------------------------------------------------- #
# G-C：列集合恰为契约所列；无 deleted_at；无角色 / 权限列
# --------------------------------------------------------------------------- #
def test_g_c_users_and_sessions_column_sets_exact(raw_conn):
    assert _columns(raw_conn, "users") == EXPECTED_USERS_COLUMNS
    assert _columns(raw_conn, "sessions") == EXPECTED_SESSIONS_COLUMNS


def test_g_c_auth_tables_have_no_deleted_at(raw_conn):
    for table in ("users", "sessions"):
        assert "deleted_at" not in _columns(raw_conn, table)


def test_g_c_no_rbac_columns_anywhere(raw_conn):
    forbidden = ("role", "permission", "rbac", "grant", "acl")
    rows = raw_conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    ).fetchall()
    for table_name, column_name in rows:
        combined = f"{table_name}.{column_name}".lower()
        assert not any(token in combined for token in forbidden), combined


def test_g_c_no_lower_username_expression_index(raw_conn):
    indexes = [
        row[0]
        for row in raw_conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'users'"
        ).fetchall()
    ]
    assert any("ux_users_username" in definition for definition in indexes)
    assert all("lower(" not in definition.lower() for definition in indexes)


def test_g_c_no_explicit_collation_on_auth_columns(raw_conn):
    rows = raw_conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name IN ('users', 'sessions') "
        "AND collation_name IS NOT NULL"
    ).fetchall()
    assert rows == [], f"认证列不得声明 collation：{rows}"


# --------------------------------------------------------------------------- #
# T-14 / AC-15 / R-AUTH-005：大小写敏感唯一性（绕应用层）
# --------------------------------------------------------------------------- #
def test_t14_case_sensitive_username_uniqueness(raw_conn):
    raw_conn.execute(
        "INSERT INTO users (username, password_hash) VALUES ('admin', '$argon2id$fake')"
    )
    raw_conn.execute(
        "INSERT INTO users (username, password_hash) VALUES ('Admin', '$argon2id$fake')"
    )

    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO users (username, password_hash) VALUES ('admin', '$argon2id$fake')"
        )
    assert excinfo.value.sqlstate == "23505"

    assert raw_conn.execute("SELECT ('admin' = 'Admin')").fetchone()[0] is False

    count = raw_conn.execute(
        "SELECT count(*) FROM users WHERE username IN ('admin', 'Admin')"
    ).fetchone()[0]
    assert count == 2


# --------------------------------------------------------------------------- #
# 会话约束：token_hash 唯一 + FK RESTRICT
# --------------------------------------------------------------------------- #
def test_session_token_hash_unique(raw_conn):
    user_id = raw_conn.execute(
        "INSERT INTO users (username, password_hash) VALUES ('sess', '$argon2id$fake') RETURNING id"
    ).fetchone()[0]
    raw_conn.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at) "
        "VALUES (%s, 'hash-1', now() + interval '8 hours')",
        (user_id,),
    )
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO sessions (user_id, token_hash, expires_at) "
            "VALUES (%s, 'hash-1', now() + interval '8 hours')",
            (user_id,),
        )
    assert excinfo.value.sqlstate == "23505"


def test_session_user_fk_is_restrict(raw_conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO sessions (user_id, token_hash, expires_at) "
            "VALUES (999999999, 'hash-x', now() + interval '8 hours')"
        )
    assert excinfo.value.sqlstate == "23503"
