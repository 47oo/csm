"""Service 数据访问（``app/services/repository.py``）。

读取路径**必须**通过 ``app/db/active.py`` 的 ``active_filter`` / ``select_active``
表达「活跃」（ADR-0004 §3）；本模块不重写 ``deleted_at.is_(None)`` 的第二份谓词。

按载体限定读取的 canonical 能力落在 :meth:`ServiceRepository.list_active_services_by_carrier`，
**供 F010 复用**（F010 必须调用该能力，不得另写过滤），由 service 层先确认载体存在且
活跃（不存在 / 已删 → 404；存在但无活跃 Service → 200 空集）。

绑定写入**只有 INSERT**（登记时建立）；**不存在** UPDATE / DELETE 绑定行的方法，
也不存在写入 ``deleted_at`` 的方法（删除领域语义唯一归属 F014 统一软删服务）。
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.db.active import active_filter, select_active
from app.models.service import Service
from app.models.service_carrier import ServiceCarrier
from app.services.schemas import CARRIER_RANK, CarrierRef, ServiceCarrierType

#: 载体类型 → ``service_carriers`` 上的可空 FK 列名（存储形态，不暴露给 API）。
CARRIER_COLUMNS: dict[ServiceCarrierType, str] = {
    ServiceCarrierType.BARE_METAL: "bare_metal_id",
    ServiceCarrierType.VIRTUAL_MACHINE: "virtual_machine_id",
    ServiceCarrierType.CONTAINER: "container_id",
}


def carrier_ref_of(row: ServiceCarrier) -> CarrierRef:
    """由非空载体列派生 ``(carrier_type, carrier_id)``。"""
    if row.bare_metal_id is not None:
        return CarrierRef(carrier_type=ServiceCarrierType.BARE_METAL, carrier_id=row.bare_metal_id)
    if row.virtual_machine_id is not None:
        return CarrierRef(
            carrier_type=ServiceCarrierType.VIRTUAL_MACHINE, carrier_id=row.virtual_machine_id
        )
    return CarrierRef(carrier_type=ServiceCarrierType.CONTAINER, carrier_id=row.container_id)


def sort_carriers(carriers: list[CarrierRef]) -> list[CarrierRef]:
    """按 ``(carrier_type rank, carrier_id)`` 升序（与登记加锁全序一致）。"""
    return sorted(carriers, key=lambda c: (CARRIER_RANK[c.carrier_type], c.carrier_id))


class ServiceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- 读取 -----------------------------------------------------------------
    def get_active(self, service_id: int) -> Service | None:
        stmt = select_active(Service).where(Service.id == service_id)
        return self.session.scalars(stmt).one_or_none()

    def active_name_exists(self, name: str) -> bool:
        """是否已存在活跃同名 Service（全局、大小写敏感，字面值等值）。"""
        stmt = select_active(Service).where(Service.name == name).limit(1)
        return self.session.scalars(stmt).first() is not None

    @staticmethod
    def _carrier_condition(carrier_type: ServiceCarrierType, carrier_id: int):
        column = getattr(ServiceCarrier, CARRIER_COLUMNS[carrier_type])
        # **相关子查询**：绑定行必须属于当前外层 Service，且载体列命中。
        return (
            select(ServiceCarrier.id)
            .where(ServiceCarrier.service_id == Service.id, column == carrier_id)
            .exists()
        )

    def list_active(
        self,
        params: PageParams,
        *,
        carriers: list[CarrierRef] | None = None,
    ) -> tuple[list[Service], int]:
        conditions = [active_filter(Service)]
        if carriers:
            for carrier in carriers:
                conditions.append(self._carrier_condition(carrier.carrier_type, carrier.carrier_id))

        total = self.session.scalar(select(func.count()).select_from(Service).where(*conditions))
        stmt = (
            select_active(Service)
            .where(*conditions)
            .order_by(Service.id)
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(self.session.scalars(stmt)), int(total or 0)

    def list_active_services_by_carrier(
        self,
        carrier_type: ServiceCarrierType,
        carrier_id: int,
        params: PageParams,
    ) -> tuple[list[Service], int]:
        """canonical「按载体限定读取活跃 Service」能力（R-QUERY-003，供 F010 复用）。"""
        return self.list_active(
            params, carriers=[CarrierRef(carrier_type=carrier_type, carrier_id=carrier_id)]
        )

    def carriers_for_services(self, service_ids: list[int]) -> dict[int, list[CarrierRef]]:
        """批量装配各 Service 的载体列表（稳定顺序），避免 N+1。"""
        if not service_ids:
            return {}
        stmt = select(ServiceCarrier).where(ServiceCarrier.service_id.in_(service_ids))
        grouped: dict[int, list[CarrierRef]] = defaultdict(list)
        for row in self.session.scalars(stmt):
            grouped[row.service_id].append(carrier_ref_of(row))
        return {service_id: sort_carriers(items) for service_id, items in grouped.items()}

    # --- 写入（仅 INSERT / Service 可选字段 UPDATE）----------------------------
    def create_with_carriers(
        self,
        *,
        name: str,
        optional: dict[str, str | None],
        carriers: list[CarrierRef],
    ) -> Service:
        values: dict[str, object] = {"name": name}
        for field in optional:
            values[field] = optional[field]

        service = Service(**values)
        self.session.add(service)
        # flush 让数据库约束（partial unique / FK / CHECK）在请求内抛出，
        # 从而经通用 SQLSTATE 映射返回契约错误（数据库为最终权威）。
        self.session.flush()
        self.insert_carriers(service.id, carriers)
        self.session.refresh(service)
        return service

    def insert_carriers(self, service_id: int, carriers: list[CarrierRef]) -> None:
        rows = []
        for carrier in carriers:
            values: dict[str, object] = {"service_id": service_id}
            values[CARRIER_COLUMNS[carrier.carrier_type]] = carrier.carrier_id
            rows.append(ServiceCarrier(**values))
        self.session.add_all(rows)
        self.session.flush()

    def update(self, service: Service, fields: dict[str, str | None]) -> Service:
        for name, value in fields.items():
            setattr(service, name, value)
        self.session.flush()
        self.session.refresh(service)
        return service
