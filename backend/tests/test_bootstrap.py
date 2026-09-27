"""初始化建表与首个管理员预置（数据库设计 §5 / §6.2）。"""

from __future__ import annotations

from sqlalchemy import func, select, text

from app.bootstrap import seed_initial_admin
from app.db import SessionLocal, engine
from app.models import AuditLog, ReservedUsername, User, UserCredential
from app.security.password import password_policy_ok, verify_password


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_seed_initial_admin_idempotent() -> None:
    with SessionLocal() as db:
        assert seed_initial_admin(db, password="Rootpass1") is True
        db.commit()

    with SessionLocal() as db:
        # 第二次执行：已有 admin，跳过预置。
        assert seed_initial_admin(db, password="Rootpass2") is False
        db.commit()

        admins = db.scalars(select(User).where(User.role == "admin")).all()
        assert len(admins) == 1
        admin = admins[0]
        # 内置管理员用户名固定为 admin（BQ-Y）。
        assert admin.username == "admin"
        assert admin.status == "enabled"
        assert admin.must_change_password is True
        assert admin.is_builtin is True

        assert _count(db, UserCredential) == 1
        assert _count(db, ReservedUsername) == 1
        assert _count(db, AuditLog) == 1

        credential = db.get(UserCredential, admin.id)
        assert credential is not None
        assert verify_password(credential.password_hash, "Rootpass1")
        assert credential.password_hash.startswith("$argon2id$")

        audit = db.scalar(select(AuditLog))
        assert audit.actor_user_id is None
        assert audit.actor_username_snapshot == "system"
        assert audit.action == "bootstrap.create_admin"
        assert audit.target_type == "user"
        assert audit.result == "success"


def test_seed_generates_password_when_missing(capsys) -> None:
    with SessionLocal() as db:
        seed_initial_admin(db)
        db.commit()

    out = capsys.readouterr().out
    assert "已生成初始口令" in out

    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.role == "admin"))
        assert admin is not None
        assert admin.username == "admin"
        assert admin.is_builtin is True
        assert password_policy_ok("placeholder") is False
        assert admin.must_change_password is True


def test_create_schema_is_idempotent() -> None:
    from app.bootstrap import create_schema

    create_schema(engine)
    create_schema(engine)


def _interface_name_constraint_deferrable() -> bool:
    with engine.connect() as conn:
        return bool(
            conn.scalar(
                text(
                    "SELECT condeferrable FROM pg_constraint "
                    "WHERE conname = 'uq_network_interfaces_resource_name'"
                )
            )
        )


def test_interface_name_unique_constraint_is_deferrable() -> None:
    # 绿地 create_all 即产生 DEFERRABLE INITIALLY IMMEDIATE（F002-R-06）。
    assert _interface_name_constraint_deferrable() is True


def test_create_schema_upgrades_existing_interface_constraint() -> None:
    """已存在库（修复前的非 deferrable 约束）由 create_schema 幂等重建。"""
    from app.bootstrap import create_schema

    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE network_interfaces "
                "DROP CONSTRAINT uq_network_interfaces_resource_name"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE network_interfaces "
                "ADD CONSTRAINT uq_network_interfaces_resource_name "
                "UNIQUE (resource_id, name)"
            )
        )
    assert _interface_name_constraint_deferrable() is False

    create_schema(engine)
    assert _interface_name_constraint_deferrable() is True

    # 幂等：再次执行不报错、保持 deferrable。
    create_schema(engine)
    assert _interface_name_constraint_deferrable() is True
