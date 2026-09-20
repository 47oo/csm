"""F019 搜索结果聚合 schema（``docs/api/f019-search-result-aggregation.md`` §4）。

- :class:`SearchResourceType`：封闭六值判别枚举。
- :class:`SearchResultRole`：行角色封闭两值 ``HIT`` | ``RELATED``。
- :class:`ResourceRef`：``{resource_type, id}`` 资源身份二元组（``group_key`` 与
  ``derivation_path`` 的元素类型，封闭恰 2 字段）。
- :class:`SearchResultRow`：单一扁平列表中的一行；``resource`` 为六个 canonical
  ``*Read`` 的**联合**（逐字段复用，不新增字段、不引入第二份 canonical 读取实现）。
- :data:`SearchAggregationPage`：单元级分页信封（复用
  :class:`app.common.pagination.Page`）。
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


class SearchResultRole(StrEnum):
    """一行在**所属组织单元**中的角色（封闭两值）。"""

    HIT = "HIT"
    RELATED = "RELATED"


class ResourceRef(BaseModel):
    """资源身份二元组（``group_key`` / ``derivation_path`` 元素，恰 2 字段）。"""

    resource_type: SearchResourceType
    id: int


class SearchResultRow(BaseModel):
    """聚合结果中的一行（契约 §4.1 的封闭字段集合）。"""

    resource_type: SearchResourceType
    id: int
    role: SearchResultRole
    group_key: ResourceRef
    matched_fields: list[str]
    derivation_path: list[ResourceRef] | None
    resource: SearchResourceRead


#: 聚合响应信封：单元级分页下的扁平行列表。
class SearchAggregationPage(Page[SearchResultRow]):
    """搜索聚合响应的分页信封（``items`` 为本页单元的扁平行）。"""
