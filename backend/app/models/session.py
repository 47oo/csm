"""``user_sessions`` model (DB-D16, DB-D18, DB-D19).

A server-side opaque session: the row stores only the SHA-256 hex digest of the
token. ``ON DELETE RESTRICT`` keeps session/history identity from being silently
discarded; FK index and expiry index are explicit because PostgreSQL does not
create an index for a foreign key automatically.
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


class UserSession(Base):
    __tablename__ = "user_sessions"

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
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("token_hash"),
        CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_format"
        ),
        CheckConstraint(
            "expires_at > created_at", name="expires_after_created"
        ),
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<UserSession id={self.id!r} user_id={self.user_id!r}>"