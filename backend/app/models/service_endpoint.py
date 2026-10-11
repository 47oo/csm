"""``service_endpoints`` model (DB-D142..DB-D156, DR-155..DR-170).

Columns/constraints mirror migration ``0012_service_endpoints`` exactly. Short
constraint names let the ``Base`` naming convention expand them to the
fully-qualified names from the database design (``ck_service_endpoints_<name>``);
the partial unique index name is written explicitly.

ServiceEndpoint is an **independent addressable object** (own ``id``/``version``
/ ``deleted_at`` / restore / Activity, DR-155), not a 1:1 child of Service or
IPAddress: the PK is its own UUID and ``service_id``/``ip_address_id`` are
ordinary ``NOT NULL`` FKs with ``ON DELETE RESTRICT``. Both are immutable after
creation (application 422, DR-157; the database deliberately has no immutable
trigger, DB-D151).

``protocol`` is ``TCP|UDP`` (uppercase only, DR-160) and ``port`` is ``1..65535``.
``(ip_address_id, protocol, port)`` is *partially* unique among undeleted rows
(``uq_service_endpoints_ip_protocol_port``) per the same IPAddress, so soft
delete releases the listener and a restore must re-check it. The structural
attribution (the IP's bound Interface Resource equals the Service's Resource)
is an application main check (422 field="ip_address") with the
``trg_service_endpoints_attribution`` database backstop (DR-158).

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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin

if TYPE_CHECKING:
    from app.models.ip_address import IPAddress
    from app.models.service import Service

# Ordered protocol values shared with the schemas/service/DB CHECK (DR-160).
VALID_PROTOCOLS = ("TCP", "UDP")


class ServiceEndpoint(SoftDeleteMixin, Base):
    __tablename__ = "service_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ip_address_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ip_addresses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    protocol: Mapped[str] = mapped_column(String(8), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), default=1
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    service: Mapped["Service"] = relationship("Service", lazy="select")
    ip_address: Mapped["IPAddress"] = relationship("IPAddress", lazy="select")

    __table_args__ = (
        # Partial unique index, not a UniqueConstraint: soft-deleted rows must
        # not participate (DB-D149/DR-159).
        Index(
            "uq_service_endpoints_ip_protocol_port",
            "ip_address_id",
            "protocol",
            "port",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("protocol IN ('TCP','UDP')", name="protocol"),
        CheckConstraint("port BETWEEN 1 AND 65535", name="port"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_service_endpoints_service_id", "service_id"),
        Index("ix_service_endpoints_ip_address_id", "ip_address_id"),
        Index("ix_service_endpoints_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<ServiceEndpoint id={self.id!r} service_id={self.service_id!r} "
            f"ip_address_id={self.ip_address_id!r} "
            f"protocol={self.protocol!r} port={self.port!r}>"
        )