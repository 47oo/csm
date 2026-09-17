"""ServiceCarrier N:M 多态绑定关系 ORM 模型（migration ``0008`` 建立）。

严格对应 ``docs/database/f008-service-migration.md`` 的 ``service_carriers`` 表：

- 列：``id`` / ``service_id`` / ``bare_metal_id`` / ``virtual_machine_id`` /
  ``container_id``（共 **5 列**）；
- 约束：``pk_service_carriers`` +
  ``ck_service_carriers_exactly_one_carrier``（``num_nonnulls(三列) = 1``）+
  4 条真实 FK（``fk_service_carriers_service`` / ``_bare_metal`` /
  ``_virtual_machine`` / ``_container``，全部 ``RESTRICT`` / ``RESTRICT``）；
- 索引：3 条集合语义 partial unique（``(service_id, <carrier_col>)
  WHERE <carrier_col> IS NOT NULL``）+ 3 条载体列索引 + ``ix_service_carriers_service_id``。

**这不是资源表，而是关系表**：不承载独立资源事实，因此**没有 ``deleted_at``、
没有时间戳**（``README`` / 架构 §2）。绑定行**只在登记时 INSERT**，永不
UPDATE / DELETE；「释放」由 ``services.deleted_at`` 派生，不产生任何写入。

无 ORM relationship（防 mapper 环；载体集合由 repository 显式装配）。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKeyConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin


class ServiceCarrier(IdMixin, Base):
    __tablename__ = "service_carriers"

    # 所属 Service；FK RESTRICT（禁止 CASCADE）。
    service_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # 载体三选一；任一时刻恰有一列非空（CHECK 保证），另两列为 NULL。
    bare_metal_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    virtual_machine_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    container_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(bare_metal_id, virtual_machine_id, container_id) = 1",
            name="exactly_one_carrier",
        ),
        ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_service_carriers_service",
        ),
        ForeignKeyConstraint(
            ["bare_metal_id"],
            ["bare_metals.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_service_carriers_bare_metal",
        ),
        ForeignKeyConstraint(
            ["virtual_machine_id"],
            ["virtual_machines.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_service_carriers_virtual_machine",
        ),
        ForeignKeyConstraint(
            ["container_id"],
            ["containers.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_service_carriers_container",
        ),
        Index(
            "ux_service_carriers_service_bare_metal",
            "service_id",
            "bare_metal_id",
            unique=True,
            postgresql_where=text("bare_metal_id IS NOT NULL"),
        ),
        Index(
            "ux_service_carriers_service_virtual_machine",
            "service_id",
            "virtual_machine_id",
            unique=True,
            postgresql_where=text("virtual_machine_id IS NOT NULL"),
        ),
        Index(
            "ux_service_carriers_service_container",
            "service_id",
            "container_id",
            unique=True,
            postgresql_where=text("container_id IS NOT NULL"),
        ),
        Index("ix_service_carriers_bare_metal_id", "bare_metal_id"),
        Index("ix_service_carriers_virtual_machine_id", "virtual_machine_id"),
        Index("ix_service_carriers_container_id", "container_id"),
        Index("ix_service_carriers_service_id", "service_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"ServiceCarrier(id={self.id!r}, service_id={self.service_id!r}, "
            f"bare_metal_id={self.bare_metal_id!r}, "
            f"virtual_machine_id={self.virtual_machine_id!r}, "
            f"container_id={self.container_id!r})"
        )
