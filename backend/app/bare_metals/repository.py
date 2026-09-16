"""BareMetal 数据访问。

读取路径**必须**通过 ``app/db/active.py`` 的 ``active_filter`` / ``select_active``
表达「活跃」（ADR-0004 §3）；本模块不重写 ``deleted_at.is_(None)`` 的第二份谓词。

写入只有 ``create`` 与 ``update``。**不存在**写入 ``deleted_at`` 的方法
（删除领域语义唯一归属 F014 的统一软删服务）。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bare_metals.schemas import HARDWARE_FIELDS
from app.common.pagination import PageParams
from app.db.active import active_filter, select_active
from app.models.bare_metal import BareMetal


class BareMetalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active(self, bare_metal_id: int) -> BareMetal | None:
        stmt = select_active(BareMetal).where(BareMetal.id == bare_metal_id)
        return self.session.scalars(stmt).one_or_none()

    def active_hostname_exists(self, cluster_id: int, hostname: str) -> bool:
        """同一 Cluster 活跃范围内是否已存在该 hostname（大小写敏感，字面值等值）。"""
        stmt = (
            select_active(BareMetal)
            .where(BareMetal.cluster_id == cluster_id, BareMetal.hostname == hostname)
            .limit(1)
        )
        return self.session.scalars(stmt).first() is not None

    def list_active(
        self, params: PageParams, *, cluster_id: int | None = None
    ) -> tuple[list[BareMetal], int]:
        conditions = [active_filter(BareMetal)]
        if cluster_id is not None:
            conditions.append(BareMetal.cluster_id == cluster_id)

        total = self.session.scalar(select(func.count()).select_from(BareMetal).where(*conditions))
        stmt = (
            select_active(BareMetal)
            .where(*conditions)
            .order_by(BareMetal.id)
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(self.session.scalars(stmt)), int(total or 0)

    def create(
        self,
        *,
        cluster_id: int,
        hostname: str,
        status: str | None,
        hardware: dict[str, str | None],
    ) -> BareMetal:
        values: dict[str, object] = {
            "cluster_id": cluster_id,
            "hostname": hostname,
        }
        # status 未显式提供时**省略该列**，让数据库默认 'IDLE' 生效（R-BM-004）。
        if status is not None:
            values["status"] = status
        for field in HARDWARE_FIELDS:
            values[field] = hardware.get(field)

        bare_metal = BareMetal(**values)
        self.session.add(bare_metal)
        # flush 让数据库约束（partial unique / CHECK / FK）在请求内抛出，
        # 从而经通用 SQLSTATE 映射返回契约错误（数据库为最终权威）。
        self.session.flush()
        self.session.refresh(bare_metal)
        return bare_metal

    def update(self, bare_metal: BareMetal, fields: dict[str, str | None]) -> BareMetal:
        for name, value in fields.items():
            setattr(bare_metal, name, value)
        self.session.flush()
        self.session.refresh(bare_metal)
        return bare_metal
