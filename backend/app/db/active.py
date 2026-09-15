"""活跃记录过滤基座（数据访问层原语，**不是**领域服务）。

ADR-0004：所有常规查询必须附加 ``deleted_at IS NULL``，且由数据访问层统一提供。
F012 只交付这个可复用原语；统一软删除领域服务属 F014。
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, Select, select

from app.db.base import SoftDeleteMixin


def active_filter[ModelT: SoftDeleteMixin](model: type[ModelT]) -> ColumnElement[bool]:
    """返回 ``model.deleted_at IS NULL`` 条件。"""
    return model.deleted_at.is_(None)


def select_active[ModelT: SoftDeleteMixin](model: type[ModelT]) -> Select[tuple[ModelT]]:
    """返回仅含活跃行的 SELECT。"""
    return select(model).where(active_filter(model))
