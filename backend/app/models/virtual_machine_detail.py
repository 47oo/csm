"""``virtual_machine_details`` model (DB-D53..DB-D63).

Columns/constraints mirror migration ``0006_virtual_machine_details`` exactly.
Short constraint names let the ``Base`` naming convention expand them to the
fully-qualified names from the database design
(``ck_virtual_machine_details_<name>``).

This is a lifecycle-bound 1:1 child of ``Resource``: ``resource_id`` is both the
primary key and an ``ON DELETE CASCADE`` foreign key, there is no ``deleted_at``
/ ``version`` / timestamp column, and the only valid owner is a
``VIRTUAL_MACHINE`` Resource (enforced by
``trg_virtual_machine_details_type_match``). ``host_resource_id`` is
``NOT NULL`` with an ``ON DELETE RESTRICT`` FK to ``resources`` (the Host is an
independent referenced object) and the database additionally validates via
``trg_virtual_machine_details_host_valid`` that it is an undeleted ``BARE_METAL``
Resource in the same cluster. There is deliberately no VM-level ``metadata``
column: metadata belongs to the Resource (DR-69).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.resource import Resource

# Ordered VM field names shared with the schemas/service.
STRING_FIELDS = ("hypervisor",)
POSITIVE_INT_FIELDS = ("vcpu", "memory_mb")
NON_NEGATIVE_INT_FIELDS = ("disk_gb",)
INT_FIELDS = POSITIVE_INT_FIELDS + NON_NEGATIVE_INT_FIELDS


class VirtualMachineDetail(Base):
    __tablename__ = "virtual_machine_details"

    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    host_resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vcpu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disk_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hypervisor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    resource: Mapped["Resource"] = relationship(  # noqa: F821
        "Resource",
        back_populates="virtual_machine_detail",
        foreign_keys="VirtualMachineDetail.resource_id",
    )

    __table_args__ = (
        CheckConstraint(
            "vcpu IS NULL OR (vcpu >= 1 AND vcpu <= 2147483647)",
            name="vcpu_range",
        ),
        CheckConstraint(
            "memory_mb IS NULL OR (memory_mb >= 1 AND memory_mb <= 2147483647)",
            name="memory_mb_range",
        ),
        CheckConstraint(
            "disk_gb IS NULL OR (disk_gb >= 0 AND disk_gb <= 2147483647)",
            name="disk_gb_range",
        ),
        CheckConstraint(
            "hypervisor IS NULL OR "
            "(hypervisor = btrim(hypervisor) AND btrim(hypervisor) <> '')",
            name="hypervisor_format",
        ),
        Index(
            "ix_virtual_machine_details_host_resource_id",
            "host_resource_id",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VirtualMachineDetail resource_id={self.resource_id!r}>"