"""SQLAlchemy 2.0 模型，严格对应 docs/database/F013.md。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    username_key: Mapped[str] = mapped_column(
        Text, Computed("username", persisted=True), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'enabled'")
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            r"username ~ '^[A-Za-z0-9]{1,128}$'",
            name="chk_users_username_format",
        ),
        CheckConstraint(
            "role IN ('viewer','maintainer','admin')", name="chk_users_role"
        ),
        CheckConstraint(
            "status IN ('enabled','disabled')", name="chk_users_status"
        ),
        CheckConstraint("version >= 1", name="chk_users_version"),
        UniqueConstraint("username_key", name="uq_users_username_key"),
        Index("ix_users_status", "status"),
        Index("ix_users_role", "role"),
        Index("ix_users_created_at", "created_at"),
    )


class UserCredential(Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "length(password_hash) > 0",
            name="chk_user_credentials_password_hash_not_empty",
        ),
    )


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        CheckConstraint("length(token_hash) > 0", name="chk_sessions_token_hash_not_empty"),
        CheckConstraint("expires_at > created_at", name="chk_sessions_expiry"),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )


class ReservedUsername(Base):
    __tablename__ = "reserved_usernames"

    username_key: Mapped[str] = mapped_column(Text, primary_key=True)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "btrim(username_key) <> ''",
            name="chk_reserved_username_key_not_blank",
        ),
    )


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    code_key: Mapped[str] = mapped_column(
        Text, Computed("upper(btrim(code))", persisted=True), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "code = btrim(code) AND btrim(code) <> ''",
            name="chk_clusters_code_trimmed",
        ),
        CheckConstraint(
            "code_key ~ '^[A-Z0-9]{1,32}$'",
            name="chk_clusters_code_key_format",
        ),
        CheckConstraint(
            "name ~ '^[A-Za-z0-9_\u4e00-\u9fff]{1,64}$'",
            name="chk_clusters_name_format",
        ),
        CheckConstraint(
            "btrim(purpose) <> '' AND char_length(purpose) <= 200",
            name="chk_clusters_purpose",
        ),
        CheckConstraint("version >= 1", name="chk_clusters_version"),
        UniqueConstraint("code_key", name="uq_clusters_code_key"),
        UniqueConstraint("name", name="uq_clusters_name"),
        Index("ix_clusters_code", "code"),
        Index("ix_clusters_created_at", "created_at"),
    )


class ReservedClusterCode(Base):
    __tablename__ = "reserved_cluster_codes"

    code_key: Mapped[str] = mapped_column(Text, primary_key=True)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "code_key ~ '^[A-Z0-9]{1,32}$'",
            name="chk_reserved_cluster_codes_format",
        ),
    )


class ResourceHistory(Base):
    __tablename__ = "resource_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_username_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_key_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    change: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        CheckConstraint(
            "btrim(actor_username_snapshot) <> ''",
            name="chk_resource_history_actor_snapshot",
        ),
        CheckConstraint(
            "btrim(target_type) <> ''",
            name="chk_resource_history_target_type",
        ),
        CheckConstraint(
            "action IN ('update','delete')",
            name="chk_resource_history_action",
        ),
        Index("ix_resource_history_occurred_at", text("occurred_at DESC")),
        Index("ix_resource_history_actor", "actor_user_id"),
        Index("ix_resource_history_target", "target_type", "target_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_username_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_key_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    change: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "btrim(actor_username_snapshot) <> ''",
            name="chk_audit_log_actor_username_not_blank",
        ),
        CheckConstraint("btrim(action) <> ''", name="chk_audit_log_action_not_blank"),
        CheckConstraint(
            "btrim(target_type) <> ''", name="chk_audit_log_target_type_not_blank"
        ),
        CheckConstraint(
            "result IN ('success','failure')", name="chk_audit_log_result"
        ),
        Index("ix_audit_log_occurred_at", text("occurred_at DESC")),
        Index("ix_audit_log_actor", "actor_user_id"),
        Index("ix_audit_log_target", "target_type", "target_id"),
    )