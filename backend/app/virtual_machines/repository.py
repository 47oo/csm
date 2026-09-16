"""VirtualMachine 数据访问。

读取路径**必须**通过 ``app/db/active.py`` 的 ``active_filter`` / ``select_active``
表达「活跃」（ADR-0004 §3）；本模块不重写 ``deleted_at.is_(None)`` 的第二份谓词。

写入只有 ``create`` 与 ``update``。**不存在**写入 ``deleted_at`` 的方法
（删除领域语义唯一归属 F014 的统一软删服务）。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.db.active import active_filter, select_active
from app.models.virtual_machine import VirtualMachine
from app.virtual_machines.schemas import OPTIONAL_FIELDS


class VirtualMachineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active(self, virtual_machine_id: int) -> VirtualMachine | None:
        stmt = select_active(VirtualMachine).where(VirtualMachine.id == virtual_machine_id)
        return self.session.scalars(stmt).one_or_none()

    def active_name_exists(self, name: str) -> bool:
        """**全局**活跃范围内是否已存在该 name（大小写敏感，字面值等值）。

        名称唯一性是全局的（跨宿主、跨 Cluster，R-VM-004）；本查询不加
        ``bare_metal_id`` 过滤。
        """
        stmt = select_active(VirtualMachine).where(VirtualMachine.name == name).limit(1)
        return self.session.scalars(stmt).first() is not None

    def list_active(
        self, params: PageParams, *, bare_metal_id: int | None = None
    ) -> tuple[list[VirtualMachine], int]:
        conditions = [active_filter(VirtualMachine)]
        if bare_metal_id is not None:
            conditions.append(VirtualMachine.bare_metal_id == bare_metal_id)

        total = self.session.scalar(
            select(func.count()).select_from(VirtualMachine).where(*conditions)
        )
        stmt = (
            select_active(VirtualMachine)
            .where(*conditions)
            .order_by(VirtualMachine.id)
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(self.session.scalars(stmt)), int(total or 0)

    def create(
        self,
        *,
        bare_metal_id: int,
        name: str,
        optional: dict[str, str | None],
    ) -> VirtualMachine:
        values: dict[str, object] = {
            "bare_metal_id": bare_metal_id,
            "name": name,
        }
        for field in OPTIONAL_FIELDS:
            values[field] = optional.get(field)

        virtual_machine = VirtualMachine(**values)
        self.session.add(virtual_machine)
        # flush 让数据库约束（partial unique / FK）在请求内抛出，
        # 从而经通用 SQLSTATE 映射返回契约错误（数据库为最终权威）。
        self.session.flush()
        self.session.refresh(virtual_machine)
        return virtual_machine

    def update(
        self, virtual_machine: VirtualMachine, fields: dict[str, str | None]
    ) -> VirtualMachine:
        for name, value in fields.items():
            setattr(virtual_machine, name, value)
        self.session.flush()
        self.session.refresh(virtual_machine)
        return virtual_machine
