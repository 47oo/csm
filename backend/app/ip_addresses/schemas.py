"""IPAddress 请求 / 响应 schema（``docs/api/f005-ip-address.md`` §2 / §3）。

- ``IpAddressRead``：字段集合**恰为** ``{id, network_interface_id, ip_address,
  created_at, updated_at}``（5 字段）：**无** ``cluster_id``（NQ-4 裁定：Cluster 归属
  是内部推导值，不对外暴露）、**无** ``deleted_at`` / ``status`` / VRF / IP 池 /
  载体多态字段。
- ``IpAddressCreate``：``network_interface_id`` + ``ip_address`` 必填（恰 2 字段）；
  ``extra="forbid"``（``cluster_id`` / 多父 / 载体选择器 / ``status`` → 400）。
  ``ip_address`` **无** ``min_length`` / ``max_length`` / ``pattern`` /
  ``str_strip_whitespace``，也不做归一化（NQ-1「不实现」）。
- ``IpAddressUpdate``：仅 ``ip_address`` 一个可变字段（恰 1 字段）；**不含**
  ``network_interface_id``（父绑定不可变）/ ``id`` / ``created_at`` / ``deleted_at`` /
  ``cluster_id`` / ``status``；``extra="forbid"``。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

#: NQ-2 / 决策 2：PATCH 可变字段封闭集合（恰为 ``ip_address``）。
MUTABLE_FIELDS: tuple[str, ...] = ("ip_address",)


class IpAddressCreate(BaseModel):
    """``POST /api/ip-addresses`` 请求体（请求 schema 封闭）。

    **不给任何字段加约束**：必填性以外的长度 / trim / 空串 / 空白 / 格式 / CIDR /
    归一化一律不实现（NQ-1）。
    """

    model_config = ConfigDict(extra="forbid")

    network_interface_id: int
    ip_address: str


class IpAddressUpdate(BaseModel):
    """``PATCH /api/ip-addresses/{ip_address_id}`` 请求体（部分更新）。

    ``extra="forbid"``：``network_interface_id`` / ``id`` / ``created_at`` /
    ``deleted_at`` / ``cluster_id`` / ``status`` 或任何未识别字段 → ``400``。
    """

    model_config = ConfigDict(extra="forbid")

    ip_address: str | None = None


class IpAddressRead(BaseModel):
    """单个 IPAddress 的对外表示（契约 §2 的封闭字段集合，恰 5 字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    network_interface_id: int
    ip_address: str
    created_at: datetime
    updated_at: datetime
