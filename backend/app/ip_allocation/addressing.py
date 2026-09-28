"""F006 IP 选址与排除集纯函数（架构 §4/§5）。

不访问数据库：由调用方查询后传入集合。复用 F005 ``network_segments.addressing``
的地址运算；本模块只补充 F006 特有的集合运算与校验口径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..network_segments.addressing import (
    SegmentAddressing,
    cidr_range,
    contains,
    excluded_nums,
    int_to_ipv4,
    ipv4_to_int,
    is_ipv4,
    network_broadcast,
    ranges_overlap,
)

__all__ = [
    "SegmentAddressing",
    "cidr_range",
    "contains",
    "excluded_nums",
    "int_to_ipv4",
    "ipv4_to_int",
    "is_ipv4",
    "network_broadcast",
    "ranges_overlap",
    "AddressExclusions",
    "allocated_nums",
    "first_available",
    "validate_manual",
]


@dataclass(frozen=True)
class AddressExclusions:
    """按来源分类的排除集合（整数地址），用于区分 §4.3 错误码。"""

    reserved: frozenset[int] = field(default_factory=frozenset)
    gateways: frozenset[int] = field(default_factory=frozenset)
    networks: frozenset[int] = field(default_factory=frozenset)
    broadcasts: frozenset[int] = field(default_factory=frozenset)

    def union(self) -> set[int]:
        return set(self.reserved) | set(self.gateways) | set(self.networks) | set(
            self.broadcasts
        )


def allocated_nums(ip_keys: Iterable[str]) -> set[int]:
    """将 ``ip_key`` 字符串集合转换为整数地址集合（调用方负责查询）。"""
    return {ipv4_to_int(key) for key in ip_keys if key}


def first_available(start: int, end: int, excluded: set[int]) -> int | None:
    """在 ``[start, end]`` 内按数值从小到大返回第一个不在 ``excluded`` 的地址。"""
    if end < start:
        return None
    num = start
    while num <= end:
        if num not in excluded:
            return num
        num += 1
    return None


def validate_manual(
    cidr: str,
    address: str,
    exclusions: AddressExclusions,
    in_use: set[int],
) -> str | None:
    """校验手动地址；返回 Contract 错误码，合法返回 ``None``。

    ``in_use`` 已扣除本次请求将删除的地址；调用方在每次成功后把新地址并入。
    """
    if not is_ipv4(address):
        return "IP_INVALID"
    if not contains(cidr, address):
        return "IP_OUT_OF_SEGMENT"
    num = ipv4_to_int(address)
    if num in exclusions.gateways:
        return "IP_GATEWAY"
    if num in exclusions.reserved:
        return "IP_RESERVED"
    if num in exclusions.networks:
        return "IP_NETWORK_ADDRESS"
    if num in exclusions.broadcasts:
        return "IP_BROADCAST_ADDRESS"
    if num in in_use:
        return "IP_ALREADY_IN_USE"
    return None