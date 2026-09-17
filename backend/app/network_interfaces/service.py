"""NetworkInterface 业务行为：登记 / 列表 / 按 id 读取 / 更新 / 逻辑删除。

不负责 HTTP 展示文案；不写入 ``deleted_at``（删除委托系统内唯一软删服务）。

创建关系写入（R-NIC-003 / 决策 5）：

1. 在**同一事务内**对宿主 BareMetal 行取共享锁并确认活跃
   （``SELECT … WHERE id=:id AND deleted_at IS NULL FOR SHARE``）；未命中 → 404。
2. 校验 ``technology_type`` / ``purpose``（唯一一份领域校验）。
3. 插入。**无唯一性预检**（NQ-2 未确认，不得实现 NIC 名称唯一性）。

读取路径（列表 + 详情）统一经 repository 的活跃过滤；按 ``bare_metal_id`` 限定时
先确认宿主存在且活跃（不存在 / 已删 → 404；存在但无活跃 NIC → 200 空集）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.errors import NotFoundError, ValidationError
from app.common.pagination import PageParams
from app.db.active import select_active
from app.deletion import soft_delete
from app.models.bare_metal import BareMetal
from app.models.network_interface import NetworkInterface
from app.network_interfaces import validation
from app.network_interfaces.deletion import NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS
from app.network_interfaces.repository import NetworkInterfaceRepository
from app.network_interfaces.schemas import (
    NetworkInterfaceCreate,
    NetworkInterfaceUpdate,
)


def _lock_active_host(session: Session, bare_metal_id: int) -> None:
    """对宿主 BareMetal 行取共享锁（``FOR SHARE``）并确认活跃；未命中 → 404。"""
    stmt = select_active(BareMetal).where(BareMetal.id == bare_metal_id).with_for_update(read=True)
    if session.scalars(stmt).one_or_none() is None:
        # 不存在 / 已逻辑删除一律 404，不做区分（契约 §3.1）。
        raise NotFoundError()


def create_network_interface(session: Session, payload: NetworkInterfaceCreate) -> NetworkInterface:
    _lock_active_host(session, payload.bare_metal_id)

    # 应用层唯一一份校验；数据库 CHECK 为最终权威。
    validation.validate_technology_type(payload.technology_type)
    validation.validate_purpose(payload.purpose)

    return NetworkInterfaceRepository(session).create(
        bare_metal_id=payload.bare_metal_id,
        name=payload.name,
        technology_type=payload.technology_type,
        purpose=payload.purpose,
    )


def list_network_interfaces(
    session: Session, params: PageParams, *, bare_metal_id: int | None = None
) -> tuple[list[NetworkInterface], int]:
    if bare_metal_id is not None:
        host = session.scalars(
            select_active(BareMetal).where(BareMetal.id == bare_metal_id)
        ).one_or_none()
        if host is None:
            # 宿主不存在 / 已逻辑删除 → 404；存在但无活跃 NIC → 200 空集。
            raise NotFoundError()
    return NetworkInterfaceRepository(session).list_active(params, bare_metal_id=bare_metal_id)


def get_network_interface_by_id(session: Session, network_interface_id: int) -> NetworkInterface:
    network_interface = NetworkInterfaceRepository(session).get_active(network_interface_id)
    if network_interface is None:
        # 「不存在」与「已逻辑删除」一律 404，不做区分（契约 §3.3）。
        raise NotFoundError()
    return network_interface


def update_network_interface(
    session: Session, network_interface_id: int, payload: NetworkInterfaceUpdate
) -> NetworkInterface:
    repository = NetworkInterfaceRepository(session)
    network_interface = repository.get_active(network_interface_id)
    if network_interface is None:
        raise NotFoundError()

    provided = payload.model_fields_set
    if not provided:
        raise ValidationError("请求体至少需包含一个可变字段")

    if "technology_type" in provided:
        validation.validate_technology_type(payload.technology_type)
    if "purpose" in provided:
        validation.validate_purpose(payload.purpose)

    updates = {name: getattr(payload, name) for name in provided}
    return repository.update(network_interface, updates)


def delete_network_interface(session: Session, network_interface_id: int) -> NetworkInterface:
    """逻辑删除 NetworkInterface：委托系统内唯一的软删写入路径（F014）。

    NetworkInterface 自身的活跃子资源检查由模块声明
    （``NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS``，F005 起包含「是否存在活跃 IPAddress」检查）并**显式传入**，
    不假定「无子资源」（F005 追加位置）。
    """
    return soft_delete(
        session,
        NetworkInterface,
        network_interface_id,
        active_children=NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS,
    )
