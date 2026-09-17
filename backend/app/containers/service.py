"""Container 业务行为：登记 / 列表 / 按 id 读取 / 更新 / 逻辑删除。

不负责 HTTP 展示文案；不写入 ``deleted_at``（删除委托系统内唯一软删服务）。

创建关系写入（R-CONTAINER-002 / AC-38）：

1. 按 ``carrier_type`` 分派到载体表，在**同一事务内**对被选中载体行取共享锁并确认
   活跃（``SELECT … WHERE id=:id AND deleted_at IS NULL FOR SHARE``，单表、无 JOIN、
   不加 ``OF``）；未命中（不存在 / 已软删 / 类型与标识不一致）→ 404（NQ-2 裁定）。
2. 载体内活跃重复预检 → 409（``details[].code = "DUPLICATE"``）。
3. 插入；数据库两条 partial unique index 为最终权威。

读取路径（列表 + 详情）统一经 repository 的活跃过滤；按载体限定时先确认载体存在且
活跃（不存在 / 已删 → 404；存在但无活跃 Container → 200 空集）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.pagination import PageParams
from app.containers.deletion import CONTAINER_ACTIVE_CHILD_CHECKS
from app.containers.repository import ContainerRepository
from app.containers.schemas import (
    OPTIONAL_FIELDS,
    CarrierType,
    ContainerCreate,
    ContainerUpdate,
)
from app.db.active import select_active
from app.deletion import soft_delete
from app.models.bare_metal import BareMetal
from app.models.container import Container
from app.models.virtual_machine import VirtualMachine


def _carrier_model(carrier_type: CarrierType) -> type[BareMetal] | type[VirtualMachine]:
    if carrier_type == CarrierType.BARE_METAL:
        return BareMetal
    return VirtualMachine


def _lock_active_carrier(session: Session, carrier_type: CarrierType, carrier_id: int) -> None:
    """按类型对被选中载体的活跃行取共享锁（``FOR SHARE``）；未命中 → 404。"""
    model = _carrier_model(carrier_type)
    stmt = select_active(model).where(model.id == carrier_id).with_for_update(read=True)
    if session.scalars(stmt).one_or_none() is None:
        # 不存在 / 已软删 / 类型与标识不一致一律 404，不做区分（NQ-2 裁定）。
        raise NotFoundError()


def create_container(session: Session, payload: ContainerCreate) -> Container:
    _lock_active_carrier(session, payload.carrier_type, payload.carrier_id)

    repository = ContainerRepository(session)
    if repository.active_name_exists(payload.carrier_type, payload.carrier_id, payload.name):
        raise ConflictError(
            "Container 名称已存在",
            details=[
                {
                    "field": "name",
                    "code": "DUPLICATE",
                    "message": "同一载体内已存在活跃的同名 Container",
                }
            ],
        )

    optional = {field: getattr(payload, field) for field in OPTIONAL_FIELDS}
    return repository.create(
        carrier_type=payload.carrier_type,
        carrier_id=payload.carrier_id,
        name=payload.name,
        optional=optional,
    )


def list_containers(
    session: Session,
    params: PageParams,
    *,
    carrier_type: CarrierType | None = None,
    carrier_id: int | None = None,
) -> tuple[list[Container], int]:
    if (carrier_type is None) != (carrier_id is None):
        # ``carrier_type`` 与 ``carrier_id`` 必须成对出现。
        missing = "carrier_id" if carrier_id is None else "carrier_type"
        raise ValidationError(
            "载体过滤参数必须成对提供",
            details=[{"field": missing, "code": "INVALID", "message": "载体过滤参数缺失"}],
        )

    if carrier_type is not None and carrier_id is not None:
        model = _carrier_model(carrier_type)
        carrier = session.scalars(select_active(model).where(model.id == carrier_id)).one_or_none()
        if carrier is None:
            # 载体不存在 / 已软删 / 类型不一致 → 404；存在但无活跃 Container → 200 空集。
            raise NotFoundError()

    return ContainerRepository(session).list_active(
        params, carrier_type=carrier_type, carrier_id=carrier_id
    )


def get_container_by_id(session: Session, container_id: int) -> Container:
    container = ContainerRepository(session).get_active(container_id)
    if container is None:
        # 「不存在」与「已逻辑删除」一律 404，不做区分（契约 §4.3）。
        raise NotFoundError()
    return container


def update_container(session: Session, container_id: int, payload: ContainerUpdate) -> Container:
    repository = ContainerRepository(session)
    container = repository.get_active(container_id)
    if container is None:
        raise NotFoundError()

    provided = payload.model_fields_set
    if not provided:
        raise ValidationError("请求体至少需包含一个可变字段")

    updates = {name: getattr(payload, name) for name in provided}
    return repository.update(container, updates)


def delete_container(session: Session, container_id: int) -> Container:
    """逻辑删除 Container：委托系统内唯一的软删写入路径（F014）。

    Container 自身的活跃子资源检查由模块显式声明
    （``CONTAINER_ACTIVE_CHILD_CHECKS``，当前空元组——代表 Service 表尚不存在）
    并**显式传入**，不假定「Container 无子资源」（F008 追加位置）。
    """
    return soft_delete(
        session,
        Container,
        container_id,
        active_children=CONTAINER_ACTIVE_CHILD_CHECKS,
    )
