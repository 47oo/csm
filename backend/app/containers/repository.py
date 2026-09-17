"""Container 数据访问。

读取路径**必须**通过 ``app/db/active.py`` 的 ``active_filter`` / ``select_active``
表达「活跃」（ADR-0004 §3）；本模块不重写 ``deleted_at.is_(None)`` 的第二份谓词。

载体过滤按 ``carrier_type`` 分派到 ``bare_metal_id`` 或 ``virtual_machine_id`` 列；
该实现是「按载体限定读取」的 canonical 能力，供 F010 复用。

写入只有 ``create`` 与 ``update``。**不存在**写入 ``deleted_at`` 的方法
（删除领域语义唯一归属 F014 的统一软删服务）。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.containers.schemas import OPTIONAL_FIELDS, CarrierType
from app.db.active import active_filter, select_active
from app.models.container import Container


class ContainerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active(self, container_id: int) -> Container | None:
        stmt = select_active(Container).where(Container.id == container_id)
        return self.session.scalars(stmt).one_or_none()

    def active_name_exists(self, carrier_type: CarrierType, carrier_id: int, name: str) -> bool:
        """指定载体内是否已存在该活跃 ``name``（大小写敏感，字面值等值）。

        唯一性边界是**运行载体**（R-CONTAINER-003），不是全局、也不是集群。
        """
        stmt = (
            select_active(Container)
            .where(
                self._carrier_condition(carrier_type, carrier_id),
                Container.name == name,
            )
            .limit(1)
        )
        return self.session.scalars(stmt).first() is not None

    @staticmethod
    def _carrier_condition(carrier_type: CarrierType, carrier_id: int):
        if carrier_type == CarrierType.BARE_METAL:
            return Container.bare_metal_id == carrier_id
        return Container.virtual_machine_id == carrier_id

    def list_active(
        self,
        params: PageParams,
        *,
        carrier_type: CarrierType | None = None,
        carrier_id: int | None = None,
    ) -> tuple[list[Container], int]:
        conditions = [active_filter(Container)]
        if carrier_type is not None and carrier_id is not None:
            conditions.append(self._carrier_condition(carrier_type, carrier_id))

        total = self.session.scalar(select(func.count()).select_from(Container).where(*conditions))
        stmt = (
            select_active(Container)
            .where(*conditions)
            .order_by(Container.id)
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(self.session.scalars(stmt)), int(total or 0)

    def create(
        self,
        *,
        carrier_type: CarrierType,
        carrier_id: int,
        name: str,
        optional: dict[str, str | None],
    ) -> Container:
        values: dict[str, object] = {"name": name}
        if carrier_type == CarrierType.BARE_METAL:
            values["bare_metal_id"] = carrier_id
        else:
            values["virtual_machine_id"] = carrier_id
        for field in OPTIONAL_FIELDS:
            values[field] = optional.get(field)

        container = Container(**values)
        self.session.add(container)
        # flush 让数据库约束（partial unique / FK / CHECK）在请求内抛出，
        # 从而经通用 SQLSTATE 映射返回契约错误（数据库为最终权威）。
        self.session.flush()
        self.session.refresh(container)
        return container

    def update(self, container: Container, fields: dict[str, str | None]) -> Container:
        for name, value in fields.items():
            setattr(container, name, value)
        self.session.flush()
        self.session.refresh(container)
        return container
