"""NetworkInterface 数据访问。

读取路径**必须**通过 ``app/db/active.py`` 的 ``active_filter`` / ``select_active``
表达「活跃」（ADR-0004 §3）；本模块不重写 ``deleted_at.is_(None)`` 的第二份谓词。

写入只有 ``create`` 与 ``update``。**不存在**写入 ``deleted_at`` 的方法
（删除领域语义唯一归属 F014 的统一软删服务）。

**不存在任何名称唯一性查询方法**：NQ-2 未确认，F004 不实现 NIC 名称唯一性
（无唯一索引、无应用层预检）。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.db.active import active_filter, select_active
from app.models.network_interface import NetworkInterface


class NetworkInterfaceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active(self, network_interface_id: int) -> NetworkInterface | None:
        stmt = select_active(NetworkInterface).where(NetworkInterface.id == network_interface_id)
        return self.session.scalars(stmt).one_or_none()

    def list_active(
        self, params: PageParams, *, bare_metal_id: int | None = None
    ) -> tuple[list[NetworkInterface], int]:
        conditions = [active_filter(NetworkInterface)]
        if bare_metal_id is not None:
            conditions.append(NetworkInterface.bare_metal_id == bare_metal_id)

        total = self.session.scalar(
            select(func.count()).select_from(NetworkInterface).where(*conditions)
        )
        stmt = (
            select_active(NetworkInterface)
            .where(*conditions)
            .order_by(NetworkInterface.id)
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(self.session.scalars(stmt)), int(total or 0)

    def create(
        self,
        *,
        bare_metal_id: int,
        name: str,
        technology_type: str,
        purpose: str,
    ) -> NetworkInterface:
        network_interface = NetworkInterface(
            bare_metal_id=bare_metal_id,
            name=name,
            technology_type=technology_type,
            purpose=purpose,
        )
        self.session.add(network_interface)
        # flush 让数据库约束（FK / CHECK）在请求内抛出，
        # 从而经通用 SQLSTATE 映射返回契约错误（数据库为最终权威）。
        self.session.flush()
        self.session.refresh(network_interface)
        return network_interface

    def update(
        self, network_interface: NetworkInterface, fields: dict[str, str | None]
    ) -> NetworkInterface:
        for name, value in fields.items():
            setattr(network_interface, name, value)
        self.session.flush()
        self.session.refresh(network_interface)
        return network_interface
