"""数据库约束与行为测试（数据库设计 §6.1，真实 PostgreSQL）。"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import engine


def _insert_user(
    conn,
    username: str,
    role: str = "viewer",
    status: str = "enabled",
) -> int:
    return conn.execute(
        text(
            "INSERT INTO users (username, role, status) "
            "VALUES (:u, :r, :s) RETURNING id"
        ),
        {"u": username, "r": role, "s": status},
    ).scalar_one()


def test_username_unique_case_sensitive() -> None:
    with engine.begin() as conn:
        _insert_user(conn, "ABC")
        # 区分大小写：abc 与 ABC 不同，允许。
        _insert_user(conn, "abc")
        assert (
            conn.execute(text("SELECT username_key FROM users WHERE username='ABC'"))
            .scalar_one()
            == "ABC"
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_user(conn, "ABC")


def test_username_format_check() -> None:
    for bad in ["ab cd", "ab!", "用户名", "a" * 129]:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert_user(conn, bad)


def test_role_status_check() -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_user(conn, "badrole", role="superuser")
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert_user(conn, "badstatus", status="suspended")


def test_is_builtin_defaults_false() -> None:
    with engine.begin() as conn:
        user_id = _insert_user(conn, "plainuser")
        assert (
            conn.execute(
                text("SELECT is_builtin FROM users WHERE id=:i"), {"i": user_id}
            ).scalar_one()
            is False
        )


def test_reserved_usernames_is_append_only() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO reserved_usernames (username_key) VALUES ('keepme')")
        )

    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE reserved_usernames SET username_key='changed' "
                    "WHERE username_key='keepme'"
                )
            )

    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM reserved_usernames WHERE username_key='keepme'")
            )

    with engine.begin() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM reserved_usernames WHERE username_key='keepme'")
        ).scalar_one() == 1


def test_reserved_username_blank_rejected() -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO reserved_usernames (username_key) VALUES ('   ')")
            )


def test_audit_log_is_append_only() -> None:
    with engine.begin() as conn:
        entry_id = conn.execute(
            text(
                "INSERT INTO audit_log "
                "(actor_username_snapshot, action, target_type, result) "
                "VALUES ('system', 'test.action', 'user', 'success') RETURNING id"
            )
        ).scalar_one()

    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE audit_log SET action='tampered' WHERE id=:i"),
                {"i": entry_id},
            )

    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM audit_log WHERE id=:i"), {"i": entry_id})

    with engine.begin() as conn:
        assert conn.execute(
            text("SELECT action FROM audit_log WHERE id=:i"), {"i": entry_id}
        ).scalar_one() == "test.action"


def test_audit_result_check() -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_log "
                    "(actor_username_snapshot, action, target_type, result) "
                    "VALUES ('system', 'x', 'user', 'maybe')"
                )
            )


def test_optimistic_lock_condition_update() -> None:
    with engine.begin() as conn:
        user_id = _insert_user(conn, "lockme")

        # 版本不匹配：rowcount = 0。
        stale = conn.execute(
            text(
                "UPDATE users SET role='admin', version=version+1 "
                "WHERE id=:i AND version=:v"
            ),
            {"i": user_id, "v": 99},
        )
        assert stale.rowcount == 0

        # 版本匹配：自增。
        ok = conn.execute(
            text(
                "UPDATE users SET role='admin', version=version+1 "
                "WHERE id=:i AND version=:v"
            ),
            {"i": user_id, "v": 1},
        )
        assert ok.rowcount == 1
        row = conn.execute(
            text("SELECT role, version FROM users WHERE id=:i"), {"i": user_id}
        ).one()
        assert tuple(row) == ("admin", 2)


def test_delete_user_cascades_and_preserves() -> None:
    with engine.begin() as conn:
        user_id = _insert_user(conn, "deltest")
        conn.execute(
            text(
                "INSERT INTO user_credentials (user_id, password_hash) "
                "VALUES (:u, 'hash')"
            ),
            {"u": user_id},
        )
        conn.execute(
            text(
                "INSERT INTO sessions (token_hash, user_id, expires_at) "
                "VALUES ('tok', :u, now() + interval '1 hour')"
            ),
            {"u": user_id},
        )
        conn.execute(
            text("INSERT INTO reserved_usernames (username_key) VALUES ('deltest')")
        )
        conn.execute(
            text(
                "INSERT INTO audit_log "
                "(actor_user_id, actor_username_snapshot, action, target_type, result) "
                "VALUES (:u, 'deltest', 'x', 'user', 'success')"
            ),
            {"u": user_id},
        )

        conn.execute(text("DELETE FROM users WHERE id=:i"), {"i": user_id})

        assert conn.execute(
            text("SELECT count(*) FROM user_credentials WHERE user_id=:i"),
            {"i": user_id},
        ).scalar_one() == 0
        assert conn.execute(
            text("SELECT count(*) FROM sessions WHERE user_id=:i"), {"i": user_id}
        ).scalar_one() == 0
        # reserved 保留。
        assert conn.execute(
            text("SELECT count(*) FROM reserved_usernames WHERE username_key='deltest'")
        ).scalar_one() == 1
        # 审计保留且 actor 置 NULL。
        row = conn.execute(
            text("SELECT actor_user_id FROM audit_log WHERE actor_username_snapshot='deltest'")
        ).scalar_one()
        assert row is None


def test_sessions_expiry_check_and_predicate() -> None:
    with engine.begin() as conn:
        user_id = _insert_user(conn, "sesstest")

    # expires_at <= created_at 被拒绝。
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) "
                    "VALUES ('bad', :u, now(), now() - interval '1 hour')"
                ),
                {"u": user_id},
            )

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sessions "
                "(token_hash, user_id, created_at, expires_at) "
                "VALUES ('expired', :u, now() - interval '2 hours', "
                "now() - interval '1 hour')"
            ),
            {"u": user_id},
        )
        conn.execute(
            text(
                "INSERT INTO sessions (token_hash, user_id, expires_at, revoked_at) "
                "VALUES ('revoked', :u, now() + interval '1 hour', now())"
            ),
            {"u": user_id},
        )
        conn.execute(
            text(
                "INSERT INTO sessions (token_hash, user_id, expires_at) "
                "VALUES ('active', :u, now() + interval '1 hour')"
            ),
            {"u": user_id},
        )

        active = conn.execute(
            text(
                "SELECT token_hash FROM sessions "
                "WHERE user_id=:u AND revoked_at IS NULL AND expires_at > now()"
            ),
            {"u": user_id},
        ).scalars().all()
        assert active == ["active"]