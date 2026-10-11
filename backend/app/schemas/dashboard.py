"""F013 Dashboard schemas (Contract §3).

Two read-only blocks: global undeleted ``counts`` and a paginated ``networks``
list whose per-Network ``capacity`` / ``auto_pools`` numbers are identical to
``GET /api/v1/networks/{id}/capacity`` (F010 §6.9). ``remaining`` is returned
verbatim and may be negative.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class DashboardCounts(BaseModel):
    clusters: int
    resources: int
    bare_metal: int
    virtual_machines: int
    networks: int


class DashboardClusterNested(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class DashboardNetworkNested(BaseModel):
    id: uuid.UUID
    name: str
    cidr: str
    status: str
    auto_allocate: bool
    cluster: DashboardClusterNested


class DashboardCapacityBlock(BaseModel):
    allocatable_total: int
    occupied: int
    remaining: int


class DashboardIpPoolNested(BaseModel):
    id: uuid.UUID
    name: str
    start_address: str
    end_address: str


class DashboardAutoPoolBlock(BaseModel):
    ip_pool: DashboardIpPoolNested
    allocatable_total: int
    occupied: int
    remaining: int


class DashboardNetworkRow(BaseModel):
    network: DashboardNetworkNested
    capacity: DashboardCapacityBlock
    auto_pools: list[DashboardAutoPoolBlock]


class DashboardNetworkPage(BaseModel):
    items: list[DashboardNetworkRow]
    page: int
    page_size: int
    total: int


class DashboardResponse(BaseModel):
    counts: DashboardCounts
    networks: DashboardNetworkPage