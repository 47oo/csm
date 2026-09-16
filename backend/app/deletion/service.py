"""统一逻辑删除领域服务 —— 系统内唯一写入 ``deleted_at`` 的代码路径。

行为契约（ADR-0004 §1/§3/§5；``docs/architecture/f014-soft-delete-handoff.md``）：

1. 在**调用方事务内**执行 ``SELECT ... WHERE id = :id AND deleted_at IS NULL
   FOR UPDATE``；未命中（不存在或已逻辑删除）→ :class:`NotFoundError`（404）。
2. 依次执行传入的每个 :data:`ActiveChildCheck`；任一返回 True →
   :class:`ConflictError`（409，``details[].code = "ACTIVE_CHILDREN_EXIST"``），
   **且不写 ``deleted_at``**（无部分写入）。
3. 仅对**已锁定的目标行**赋值 ``deleted_at = now()``（``updated_at`` 由既有
   ``onupdate`` 维护），``flush()``。
4. 不触碰任何其他行；不级联、不物理删除；不允许把 ``deleted_at`` 回写为空
   （R-DELETE-003：V1 无 undelete）。
5. 不在服务内部 ``commit`` / ``rollback``：事务边界由 ``app/api/deps.py`` 统一负责。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError
from app.db.active import select_active
from app.db.base import SoftDeleteMixin
from app.deletion.checks import ActiveChildCheck

#: 资源级冲突的稳定判别值（契约 §4.1）。``message`` 不构成契约。
_ACTIVE_CHILDREN_DETAIL = {
    "row": None,
    "field": None,
    "code": "ACTIVE_CHILDREN_EXIST",
    "message": "资源仍存在活跃子资源，无法删除",
}


def soft_delete[ModelT: SoftDeleteMixin](
    session: Session,
    resource_model: type[ModelT],
    resource_id: int,
    *,
    active_children: Sequence[ActiveChildCheck] = (),
) -> ModelT:
    """对 ``resource_model`` 中 ``id == resource_id`` 的活跃行执行逻辑删除。

    返回被软删的 ORM 实例。失败时抛出 :class:`NotFoundError` / :class:`ConflictError`。
    """
    # 1) 同一事务内锁定活跃目标行；FOR UPDATE 在获得锁后重新求值
    #    ``deleted_at IS NULL``（READ COMMITTED），并发软删竞争下后到者 404。
    stmt = select_active(resource_model).where(resource_model.id == resource_id).with_for_update()
    instance = session.scalars(stmt).one_or_none()
    if instance is None:
        raise NotFoundError()

    # 2) 锁已取得，再执行资源模块声明的活跃子资源检查；命中即拒绝且不写 deleted_at。
    for check in active_children:
        if check(session, resource_id):
            raise ConflictError(
                "父资源存在活跃子资源，无法删除",
                details=[dict(_ACTIVE_CHILDREN_DETAIL)],
            )

    # 3) 只改目标行；不级联、不物理删除、不触碰其他行。
    instance.deleted_at = datetime.now(UTC)
    session.flush()
    return instance
