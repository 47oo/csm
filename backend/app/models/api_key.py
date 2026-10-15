"""``api_keys`` model (DB-D301..DB-D307).

API Key machine credentials (requirements §23.1). This is **not** a §21 business
object: it uses revoke semantics (``revoked_at``) and must NOT inherit
``SoftDeleteMixin`` (DR-305/DB-D301). There is no ``deleted_at``/``version``/
``last_used_at``. Only the SHA-256 hex digest of the credential is stored — no
plaintext column exists (DB-D304).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

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
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("key_hash"),
        CheckConstraint("btrim(label) <> ''", name="label_not_blank"),
        CheckConstraint("key_hash ~ '^[0-9a-f]{64}$'", name="key_hash_format"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint(
            "expires_at <= created_at + interval '365 days' + interval '5 minutes'",
            name="expires_within_max",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="revoked_after_created",
        ),
        Index("ix_api_keys_user_id", "user_id"),
        Index("ix_api_keys_created_by", "created_by"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ApiKey id={self.id!r} user_id={self.user_id!r} label={self.label!r}>"