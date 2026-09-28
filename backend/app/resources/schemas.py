"""F002 资源 Pydantic v2 Schemas（字段以 docs/api/F002.md，F006 扩展为准）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..ip_allocation.schemas import (
    IpAddressResource,
    IpCreate,
    IpOp,
    ManagementIpRef,
    ManagementIpSummary,
)


class InterfaceSegmentSummary(BaseModel):
    id: int
    name: str
    cidr: str
    purpose: str
    technology: str
    vlan: int | None
    gateway: str | None


class NetworkInterfaceResource(BaseModel):
    id: int
    name: str
    segment_id: int | None
    segment: InterfaceSegmentSummary | None
    ips: list[IpAddressResource]
    created_at: datetime
    updated_at: datetime


class ClusterScope(BaseModel):
    """F003 列表作用域回显（只读）。"""

    cluster_id: int
    cluster_code: str
    cluster_name: str


class ResourceListItem(BaseModel):
    """F003 计算资源列表项（公共列；类型摘要由 F004 扩展）。"""

    id: int
    name: str
    cluster_id: int
    cluster_code: str
    cluster_name: str
    resource_type: str
    resource_type_label: str
    status: str
    status_label: str
    management_ip: ManagementIpSummary | None
    updated_at: datetime


class PagedResources(BaseModel):
    items: list[ResourceListItem]
    total: int
    page: int
    page_size: int
    scope: ClusterScope


class ResourceFormDetail(BaseModel):
    id: int
    cluster_id: int
    cluster_code: str
    cluster_name: str
    name: str
    resource_type: str
    status: str
    status_updated_by: int | None
    status_updated_by_username: str | None
    status_updated_at: datetime
    interfaces: list[NetworkInterfaceResource]
    management_ip: ManagementIpSummary | None
    version: int
    created_at: datetime
    updated_at: datetime


class NetworkInterfaceCreateRequest(BaseModel):
    # 名称可空以便手动返回 INTERFACE_NAME_FORMAT（而非通用请求体校验）。
    name: str | None = None
    segment_id: int | None = None
    ips: list[IpCreate] | None = None
    model_config = ConfigDict(extra="ignore")


class ResourceCreateRequest(BaseModel):
    cluster_id: int
    name: str | None = None
    resource_type: str | None = None
    status: str | None = None
    interfaces: list[NetworkInterfaceCreateRequest] | None = None
    management_ip: ManagementIpRef | None = None
    model_config = ConfigDict(extra="ignore")


class NetworkInterfaceOpRequest(BaseModel):
    # 省略与显式 null 由 ``model_fields_set`` 区分。
    op: str | None = None
    id: int | None = None
    name: str | None = None
    segment_id: int | None = None
    ips: list[IpOp] | None = None
    model_config = ConfigDict(extra="ignore")


class ResourceUpdateRequest(BaseModel):
    # ``resource_type``/``cluster_id`` 只读：由路由层经 ``model_extra`` 判定。
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    status: str | None = None
    interfaces: list[NetworkInterfaceOpRequest] | None = None
    management_ip: ManagementIpRef | None = None
    version: int