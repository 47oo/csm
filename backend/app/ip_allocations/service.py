"""F021 分配业务行为：自动分配 / 手动分配。

不负责 HTTP 展示文案；不写入 ``deleted_at``（删除委托系统内唯一软删服务）；不写
``cluster_id``（仍唯一经 ``app/ip_addresses/service.py::create_ip_address``）。

比较边界（R-IP-007，**不得混用**）：

- **范围归属 / 合法性**按 IPv4 **数值**（复用 :mod:`app.ip_address_ranges.ipv4`）；
- **占用 / 唯一性**按 ``ip_address`` **字面**（不 trim / 不归一化 / 不折叠）。

自动分配（契约 F023 §6.1）：``derive_cluster_id``（父 NIC 行 ``FOR SHARE``）→ 读取所选
``ip_address_range_id`` 指向的**活跃**范围段并校验其 ``cluster_id`` 恰为目标 Cluster →
读取活跃占用字面 → **仅在该所选单个范围段**内取数值最小未占用 IPv4（**不跳过**网络 /
广播 / 网关 / 端点）→ 经 ``create_ip_address`` 写入。范围段不存在 / 已逻辑删除（``404``）
或跨 Cluster（``409``）→ ``details[].code = "IP_ADDRESS_RANGE_UNAVAILABLE"``；所选范围段
耗尽 → **先于任何写入**抛 ``409 CONFLICT + details[].code = "NO_AVAILABLE_IP"``，**不回退**
到其它范围段、不跨 Cluster 取址。

手动分配（契约 §6.2）：``parse_ipv4``（非法 → ``400``）→ ``derive_cluster_id``（未命中
→ ``404``）→ 数值范围归属（否则 ``409 OUT_OF_RANGE``）→ 规范化后字面占用判定（否则
``409 DUPLICATE``）→ 经 ``create_ip_address`` 写入规范化 dotted-quad。

并发不新增锁 / 不自动重试：``ux_ip_addresses_cluster_ip_active``（R-IP-001）为最终
权威，``23505`` 经既有通用映射 → ``409 DUPLICATE``（永不 5xx）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.ip_address_ranges.ipv4 import format_ipv4, parse_ipv4
from app.ip_address_ranges.repository import IpAddressRangeRepository
from app.ip_addresses.derivation import derive_cluster_id
from app.ip_addresses.schemas import IpAddressCreate
from app.ip_addresses.service import create_ip_address
from app.ip_allocations.repository import IpAllocationRepository
from app.ip_allocations.schemas import (
    IpAddressAutoAllocateRequest,
    IpAddressManualAllocateRequest,
)
from app.models.ip_address import IpAddress

#: 契约 §4.1：所选范围段耗尽的稳定判别值（F023：仅限所选单个范围段，不回退）。
_NO_AVAILABLE_IP_DETAIL = {
    "row": None,
    "field": None,
    "code": "NO_AVAILABLE_IP",
    "message": "所选活跃 IP 地址范围段内已无未被占用的 IPv4",
}

#: 契约 §4.6：所选范围段不可用（不存在 / 已逻辑删除 / 跨 Cluster）的稳定判别值。
_RANGE_UNAVAILABLE_DETAIL = {
    "row": None,
    "field": "ip_address_range_id",
    "code": "IP_ADDRESS_RANGE_UNAVAILABLE",
    "message": "所选范围段不存在、已逻辑删除，或不属于目标 Cluster",
}

#: 契约 §4.2：手动分配范围外的稳定判别值。
_OUT_OF_RANGE_DETAIL = {
    "row": None,
    "field": "ip_address",
    "code": "OUT_OF_RANGE",
    "message": "该地址不落在目标 Cluster 的任何活跃 IP 地址范围段内",
}

#: 契约 §4.3：地址已占用 / 并发落败的稳定判别值（沿用 F005，不新增）。
_DUPLICATE_DETAIL = {
    "row": None,
    "field": "ip_address",
    "code": "DUPLICATE",
    "message": "同一 Cluster 内已存在活跃的相同 IP 地址",
}


def select_first_free(
    ranges: list[tuple[int, int]], occupied: set[str]
) -> int | None:
    """在给定范围段内取数值最小、字面未占用的 IPv4。

    纯函数（不依赖 DB / HTTP）。F023 自动分配**仅传入所选单个范围段**（以
    ``[(range.start_ip, range.end_ip)]`` 调用），故扫描首个可用值即所选范围段内
    数值最小未占用地址。**不跳过**网络 / 广播 / 网关 / 范围端点。全部占用 → ``None``。
    """
    for start, end in ranges:
        for value in range(start, end + 1):
            if format_ipv4(value) not in occupied:
                return value
    return None


def allocate_ip_auto(session: Session, payload: IpAddressAutoAllocateRequest) -> IpAddress:
    # 1) 推导（同时对父 NIC 行取 FOR SHARE 并确认父 NIC / 宿主活跃）；未命中 → 404。
    cluster_id = derive_cluster_id(session, payload.network_interface_id)

    # 2) 读取所选范围段（活跃）；不存在 / 已逻辑删除 → 404，跨 Cluster → 409。
    #    复用既有 IpAddressRangeRepository.get_active（活跃谓词单一实现，不自造第二份）。
    ip_address_range = IpAddressRangeRepository(session).get_active(
        payload.ip_address_range_id
    )
    if ip_address_range is None:
        raise NotFoundError(
            "所选地址范围段不可用", details=[dict(_RANGE_UNAVAILABLE_DETAIL)]
        )
    if ip_address_range.cluster_id != cluster_id:
        raise ConflictError(
            "所选地址范围段不可用于该集群",
            details=[dict(_RANGE_UNAVAILABLE_DETAIL)],
        )

    repository = IpAllocationRepository(session)
    # 3) 读目标 Cluster 活跃占用字面（无锁快照）。
    occupied = repository.active_ip_literals(cluster_id)

    # 4) 仅在所选该单个范围段内取数值最小未占用 IPv4；耗尽 → 409，**在任何写入之前**。
    candidate = select_first_free(
        [(ip_address_range.start_ip, ip_address_range.end_ip)], occupied
    )
    if candidate is None:
        raise ConflictError(
            "所选地址范围段已无可用 IP", details=[dict(_NO_AVAILABLE_IP_DETAIL)]
        )

    # 5) 经 F005 单一受控写入路径落库（partial unique 为最终权威）。
    return create_ip_address(
        session,
        IpAddressCreate(
            network_interface_id=payload.network_interface_id,
            ip_address=format_ipv4(candidate),
        ),
    )


def allocate_ip_manual(session: Session, payload: IpAddressManualAllocateRequest) -> IpAddress:
    # 1) 严格解析 IPv4；非法 → 400（先于 NIC 校验，稳定顺序）。
    try:
        value = parse_ipv4(payload.ip_address)
    except ValueError as exc:
        raise ValidationError(
            "IPv4 地址非法",
            details=[{"field": "ip_address", "code": "INVALID", "message": str(exc)}],
        ) from exc

    # 2) 推导（同自动）；未命中 → 404。
    cluster_id = derive_cluster_id(session, payload.network_interface_id)

    repository = IpAllocationRepository(session)
    # 3) 范围归属按数值；不落在任何活跃范围内 → 409 OUT_OF_RANGE。
    ranges = repository.list_active_ranges(cluster_id)
    if not any(start <= value <= end for start, end in ranges):
        raise ConflictError("地址不在任何活跃范围内", details=[dict(_OUT_OF_RANGE_DETAIL)])

    # 4) 占用判定按规范化后字面；命中 → 409 DUPLICATE。
    canonical = format_ipv4(value)
    if canonical in repository.active_ip_literals(cluster_id):
        raise ConflictError("IP 地址已存在", details=[dict(_DUPLICATE_DETAIL)])

    # 5) 经 F005 单一受控写入路径落库（写入规范化 dotted-quad）。
    return create_ip_address(
        session,
        IpAddressCreate(
            network_interface_id=payload.network_interface_id,
            ip_address=canonical,
        ),
    )