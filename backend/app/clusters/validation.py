"""Cluster 领域校验 —— **唯一一份**实现，``POST`` / ``PATCH`` 共用。

职责（F001 REQUIRED #3）：

1. ``/`` 禁令（R-CLUSTER-005）：在**任何数据库写入之前**执行，返回
   ``400 VALIDATION_ERROR`` + ``details[].field = "name"`` +
   ``details[].code = "INVALID_CHARACTER"``，**永不** 500。
2. 活跃唯一性预检（R-CLUSTER-002）：给出友好 ``409 CONFLICT``；
   数据库 ``ux_clusters_name_active`` 仍是最终权威（预检被绕过时
   ``23505`` 由通用映射返回 ``409``）。

后续 Excel 导入（F011 / R-IMPORT-002）也复用同一入口，不在别处重复校验。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.common.errors import ConflictError, ValidationError

if TYPE_CHECKING:
    from app.clusters.repository import ClusterRepository


def validate_name_characters(name: str) -> None:
    """R-CLUSTER-005：名称不得包含 ``/``。"""
    if "/" in name:
        raise ValidationError(
            "集群名称不得包含 '/'",
            details=[
                {
                    "field": "name",
                    "code": "INVALID_CHARACTER",
                    "message": "集群名称不得包含 '/'",
                }
            ],
        )


def ensure_active_name_available(
    repository: ClusterRepository, name: str, *, exclude_id: int | None = None
) -> None:
    """活跃范围内名称不得重复（大小写敏感）。

    ``exclude_id`` 用于 ``PATCH``：改成自身当前名不算冲突，必须返回 ``200``。
    """
    if repository.active_name_exists(name, exclude_id=exclude_id):
        raise ConflictError(
            "集群名称已存在",
            details=[
                {
                    "field": "name",
                    "code": "DUPLICATE",
                    "message": "活跃集群中已存在同名名称",
                }
            ],
        )
