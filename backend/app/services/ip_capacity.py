"""IP capacity (§20 / DR-130, F010 DB-D125).

Implements the §20 capacity formula shared by the capacity data endpoint and
(later) F013. The allocatable set is the Network's base usable addresses (§11.1)
minus its gateway, minus its undeleted RESERVED pool ranges, minus the §11.1
disabled ranges — excluded items are de-duplicated by set subtraction. Occupancy
counts undeleted IP records in the Network (bound or not, in-pool or out).

All arithmetic is done on integer address intervals (no ``generate_series``), so
large CIDRs (/0-/8) are handled in O(number of exclusions). ``remaining`` is
returned as the direct difference and is **not** clamped to zero: a stored IP
that now falls in a newly RESERVED/gateway/disabled range can make it negative
(Contract §6.9).
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import INET

from app.models.ip_address import IPAddress
from app.models.ip_pool import IPPool
from app.models.network import Network
from app.services import normalization

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

Interval = tuple[int, int]

_DISABLED_INTERVALS: list[Interval] = [
    (int(net.network_address), int(net.broadcast_address))
    for net in normalization.DISABLED_GATEWAY_NETWORKS
]


def _int(address: str) -> int:
    return int(ipaddress.IPv4Address(address))


def base_usable_intervals(cidr: str) -> list[Interval]:
    """Return the §11.1 base usable address interval(s) for ``cidr``.

    /0-/30 exclude the network/broadcast addresses; /31 has both addresses
    usable; /32 has its single address usable. Always returns one contiguous
    interval.
    """
    net = ipaddress.ip_network(cidr, strict=False)
    first = int(net.network_address)
    last = int(net.broadcast_address)
    if net.prefixlen <= 30:
        return [(first + 1, last - 1)]
    if net.prefixlen == 31:
        return [(first, last)]
    return [(first, first)]


def subtract_intervals(intervals: list[Interval], exclusions: list[Interval]) -> list[Interval]:
    """Return ``intervals`` with every ``exclusions`` range removed.

    Both inputs are closed integer intervals; output is sorted and disjoint.
    Exclusions outside an interval are ignored, so callers may pass whole
    ranges (e.g. the §11.1 disabled networks) without pre-clipping.
    """
    result: list[Interval] = []
    for lo, hi in intervals:
        segments: list[Interval] = [(lo, hi)]
        for ex_lo, ex_hi in exclusions:
            next_segments: list[Interval] = []
            for seg_lo, seg_hi in segments:
                if ex_hi < seg_lo or ex_lo > seg_hi:
                    next_segments.append((seg_lo, seg_hi))
                    continue
                if ex_lo > seg_lo:
                    next_segments.append((seg_lo, ex_lo - 1))
                if ex_hi < seg_hi:
                    next_segments.append((ex_hi + 1, seg_hi))
            segments = next_segments
            if not segments:
                break
        result.extend(segments)
    result.sort()
    return result


def _reserved_pool_intervals(db: "Session", network_id: uuid.UUID) -> list[Interval]:
    rows = db.execute(
        select(IPPool.start_address, IPPool.end_address).where(
            IPPool.network_id == network_id,
            IPPool.allocation_mode == "RESERVED",
            IPPool.deleted_at.is_(None),
        )
    ).all()
    return [(_int(str(row[0])), _int(str(row[1]))) for row in rows]


def network_allocatable_intervals(
    db: "Session", network: Network
) -> list[Interval]:
    """Return the Network's allocatable integer intervals (§11.1/§12/§20)."""
    base = base_usable_intervals(str(network.cidr))
    exclusions: list[Interval] = list(_DISABLED_INTERVALS)
    if network.gateway is not None:
        gateway_int = _int(str(network.gateway))
        exclusions.append((gateway_int, gateway_int))
    exclusions.extend(_reserved_pool_intervals(db, network.id))
    return subtract_intervals(base, exclusions)


def interval_contains(intervals: list[Interval], address: str) -> bool:
    """Whether ``address`` (IPv4 host) falls in any allocatable interval."""
    value = _int(address)
    return any(lo <= value <= hi for lo, hi in intervals)


def interval_length(intervals: list[Interval]) -> int:
    return sum(hi - lo + 1 for lo, hi in intervals)


def _count_ips(db: "Session", network_id: uuid.UUID, lo: int | None = None, hi: int | None = None) -> int:
    filters = [
        IPAddress.network_id == network_id,
        IPAddress.deleted_at.is_(None),
    ]
    if lo is not None and hi is not None:
        start = str(ipaddress.IPv4Address(lo))
        end = str(ipaddress.IPv4Address(hi))
        filters.append(IPAddress.address >= cast(start, INET))
        filters.append(IPAddress.address <= cast(end, INET))
    return int(
        db.execute(select(func.count()).select_from(IPAddress).where(*filters)).scalar_one()
    )


def network_capacity(db: "Session", network: Network) -> dict[str, Any]:
    """Compute the §20 Network capacity block for ``network``."""
    intervals = network_allocatable_intervals(db, network)
    total = interval_length(intervals)
    occupied = _count_ips(db, network.id)
    return {
        "allocatable_total": total,
        "occupied": occupied,
        "remaining": total - occupied,
    }


def auto_pools_capacity(db: "Session", network: Network) -> list[dict[str, Any]]:
    """Compute the §20 AUTO-pool capacity blocks for ``network``.

    ``allocatable_total`` is ``|pool range ∩ allocatable set|`` and
    ``occupied`` counts undeleted IPs whose current address is in that
    intersection (by address, not by allocation source).
    """
    intervals = network_allocatable_intervals(db, network)
    pools = (
        db.execute(
            select(IPPool)
            .where(
                IPPool.network_id == network.id,
                IPPool.allocation_mode == "AUTO",
                IPPool.deleted_at.is_(None),
            )
            .order_by(IPPool.start_address.asc(), IPPool.id.asc())
        )
        .scalars()
        .all()
    )
    result: list[dict[str, Any]] = []
    for pool in pools:
        pool_lo = _int(str(pool.start_address))
        pool_hi = _int(str(pool.end_address))
        total = interval_length(
            intersect_with_range(intervals, pool_lo, pool_hi)
        )
        occupied = _count_ips(db, network.id, pool_lo, pool_hi)
        result.append(
            {
                "ip_pool": pool,
                "allocatable_total": total,
                "occupied": occupied,
                "remaining": total - occupied,
            }
        )
    return result


def intersect_with_range(
    intervals: list[Interval], lo: int, hi: int
) -> list[Interval]:
    """Return ``intervals`` clipped to the closed ``[lo, hi]`` range."""
    clipped: list[Interval] = []
    for seg_lo, seg_hi in intervals:
        start = max(lo, seg_lo)
        end = min(hi, seg_hi)
        if start <= end:
            clipped.append((start, end))
    return clipped