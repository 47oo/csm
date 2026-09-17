"""IPAddress 业务行为：登记 / 列表 / 按 id 读取 / 修正字面值 / 逻辑删除。

不负责 HTTP 展示文案；不写入 ``deleted_at``（删除委托系统内唯一软删服务）。

创建路径（决策 5 / 决策 7）：

1. ``derive_cluster_id`` 从父 NIC 推导 Cluster 归属（同事务对父 NIC 行取 ``FOR SHARE``
   并确认父 NIC 与其宿主 BareMetal 均活跃）；未命中 → ``404``；
2. 应用层预检 ``active_ip_exists`` 命中 → ``409 CONFLICT`` +
   ``details[{"field": "ip_address", "code": "DUPLICATE"}]``（体验优化）；
3. 写入。``cluster_id`` 只经此路径传入 ``IpAddressRepository.create``。

更新路径**不触碰** ``cluster_id`` 与 ``network_interface_id``（父绑定不可变）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.pagination import PageParams
from app.db.active import select_active
from app.deletion import soft_delete
from app.ip_addresses.deletion import IP_ADDRESS_ACTIVE_CHILD_CHECKS
from app.ip_addresses.derivation import derive_cluster_id
from app.ip_addresses.repository import IpAddressRepository
from app.ip_addresses.schemas import IpAddressCreate, IpAddressUpdate
from app.models.ip_address import IpAddress
from app.models.network_interface import NetworkInterface

_DUPLICATE_DETAIL = {
    "field": "ip_address",
    "code": "DUPLICATE",
    "message": "同一 Cluster 内已存在活跃的相同 IP 地址",
}


def create_ip_address(session: Session, payload: IpAddressCreate) -> IpAddress:
    # 1) 推导（同时锁定父 NIC 行并确认父 NIC / 宿主活跃）；未命中 → 404。
    cluster_id = derive_cluster_id(session, payload.network_interface_id)

    repository = IpAddressRepository(session)
    # 2) 应用层预检仅为友好 409；partial unique index 为最终权威。
    if repository.active_ip_exists(cluster_id, payload.ip_address):
        raise ConflictError("IP 地址已存在", details=[dict(_DUPLICATE_DETAIL)])

    return repository.create(
        network_interface_id=payload.network_interface_id,
        cluster_id=cluster_id,
        ip_address=payload.ip_address,
    )


def list_ip_addresses(
    session: Session, params: PageParams, *, network_interface_id: int | None = None
) -> tuple[list[IpAddress], int]:
    if network_interface_id is not None:
        parent = session.scalars(
            select_active(NetworkInterface).where(NetworkInterface.id == network_interface_id)
        ).one_or_none()
        if parent is None:
            # 父 NIC 不存在 / 已软删 → 404；存在但无活跃 IP → 200 空集。
            raise NotFoundError()
    return IpAddressRepository(session).list_active(
        params, network_interface_id=network_interface_id
    )


def get_ip_address_by_id(session: Session, ip_address_id: int) -> IpAddress:
    ip = IpAddressRepository(session).get_active(ip_address_id)
    if ip is None:
        # 「不存在」与「已逻辑删除」一律 404，不做区分（契约 §3.3）。
        raise NotFoundError()
    return ip


def update_ip_address(session: Session, ip_address_id: int, payload: IpAddressUpdate) -> IpAddress:
    repository = IpAddressRepository(session)
    ip = repository.get_active(ip_address_id)
    if ip is None:
        raise NotFoundError()

    provided = payload.model_fields_set
    if not provided:
        raise ValidationError("请求体至少需包含一个可变字段")

    if "ip_address" in provided:
        if payload.ip_address is None:
            raise ValidationError(
                "ip_address 不能为空",
                details=[{"field": "ip_address", "code": "INVALID", "message": "字段不能为 null"}],
            )
        # 修正后重校验唯一性；排除目标行自身。partial unique index 为最终权威。
        if repository.active_ip_exists(ip.cluster_id, payload.ip_address, exclude_id=ip.id):
            raise ConflictError("IP 地址已存在", details=[dict(_DUPLICATE_DETAIL)])

    updates = {name: getattr(payload, name) for name in provided}
    # 不写 cluster_id / network_interface_id（父绑定不可变）。
    return repository.update(ip, updates)


def delete_ip_address(session: Session, ip_address_id: int) -> IpAddress:
    """逻辑删除 IPAddress：委托系统内唯一的软删写入路径（F014）。

    IPAddress 是 V1 叶子资源，自身活跃子资源检查显式为空元组并**显式传入**，
    不假定「无子资源」。
    """
    return soft_delete(
        session,
        IpAddress,
        ip_address_id,
        active_children=IP_ADDRESS_ACTIVE_CHILD_CHECKS,
    )
