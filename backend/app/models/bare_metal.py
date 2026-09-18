"""BareMetal 资源 ORM 模型（F002 的显式资源表，由 migration ``0003`` 建立）。

严格对应 ``docs/database/f002-bare-metal-migration.md`` 的 ``bare_metals`` 表：

- 列：``id`` / ``cluster_id`` / ``hostname`` / ``status`` / R-BM-007 七列 /
  ``created_at`` / ``updated_at`` / ``deleted_at``（共 14 列）；
- 约束：``pk_bare_metals``、``fk_bare_metals_cluster``（``RESTRICT`` / ``RESTRICT``）、
  ``ck_bare_metals_status``；
- 索引：``ux_bare_metals_cluster_hostname_active``（partial unique，
  ``WHERE deleted_at IS NULL``，大小写敏感）、``ix_bare_metals_cluster_id``。

ORM 不牺牲数据库完整性；``hostname`` / ``serial_number`` 无任何长度 / trim / 字符 /
唯一约束（R-BM-007、未定义约束「不实现」）。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKeyConstraint, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class BareMetal(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "bare_metals"

    cluster_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hostname: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'IDLE'"))

    # R-BM-007：可选、纯文本、允许 NULL；不参与唯一性。
    vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    serial_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    cpu: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory: Mapped[str | None] = mapped_column(Text, nullable=True)
    gpu: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_bare_metals_cluster",
        ),
        CheckConstraint("status IN ('IDLE', 'ALLOC', 'DOWN', 'UNKNOWN')", name="status"),
        Index(
            "ux_bare_metals_cluster_hostname_active",
            "cluster_id",
            "hostname",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_bare_metals_cluster_id", "cluster_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"BareMetal(id={self.id!r}, cluster_id={self.cluster_id!r}, hostname={self.hostname!r})"
        )
