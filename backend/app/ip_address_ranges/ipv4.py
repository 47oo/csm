"""IPv4 解析 / 规范化纯函数（F020 的单一实现，无 DB / HTTP 依赖）。

- :func:`parse_ipv4`：严格解析 dotted-quad IPv4 为无符号 32 位整数。
  恰好 4 个以 ``.`` 分隔的十进制段，每段 1~3 位数字、值 ``0..255``；**允许前导零**
  （``010`` → ``10``）；**拒绝**前缀长度（``/n``）、IPv6、空白、空串、非数字字符。
  ``ipaddress.IPv4Address`` 会拒绝前导零（Fix 3.9.5+），与 R-IP-004 的规范化承诺
  冲突，故本模块**不依赖**标准库 ``ipaddress``。
- :func:`format_ipv4`：把无符号 32 位整数渲染为 canonical dotted-quad。
- :func:`extract_ipv4_for_guard`：删除守卫专用只读解析——取字面值中**第一个 ``/``
  之前**的部分严格解析为 IPv4；解析失败返回 ``None``（跳过，不阻断、不 500）。
  该函数**不构成**对 ``ip_addresses.ip_address`` 的写入约束（R-IP-004 显式边界）。
"""

from __future__ import annotations

_ASCII_DIGITS = "0123456789"
_IPV4_MAX = 4294967295


def parse_ipv4(value: str) -> int:
    """严格解析 dotted-quad IPv4 为 ``0..4294967295`` 的整数；非法 → ``ValueError``。"""
    if not isinstance(value, str):
        raise ValueError("IPv4 必须是字符串")

    parts = value.split(".")
    if len(parts) != 4:
        raise ValueError("IPv4 必须恰好包含 4 段")

    result = 0
    for part in parts:
        if not 1 <= len(part) <= 3:
            raise ValueError("IPv4 每段必须为 1~3 位数字")
        if any(character not in _ASCII_DIGITS for character in part):
            raise ValueError("IPv4 段必须为十进制数字")
        octet = int(part)
        if octet > 255:
            raise ValueError("IPv4 段必须处于 0..255")
        result = (result << 8) | octet
    return result


def format_ipv4(value: int) -> str:
    """把 ``0..4294967295`` 的整数渲染为 canonical dotted-quad。"""
    if not 0 <= value <= _IPV4_MAX:
        raise ValueError("IPv4 数值必须处于 0..4294967295")
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def extract_ipv4_for_guard(literal: str) -> int | None:
    """取字面值中第一个 ``/`` 之前的地址部分并严格解析；失败 → ``None``。

    ``ip_addresses.ip_address`` 是自由文本（F005 立场不变）：无法解析为 IPv4 的
    字面值不参与删除守卫判定（不阻断删除、不得 500）。
    """
    if not isinstance(literal, str):
        return None
    address_part = literal.split("/", 1)[0]
    try:
        return parse_ipv4(address_part)
    except ValueError:
        return None
