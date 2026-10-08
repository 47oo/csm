"""``interfaces`` model (DB-D64..DB-D79, DR-72..DR-85).

Columns/constraints mirror migration ``0007_interfaces`` exactly. Short
constraint names let the ``Base`` naming convention expand them to the
fully-qualified names from the database design (``ck_interfaces_<name>``).

Interface is an **independent addressable object** (own ``id``/``version`` /
``deleted_at`` / restore / Activity), not a 1:1 child of ``Resource``: the PK is
its own UUID and ``resource_id`` is an ordinary ``NOT NULL`` FK with
``ON DELETE RESTRICT`` (DB-D64/DR-72). ``resource_id``/``id`` are immutable
(enforced by ``trg_interfaces_immutable_resource``; the application returns 422
first). ``parent_interface_id`` is a nullable self-referential FK
(``ON DELETE RESTRICT``) whose same-Resource / non-self / acyclic correctness is
enforced by ``trg_interfaces_parent_valid`` plus the Service layer.

``name`` is trimmed, non-empty, whitespace/control free and 1-64 code points,
case-preserving; ``(resource_id, name)`` is *partially* unique among undeleted
rows (``uq_interfaces_resource_id_name``), so soft delete releases the name and
a restore must re-check it. ``metadata`` is Interface-owned JSONB; the ORM
attribute is named ``meta`` because ``metadata`` is reserved by declarative.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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

# Ordered Interface field names shared with the schemas/service/audit.
VALID_INTERFACE_TYPES = (
    "PHYSICAL",
    "VIRTUAL",
    "BOND",
    "BRIDGE",
    "VLAN",
    "LOOPBACK",
    "OTHER",
)


class Interface(SoftDeleteMixin, Base):
    __tablename__ = "interfaces"

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
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    interface_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'OTHER'"), default="OTHER"
    )
    mac_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    speed_mbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mtu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_interface_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interfaces.id", ondelete="RESTRICT"),
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
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
    parent_interface: Mapped["Interface | None"] = relationship(
        "Interface",
        remote_side="Interface.id",
        lazy="select",
        foreign_keys="Interface.parent_interface_id",
    )

    __table_args__ = (
        # Partial unique index, not a UniqueConstraint: soft-deleted rows must
        # not participate (DB-D66/DR-73).
        Index(
            "uq_interfaces_resource_id_name",
            "resource_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("name = btrim(name)", name="name_trimmed"),
        CheckConstraint("name !~ '[[:space:][:cntrl:]]'", name="name_no_ws_control"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 64", name="name_length"),
        CheckConstraint(
            "interface_type IN ('PHYSICAL','VIRTUAL','BOND','BRIDGE',"
            "'VLAN','LOOPBACK','OTHER')",
            name="interface_type",
        ),
        CheckConstraint(
            "mac_address IS NULL OR "
            "(mac_address = btrim(mac_address) AND btrim(mac_address) <> '' "
            "AND mac_address !~ '[[:cntrl:]]')",
            name="mac_address_format",
        ),
        CheckConstraint(
            "speed_mbps IS NULL OR (speed_mbps BETWEEN 1 AND 2147483647)",
            name="speed_mbps_range",
        ),
        CheckConstraint(
            "mtu IS NULL OR (mtu BETWEEN 1 AND 2147483647)",
            name="mtu_range",
        ),
        CheckConstraint(
            "parent_interface_id IS NULL OR parent_interface_id <> id",
            name="parent_not_self",
        ),
        CheckConstraint("jsonb_typeof(metadata) = 'object'", name="metadata_object"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_interfaces_resource_id", "resource_id"),
        Index("ix_interfaces_parent_interface_id", "parent_interface_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Interface id={self.id!r} name={self.name!r} "
            f"resource_id={self.resource_id!r}>"
        )