"""F005 网段地址运算纯函数（架构 §2.1 / §5.2 / §7.1）。

本模块不访问数据库、不做业务判断，只完成 §5 口径的地址集合运算，供 F005 与
F006 复用。地址统一为点分十进制 IPv4 字符串。
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Sequence


class CidrError(ValueError):
    """CIDR 规范化失败，``code`` 为 Contract 错误码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SegmentAddressing:
    """参与排除集计算的网段地址视图（与 ORM 解耦）。"""

    cidr: str
    gateway: str | None = None
    #: 保留地址区间，元素为 (start_ip, end_ip)。
    reserved: tuple[tuple[str, str], ...] = ()


def normalize_cidr(raw: str) -> str:
    """将 IPv4 CIDR 规范化为网络地址字符串；IPv6/非法抛 ``CidrError``。"""
    try:
        network = ipaddress.ip_network(raw, strict=False)
    except (ValueError, TypeError):
        raise CidrError("CIDR_INVALID", "CIDR 非法") from None
    if network.version != 4:
        raise CidrError("CIDR_NOT_IPV4", "仅支持 IPv4 CIDR")
    return str(network)


def is_ipv4(raw: str) -> bool:
    """判断字符串是否为合法、规范的 IPv4 地址。"""
    if not isinstance(raw, str):
        return False
    try:
        return ipaddress.ip_address(raw).version == 4
    except ValueError:
        return False


def ipv4_to_int(ip: str) -> int:
    return int(ipaddress.IPv4Address(ip))


def int_to_ipv4(num: int) -> str:
    return str(ipaddress.IPv4Address(num))


def cidr_range(cidr: str) -> tuple[int, int]:
    """返回 CIDR 的 ``(network, broadcast)`` 整数区间。"""
    network = ipaddress.ip_network(cidr, strict=False)
    return int(network.network_address), int(network.broadcast_address)


def ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def contains(cidr: str, ip: str) -> bool:
    """判断 ``ip`` 是否落在 ``cidr`` 内；非法地址返回 False。"""
    try:
        addr = ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return False
    if addr.version != 4:
        return False
    return addr in ipaddress.ip_network(cidr, strict=False)


def _network_broadcast(cidr: str) -> tuple[int, int] | None:
    return network_broadcast(cidr)


def network_broadcast(cidr: str) -> tuple[int, int] | None:
    """前缀 ``≤ 30`` 网段的 ``(network, broadcast)`` 整数；``/31``、``/32`` 返回 None。"""
    network = ipaddress.ip_network(cidr, strict=False)
    if network.prefixlen > 30:
        # /31 点到点、/32 单主机：不产生网络/广播排除（架构 §5.2 第 4 条）。
        return None
    return int(network.network_address), int(network.broadcast_address)


def excluded_nums(
    segment: SegmentAddressing,
    overlapping_segments: Sequence[SegmentAddressing],
) -> set[int]:
    """§5.2 分配排除集（不含已分配 IP；F005 已分配集为空）。

    排除：所有传入网段（自身 + 仍存重叠网段）的网关、保留地址区间，以及前缀
    ``≤ 30`` 网段的网络/广播地址。已真实删除网段不在入参中，其历史不参与排除。
    """
    result: set[int] = set()
    for item in (segment, *overlapping_segments):
        if item.gateway:
            result.add(ipv4_to_int(item.gateway))
        for start, end in item.reserved:
            result.update(range(ipv4_to_int(start), ipv4_to_int(end) + 1))
        special = _network_broadcast(item.cidr)
        if special is not None:
            result.add(special[0])
            result.add(special[1])
    return result


def auto_assignable_count(
    auto_start: str | None,
    auto_end: str | None,
    segment: SegmentAddressing,
    overlapping_segments: Sequence[SegmentAddressing],
) -> int:
    """§7.1 可自动分配数量快照；未启用自动分配范围时为 0。"""
    if auto_start is None or auto_end is None:
        return 0
    start = ipv4_to_int(auto_start)
    end = ipv4_to_int(auto_end)
    if end < start:
        return 0
    total = end - start + 1
    blocked = sum(
        1
        for num in excluded_nums(segment, overlapping_segments)
        if start <= num <= end
    )
    return max(total - blocked, 0)