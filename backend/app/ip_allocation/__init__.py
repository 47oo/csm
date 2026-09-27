"""F006 IPv4 分配模块。"""

from __future__ import annotations

from ..network_segments.usage import register_provider
from .service import IpAllocationUsageProvider

# 注册 F005 ``SegmentUsage`` 的真实实现（只读 ``ip_addresses``）。
register_provider(IpAllocationUsageProvider())

__all__ = ["IpAllocationUsageProvider"]