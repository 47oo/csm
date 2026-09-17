"""IPAddress 数据访问。

读取路径**必须**通过 ``app/db/active.py`` 的 ``active_filter`` / ``select_active``
表达「活跃」（ADR-0004 §3）；本模块不重写 ``deleted_at.is_(None)`` 的第二份谓词。

``create`` 是系统内**唯一**向 ``ip_addresses.cluster_id`` 写入的位置（AC-37）；
其 ``cluster_id`` 实参**只能**来自 ``app/ip_addresses/derivation.py::derive_cluster_id``。
写入只有 ``create`` 与 ``update``；**不存在**写入 ``deleted_at`` 的方法（删除领域语义
唯一归属 F014 的统一软删服务）。**不存在**任何格式校验 / trim / 归一化方法（NQ-1）。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.db.active import active_filter, select_active
from app.models.ip_address import IpAddress


class IpAddressRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active(self, ip_address_id: int) -> IpAddress | None:
        stmt = select_active(IpAddress).where(IpAddress.id == ip_address_id)
        return self.session.scalars(stmt).one_or_none()

    def list_active(
        self, params: PageParams, *, network_interface_id: int | None = None
    ) -> tuple[list[IpAddress], int]:
        conditions = [active_filter(IpAddress)]
        if network_interface_id is not None:
            conditions.append(IpAddress.network_interface_id == network_interface_id)

        total = self.session.scalar(select(func.count()).select_from(IpAddress).where(*conditions))
        stmt = (
            select_active(IpAddress)
            .where(*conditions)
            .order_by(IpAddress.id)
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(self.session.scalars(stmt)), int(total or 0)

    def active_ip_exists(
        self, cluster_id: int, ip_address: str, *, exclude_id: int | None = None
    ) -> bool:
        """活跃范围内 ``(cluster_id, ip_address)`` 字面等值是否已存在。

        仅用于返回友好 ``409``（体验优化）；``ux_ip_addresses_cluster_ip_active``
        才是唯一性**最终权威**（§21）。
        """
        stmt = select(IpAddress.id).where(
            active_filter(IpAddress),
            IpAddress.cluster_id == cluster_id,
            IpAddress.ip_address == ip_address,
        )
        if exclude_id is not None:
            stmt = stmt.where(IpAddress.id != exclude_id)
        return self.session.scalars(stmt.limit(1)).first() is not None

    def create(
        self,
        *,
        network_interface_id: int,
        cluster_id: int,
        ip_address: str,
    ) -> IpAddress:
        ip = IpAddress(
            network_interface_id=network_interface_id,
            cluster_id=cluster_id,
            ip_address=ip_address,
        )
        self.session.add(ip)
        # flush 让数据库约束（FK / partial unique）在请求内抛出，
        # 从而经通用 SQLSTATE 映射返回契约错误（数据库为最终权威）。
        self.session.flush()
        self.session.refresh(ip)
        return ip

    def update(self, ip: IpAddress, fields: dict[str, str]) -> IpAddress:
        for name, value in fields.items():
            setattr(ip, name, value)
        self.session.flush()
        self.session.refresh(ip)
        return ip
