"""F018 搜索结果 schema（``docs/api/f018-cluster-keyword-search.md`` §3）。

- :class:`SearchResourceType`：封闭六值判别枚举。
- :class:`SearchResultItem`：``{resource_type, id, matched_fields, resource}``；
  其中 ``resource`` **逐字段复用**既有 canonical ``*Read``（不新增字段、不引入
  第二份 canonical 读取实现），``matched_fields`` 非空且顺序为契约 §2 声明顺序。
- :data:`SearchResultsPage`：复用 :class:`app.common.pagination.Page` 分页信封。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from app.bare_metals.schemas import BareMetalRead
from app.common.pagination import Page
from app.containers.schemas import ContainerRead
from app.ip_addresses.schemas import IpAddressRead
from app.network_interfaces.schemas import NetworkInterfaceRead
from app.services.schemas import ServiceRead
from app.virtual_machines.schemas import VirtualMachineRead


class SearchResourceType(StrEnum):
    """搜索结果的资源类型（封闭六值，判别字段）。"""

    BARE_METAL = "BARE_METAL"
    NETWORK_INTERFACE = "NETWORK_INTERFACE"
    IP_ADDRESS = "IP_ADDRESS"
    VIRTUAL_MACHINE = "VIRTUAL_MACHINE"
    CONTAINER = "CONTAINER"
    SERVICE = "SERVICE"


#: ``resource`` 的联合类型：恰为六个 canonical ``*Read``。
SearchResourceRead = (
    BareMetalRead
    | NetworkInterfaceRead
    | IpAddressRead
    | VirtualMachineRead
    | ContainerRead
    | ServiceRead
)


class SearchResultItem(BaseModel):
    """单条混合列表结果（契约 §3 的封闭字段集合）。"""

    resource_type: SearchResourceType
    id: int
    matched_fields: list[str]
    resource: SearchResourceRead


SearchResultsPage = Page[SearchResultItem]
