"""``cluster_id`` 受控推导（决策 5 / AC-32 / AC-33 / AC-37）。

本模块是系统内**唯一**从 ``NetworkInterface → BareMetal`` 链路读取 ``cluster_id``
用作 IP 归属推导的位置。``derive_cluster_id`` 以**单条语句**沿
``network_interface_id → network_interfaces.bare_metal_id → bare_metals.cluster_id``
推导，并在同一语句内：

1. 对**父 NIC 行**取共享锁（``FOR SHARE OF network_interfaces``）；
2. 同时确认父 NIC 与其宿主 BareMetal 均活跃（``WHERE deleted_at IS NULL``）。

未命中（NIC 不存在 / 已软删 / 上游链不活跃）→ ``404 NOT_FOUND``。

**不额外锁定** BareMetal / Cluster 行：``network_interfaces.bare_metal_id`` 与
``bare_metals.cluster_id`` 在 V1 均不可变（F002 / F004 的 ``PATCH`` 均不含），持有父
NIC 行共享锁已足以固定推导结果；「活跃 NIC ⇒ 活跃宿主」由 F014 的宿主删除活跃子检查
保证。该结论在「上游列可变」能力落地时必须重开。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.db.active import active_filter
from app.models.bare_metal import BareMetal
from app.models.network_interface import NetworkInterface


def derive_cluster_id(session: Session, network_interface_id: int) -> int:
    """从父 NIC 沿 ``NIC → BareMetal`` 推导 Cluster 归属；未命中 → ``404``。"""
    stmt = (
        select(BareMetal.cluster_id)
        .join(NetworkInterface, NetworkInterface.bare_metal_id == BareMetal.id)
        .where(
            NetworkInterface.id == network_interface_id,
            active_filter(NetworkInterface),
            active_filter(BareMetal),
        )
        .with_for_update(read=True, of=NetworkInterface)  # FOR SHARE OF network_interfaces
    )
    cluster_id = session.scalars(stmt).one_or_none()
    if cluster_id is None:
        # 不存在 / 已软删 / 上游链不活跃一律 404，不做区分（决策 7）。
        raise NotFoundError()
    return cluster_id
