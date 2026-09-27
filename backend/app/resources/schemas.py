"""F002 资源 Pydantic v2 Schemas（字段以 docs/api/F002.md 为准）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    created_at: datetime
    updated_at: datetime


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
    version: int
    created_at: datetime
    updated_at: datetime


class NetworkInterfaceCreateRequest(BaseModel):
    # 名称可空以便手动返回 INTERFACE_NAME_FORMAT（而非通用请求体校验）。
    name: str | None = None
    segment_id: int | None = None
    model_config = ConfigDict(extra="ignore")


class ResourceCreateRequest(BaseModel):
    cluster_id: int
    name: str | None = None
    resource_type: str | None = None
    status: str | None = None
    interfaces: list[NetworkInterfaceCreateRequest] | None = None
    model_config = ConfigDict(extra="ignore")


class NetworkInterfaceOpRequest(BaseModel):
    # 省略与显式 null 由 ``model_fields_set`` 区分。
    op: str | None = None
    id: int | None = None
    name: str | None = None
    segment_id: int | None = None
    model_config = ConfigDict(extra="ignore")


class ResourceUpdateRequest(BaseModel):
    # ``resource_type``/``cluster_id`` 只读：由路由层经 ``model_extra`` 判定。
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    status: str | None = None
    interfaces: list[NetworkInterfaceOpRequest] | None = None
    version: int