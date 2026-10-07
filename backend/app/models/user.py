"""``users`` model (DB-D13..DB-D15, DB-D19).

Constraints mirror migration ``0002_users_sessions`` exactly. Check constraints
use short names so the ``Base`` naming convention expands them to the
fully-qualified names from the database design (``ck_users_<name>``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserStatus(StrEnum):
    """Account lifecycle status. Disabling is NOT soft delete (§21)."""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'ACTIVE'"), default="ACTIVE"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), default=1
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("username"),
        CheckConstraint("username ~ '^[a-z0-9._-]{3,64}$'", name="username_format"),
        CheckConstraint("role IN ('VIEWER','EDITOR','ADMIN')", name="role"),
        CheckConstraint("status IN ('ACTIVE','DISABLED')", name="status"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "length(btrim(password_hash)) > 0", name="password_hash_nonempty"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id!r} username={self.username!r} role={self.role!r}>"