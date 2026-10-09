"""``ip_pools`` model (DB-D95..DB-D110, DR-102..DR-117).

Columns/constraints mirror migration ``0009_ip_pools`` exactly. Short constraint
names let the ``Base`` naming convention expand them to the fully-qualified
names from the database design (``ck_ip_pools_<name>``).

IPPool is an **independent addressable object** (own ``id``/``version`` /
``deleted_at`` / restore / Activity), not a 1:1 child of Network: the PK is its
own UUID and ``network_id`` is an ordinary ``NOT NULL`` FK with
``ON DELETE RESTRICT`` (DB-D95/DR-102); it is immutable after creation
(application 422, DR-107). ``name`` is trimmed, non-empty, Cc/Cf free and 1-255
code points, case-preserving; ``name_key`` is the internal, non-exposed
normalisation key ``ASCII_lower(btrim(name))`` and ``(network_id, name_key)`` is
*partially* unique among undeleted rows (``uq_ip_pools_network_id_name_key``), so
soft delete releases the name and a restore must re-check it (DR-103).

``start_address``/``end_address`` are PostgreSQL ``inet`` host addresses
(family 4, masklen 32) with ``start <= end``. ``address_range`` is a generated
stored ``int8range`` over the closed interval used by the exclusion constraint
``excl_ip_pools_network_id_address_range``; it is read-only (DR-106). The
same-Network CIDR containment rule is enforced by the
``trg_ip_pools_cidr_contains`` trigger backstop plus the Service layer (DR-104).

Soft-delete semantics (Contract §5): the Session-level ``with_loader_criteria``
filter hides ``deleted_at IS NOT NULL`` rows by default; callers opt in with
``include_deleted=True``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INT8RANGE, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin

if TYPE_CHECKING:
    from app.models.network import Network

# Ordered allocation modes shared with the schemas/service/DB CHECK.
VALID_ALLOCATION_MODES = ("MANUAL", "AUTO", "RESERVED")

# Closed-interval integer range over the two host addresses (DB-D99). Kept
# identical to the migration so a schema diff never diverges.
_ADDRESS_RANGE = (
    "int8range("
    "set_masklen(start_address, 32) - '0.0.0.0'::inet, "
    "set_masklen(end_address, 32) - '0.0.0.0'::inet, "
    "'[]')"
)


class IPPool(SoftDeleteMixin, Base):
    __tablename__ = "ip_pools"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_key: Mapped[str] = mapped_column(String(255), nullable=False)
    start_address: Mapped[str] = mapped_column(INET(), nullable=False)
    end_address: Mapped[str] = mapped_column(INET(), nullable=False)
    # Generated stored column: read-only from the ORM (DB-D99/DR-106).
    address_range: Mapped[Any] = mapped_column(
        INT8RANGE(),
        Computed(_ADDRESS_RANGE, persisted=True),
        nullable=False,
    )
    allocation_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'MANUAL'"),
        default="MANUAL",
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

    __table_args__ = (
        # Partial unique index, not a UniqueConstraint: soft-deleted rows must
        # not participate (DB-D97/DR-103).
        Index(
            "uq_ip_pools_network_id_name_key",
            "network_id",
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
            "family(start_address) = 4 AND masklen(start_address) = 32",
            name="start_address_host",
        ),
        CheckConstraint(
            "family(end_address) = 4 AND masklen(end_address) = 32",
            name="end_address_host",
        ),
        CheckConstraint("start_address <= end_address", name="address_order"),
        CheckConstraint(
            "allocation_mode IN ('MANUAL','AUTO','RESERVED')",
            name="allocation_mode",
        ),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_ip_pools_network_id", "network_id"),
        Index("ix_ip_pools_allocation_mode", "allocation_mode"),
        Index("ix_ip_pools_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<IPPool id={self.id!r} name={self.name!r} "
            f"network_id={self.network_id!r} "
            f"start={self.start_address!r} end={self.end_address!r}>"
        )