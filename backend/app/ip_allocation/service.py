"""F006 IP 分配服务层：排除集、选址、管理 IP 解析、冲突映射与只读查询。

业务编排（资源表单事务内的 IP 应用）在 ``app.resources``；本模块提供可复用
的持久化/计算辅助，并被 F005 ``SegmentUsage`` 扩展点消费。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..errors import problem
from ..models import IpAddress, NetworkInterface, NetworkSegment, Resource
from ..network_segments.addressing import (
    int_to_ipv4,
    ipv4_to_int,
    network_broadcast,
)
from ..network_segments.service import find_overlaps, reserved_addresses
from .addressing import AddressExclusions, allocated_nums, first_available, validate_manual

MANUAL = "manual"
AUTO = "auto"


@dataclass
class PlannedIp:
    address: str
    mode: str


def _ip_err(
    field: str, code: str, message: str, *, address: str | None = None
) -> dict[str, Any]:
    item: dict[str, Any] = {"field": field, "code": code, "message": message}
    if address is not None:
        item["address"] = address
    return item


def allocate_specs(
    db: Session,
    *,
    segment: NetworkSegment,
    specs: list[tuple[int, str | None, str | None]],
    in_use: set[int],
    field_prefix: str,
) -> tuple[list[PlannedIp], list[dict[str, Any]], list[dict[str, Any]]]:
    """对单个网卡的 IP 新增项做选址与校验。

    ``specs`` 为 ``(ip_index, mode, address)``；``in_use`` 为可变集合（已扣除本次
    将删除的地址），成功后把选中地址并入，以拦截同一请求内的重复分配。
    返回 ``(planned, validation_errors, conflict_errors)``；validation 为 422 族，
    conflict 为 409 族（``IP_ALREADY_IN_USE``/``NO_AVAILABLE_ADDRESS``）。
    """
    exclusions = exclusions_for(db, segment)
    planned: list[PlannedIp] = []
    validation: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for ip_index, mode, address in specs:
        field = f"{field_prefix}.ips[{ip_index}]"
        if mode == MANUAL:
            candidate = address.strip() if isinstance(address, str) else ""
            if candidate == "":
                validation.append(
                    _ip_err(
                        f"{field}.address",
                        "IP_INVALID",
                        "手动分配须提供合法 IPv4 地址",
                    )
                )
                continue
            code = validate_manual(segment.cidr, candidate, exclusions, in_use)
            if code is None:
                planned.append(PlannedIp(candidate, MANUAL))
                in_use.add(ipv4_to_int(candidate))
            elif code == "IP_ALREADY_IN_USE":
                conflicts.append(
                    _ip_err(
                        f"{field}.address",
                        code,
                        f"{candidate} 已被本集群使用",
                        address=candidate,
                    )
                )
            else:
                validation.append(
                    _ip_err(f"{field}.address", code, _code_message(code, candidate))
                )
        elif mode == AUTO:
            if segment.auto_alloc_start is None or segment.auto_alloc_end is None:
                validation.append(
                    _ip_err(
                        field,
                        "AUTO_RANGE_NOT_ENABLED",
                        "网段未启用自动分配范围，只能手动分配",
                    )
                )
                continue
            start = ipv4_to_int(segment.auto_alloc_start)
            end = ipv4_to_int(segment.auto_alloc_end)
            excluded = exclusions.union() | in_use
            num = first_available(start, end, excluded)
            if num is None:
                conflicts.append(
                    _ip_err(field, "NO_AVAILABLE_ADDRESS", "自动分配范围内暂无可用地址")
                )
            else:
                planned.append(PlannedIp(int_to_ipv4(num), AUTO))
                in_use.add(num)
        else:
            validation.append(
                _ip_err(f"{field}.mode", "VALIDATION_ERROR", "mode 必须为 manual 或 auto")
            )
    return planned, validation, conflicts


def _code_message(code: str, address: str) -> str:
    return {
        "IP_OUT_OF_SEGMENT": f"{address} 不在网卡所选网段内",
        "IP_RESERVED": f"{address} 命中保留地址",
        "IP_GATEWAY": f"{address} 命中网段网关",
        "IP_NETWORK_ADDRESS": f"{address} 为网络地址",
        "IP_BROADCAST_ADDRESS": f"{address} 为广播地址",
        "IP_INVALID": "地址必须为合法 IPv4",
    }.get(code, "字段校验失败")


class IpAllocationUsageProvider:
    """F005 ``SegmentUsage`` 的真实实现（只读 ``ip_addresses``）。"""

    def allocated_count(self, db: Session, segment_id: int) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(IpAddress)
                .where(IpAddress.segment_id == segment_id)
            )
            or 0
        )

    def allocated_ip_nums(self, db: Session, cluster_id: int) -> set[int]:
        keys = db.scalars(
            select(IpAddress.ip_key).where(IpAddress.cluster_id == cluster_id)
        ).all()
        return allocated_nums(keys)


def exclusions_for(db: Session, segment: NetworkSegment) -> AddressExclusions:
    """§5.2 排除集：自身 + 仍存重叠网段的保留/网关/网络广播（按来源分类）。"""
    segments = [segment, *find_overlaps(db, segment)]
    reserved: set[int] = set()
    gateways: set[int] = set()
    networks: set[int] = set()
    broadcasts: set[int] = set()
    for item in segments:
        if item.gateway:
            gateways.add(ipv4_to_int(item.gateway))
        for row in reserved_addresses(db, item.id):
            reserved.update(
                range(ipv4_to_int(row.start_ip), ipv4_to_int(row.end_ip) + 1)
            )
        special = network_broadcast(item.cidr)
        if special is not None:
            networks.add(special[0])
            broadcasts.add(special[1])
    return AddressExclusions(
        reserved=frozenset(reserved),
        gateways=frozenset(gateways),
        networks=frozenset(networks),
        broadcasts=frozenset(broadcasts),
    )


def existing_ips_for_resource(db: Session, resource_id: int) -> list[IpAddress]:
    return list(
        db.scalars(
            select(IpAddress)
            .where(IpAddress.resource_id == resource_id)
            .order_by(IpAddress.id.asc())
        ).all()
    )


def interface_ips(db: Session, interface_id: int) -> list[IpAddress]:
    return list(
        db.scalars(
            select(IpAddress)
            .where(IpAddress.interface_id == interface_id)
            .order_by(IpAddress.id.asc())
        ).all()
    )


def sort_ips(rows: Iterable[IpAddress]) -> list[IpAddress]:
    return sorted(rows, key=lambda row: ipv4_to_int(row.ip))


def conflicting_ips(
    db: Session, cluster_id: int, addresses: set[str]
) -> list[dict[str, Any]]:
    """返回占用指定地址的现存 IP 归属，供 ``conflicts`` 扩展成员使用。"""
    if not addresses:
        return []
    rows = db.execute(
        select(IpAddress, NetworkInterface, Resource)
        .join(NetworkInterface, NetworkInterface.id == IpAddress.interface_id)
        .join(Resource, Resource.id == IpAddress.resource_id)
        .where(
            IpAddress.cluster_id == cluster_id,
            IpAddress.ip_key.in_(addresses),
        )
        .order_by(IpAddress.ip_key.asc())
    ).all()
    return [
        {
            "ip": ip.ip,
            "resource_id": ip.resource_id,
            "resource_name": resource.name,
            "interface_id": ip.interface_id,
            "interface_name": interface.name,
        }
        for ip, interface, resource in rows
    ]


def constraint_name(exc: IntegrityError) -> str:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", "") or ""


def ip_write_problem(
    exc: IntegrityError, *, automatic: bool = False, phase: str | None = None
):
    """IP 写入的 DB 完整性冲突 → Contract 错误语义（前置校验的兜底）。

    ``phase`` 区分同一约束在不同父行操作下的语义（删除网卡 vs 网卡改段）。
    """
    name = constraint_name(exc)
    if "uq_ip_addresses_cluster_ip" in name:
        if automatic:
            return problem(
                409,
                "NO_AVAILABLE_ADDRESS",
                "自动分配范围内暂无可用地址，不切换网段",
            )
        return problem(409, "IP_ALREADY_IN_USE", "该 IPv4 已被本集群占用")
    if name == "fk_ip_addresses_interface_segment" and phase == "interface_update":
        return problem(
            422,
            "INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE",
            "改网段前须释放该网卡旧 IP",
        )
    if "fk_ip_addresses_interface" in name:
        return problem(409, "INTERFACE_HAS_IPS", "网卡仍有 IP，禁止删除")
    if "fk_ip_addresses_segment" in name:
        return problem(409, "SEGMENT_HAS_ALLOCATIONS", "网段仍有已分配 IP，禁止删除")
    if "fk_resources_management_ip" in name:
        return problem(
            422,
            "MANAGEMENT_IP_REQUIRED",
            "删除管理 IP 或其网卡前须同次显式清空或重选管理 IP",
        )
    return None


def ip_write_conflict_problem(
    db: Session,
    exc: IntegrityError,
    *,
    cluster_id: int,
    candidate_addresses: set[str],
    automatic: bool = False,
    phase: str | None = None,
):
    """``ip_write_problem`` 的并发兜底扩展：``IP_ALREADY_IN_USE`` 附 ``conflicts``。

    前置可用性快照与写入之间被并发提交插入了同集群同地址时，唯一约束在写入
    阶段兜底触发（创建路径不在事务内延迟该约束）。此处在回滚后按本次计划地址
    反查现存占用行，补齐 Contract 要求的 ``conflicts`` 成员；其余错误语义不变。
    """
    prob = ip_write_problem(exc, automatic=automatic, phase=phase)
    if (
        prob is not None
        and prob.code == "IP_ALREADY_IN_USE"
        and candidate_addresses
    ):
        conflicts = conflicting_ips(db, cluster_id, candidate_addresses)
        if conflicts:
            prob.extra = {**prob.extra, "conflicts": conflicts}
    return prob


def allocated_ip_item(
    ip: IpAddress, interface: NetworkInterface, resource: Resource, is_management: bool
) -> dict[str, Any]:
    return {
        "ip_id": ip.id,
        "address": ip.ip,
        "resource_id": ip.resource_id,
        "resource_name": resource.name,
        "resource_type": resource.resource_type,
        "interface_id": ip.interface_id,
        "interface_name": interface.name,
        "is_management": is_management,
        "created_at": ip.created_at,
    }


def int_address(num: int) -> str:
    return int_to_ipv4(num)