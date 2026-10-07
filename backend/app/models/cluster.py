"""``clusters`` model (DB-D20..DB-D26, DB-D32).

Columns/constraints mirror migration ``0003_clusters_audit`` exactly. Constraint
short names let the ``Base`` naming convention expand them to the
fully-qualified names from the database design (``ck_clusters_<name>``).

``code`` is the display value (trimmed, case/structure preserved) and ``code_key``
is the internal, non-exposed normalisation key that carries case-insensitive
full uniqueness (including soft-deleted rows). Only ASCII ``a-z`` are folded to
``A-Z``; non-ASCII code points are kept verbatim (locale-independent, matching
``app.services.normalization.code_key`` and the migration CHECK). The
``metadata`` property is named ``meta`` on the ORM class because ``metadata`` is
reserved by SQLAlchemy's declarative machinery; the underlying column remains
``metadata``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin


class Cluster(SoftDeleteMixin, Base):
    __tablename__ = "clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    code_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'ACTIVE'"), default="ACTIVE"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
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
        UniqueConstraint("code_key", name="uq_clusters_code_key"),
        CheckConstraint("btrim(code) <> ''", name="code_not_blank"),
        CheckConstraint("code = btrim(code)", name="code_trimmed"),
        CheckConstraint("code !~ '[[:space:][:cntrl:]]'", name="code_no_ws_control"),
        CheckConstraint("char_length(code) BETWEEN 1 AND 64", name="code_length"),
        CheckConstraint("btrim(code_key) <> ''", name="code_key_not_blank"),
        CheckConstraint(
            "char_length(code_key) BETWEEN 1 AND 64", name="code_key_length"
        ),
        CheckConstraint(
            "code_key = translate(btrim(code), "
            "'abcdefghijklmnopqrstuvwxyz', "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ')",
            name="code_key_matches",
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("name = btrim(name)", name="name_trimmed"),
        CheckConstraint("name !~ '[[:cntrl:]]'", name="name_no_control"),
        CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')", name="status"
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name="metadata_object"
        ),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_clusters_status", "status"),
        Index("ix_clusters_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Cluster id={self.id!r} code={self.code!r} status={self.status!r}>"