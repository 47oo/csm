"""F021 分配请求 schema（``docs/api/f021-ip-address-allocation.md`` §3）。

- ``IpAddressAutoAllocateRequest``：字段集合**恰为** ``{network_interface_id}``；
  ``extra="forbid"``（``cluster_id`` / ``status`` / ``ip_address`` / ``mode`` /
  ``reserved_addresses`` 或任何未识别字段 → ``400``）。
- ``IpAddressManualAllocateRequest``：字段集合**恰为**
  ``{network_interface_id, ip_address}``；``extra="forbid"``。

``ip_address`` **不在 Pydantic 层做 IPv4 格式约束**（与 F020 一致）：合法性由领域
service 调用 :mod:`app.ip_address_ranges.ipv4` 裁决，保证错误细节为契约要求的
``details[].field = "ip_address"`` / ``code = "INVALID"``。

**响应 schema 复用** :class:`app.ip_addresses.schemas.IpAddressRead`（恰 5 字段，
无 ``cluster_id`` / ``status`` / ``deleted_at``），本模块不新建响应类型。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IpAddressAutoAllocateRequest(BaseModel):
    """``POST /api/ip-addresses/allocate`` 请求体（请求 schema 封闭）。"""

    model_config = ConfigDict(extra="forbid")

    network_interface_id: int


class IpAddressManualAllocateRequest(BaseModel):
    """``POST /api/ip-addresses/allocate-manual`` 请求体（请求 schema 封闭）。"""

    model_config = ConfigDict(extra="forbid")

    network_interface_id: int
    ip_address: str


__all__ = [
    "IpAddressAutoAllocateRequest",
    "IpAddressManualAllocateRequest",
]