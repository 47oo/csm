"""IPAddressRange 数据访问（``app/ip_address_ranges/repository.py``）。

读取路径**必须**通过 ``app/db/active.py`` 的 ``active_filter`` / ``select_active``
表达「活跃」（ADR-0004 §3）；本模块不重写 ``deleted_at.is_(None)`` 的第二份谓词。

写入**只有** :meth:`IpAddressRangeRepository.create` 与
:meth:`IpAddressRangeRepository.update`；**不存在**写入 ``deleted_at`` 的方法（删除领域
语义唯一归属 F014 统一软删服务）。``start_ip`` / ``end_ip`` 的数值化解析由 service 层
（``ipv4.py``）完成，本模块只接收已规范化的整数。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.db.active import active_filter, select_active
from app.models.ip_address_range import IpAddressRange


class IpAddressRangeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active(self, ip_address_range_id: int) -> IpAddressRange | None:
        stmt = select_active(IpAddressRange).where(IpAddressRange.id == ip_address_range_id)
        return self.session.scalars(stmt).one_or_none()

    def list_active(
        self, params: PageParams, *, cluster_id: int | None = None
    ) -> tuple[list[IpAddressRange], int]:
        conditions = [active_filter(IpAddressRange)]
        if cluster_id is not None:
            conditions.append(IpAddressRange.cluster_id == cluster_id)

        total = self.session.scalar(
            select(func.count()).select_from(IpAddressRange).where(*conditions)
        )
        stmt = (
            select_active(IpAddressRange)
            .where(*conditions)
            .order_by(IpAddressRange.id)
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(self.session.scalars(stmt)), int(total or 0)

    def overlap_exists(
        self,
        cluster_id: int,
        start_ip: int,
        end_ip: int,
        *,
        exclude_id: int | None = None,
    ) -> bool:
        """同 Cluster 活跃范围内是否存在与 ``[start_ip, end_ip]`` 交集非空的行。

        仅用于返回友好 ``409 OVERLAP``；``ex_ip_address_ranges_active_no_overlap``
        排它约束才是不重叠的**最终权威**（§6）。
        """
        stmt = select(IpAddressRange.id).where(
            active_filter(IpAddressRange),
            IpAddressRange.cluster_id == cluster_id,
            IpAddressRange.start_ip <= end_ip,
            IpAddressRange.end_ip >= start_ip,
        )
        if exclude_id is not None:
            stmt = stmt.where(IpAddressRange.id != exclude_id)
        return self.session.scalars(stmt.limit(1)).first() is not None

    def active_name_exists(
        self, cluster_id: int, name: str, *, exclude_id: int | None = None
    ) -> bool:
        """同 Cluster 活跃范围内是否已存在**字面相同**的 ``name``。

        仅用于返回友好 ``409 DUPLICATE``；
        ``ux_ip_address_ranges_cluster_name_active`` partial unique index 才是最终权威
        （区分大小写、软删 / 未命名行释放）。
        """
        stmt = select(IpAddressRange.id).where(
            active_filter(IpAddressRange),
            IpAddressRange.cluster_id == cluster_id,
            IpAddressRange.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(IpAddressRange.id != exclude_id)
        return self.session.scalars(stmt.limit(1)).first() is not None

    def create(
        self,
        *,
        cluster_id: int,
        start_ip: int,
        end_ip: int,
        name: str | None = None,
        subnet_mask: str | None = None,
        vlan: int | None = None,
    ) -> IpAddressRange:
        ip_address_range = IpAddressRange(
            cluster_id=cluster_id,
            start_ip=start_ip,
            end_ip=end_ip,
            name=name,
            subnet_mask=subnet_mask,
            vlan=vlan,
        )
        self.session.add(ip_address_range)
        # flush 让数据库约束（FK / CHECK / EXCLUDE / partial unique）在请求内抛出，
        # 从而经通用 SQLSTATE 映射返回契约错误（数据库为最终权威）。
        self.session.flush()
        self.session.refresh(ip_address_range)
        return ip_address_range

    def update(
        self, ip_address_range: IpAddressRange, fields: dict[str, int | str | None]
    ) -> IpAddressRange:
        for name, value in fields.items():
            setattr(ip_address_range, name, value)
        self.session.flush()
        self.session.refresh(ip_address_range)
        return ip_address_range
