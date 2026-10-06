"""F005 网段服务层：查询、重叠/计数计算、序列化与 DB 冲突映射。

业务端点位于 ``router``；本模块只承载可复用的持久化与计算辅助，便于 F006 扩展。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..errors import problem
from ..models import Cluster, NetworkSegment, SegmentReservedAddress
from .addressing import (
    SegmentAddressing,
    auto_assignable_count,
    cidr_range,
    ipv4_to_int,
    ranges_overlap,
)
from .usage import SegmentUsage

__all__ = ["SegmentUsage"]


def is_fk_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    state = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return state == "23503"


def constraint_name(exc: IntegrityError) -> str:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", "") or ""


def integrity_problem(exc: IntegrityError):
    """将网段写入的 DB 完整性冲突映射为 Contract 错误语义。"""
    name = constraint_name(exc)
    if "uq_network_segments_cluster_name" in name:
        return problem(409, "SEGMENT_NAME_TAKEN", "同集群已存在同名网段")
    if "uq_network_segments_cluster_cidr" in name:
        return problem(409, "SEGMENT_CIDR_TAKEN", "同集群已存在相同规范化 CIDR 的网段")
    if "fk_network_segments_cluster" in name:
        return problem(404, "CLUSTER_NOT_FOUND", "所属集群不存在")
    return problem(
        422,
        "VALIDATION_ERROR",
        "字段校验失败",
        errors=[
            {
                "field": "request",
                "code": "VALIDATION_ERROR",
                "message": "数据不满足数据库约束",
            }
        ],
    )


def fk_delete_problem(exc: IntegrityError):
    """网段删除时的 23503 映射（按约束名区分引用方，预留 F002/F006）。"""
    name = constraint_name(exc)
    lowered = name.lower()
    if "reserved" in lowered:
        return problem(409, "SEGMENT_HAS_RESERVED_ADDRESSES", "仍存保留地址，禁止删除")
    if "interface" in lowered or "nic" in lowered:
        return problem(409, "SEGMENT_HAS_INTERFACES", "仍被网卡引用，禁止删除")
    if "alloc" in lowered or "assign" in lowered or "ip" in lowered:
        return problem(409, "SEGMENT_HAS_ALLOCATIONS", "仍有已分配 IP，禁止删除")
    # 未知引用方：保守返回通用关联冲突，不静默级联。
    return problem(409, "SEGMENT_HAS_RESERVED_ADDRESSES", "网段仍有关联资源，禁止删除")


def get_segment_or_404(
    db: Session, segment_id: int, *, for_update: bool = False
) -> NetworkSegment:
    """按 id 取网段，不存在返回 ``404 SEGMENT_NOT_FOUND``。

    ``for_update=True`` 时对目标行加 ``SELECT ... FOR UPDATE`` 行锁（架构 §6.3），
    与保留地址新增共享同一父行锁，串行化「改 CIDR」与「新增保留地址」的竞争。
    """
    if for_update:
        segment = db.execute(
            select(NetworkSegment)
            .where(NetworkSegment.id == segment_id)
            .with_for_update()
        ).scalar_one_or_none()
    else:
        segment = db.get(NetworkSegment, segment_id)
    if segment is None:
        raise problem(404, "SEGMENT_NOT_FOUND", "网段不存在")
    return segment


def reserved_addresses(db: Session, segment_id: int) -> list[SegmentReservedAddress]:
    rows = db.scalars(
        select(SegmentReservedAddress).where(
            SegmentReservedAddress.segment_id == segment_id
        )
    ).all()
    return sorted(rows, key=lambda r: ipv4_to_int(r.start_ip))


def find_overlaps(db: Session, segment: NetworkSegment) -> list[NetworkSegment]:
    """同集群其它仍存网段中，CIDR 地址区间相交者（仅提示，不阻断保存）。"""
    others = db.scalars(
        select(NetworkSegment).where(
            NetworkSegment.cluster_id == segment.cluster_id,
            NetworkSegment.id != segment.id,
        )
    ).all()
    target = cidr_range(segment.cidr)
    return [o for o in others if ranges_overlap(target, cidr_range(o.cidr))]


def _addressing(db: Session, segment: NetworkSegment) -> SegmentAddressing:
    rows = reserved_addresses(db, segment.id)
    return SegmentAddressing(
        cidr=segment.cidr,
        gateway=segment.gateway,
        reserved=tuple((r.start_ip, r.end_ip) for r in rows),
    )


def _reserved_out(row: SegmentReservedAddress) -> dict[str, Any]:
    return {
        "id": row.id,
        "start_ip": row.start_ip,
        "end_ip": row.end_ip,
        "is_range": row.start_ip != row.end_ip,
        "created_at": row.created_at,
    }


def _auto_assignable(
    db: Session,
    segment: NetworkSegment,
    overlaps: list[NetworkSegment],
) -> int:
    base = auto_assignable_count(
        segment.auto_alloc_start,
        segment.auto_alloc_end,
        _addressing(db, segment),
        [_addressing(db, o) for o in overlaps],
    )
    if base == 0 or segment.auto_alloc_start is None or segment.auto_alloc_end is None:
        return base
    # F006 接入：同集群已分配 IP 也扣除（快照，不预占；架构 §5 BQ-R / 场景 65）。
    start = ipv4_to_int(segment.auto_alloc_start)
    end = ipv4_to_int(segment.auto_alloc_end)
    allocated = SegmentUsage.allocated_ip_nums(db, segment.cluster_id)
    extra = sum(1 for num in allocated if start <= num <= end)
    return max(base - extra, 0)


def _base_item(
    db: Session,
    segment: NetworkSegment,
    overlaps: list[NetworkSegment],
) -> dict[str, Any]:
    cluster = db.get(Cluster, segment.cluster_id)
    rows = reserved_addresses(db, segment.id)
    return {
        "id": segment.id,
        "cluster_id": segment.cluster_id,
        "cluster_code": cluster.code if cluster is not None else "",
        "cluster_name": cluster.name if cluster is not None else "",
        "name": segment.name,
        "cidr": segment.cidr,
        "purpose": segment.purpose,
        "technology": segment.technology,
        "vlan": segment.vlan,
        "gateway": segment.gateway,
        "auto_alloc_start": segment.auto_alloc_start,
        "auto_alloc_end": segment.auto_alloc_end,
        "auto_alloc_enabled": segment.auto_alloc_start is not None
        and segment.auto_alloc_end is not None,
        "reserved_address_count": len(rows),
        "allocated_count": SegmentUsage.allocated_count(db, segment.id),
        "auto_assignable_count": _auto_assignable(db, segment, overlaps),
        "has_overlap": bool(overlaps),
        "created_at": segment.created_at,
        "updated_at": segment.updated_at,
    }


def list_item(db: Session, segment: NetworkSegment) -> dict[str, Any]:
    return _base_item(db, segment, find_overlaps(db, segment))


def detail(db: Session, segment: NetworkSegment) -> dict[str, Any]:
    overlaps = find_overlaps(db, segment)
    payload = _base_item(db, segment, overlaps)
    payload["reserved_addresses"] = [
        _reserved_out(r) for r in reserved_addresses(db, segment.id)
    ]
    payload["overlaps"] = [
        {"segment_id": o.id, "name": o.name, "cidr": o.cidr} for o in overlaps
    ]
    payload["version"] = segment.version
    return payload