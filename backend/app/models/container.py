"""Container 资源 ORM 模型（F007 的显式资源表，由 migration ``0007`` 建立）。

严格对应 ``docs/database/f007-container-migration.md`` 的 ``containers`` 表：

- 列：``id`` / ``bare_metal_id`` / ``virtual_machine_id`` / ``name`` / ``image`` /
  ``cpu`` / ``memory`` / ``owner`` / ``created_at`` / ``updated_at`` / ``deleted_at``
  （共 **11 列**）；**无** ``status`` 列、**无** 集群维度列、**无** 载体判别列；
- 约束：``pk_containers``、
  ``ck_containers_carrier_exactly_one``（``num_nonnulls(...) = 1``）、
  ``fk_containers_bare_metal`` 与 ``fk_containers_virtual_machine``
  （均 ``RESTRICT`` / ``RESTRICT``）；
- 索引：``ux_containers_bare_metal_name_active`` /
  ``ux_containers_virtual_machine_name_active``（两条 partial unique，
  ``WHERE deleted_at IS NULL``，大小写敏感）、``ix_containers_bare_metal_id`` /
  ``ix_containers_virtual_machine_id``。

Container → 运行载体为 mandatory、恰好一个（R-CONTAINER-002），由两列可空 FK 承载；
任一时刻恰有一列非空，另一列为 NULL。``name`` 与四个可选字段无任何长度 / trim /
字符 / 格式约束（R-CONTAINER-003 / R-CONTAINER-004），不声明 ``COLLATE``、
不使用 ``lower()``。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKeyConstraint, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class Container(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "containers"

    # R-CONTAINER-002：运行载体二选一（BareMetal 或 VirtualMachine），恰好一个。
    bare_metal_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    virtual_machine_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # R-CONTAINER-003：身份标识；载体内活跃唯一、区分大小写；无长度 / trim / 空串约束。
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # R-CONTAINER-004：四个可选、纯文本、允许 NULL；不结构化、不参与唯一性。
    image: Mapped[str | None] = mapped_column(Text, nullable=True)
    cpu: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(bare_metal_id, virtual_machine_id) = 1",
            name="carrier_exactly_one",
        ),
        ForeignKeyConstraint(
            ["bare_metal_id"],
            ["bare_metals.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_containers_bare_metal",
        ),
        ForeignKeyConstraint(
            ["virtual_machine_id"],
            ["virtual_machines.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_containers_virtual_machine",
        ),
        Index(
            "ux_containers_bare_metal_name_active",
            "bare_metal_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ux_containers_virtual_machine_name_active",
            "virtual_machine_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_containers_bare_metal_id", "bare_metal_id"),
        Index("ix_containers_virtual_machine_id", "virtual_machine_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        carrier = (
            f"bare_metal_id={self.bare_metal_id!r}"
            if self.bare_metal_id is not None
            else f"virtual_machine_id={self.virtual_machine_id!r}"
        )
        return f"Container(id={self.id!r}, {carrier}, name={self.name!r})"
