"""F005 网段 Pydantic v2 Schemas（字段以 docs/api/F005.md 为准）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReservedAddressOut(BaseModel):
    id: int
    start_ip: str
    end_ip: str
    is_range: bool
    created_at: datetime


class OverlapWarning(BaseModel):
    segment_id: int
    name: str
    cidr: str


class NetworkSegmentListItem(BaseModel):
    id: int
    cluster_id: int
    cluster_code: str
    cluster_name: str
    name: str
    cidr: str
    purpose: str
    technology: str
    vlan: int | None
    gateway: str | None
    auto_alloc_start: str | None
    auto_alloc_end: str | None
    auto_alloc_enabled: bool
    reserved_address_count: int
    allocated_count: int
    auto_assignable_count: int
    has_overlap: bool
    created_at: datetime
    updated_at: datetime


class NetworkSegmentDetail(NetworkSegmentListItem):
    reserved_addresses: list[ReservedAddressOut]
    overlaps: list[OverlapWarning]
    version: int


class PagedNetworkSegments(BaseModel):
    items: list[NetworkSegmentListItem]
    total: int
    page: int
    page_size: int


class ReservedAddressList(BaseModel):
    items: list[ReservedAddressOut]


class NetworkSegmentCreateRequest(BaseModel):
    cluster_id: int
    name: str
    cidr: str
    purpose: str
    technology: str
    vlan: int | None = None
    gateway: str | None = None
    auto_alloc_start: str | None = None
    auto_alloc_end: str | None = None


class NetworkSegmentUpdateRequest(BaseModel):
    # 省略字段=不修改；``model_fields_set`` 区分「未提供」与「显式 null」。
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    cidr: str | None = None
    purpose: str | None = None
    technology: str | None = None
    vlan: int | None = None
    gateway: str | None = None
    auto_alloc_start: str | None = None
    auto_alloc_end: str | None = None
    version: int


class ReservedAddressCreateRequest(BaseModel):
    start_ip: str
    end_ip: str | None = None