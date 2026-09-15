"""非产品自检面 ``/_foundation/clusters`` 的 schema。

**这不是产品契约。** 仅做通用 schema 校验：``name`` 为字符串、必填；无 ``/``
校验、无唯一性预检、无长度 / 空白规则。``deleted_at`` 不对外暴露。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClusterFixtureCreate(BaseModel):
    name: str = Field(..., description="通用字符串（无领域规则）")


class ClusterFixtureUpdate(BaseModel):
    name: str = Field(..., description="通用字符串（无领域规则）")


class ClusterFixtureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
