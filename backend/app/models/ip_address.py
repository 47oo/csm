"""``ip_addresses`` model (DB-D111..DB-D127, DR-118..DR-139).

Columns/constraints mirror migration ``0010_ip_addresses`` exactly. Short
constraint names let the ``Base`` naming convention expand them to the
fully-qualified names from the database design (``ck_ip_addresses_<name>``);
index names are written explicitly (partial unique index).

IPAddress is an **independent addressable object** (own ``id``/``version`` /
``deleted_at`` / restore / Activity), not a 1:1 child of Interface or Network:
the PK is its own UUID. ``network_id`` is an ordinary ``NOT NULL`` FK
(``ON DELETE RESTRICT``) and ``network``/``address`` are immutable after
creation (application 422, DR-120). ``cluster_id`` is a **redundant** FK holding
``networks.cluster_id``; it is the carrier for the same-Cluster uniqueness scope
and is kept consistent by ``trg_ip_addresses_cluster_consistent`` (DB-D121).

``address`` is a PostgreSQL ``inet`` IPv4 **host** address (``family=4``,
``masklen=32``, never in a §11.1 disabled range); CIDR containment and
network/broadcast exclusion are the ``trg_ip_addresses_cidr_contains`` backstop.
``(cluster_id, address)`` is *partially* unique among undeleted rows
(``uq_ip_addresses_cluster_id_address``), so soft delete releases the address
and a restore must re-check it. ``interface_id`` is a nullable FK whose
non-null Resource must share the IP's Cluster
(``trg_ip_addresses_interface_cluster``). ``ip_pool_id`` is a nullable FK
carrying the allocation-source history (pool delete/shrink never reclaims).

Soft-delete semantics (Contract §5): the Session-level
``with_loader_criteria`` filter hides ``deleted_at IS NOT NULL`` rows by
default; callers opt in with ``include_deleted=True``.
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
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin

if TYPE_CHECKING:
    from app.models.interface import Interface
    from app.models.ip_pool import IPPool
    from app.models.network import Network


class IPAddress(SoftDeleteMixin, Base):
    __tablename__ = "ip_addresses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    network_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("networks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clusters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    address: Mapped[str] = mapped_column(INET(), nullable=False)
    interface_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interfaces.id", ondelete="RESTRICT"),
        nullable=True,
    )
    ip_pool_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ip_pools.id", ondelete="RESTRICT"),
        nullable=True,
    )
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

    network: Mapped["Network"] = relationship("Network", lazy="select")
    interface: Mapped["Interface | None"] = relationship("Interface", lazy="select")
    ip_pool: Mapped["IPPool | None"] = relationship("IPPool", lazy="select")

    __table_args__ = (
        # Partial unique index, not a UniqueConstraint: soft-deleted rows must
        # not participate (DB-D119/DR-119).
        Index(
            "uq_ip_addresses_cluster_id_address",
            "cluster_id",
            "address",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "family(address) = 4 AND masklen(address) = 32",
            name="address_host",
        ),
        CheckConstraint(
            "NOT ("
            "address << '0.0.0.0/8'::inet "
            "OR address << '127.0.0.0/8'::inet "
            "OR address << '169.254.0.0/16'::inet "
            "OR address << '224.0.0.0/4'::inet "
            "OR address << '240.0.0.0/4'::inet)",
            name="address_not_disabled",
        ),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_ip_addresses_network_id", "network_id"),
        Index("ix_ip_addresses_cluster_id", "cluster_id"),
        Index("ix_ip_addresses_interface_id", "interface_id"),
        Index("ix_ip_addresses_ip_pool_id", "ip_pool_id"),
        Index("ix_ip_addresses_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<IPAddress id={self.id!r} address={self.address!r} "
            f"network_id={self.network_id!r} cluster_id={self.cluster_id!r}>"
        )