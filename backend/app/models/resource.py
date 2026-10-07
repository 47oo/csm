"""``resources`` model (DB-D33..DB-D44).

Columns/constraints mirror migration ``0004_resources`` exactly. Short
constraint names let the ``Base`` naming convention expand them to the
fully-qualified names from the database design (``ck_resources_<name>``).

``hostname`` is the trimmed, ASCII-only lower display value and ``hostname_key``
is the internal, non-exposed normalisation key that carries the *partial*
uniqueness ``(cluster_id, hostname_key) WHERE deleted_at IS NULL`` (undeleted
rows unique per cluster, soft-deleted rows release the key, cross-cluster reuse
allowed). Only ASCII ``A-Z`` are folded to ``a-z``; non-ASCII code points are
kept verbatim (locale-independent, matching
``app.services.normalization.hostname_key`` and the migration CHECK). The
``metadata`` property is named ``meta`` on the ORM class because ``metadata``
is reserved by SQLAlchemy's declarative machinery; the underlying column remains
``metadata``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin
from app.models.cluster import Cluster


class Resource(SoftDeleteMixin, Base):
    __tablename__ = "resources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clusters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(String(253), nullable=False)
    hostname_key: Mapped[str] = mapped_column(String(253), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'OTHER'"), default="OTHER"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'UNKNOWN'"), default="UNKNOWN"
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

    # Ownership relationship. The Session-level soft-delete filter applies to
    # eager loads of this relationship too (F003 I-5/B45); the HTTP response
    # layer deliberately loads the owning cluster explicitly with
    # ``include_deleted=True`` so a soft-deleted cluster is still shown for a
    # soft-deleted resource.
    cluster: Mapped["Cluster"] = relationship("Cluster", lazy="select")

    __table_args__ = (
        # Partial unique index, not a UniqueConstraint: soft-deleted rows must
        # not participate (DB-D38).
        Index(
            "uq_resources_cluster_id_hostname_key",
            "cluster_id",
            "hostname_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("btrim(hostname) <> ''", name="hostname_not_blank"),
        CheckConstraint("hostname = btrim(hostname)", name="hostname_trimmed"),
        CheckConstraint(
            "hostname !~ '[[:space:][:cntrl:]]'", name="hostname_no_ws_control"
        ),
        CheckConstraint(
            "char_length(hostname) BETWEEN 1 AND 253", name="hostname_length"
        ),
        CheckConstraint(
            "hostname = translate(hostname, "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz')",
            name="hostname_ascii_lower",
        ),
        CheckConstraint(
            "btrim(hostname_key) <> ''", name="hostname_key_not_blank"
        ),
        CheckConstraint(
            "char_length(hostname_key) BETWEEN 1 AND 253", name="hostname_key_length"
        ),
        CheckConstraint(
            "hostname_key = translate(btrim(hostname), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz')",
            name="hostname_key_matches",
        ),
        CheckConstraint(
            "resource_type IN ('BARE_METAL','VIRTUAL_MACHINE')",
            name="resource_type",
        ),
        CheckConstraint(
            "role IN ('COMPUTE','LOGIN','MANAGEMENT','STORAGE',"
            "'SERVICE','GPU','OTHER')",
            name="role",
        ),
        CheckConstraint(
            "status IN ('IDLE','ALLOC','DOWN','UNKNOWN')", name="status"
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name="metadata_object"
        ),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_resources_cluster_id", "cluster_id"),
        Index("ix_resources_resource_type", "resource_type"),
        Index("ix_resources_role", "role"),
        Index("ix_resources_status", "status"),
        Index("ix_resources_deleted_at", "deleted_at"),
        Index("ix_resources_hostname_key", "hostname_key"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Resource id={self.id!r} hostname={self.hostname!r} "
            f"type={self.resource_type!r}>"
        )