"""``bare_metal_details`` model (DB-D45..DB-D52).

Columns/constraints mirror migration ``0005_bare_metal_details`` exactly. Short
constraint names let the ``Base`` naming convention expand them to the
fully-qualified names from the database design (``ck_bare_metal_details_<name>``).

This is a lifecycle-bound 1:1 child of ``Resource``: ``resource_id`` is both the
primary key and an ``ON DELETE CASCADE`` foreign key, there is no ``deleted_at``
/ ``version`` / timestamp column, and the only valid owner is a ``BARE_METAL``
Resource (enforced by the ``trg_bare_metal_details_type_match`` trigger). The
``metadata`` column is mapped to the ``meta`` ORM attribute because ``metadata``
is reserved by SQLAlchemy's declarative machinery; the underlying column remains
``metadata``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.resource import Resource

# Ordered hardware field names shared with the schemas/service.
STRING_FIELDS = ("manufacturer", "model", "serial_number", "cpu_model", "gpu_model")
POSITIVE_INT_FIELDS = ("cpu_sockets", "cpu_cores", "memory_mb")
NON_NEGATIVE_INT_FIELDS = ("gpu_count",)
INT_FIELDS = POSITIVE_INT_FIELDS + NON_NEGATIVE_INT_FIELDS


class BareMetalDetail(Base):
    __tablename__ = "bare_metal_details"

    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cpu_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gpu_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cpu_sockets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpu_cores: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpu_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    resource: Mapped["Resource"] = relationship(  # noqa: F821
        "Resource", back_populates="bare_metal_detail"
    )

    __table_args__ = (
        *(
            CheckConstraint(
                f"{column} IS NULL OR "
                f"({column} = btrim({column}) AND btrim({column}) <> '')",
                name=f"{column}_format",
            )
            for column in STRING_FIELDS
        ),
        CheckConstraint(
            "cpu_sockets IS NULL OR (cpu_sockets >= 1 AND cpu_sockets <= 2147483647)",
            name="cpu_sockets_range",
        ),
        CheckConstraint(
            "cpu_cores IS NULL OR (cpu_cores >= 1 AND cpu_cores <= 2147483647)",
            name="cpu_cores_range",
        ),
        CheckConstraint(
            "memory_mb IS NULL OR (memory_mb >= 1 AND memory_mb <= 2147483647)",
            name="memory_mb_range",
        ),
        CheckConstraint(
            "gpu_count IS NULL OR (gpu_count >= 0 AND gpu_count <= 2147483647)",
            name="gpu_count_range",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name="metadata_object"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<BareMetalDetail resource_id={self.resource_id!r}>"