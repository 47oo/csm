"""F021 分配数据访问（**纯只读**）。

读取路径**必须**通过 ``app/db/active.py`` 的 ``active_filter`` 表达「活跃」
（ADR-0004 §3）；本模块不重写 ``deleted_at.is_(None)`` 的第二份谓词。

**不存在任何写入方法**：分配的写入经 ``app/ip_addresses/repository.py`` 的
``IpAddressRepository.create``（唯一 ``cluster_id`` 写入点）。占用判定按
``ip_address`` **字面**（R-IP-007）：不 trim / 不归一化 / 不做大小写折叠。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.active import active_filter
from app.models.ip_address import IpAddress
from app.models.ip_address_range import IpAddressRange


class IpAllocationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_active_ranges(self, cluster_id: int) -> list[tuple[int, int]]:
        """目标 Cluster 的活跃范围段 ``(start_ip, end_ip)``，按 ``start_ip`` 升序。"""
        stmt = (
            select(IpAddressRange.start_ip, IpAddressRange.end_ip)
            .where(
                active_filter(IpAddressRange),
                IpAddressRange.cluster_id == cluster_id,
            )
            .order_by(IpAddressRange.start_ip)
        )
        return [
            (row.start_ip, row.end_ip) for row in self.session.execute(stmt).all()
        ]

    def active_ip_literals(self, cluster_id: int) -> set[str]:
        """目标 Cluster 内全部活跃 IPAddress 的 ``ip_address`` **字面**集合。"""
        stmt = select(IpAddress.ip_address).where(
            active_filter(IpAddress),
            IpAddress.cluster_id == cluster_id,
        )
        return set(self.session.scalars(stmt))