"""F006 IP 分配 Pydantic v2 Schemas（字段以 docs/api/F006.md 为准）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IpCreate(BaseModel):
    """新增 IP（`interfaces[].ips[]`，`POST /resources` 或网卡 `op:"create"`）。"""

    model_config = ConfigDict(extra="ignore")

    mode: str | None = None
    address: str | None = None


class IpOp(BaseModel):
    """编辑请求中网卡的 ``ips[]`` 项（判别字段 ``op``）。"""

    model_config = ConfigDict(extra="ignore")

    op: str | None = None
    id: int | None = None
    mode: str | None = None
    address: str | None = None


class ManagementIpRef(BaseModel):
    """管理 IP 引用（请求）。``ip_id`` 或 ``interface_index`` + ``address``。"""

    model_config = ConfigDict(extra="ignore")

    ip_id: int | None = None
    interface_index: int | None = None
    address: str | None = None


class IpAddressResource(BaseModel):
    id: int
    address: str
    segment_id: int
    interface_id: int
    is_management: bool
    created_at: datetime


class ManagementIpSummary(BaseModel):
    ip_id: int
    address: str
    interface_id: int
    interface_name: str


class AllocatedIpItem(BaseModel):
    ip_id: int
    address: str
    resource_id: int
    resource_name: str
    resource_type: str
    interface_id: int
    interface_name: str
    is_management: bool
    created_at: datetime


class PagedAllocatedIps(BaseModel):
    items: list[AllocatedIpItem]
    total: int
    page: int
    page_size: int