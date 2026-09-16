"""VirtualMachine 业务行为：登记 / 列表 / 按 id 读取 / 更新 / 逻辑删除。

不负责 HTTP 展示文案；不写入 ``deleted_at``（删除委托系统内唯一软删服务）。

创建关系写入（R-VM-005 / AC-27）：

1. 在**同一事务内**对宿主 BareMetal 行取共享锁并确认活跃
   （``SELECT … WHERE id=:id AND deleted_at IS NULL FOR SHARE``）；未命中 → 404。
2. 全局活跃重复预检 → 409（``details[].code = "DUPLICATE"``）。
3. 插入；数据库 ``ux_virtual_machines_name_active`` 为最终权威。

读取路径（列表 + 详情）统一经 repository 的活跃过滤；按 ``bare_metal_id`` 限定时
先确认宿主存在且活跃（不存在 / 已删 → 404；存在但无活跃 VM → 200 空集）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.pagination import PageParams
from app.db.active import select_active
from app.deletion import soft_delete
from app.models.bare_metal import BareMetal
from app.models.virtual_machine import VirtualMachine
from app.virtual_machines.deletion import VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS
from app.virtual_machines.repository import VirtualMachineRepository
from app.virtual_machines.schemas import (
    OPTIONAL_FIELDS,
    VirtualMachineCreate,
    VirtualMachineUpdate,
)


def _lock_active_host(session: Session, bare_metal_id: int) -> None:
    """对宿主 BareMetal 行取共享锁（``FOR SHARE``）并确认活跃；未命中 → 404。"""
    stmt = select_active(BareMetal).where(BareMetal.id == bare_metal_id).with_for_update(read=True)
    if session.scalars(stmt).one_or_none() is None:
        # 不存在 / 已逻辑删除一律 404，不做区分（契约 §3.1）。
        raise NotFoundError()


def create_virtual_machine(session: Session, payload: VirtualMachineCreate) -> VirtualMachine:
    _lock_active_host(session, payload.bare_metal_id)

    repository = VirtualMachineRepository(session)
    if repository.active_name_exists(payload.name):
        raise ConflictError(
            "VirtualMachine 名称已存在",
            details=[
                {
                    "field": "name",
                    "code": "DUPLICATE",
                    "message": "已存在活跃的同名 VirtualMachine",
                }
            ],
        )

    optional = {field: getattr(payload, field) for field in OPTIONAL_FIELDS}
    return repository.create(
        bare_metal_id=payload.bare_metal_id,
        name=payload.name,
        optional=optional,
    )


def list_virtual_machines(
    session: Session, params: PageParams, *, bare_metal_id: int | None = None
) -> tuple[list[VirtualMachine], int]:
    if bare_metal_id is not None:
        host = session.scalars(
            select_active(BareMetal).where(BareMetal.id == bare_metal_id)
        ).one_or_none()
        if host is None:
            # 宿主不存在 / 已逻辑删除 → 404；存在但无活跃 VM → 200 空集。
            raise NotFoundError()
    return VirtualMachineRepository(session).list_active(params, bare_metal_id=bare_metal_id)


def get_virtual_machine_by_id(session: Session, virtual_machine_id: int) -> VirtualMachine:
    virtual_machine = VirtualMachineRepository(session).get_active(virtual_machine_id)
    if virtual_machine is None:
        # 「不存在」与「已逻辑删除」一律 404，不做区分（契约 §3.3）。
        raise NotFoundError()
    return virtual_machine


def update_virtual_machine(
    session: Session, virtual_machine_id: int, payload: VirtualMachineUpdate
) -> VirtualMachine:
    repository = VirtualMachineRepository(session)
    virtual_machine = repository.get_active(virtual_machine_id)
    if virtual_machine is None:
        raise NotFoundError()

    provided = payload.model_fields_set
    if not provided:
        raise ValidationError("请求体至少需包含一个可变字段")

    updates = {name: getattr(payload, name) for name in provided}
    return repository.update(virtual_machine, updates)


def delete_virtual_machine(session: Session, virtual_machine_id: int) -> VirtualMachine:
    """逻辑删除 VirtualMachine：委托系统内唯一的软删写入路径（F014）。

    VirtualMachine 自身的活跃子资源检查由模块声明
    （``VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS``，当前显式空元组）并**显式传入**，
    不假定「无子资源」（F007 追加位置）。
    """
    return soft_delete(
        session,
        VirtualMachine,
        virtual_machine_id,
        active_children=VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS,
    )
