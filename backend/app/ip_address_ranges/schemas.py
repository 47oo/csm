"""IPAddressRange 请求 / 响应 schema（``docs/api/f020-ip-address-range.md`` §2 / §3）。

- ``IpAddressRangeCreate``：字段集合**恰为** ``{cluster_id, start_ip, end_ip}``；
  ``extra="forbid"``（``name`` / ``description`` / ``status`` / ``deleted_at`` / CIDR /
  前缀长度 → ``400``）。
- ``IpAddressRangeUpdate``：可变字段封闭集合**恰为** ``{start_ip, end_ip}``；
  ``cluster_id`` 不可变；``extra="forbid"``。
- ``IpAddressRangeRead``：字段集合**恰为** ``{id, cluster_id, start_ip, end_ip,
  created_at, updated_at}``；**无** ``deleted_at`` / ``status`` / ``name``。ORM 内以
  ``BIGINT`` 数值存储，经 :meth:`IpAddressRangeRead.from_model` 渲染为 dotted-quad。

``start_ip`` / ``end_ip`` 不在 Pydantic 层做 IPv4 格式约束：合法性 / 规范化由领域
service 调用 :mod:`app.ip_address_ranges.ipv4` 裁决（保证错误细节为契约要求的
``details[].field``）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.ip_address_ranges.ipv4 import format_ipv4
from app.models.ip_address_range import IpAddressRange

#: PATCH 可变字段封闭集合（恰为 ``start_ip`` / ``end_ip``）。
MUTABLE_FIELDS: tuple[str, ...] = ("start_ip", "end_ip")


class IpAddressRangeCreate(BaseModel):
    """``POST /api/ip-address-ranges`` 请求体（请求 schema 封闭）。"""

    model_config = ConfigDict(extra="forbid")

    cluster_id: int
    start_ip: str
    end_ip: str


class IpAddressRangeUpdate(BaseModel):
    """``PATCH /api/ip-address-ranges/{ip_address_range_id}`` 请求体（部分更新）。

    ``extra="forbid"``：``cluster_id`` / ``id`` / ``created_at`` / ``deleted_at`` /
    ``status`` / ``name`` 或任何未识别字段 → ``400``。
    """

    model_config = ConfigDict(extra="forbid")

    start_ip: str | None = None
    end_ip: str | None = None


class IpAddressRangeRead(BaseModel):
    """单个 IPAddressRange 的对外表示（契约 §2 的封闭字段集合，恰 6 字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cluster_id: int
    start_ip: str
    end_ip: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, ip_address_range: IpAddressRange) -> IpAddressRangeRead:
        """从 ORM 行（数值列）构造对外表示（dotted-quad）。"""
        return cls(
            id=ip_address_range.id,
            cluster_id=ip_address_range.cluster_id,
            start_ip=format_ipv4(ip_address_range.start_ip),
            end_ip=format_ipv4(ip_address_range.end_ip),
            created_at=ip_address_range.created_at,
            updated_at=ip_address_range.updated_at,
        )


__all__ = [
    "MUTABLE_FIELDS",
    "IpAddressRangeCreate",
    "IpAddressRangeRead",
    "IpAddressRangeUpdate",
]
