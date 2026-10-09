"""``networks`` model (DB-D80..DB-D94, DR-89..DR-101).

Columns/constraints mirror migration ``0008_networks`` exactly. Short
constraint names let the ``Base`` naming convention expand them to the
fully-qualified names from the database design (``ck_networks_<name>``).

Network is an **independent addressable object** (own ``id``/``version``/
``deleted_at``/restore/Activity), not a child of Cluster: the PK is its own UUID
and ``cluster_id`` is an ordinary ``NOT NULL`` FK with ``ON DELETE RESTRICT``
(DB-D80/DR-89). ``name_key`` is the internal, non-exposed normalisation key
``ASCII_lower(btrim(name))``; ``(cluster_id, name_key)`` is *partially* unique
among undeleted rows (``uq_networks_cluster_id_name_key``), so soft delete
releases the name and a restore must re-check it (DR-90). ``cidr`` uses the
native PostgreSQL ``cidr`` type (IPv4 only) and ``gateway`` nullable ``inet``.
``metadata`` is Network-owned JSONB; the ORM attribute is named ``meta`` because
``metadata`` is reserved by declarative (DR-95/I-6).

The same-Cluster CIDR no-overlap rule is enforced by the exclusion constraint
``excl_networks_cluster_id_cidr`` (btree_gist) created in the migration; the
Service layer pre-checks and maps overlaps to a ``range_overlap`` conflict.
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
from sqlalchemy.dialects.postgresql import CIDR, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin

if TYPE_CHECKING:
    from app.models.cluster import Cluster

# Ordered Network status values shared with the schemas/service.
VALID_NETWORK_STATUSES = ("ACTIVE", "INACTIVE")


class Network(SoftDeleteMixin, Base):
    __tablename__ = "networks"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_key: Mapped[str] = mapped_column(String(255), nullable=False)
    cidr: Mapped[str] = mapped_column(CIDR(), nullable=False)
    gateway: Mapped[str | None] = mapped_column(INET(), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'ACTIVE'"), default="ACTIVE"
    )
    auto_allocate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
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

    cluster: Mapped["Cluster"] = relationship("Cluster", lazy="select")

    __table_args__ = (
        # Partial unique index, not a UniqueConstraint: soft-deleted rows must
        # not participate (DB-D82/DR-90).
        Index(
            "uq_networks_cluster_id_name_key",
            "cluster_id",
            "name_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("name = btrim(name)", name="name_trimmed"),
        CheckConstraint("name !~ '[[:cntrl:]]'", name="name_no_control"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 255", name="name_length"),
        CheckConstraint(
            "name_key = translate(btrim(name), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')",
            name="name_key_matches",
        ),
        CheckConstraint("family(cidr) = 4", name="cidr_ipv4"),
        CheckConstraint(
            "gateway IS NULL OR ("
            "family(gateway) = 4 AND masklen(cidr) <= 31 AND gateway << cidr::inet "
            "AND (masklen(cidr) = 31 OR (gateway <> host(network(cidr))::inet "
            "AND gateway <> host(broadcast(cidr))::inet)) "
            "AND NOT (gateway << '0.0.0.0/8'::inet "
            "OR gateway << '127.0.0.0/8'::inet "
            "OR gateway << '169.254.0.0/16'::inet "
            "OR gateway << '224.0.0.0/4'::inet "
            "OR gateway << '240.0.0.0/4'::inet))",
            name="gateway",
        ),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("jsonb_typeof(metadata) = 'object'", name="metadata_object"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_networks_cluster_id", "cluster_id"),
        Index("ix_networks_status", "status"),
        Index("ix_networks_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Network id={self.id!r} name={self.name!r} cidr={self.cidr!r} "
            f"cluster_id={self.cluster_id!r}>"
        )