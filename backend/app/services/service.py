"""Service 业务行为：登记 / 列表 / 按 id 读取 / 更新 / 逻辑删除。

不负责 HTTP 展示文案；不写入 ``deleted_at``（删除委托系统内唯一软删服务）。

登记关系写入（R-SVC-005 / AC-47，契约 §7.1）：

1. 对请求 ``carriers`` 做集合去重检查（重复 → ``400``，``field="carriers"``、
   ``code="DUPLICATE"``）。
2. 按 ``(carrier_type rank, carrier_id)`` **升序**确定全序。
3. 按该序逐载体执行 ``select_active(Model).where(Model.id == carrier_id)
   .with_for_update(read=True)``（单表 ``FOR SHARE``，无 JOIN、不加 ``OF``）；
   任一未命中（不存在 / 已软删 / 类型与标识不一致）→ ``404``，且**在任何 INSERT
   之前**抛出（无 Service 行、无绑定行）。
4. ``name`` 全局活跃唯一预检 → ``409``。
5. 插入 1 行 ``services`` + N 行 ``service_carriers``（同一事务）；数据库约束为最终权威。

读取路径（列表 + 详情）统一经 repository 的活跃过滤；按载体限定时先确认载体存在且
活跃（不存在 / 已删 → 404；存在但无活跃 Service → 200 空集）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.pagination import PageParams
from app.db.active import select_active
from app.deletion import soft_delete
from app.models.bare_metal import BareMetal
from app.models.container import Container
from app.models.service import Service
from app.models.virtual_machine import VirtualMachine
from app.services.deletion import SERVICE_ACTIVE_CHILD_CHECKS
from app.services.repository import ServiceRepository, sort_carriers
from app.services.schemas import (
    OPTIONAL_FIELDS,
    CarrierRef,
    ServiceCarrierType,
    ServiceCreate,
    ServiceUpdate,
)

_CARRIER_MODELS = {
    ServiceCarrierType.BARE_METAL: BareMetal,
    ServiceCarrierType.VIRTUAL_MACHINE: VirtualMachine,
    ServiceCarrierType.CONTAINER: Container,
}


def _lock_active_carrier(session: Session, carrier: CarrierRef) -> None:
    """对载体活跃行取共享锁（``FOR SHARE``）并确认活跃；未命中 → 404。"""
    model = _CARRIER_MODELS[carrier.carrier_type]
    stmt = select_active(model).where(model.id == carrier.carrier_id).with_for_update(read=True)
    if session.scalars(stmt).one_or_none() is None:
        # 不存在 / 已软删 / 类型与标识不一致一律 404，不做区分（NQ-07 裁定）。
        raise NotFoundError()


def _deduplicate_or_reject(carriers: list[CarrierRef]) -> list[CarrierRef]:
    seen: set[tuple[ServiceCarrierType, int]] = set()
    for carrier in carriers:
        key = (carrier.carrier_type, carrier.carrier_id)
        if key in seen:
            raise ValidationError(
                "同一请求内不得重复给出同一载体",
                details=[
                    {
                        "field": "carriers",
                        "code": "DUPLICATE",
                        "message": "同一请求内重复给出同一 (carrier_type, carrier_id)",
                    }
                ],
            )
        seen.add(key)
    return carriers


def create_service(session: Session, payload: ServiceCreate) -> Service:
    _deduplicate_or_reject(payload.carriers)

    # 确定性全序：按 (carrier_type rank, carrier_id) 升序逐一取共享锁（§3）。
    ordered = sort_carriers(list(payload.carriers))
    for carrier in ordered:
        _lock_active_carrier(session, carrier)

    repository = ServiceRepository(session)
    if repository.active_name_exists(payload.name):
        raise ConflictError(
            "Service 名称已存在",
            details=[
                {
                    "field": "name",
                    "code": "DUPLICATE",
                    "message": "已存在活跃的同名 Service",
                }
            ],
        )

    optional = {field: getattr(payload, field) for field in OPTIONAL_FIELDS}
    return repository.create_with_carriers(name=payload.name, optional=optional, carriers=ordered)


def list_services(
    session: Session,
    params: PageParams,
    *,
    carrier_type: ServiceCarrierType | None = None,
    carrier_id: int | None = None,
) -> tuple[list[Service], int]:
    if (carrier_type is None) != (carrier_id is None):
        # ``carrier_type`` 与 ``carrier_id`` 必须成对出现（AC-32）。
        missing = "carrier_id" if carrier_id is None else "carrier_type"
        raise ValidationError(
            "载体过滤参数必须成对提供",
            details=[{"field": missing, "code": "INVALID", "message": "载体过滤参数缺失"}],
        )

    repository = ServiceRepository(session)
    if carrier_type is not None and carrier_id is not None:
        # 载体不存在 / 已软删 / 类型与标识不一致 → 404；存在但无活跃 Service → 200 空集。
        model = _CARRIER_MODELS[carrier_type]
        exists = session.scalars(select_active(model).where(model.id == carrier_id)).one_or_none()
        if exists is None:
            raise NotFoundError()
        return repository.list_active_services_by_carrier(carrier_type, carrier_id, params)

    return repository.list_active(params)


def carriers_of(session: Session, service: Service) -> list[CarrierRef]:
    """装配单个 Service 的载体列表（稳定顺序）。"""
    return ServiceRepository(session).carriers_for_services([service.id]).get(service.id, [])


def get_service_by_id(session: Session, service_id: int) -> Service:
    service = ServiceRepository(session).get_active(service_id)
    if service is None:
        # 「不存在」与「已逻辑删除」一律 404，不做区分（契约 §4.3）。
        raise NotFoundError()
    return service


def update_service(session: Session, service_id: int, payload: ServiceUpdate) -> Service:
    repository = ServiceRepository(session)
    service = repository.get_active(service_id)
    if service is None:
        raise NotFoundError()

    provided = payload.model_fields_set
    if not provided:
        raise ValidationError("请求体至少需包含一个可变字段")

    updates = {name: getattr(payload, name) for name in provided}
    return repository.update(service, updates)


def delete_service(session: Session, service_id: int) -> Service:
    """逻辑删除 Service：委托系统内唯一的软删写入路径（F014）。

    Service 无子资源，故 ``SERVICE_ACTIVE_CHILD_CHECKS`` 为显式空元组并**显式传入**。
    删除只改目标行；绑定行**不被修改、不被删除**（释放由 ``services.deleted_at`` 派生）。
    """
    return soft_delete(
        session,
        Service,
        service_id,
        active_children=SERVICE_ACTIVE_CHILD_CHECKS,
    )
