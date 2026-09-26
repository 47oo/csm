"""幂等初始化建表 + 首个平台管理员预置（架构 §3.1、数据库设计 §5）。

P0 无迁移工具（ADR-002）：绿地初始化在此完成。重复执行不报错、不覆盖已有数据。
"""

from __future__ import annotations

import secrets
import string

from sqlalchemy import Engine, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import audit
from .config import settings
from .db import Base, SessionLocal
from .models import User, UserCredential, ReservedUsername
from .security.password import hash_password, password_policy_ok

TRIGGER_STATEMENTS = [
    # 通用只增不删触发器（reserved_usernames）。
    """
    CREATE OR REPLACE FUNCTION csm_reject_mutation() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'append-only table: % mutation rejected', TG_TABLE_NAME;
    END;
    $$ LANGUAGE plpgsql;
    """,
    # audit_log append-only：拒绝 DELETE 与任何内容 UPDATE，但允许
    # users 删除时 FK ON DELETE SET NULL 将 actor_user_id 置 NULL（数据库
    # 设计 §2.5 同时要求 SET NULL 与 append-only；两者需此豁免才能共存）。
    """
    CREATE OR REPLACE FUNCTION csm_audit_log_append_only() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'append-only table: % delete rejected', TG_TABLE_NAME;
        END IF;
        IF NEW.id = OLD.id
           AND NEW.occurred_at = OLD.occurred_at
           AND NEW.actor_username_snapshot = OLD.actor_username_snapshot
           AND NEW.action = OLD.action
           AND NEW.target_type = OLD.target_type
           AND NEW.target_id IS NOT DISTINCT FROM OLD.target_id
           AND NEW.target_key_snapshot IS NOT DISTINCT FROM OLD.target_key_snapshot
           AND NEW.change = OLD.change
           AND NEW.result = OLD.result
           AND NEW.actor_user_id IS NULL
           AND OLD.actor_user_id IS NOT NULL
        THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'append-only table: % update rejected', TG_TABLE_NAME;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log;
    """,
    """
    CREATE TRIGGER trg_audit_log_append_only
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION csm_audit_log_append_only();
    """,
    """
    DROP TRIGGER IF EXISTS trg_reserved_usernames_append_only ON reserved_usernames;
    """,
    """
    CREATE TRIGGER trg_reserved_usernames_append_only
        BEFORE UPDATE OR DELETE ON reserved_usernames
        FOR EACH ROW EXECUTE FUNCTION csm_reject_mutation();
    """,
]


def create_schema(engine: Engine) -> None:
    """建立 5 张表、约束、索引（幂等）并补充触发器 DDL。"""
    # 确保模型已注册到元数据。
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for statement in TRIGGER_STATEMENTS:
            conn.execute(text(statement))


def generate_password(length: int = 16) -> str:
    """生成满足策略（含字母与数字）的随机口令。"""
    alphabet = string.ascii_letters + string.digits
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if password_policy_ok(candidate):
            return candidate


def seed_initial_admin(
    db: Session,
    password: str | None = None,
) -> bool:
    """若无任何 admin 用户，则预置内置管理员。返回是否执行了预置。

    内置默认管理员用户名固定为 ``admin``（BQ-Y；不再读取
    CSM_INITIAL_ADMIN_USERNAME）。
    """
    admin_count = db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin")
    )
    if admin_count and admin_count > 0:
        return False

    username = "admin"
    if password is None:
        password = settings.initial_admin_password
    if not password:
        password = generate_password()
        print(
            f"[csm-init] 未提供 CSM_INITIAL_ADMIN_PASSWORD，已生成初始口令"
            f"（仅本次打印）：{password}",
            flush=True,
        )

    if not password_policy_ok(password):
        raise RuntimeError("初始管理员口令不满足策略：至少 8 位且包含字母与数字")

    # 预置路径允许 ON CONFLICT DO NOTHING；业务路径仍以冲突映射 409。
    db.execute(
        pg_insert(ReservedUsername)
        .values(username_key=username)
        .on_conflict_do_nothing(index_elements=["username_key"])
    )

    user = User(
        username=username,
        role="admin",
        status="enabled",
        must_change_password=True,
        is_builtin=True,
    )
    db.add(user)
    db.flush()

    db.add(
        UserCredential(
            user_id=user.id,
            password_hash=hash_password(password),
        )
    )
    audit.write(
        db,
        actor=None,
        action="bootstrap.create_admin",
        target_type="user",
        target_id=str(user.id),
        target_key_snapshot=user.username,
        change={"role": "admin", "must_change_password": True, "is_builtin": True},
        result="success",
    )
    db.flush()
    return True


def initialize(
    engine: Engine | None = None,
    *,
    password: str | None = None,
) -> None:
    """创建 Schema 并（按需）预置内置管理员。用于部署初始化脚本。"""
    from .db import engine as default_engine

    target_engine = engine or default_engine
    create_schema(target_engine)
    db = SessionLocal()
    try:
        seed_initial_admin(db, password=password)
        db.commit()
    finally:
        db.close()