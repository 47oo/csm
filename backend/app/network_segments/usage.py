"""F005 计数扩展点（架构 §3.4 / §7.2），F006 以真实 IP 查询接入。

依赖方向：``network_segments`` 不反向依赖 ``ip_allocation``；F006 通过
``register_provider`` 注入 provider。未注册时保持 F005 阶段语义（计数为 0）。
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session


class SegmentUsageProvider(Protocol):
    def allocated_count(self, db: Session, segment_id: int) -> int: ...

    def allocated_ip_nums(self, db: Session, cluster_id: int) -> set[int]: ...


_provider: SegmentUsageProvider | None = None


def register_provider(provider: SegmentUsageProvider) -> None:
    global _provider
    _provider = provider


class SegmentUsage:
    """F005 计数扩展点。"""

    @staticmethod
    def allocated_count(db: Session, segment_id: int) -> int:
        if _provider is None:
            return 0
        return _provider.allocated_count(db, segment_id)

    @staticmethod
    def allocated_ip_nums(db: Session, cluster_id: int) -> set[int]:
        if _provider is None:
            return set()
        return _provider.allocated_ip_nums(db, cluster_id)