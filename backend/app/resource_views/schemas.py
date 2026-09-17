"""F010 聚合读取响应 schema（``docs/api/f010-resource-detail.md`` §2）。

- :class:`RelatedSet`：单类关联的统一信封 ``{items, total}``（``total == len(items)``）。
- :class:`RelatedResourcesRead`：顶层字段集合**恰为** ``network_interfaces /
  ip_addresses / virtual_machines / containers / services``。
- 元素类型**复用**既有 canonical ``*Read``（``NetworkInterfaceRead`` /
  ``IpAddressRead`` / ``VirtualMachineRead`` / ``ContainerRead`` / ``ServiceRead``）：
  不新增字段、不引入 Cluster / 位置 / 发现信息，也不暴露软删标记。
"""

from __future__ import annotations

from pydantic import BaseModel

from app.containers.schemas import ContainerRead
from app.ip_addresses.schemas import IpAddressRead
from app.network_interfaces.schemas import NetworkInterfaceRead
from app.services.schemas import ServiceRead
from app.virtual_machines.schemas import VirtualMachineRead


class RelatedSet[ItemT](BaseModel):
    """单类关联的 ``{items, total}`` 信封。"""

    items: list[ItemT]
    total: int


class RelatedResourcesRead(BaseModel):
    """BareMetal 上下文五类关联的聚合表示（顶层字段集合封闭）。"""

    network_interfaces: RelatedSet[NetworkInterfaceRead]
    ip_addresses: RelatedSet[IpAddressRead]
    virtual_machines: RelatedSet[VirtualMachineRead]
    containers: RelatedSet[ContainerRead]
    services: RelatedSet[ServiceRead]
