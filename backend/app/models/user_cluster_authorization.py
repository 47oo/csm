"""``user_cluster_authorizations`` model (F026, DB-D401..DB-D420).

This is a relationship object, **not** a §21 business object: it has no
``deleted_at``/``version`` and must NOT inherit ``SoftDeleteMixin``. Revocation
is a one-way state change (``revoked_at``/``revoked_by``); rows are never
physically deleted and the attribution columns are immutable (enforced by the
migration's triggers).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserClusterAuthorization(Base):
    __tablename__ = "user_cluster_authorizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clusters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # NULL = migration/system backfill; never fabricated as a human operator.
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by IS NULL)",
            name="revoked_pair",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= granted_at",
            name="revoked_after_granted",
        ),
        Index(
            "uq_user_cluster_authorizations_user_id_cluster_id",
            "user_id",
            "cluster_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_user_cluster_authorizations_user_id", "user_id"),
        Index("ix_user_cluster_authorizations_cluster_id", "cluster_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<UserClusterAuthorization id={self.id!r} user_id={self.user_id!r} "
            f"cluster_id={self.cluster_id!r} revoked_at={self.revoked_at!r}>"
        )
