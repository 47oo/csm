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
    ForeignKeyConstraint,
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

_IPV4_RE = (
    r"^(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\."
    r"(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\."
    r"(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\."
    r"(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$"
)
_IPV4_CIDR_RE = (
    r"^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}"
    r"(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])/(3[0-2]|[12]?[0-9])$"
)


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


class NetworkSegment(Base):
    __tablename__ = "network_segments"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "clusters.id",
            ondelete="RESTRICT",
            name="fk_network_segments_cluster",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    cidr: Mapped[str] = mapped_column(Text, nullable=False)
    cidr_key: Mapped[str] = mapped_column(
        Text, Computed("cidr", persisted=True), nullable=False
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    technology: Mapped[str] = mapped_column(Text, nullable=False)
    vlan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gateway: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_alloc_start: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_alloc_end: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        UniqueConstraint(
            "cluster_id", "name", name="uq_network_segments_cluster_name"
        ),
        UniqueConstraint(
            "cluster_id", "cidr_key", name="uq_network_segments_cluster_cidr"
        ),
        # F002 §7.1：作 ``network_interfaces (segment_id, cluster_id)`` 复合 FK 的目标。
        UniqueConstraint(
            "id", "cluster_id", name="uq_network_segments_id_cluster"
        ),
        CheckConstraint(
            "name = btrim(name) AND btrim(name) <> '' AND char_length(name) <= 128",
            name="chk_network_segments_name",
        ),
        CheckConstraint(
            f"cidr ~ '{_IPV4_CIDR_RE}'",
            name="chk_network_segments_cidr",
        ),
        CheckConstraint(
            "btrim(purpose) <> '' AND char_length(purpose) <= 200",
            name="chk_network_segments_purpose",
        ),
        CheckConstraint(
            "btrim(technology) <> '' AND char_length(technology) <= 100",
            name="chk_network_segments_technology",
        ),
        CheckConstraint(
            "vlan IS NULL OR vlan BETWEEN 1 AND 4094",
            name="chk_network_segments_vlan",
        ),
        CheckConstraint(
            f"gateway IS NULL OR gateway ~ '{_IPV4_RE}'",
            name="chk_network_segments_gateway",
        ),
        CheckConstraint(
            (
                "(auto_alloc_start IS NULL) = (auto_alloc_end IS NULL) AND "
                "(auto_alloc_start IS NULL OR ("
                f"auto_alloc_start ~ '{_IPV4_RE}' AND auto_alloc_end ~ '{_IPV4_RE}'"
                "))"
            ),
            name="chk_network_segments_auto_alloc",
        ),
        CheckConstraint("version >= 1", name="chk_network_segments_version"),
        Index("ix_network_segments_cluster_id", "cluster_id"),
    )


class SegmentReservedAddress(Base):
    __tablename__ = "segment_reserved_addresses"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    segment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "network_segments.id",
            ondelete="RESTRICT",
            name="fk_segment_reserved_addresses_segment",
        ),
        nullable=False,
    )
    start_ip: Mapped[str] = mapped_column(Text, nullable=False)
    end_ip: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            f"start_ip ~ '{_IPV4_RE}'",
            name="chk_segment_reserved_addresses_start_ip",
        ),
        CheckConstraint(
            f"end_ip ~ '{_IPV4_RE}'",
            name="chk_segment_reserved_addresses_end_ip",
        ),
        Index("ix_segment_reserved_addresses_segment_id", "segment_id"),
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


class Resource(Base):
    """计算资源主表（docs/database/F002.md §2.1）。"""

    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "clusters.id",
            ondelete="RESTRICT",
            name="fk_resources_cluster",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ALLOC'")
    )
    status_updated_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_resources_status_updated_by",
        ),
        nullable=True,
    )
    status_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
        UniqueConstraint("cluster_id", "name", name="uq_resources_cluster_name"),
        UniqueConstraint("id", "cluster_id", name="uq_resources_id_cluster"),
        CheckConstraint(
            "name = btrim(name) AND btrim(name) <> '' AND char_length(name) <= 128",
            name="chk_resources_name",
        ),
        CheckConstraint(
            "resource_type IN ('bare_metal','virtual_machine')",
            name="chk_resources_type",
        ),
        CheckConstraint(
            "status IN ('IDLE','ALLOC','DOWN','UNKNOWN')",
            name="chk_resources_status",
        ),
        CheckConstraint("version >= 1", name="chk_resources_version"),
        Index("ix_resources_cluster_id", "cluster_id"),
    )


class NetworkInterface(Base):
    """无 IP 网卡子表（docs/database/F002.md §2.2）。"""

    __tablename__ = "network_interfaces"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    resource_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 冗余列：由复合 FK 钉住为所属资源的集群（落实「网段同集群」）。
    cluster_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    segment_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
        # 延迟唯一约束（DEFERRABLE INITIALLY IMMEDIATE）：同一 PATCH 内互换
        # 两个接口名（终态合法）时，逐条 UPDATE 的中间态可瞬时重名；唯一性在
        # 提交时统一判定（F002-R-06）。仍保持立即生效的默认行为，仅当写事务显式
        # ``SET CONSTRAINTS ... DEFERRED`` 才延迟到提交。组合键语义与数据库设计
        # §2.2 一致（同一资源下接口名唯一）。
        UniqueConstraint(
            "resource_id",
            "name",
            name="uq_network_interfaces_resource_name",
            deferrable=True,
            initially="IMMEDIATE",
        ),
        CheckConstraint(
            "name = btrim(name) AND btrim(name) <> '' AND char_length(name) <= 128",
            name="chk_network_interfaces_name",
        ),
        ForeignKeyConstraint(
            ["resource_id", "cluster_id"],
            ["resources.id", "resources.cluster_id"],
            ondelete="RESTRICT",
            name="fk_network_interfaces_resource",
        ),
        ForeignKeyConstraint(
            ["segment_id", "cluster_id"],
            ["network_segments.id", "network_segments.cluster_id"],
            ondelete="RESTRICT",
            name="fk_network_interfaces_segment",
        ),
        Index(
            "ix_network_interfaces_resource_cluster", "resource_id", "cluster_id"
        ),
        Index(
            "ix_network_interfaces_segment_cluster", "segment_id", "cluster_id"
        ),
    )