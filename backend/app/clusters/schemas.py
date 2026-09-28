"""集群 Pydantic v2 Schemas（字段以 docs/api/F001.md 为准）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClusterListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    purpose: str
    created_at: datetime
    updated_at: datetime


class ClusterDetailOut(ClusterListItemOut):
    version: int


class PagedClusters(BaseModel):
    items: list[ClusterListItemOut]
    total: int
    page: int
    page_size: int


class ClusterCreateRequest(BaseModel):
    code: str
    name: str
    purpose: str


class ClusterUpdateRequest(BaseModel):
    # 仅 name/purpose 可改；code 出现即由路由层判定为 400 CODE_IMMUTABLE。
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    purpose: str | None = None
    version: int