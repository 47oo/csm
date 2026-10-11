"""``services`` model (DB-D128..DB-D141, DR-140..DR-154).

Columns/constraints mirror migration ``0011_services`` exactly. Short constraint
names let the ``Base`` naming convention expand them to the fully-qualified
names from the database design (``ck_services_<name>``).

Service is an **independent addressable object** (own ``id``/``version`` /
``deleted_at`` / restore / Activity, DR-140), not a 1:1 child of Resource: the PK
is its own UUID and ``resource_id`` is an ordinary ``NOT NULL`` FK with
``ON DELETE RESTRICT``. It is immutable after creation (application 422,
DR-144; the database deliberately has no immutable trigger, DB-D136). ``name``
is trimmed, non-empty, Cc/Cf free and 1-255 code points, case-preserving;
``name_key`` is the internal, non-exposed normalisation key
``ASCII_lower(btrim(name))`` and ``(resource_id, name_key)`` is *partially*
unique among undeleted rows (``uq_services_resource_id_name_key``), so soft
delete releases the name and a restore must re-check it (DR-141).

``status`` is a registered, manually maintained value in
``{RUNNING,STOPPED,UNKNOWN}`` (default ``UNKNOWN``); it is never derived from the
name or an external probe (DR-142). ``metadata`` is Service-owned JSONB
(``object``, default ``{}``, whole-value replacement, DR-143); the ORM attribute
is named ``meta`` because ``metadata`` is reserved by SQLAlchemy's declarative
machinery while the physical column remains ``metadata``.

Soft-delete semantics (Contract §5): the Session-level ``with_loader_criteria``
filter hides ``deleted_at IS NOT NULL`` rows by default; callers opt in with
``include_deleted=True``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from app.models.resource import Resource

# Ordered status values shared with the schemas/service/DB CHECK (DR-142).
VALID_STATUSES = ("RUNNING", "STOPPED", "UNKNOWN")


class Service(SoftDeleteMixin, Base):
    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'UNKNOWN'"),
        default="UNKNOWN",
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

    resource: Mapped["Resource"] = relationship("Resource", lazy="select")

    __table_args__ = (
        # Partial unique index, not a UniqueConstraint: soft-deleted rows must
        # not participate (DB-D131/DR-141).
        Index(
            "uq_services_resource_id_name_key",
            "resource_id",
            "name_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("name = btrim(name)", name="name_trimmed"),
        CheckConstraint("name !~ '[[:cntrl:]]'", name="name_no_control"),
        CheckConstraint(
            "char_length(name) BETWEEN 1 AND 255", name="name_length"
        ),
        CheckConstraint(
            "name_key = translate(btrim(name), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')",
            name="name_key_matches",
        ),
        CheckConstraint(
            "status IN ('RUNNING','STOPPED','UNKNOWN')", name="status"
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name="metadata_object"
        ),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_services_resource_id", "resource_id"),
        Index("ix_services_status", "status"),
        Index("ix_services_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Service id={self.id!r} name={self.name!r} "
            f"resource_id={self.resource_id!r} status={self.status!r}>"
        )