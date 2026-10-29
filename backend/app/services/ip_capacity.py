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
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, cast, func, select
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


def _address_bound(value: Any) -> Any:
    """Render one range endpoint for the shared occupancy predicate.

    Literal host integers become ``inet`` literals (per-object counts); column
    references (``ip_pools.start_address`` / ``end_address``) are passed through
    unchanged so the batch statement compares ``inet`` columns directly (F039 §3).
    """
    if isinstance(value, int):
        return cast(str(ipaddress.IPv4Address(value)), INET)
    return value


def _undeleted_ips_in_range(
    network_id: Any = None, lo: Any = None, hi: Any = None
) -> list[Any]:
    """Predicates selecting undeleted IP records (optionally inside ``[lo, hi]``).

    Single definition of the §20 occupancy predicate, shared by the per-object
    counts used by the F010 endpoint and by the F039 batch statements, so both
    paths count the same rows (F039 §3 / AP-F039-4): undeleted only, no
    ``interface_id`` predicate (unbound IPs occupy), no ``status`` predicate
    (``INACTIVE`` rows are not zeroed), and by *current address* rather than by
    allocation source.
    """
    clauses: list[Any] = [IPAddress.deleted_at.is_(None)]
    if network_id is not None:
        clauses.append(IPAddress.network_id == network_id)
    if lo is not None and hi is not None:
        clauses.append(IPAddress.address >= _address_bound(lo))
        clauses.append(IPAddress.address <= _address_bound(hi))
    return clauses


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


def allocatable_intervals_for(
    network: Network, reserved: dict[uuid.UUID, list[Interval]]
) -> list[Interval]:
    """Pure §11.1/§12/§20 allocatable intervals for ``network`` (F039 §2).

    ``reserved`` maps ``network_id`` to that Network's undeleted RESERVED pool
    ranges; a missing key means "no RESERVED pools". The gateway exclusion is a
    single point, so a gateway inside a RESERVED range is de-duplicated by
    ``subtract_intervals`` (F039 A2).
    """
    base = base_usable_intervals(str(network.cidr))
    exclusions: list[Interval] = list(_DISABLED_INTERVALS)
    if network.gateway is not None:
        gateway_int = _int(str(network.gateway))
        exclusions.append((gateway_int, gateway_int))
    exclusions.extend(reserved.get(network.id, []))
    return subtract_intervals(base, exclusions)


def network_allocatable_intervals(
    db: "Session", network: Network
) -> list[Interval]:
    """Return the Network's allocatable integer intervals (§11.1/§12/§20)."""
    return allocatable_intervals_for(
        network, {network.id: _reserved_pool_intervals(db, network.id)}
    )


def interval_contains(intervals: list[Interval], address: str) -> bool:
    """Whether ``address`` (IPv4 host) falls in any allocatable interval."""
    value = _int(address)
    return any(lo <= value <= hi for lo, hi in intervals)


def interval_length(intervals: list[Interval]) -> int:
    return sum(hi - lo + 1 for lo, hi in intervals)


def _count_ips(
    db: "Session", network_id: uuid.UUID, lo: int | None = None, hi: int | None = None
) -> int:
    filters = _undeleted_ips_in_range(network_id, lo, hi)
    return int(
        db.execute(select(func.count()).select_from(IPAddress).where(*filters)).scalar_one()
    )


def _capacity_block(total: int, occupied: int) -> dict[str, Any]:
    """Single place computing §20 ``remaining`` (never clamped, Contract §6.9)."""
    return {
        "allocatable_total": total,
        "occupied": occupied,
        "remaining": total - occupied,
    }


@dataclass(frozen=True)
class CapacityContext:
    """Pre-fetched capacity inputs for a page of Networks (F039 §2).

    Loaded by :func:`load_capacity_context` with three fixed batch statements and
    read-only afterwards. It only carries *data*: ``reserved`` holds each
    Network's undeleted RESERVED ranges, ``auto_pools`` holds ``(pool,
    occupied)`` in ``(start_address, id)`` order, ``occupied`` holds the
    Network-wide undeleted IP count (missing key = 0). All §20 arithmetic stays
    in :func:`network_capacity` / :func:`auto_pools_capacity`.
    """

    reserved: dict[uuid.UUID, list[Interval]]
    auto_pools: dict[uuid.UUID, list[tuple[IPPool, int]]]
    occupied: dict[uuid.UUID, int]


def load_capacity_context(
    db: "Session", networks: Sequence[Network]
) -> CapacityContext:
    """Pre-fetch the capacity inputs of ``networks`` (3 statements, F039 §3).

    An empty page short-circuits with zero statements. The three batch
    statements reuse ``_undeleted_ips_in_range`` so they count exactly the rows
    the per-object path counts (A2). ``excl_ip_pools_network_id_address_range``
    keeps same-Network pool ranges disjoint, so each IP matches at most one AUTO
    pool and is never double counted.
    """
    reserved: dict[uuid.UUID, list[Interval]] = {}
    auto_pools: dict[uuid.UUID, list[tuple[IPPool, int]]] = {}
    occupied: dict[uuid.UUID, int] = {}
    network_ids = [network.id for network in networks]
    if not network_ids:
        return CapacityContext(
            reserved=reserved, auto_pools=auto_pools, occupied=occupied
        )

    # B1: RESERVED pool intervals per Network.
    reserved_rows = db.execute(
        select(IPPool.network_id, IPPool.start_address, IPPool.end_address).where(
            IPPool.network_id.in_(network_ids),
            IPPool.allocation_mode == "RESERVED",
            IPPool.deleted_at.is_(None),
        )
    ).all()
    for network_id, start_address, end_address in reserved_rows:
        reserved.setdefault(network_id, []).append(
            (_int(str(start_address)), _int(str(end_address)))
        )

    # B2: AUTO pools with their occupied count in one statement (LEFT JOIN keeps
    # zero-occupancy pools; row order follows the per-Network F010 order).
    pool_rows = db.execute(
        select(IPPool, func.count(IPAddress.id))
        .outerjoin(
            IPAddress,
            and_(
                *_undeleted_ips_in_range(
                    IPPool.network_id,
                    IPPool.start_address,
                    IPPool.end_address,
                )
            ),
        )
        .where(
            IPPool.network_id.in_(network_ids),
            IPPool.allocation_mode == "AUTO",
            IPPool.deleted_at.is_(None),
        )
        .group_by(IPPool.id)
        .order_by(
            IPPool.network_id.asc(),
            IPPool.start_address.asc(),
            IPPool.id.asc(),
        )
    ).all()
    for pool, pool_occupied in pool_rows:
        auto_pools.setdefault(pool.network_id, []).append((pool, int(pool_occupied)))

    # B3: Network-wide occupied count (missing Network = 0).
    occupied_rows = db.execute(
        select(IPAddress.network_id, func.count())
        .select_from(IPAddress)
        .where(
            IPAddress.network_id.in_(network_ids),
            *_undeleted_ips_in_range(),
        )
        .group_by(IPAddress.network_id)
    ).all()
    for network_id, network_occupied in occupied_rows:
        occupied[network_id] = int(network_occupied)

    return CapacityContext(
        reserved=reserved, auto_pools=auto_pools, occupied=occupied
    )


def _network_inputs(
    db: "Session", network: Network, context: CapacityContext | None
) -> tuple[list[Interval], int]:
    """Return ``(allocatable intervals, occupied)`` for ``network``.

    With a ``context`` this is statement-free; without one it loads the same
    data for a single Network, so the F010 endpoint keeps its signature and
    statement count (F039 §2).
    """
    if context is not None:
        return (
            allocatable_intervals_for(network, context.reserved),
            context.occupied.get(network.id, 0),
        )
    return network_allocatable_intervals(db, network), _count_ips(db, network.id)


def _auto_pool_inputs(
    db: "Session", network: Network, context: CapacityContext | None
) -> tuple[list[Interval], list[tuple[IPPool, int]]]:
    """Return ``(allocatable intervals, [(AUTO pool, occupied), ...])``."""
    if context is not None:
        return (
            allocatable_intervals_for(network, context.reserved),
            context.auto_pools.get(network.id, []),
        )
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
    entries = [
        (
            pool,
            _count_ips(
                db,
                network.id,
                _int(str(pool.start_address)),
                _int(str(pool.end_address)),
            ),
        )
        for pool in pools
    ]
    return intervals, entries


def network_capacity(
    db: "Session", network: Network, *, context: CapacityContext | None = None
) -> dict[str, Any]:
    """Compute the §20 Network capacity block for ``network``.

    ``context`` (F039) supplies pre-fetched inputs and costs zero statements;
    ``None`` keeps the single-Network behaviour used by the F010 endpoint.
    """
    intervals, occupied = _network_inputs(db, network, context)
    return _capacity_block(interval_length(intervals), occupied)


def auto_pools_capacity(
    db: "Session", network: Network, *, context: CapacityContext | None = None
) -> list[dict[str, Any]]:
    """Compute the §20 AUTO-pool capacity blocks for ``network``.

    ``allocatable_total`` is ``|pool range ∩ allocatable set|`` and
    ``occupied`` counts undeleted IPs whose current address is in that
    intersection (by address, not by allocation source).
    """
    intervals, entries = _auto_pool_inputs(db, network, context)
    result: list[dict[str, Any]] = []
    for pool, occupied in entries:
        total = interval_length(
            intersect_with_range(
                intervals,
                _int(str(pool.start_address)),
                _int(str(pool.end_address)),
            )
        )
        result.append({"ip_pool": pool, **_capacity_block(total, occupied)})
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