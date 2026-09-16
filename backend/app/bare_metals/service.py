"""BareMetal 业务行为：登记 / 列表 / 按 id 读取 / 更新 / 逻辑删除。

不负责 HTTP 展示文案；不写入 ``deleted_at``（删除委托系统内唯一软删服务）。
领域校验统一委托 ``app.bare_metals.validation``（唯一实现入口）。

创建关系写入（R-BM-001 / AC-26）：

1. 在**同一事务内**对父 Cluster 行取共享锁并确认活跃
   （``SELECT … WHERE id=:id AND deleted_at IS NULL FOR SHARE``）；未命中 → 404。
2. 活跃重复预检 → 409。
3. ``validate_status``（若提供）。
4. 插入；``status`` 未提供时由数据库默认 ``IDLE`` 生效。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.bare_metals import validation
from app.bare_metals.deletion import BARE_METAL_ACTIVE_CHILD_CHECKS
from app.bare_metals.repository import BareMetalRepository
from app.bare_metals.schemas import HARDWARE_FIELDS, BareMetalCreate, BareMetalUpdate
from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.pagination import PageParams
from app.db.active import select_active
from app.deletion import soft_delete
from app.models.bare_metal import BareMetal
from app.models.cluster import Cluster


def _lock_active_parent(session: Session, cluster_id: int) -> None:
    """对父 Cluster 行取共享锁（``FOR SHARE``）并确认活跃；未命中 → 404。"""
    stmt = select_active(Cluster).where(Cluster.id == cluster_id).with_for_update(read=True)
    if session.scalars(stmt).one_or_none() is None:
        # 不存在 / 已逻辑删除一律 404，不做区分（契约 §3.1）。
        raise NotFoundError()


def create_bare_metal(session: Session, payload: BareMetalCreate) -> BareMetal:
    _lock_active_parent(session, payload.cluster_id)

    repository = BareMetalRepository(session)
    if repository.active_hostname_exists(payload.cluster_id, payload.hostname):
        raise ConflictError(
            "同一 Cluster 内 hostname 已存在",
            details=[
                {
                    "field": "hostname",
                    "code": "DUPLICATE",
                    "message": "同一 Cluster 内已存在活跃的同名 hostname",
                }
            ],
        )

    status_to_apply: str | None = None
    if "status" in payload.model_fields_set:
        validation.validate_status(payload.status)
        status_to_apply = payload.status

    hardware = {field: getattr(payload, field) for field in HARDWARE_FIELDS}
    return repository.create(
        cluster_id=payload.cluster_id,
        hostname=payload.hostname,
        status=status_to_apply,
        hardware=hardware,
    )


def list_bare_metals(
    session: Session, params: PageParams, *, cluster_id: int | None = None
) -> tuple[list[BareMetal], int]:
    if cluster_id is not None:
        parent = session.scalars(
            select_active(Cluster).where(Cluster.id == cluster_id)
        ).one_or_none()
        if parent is None:
            # Cluster 不存在 / 已逻辑删除 → 404；存在但无活跃 BareMetal → 200 空集。
            raise NotFoundError()
    return BareMetalRepository(session).list_active(params, cluster_id=cluster_id)


def get_bare_metal_by_id(session: Session, bare_metal_id: int) -> BareMetal:
    bare_metal = BareMetalRepository(session).get_active(bare_metal_id)
    if bare_metal is None:
        # 「不存在」与「已逻辑删除」一律 404，不做区分（契约 §3.3）。
        raise NotFoundError()
    return bare_metal


def update_bare_metal(session: Session, bare_metal_id: int, payload: BareMetalUpdate) -> BareMetal:
    repository = BareMetalRepository(session)
    bare_metal = repository.get_active(bare_metal_id)
    if bare_metal is None:
        raise NotFoundError()

    provided = payload.model_fields_set
    if not provided:
        raise ValidationError("请求体至少需包含一个可变字段")

    if "status" in provided:
        validation.validate_status(payload.status)

    updates = {name: getattr(payload, name) for name in provided}
    return repository.update(bare_metal, updates)


def delete_bare_metal(session: Session, bare_metal_id: int) -> BareMetal:
    """逻辑删除 BareMetal：委托系统内唯一的软删写入路径（F014）。

    BareMetal 自身的活跃子资源检查由模块声明
    （``BARE_METAL_ACTIVE_CHILD_CHECKS``，F006 起包含「是否存在活跃 VirtualMachine」
    检查）并**显式传入**，不假定「无子资源」。
    """
    return soft_delete(
        session,
        BareMetal,
        bare_metal_id,
        active_children=BARE_METAL_ACTIVE_CHILD_CHECKS,
    )
