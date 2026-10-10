"""IP occupancy provider registry (DR-109/DR-110, F010 DR-138).

The "an address in the changed range is already allocated" rule (§12.1) is
delegated to a small provider registry. F009 shipped :class:`NullIpOccupancyProvider`
(empty set); F010 registers :class:`IpAddressOccupancyProvider`, backed by the
``ip_addresses`` table, so the RESERVED-pool / Network-gateway checks are
end-to-end reachable. The Service layer calls :func:`check_occupancy` while
holding ``_lock_network`` (``networks`` row ``FOR UPDATE``) so a check serialises
with F010 allocation (which takes the same lock).

A provider returns ``{"total": int, "items": [...]}`` where ``total`` is the
number of undeleted IPs in the (closed) ``[start, end]`` range and ``items`` is
a preview of at most ``limit`` conflict descriptors::

    {"object_type": "ip_address", "object_id": str, "address": str,
     "bound": bool, "interface_id": str | None, "resource_id": str | None,
     "resource_hostname": str | None}

The caller maps a non-zero ``total`` to a 409 ``address_in_use`` conflict. The
registry holds a list of providers so later Features can append without
rewiring call sites.
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import INET

from app.models.interface import Interface
from app.models.ip_address import IPAddress
from app.models.network import Network
from app.models.resource import Resource

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@runtime_checkable
class IpOccupancyProvider(Protocol):
    """A source of already-allocated IPs inside a range (DR-109)."""

    def occupancy(
        self,
        db: "Session",
        network_id: uuid.UUID,
        start_address: str,
        end_address: str,
        limit: int,
    ) -> dict[str, Any]:
        """Return ``{"total": int, "items": list[dict]}`` for the closed range."""
        ...  # pragma: no cover - protocol declaration


class NullIpOccupancyProvider:
    """Empty set provider (kept for tests / compatibility)."""

    def occupancy(
        self,
        db: "Session",
        network_id: uuid.UUID,
        start_address: str,
        end_address: str,
        limit: int,
    ) -> dict[str, Any]:
        return {"total": 0, "items": []}


class IpAddressOccupancyProvider:
    """Real provider backed by ``ip_addresses`` (F010 DR-138).

    A closed ``[start_address, end_address]`` range is matched on the redundant
    ``cluster_id`` (looked up from the owning Network) so the partial unique
    index ``uq_ip_addresses_cluster_id_address`` supports the scan (DB-D125).
    Only undeleted IPs count; a bound Interface contributes its Resource
    id/hostname to the preview.
    """

    def occupancy(
        self,
        db: "Session",
        network_id: uuid.UUID,
        start_address: str,
        end_address: str,
        limit: int,
    ) -> dict[str, Any]:
        cluster_id = db.execute(
            select(Network.cluster_id).where(Network.id == network_id),
            execution_options={"include_deleted": True},
        ).scalar_one_or_none()
        if cluster_id is None:
            return {"total": 0, "items": []}

        # Index-friendly closed range on the (cluster_id, address) partial unique
        # index; the case params are cast to ``inet`` so PG can use the btree.
        in_range = [
            IPAddress.cluster_id == cluster_id,
            IPAddress.deleted_at.is_(None),
            IPAddress.address >= cast(start_address, INET),
            IPAddress.address <= cast(end_address, INET),
        ]

        total = int(
            db.execute(
                select(func.count()).select_from(IPAddress).where(*in_range)
            ).scalar_one()
        )
        if total == 0:
            return {"total": 0, "items": []}

        rows = db.execute(
            select(
                IPAddress.id,
                IPAddress.address,
                IPAddress.interface_id,
                Resource.id,
                Resource.hostname,
            )
            .select_from(IPAddress)
            .outerjoin(Interface, Interface.id == IPAddress.interface_id)
            .outerjoin(Resource, Resource.id == Interface.resource_id)
            .where(*in_range)
            .order_by(IPAddress.address.asc(), IPAddress.id.asc())
            .limit(limit)
        ).all()

        items = [
            {
                "object_type": "ip_address",
                "object_id": str(row[0]),
                "address": str(row[1]),
                "bound": row[2] is not None,
                "interface_id": str(row[2]) if row[2] is not None else None,
                "resource_id": str(row[3]) if row[3] is not None else None,
                "resource_hostname": row[4],
            }
            for row in rows
        ]
        return {"total": total, "items": items}


_PROVIDERS: list[IpOccupancyProvider] = [IpAddressOccupancyProvider()]


def register_provider(provider: IpOccupancyProvider) -> None:
    """Append a provider to the registry (F010 registers the real one)."""
    _PROVIDERS.append(provider)


def providers() -> list[IpOccupancyProvider]:
    """Return the registered providers (test/introspection hook)."""
    return list(_PROVIDERS)


def check_occupancy(
    db: "Session",
    network_id: uuid.UUID,
    start_address: str,
    end_address: str,
    limit: int,
) -> dict[str, Any]:
    """Merge every registered provider's conflicts for the closed range.

    ``total`` is the summed count; ``items`` is the concatenation truncated to
    ``limit``. The caller computes ``conflicts_truncated`` as ``total >
    len(items)``.
    """
    total = 0
    items: list[dict[str, Any]] = []
    for provider in _PROVIDERS:
        result = provider.occupancy(
            db, network_id, start_address, end_address, limit
        )
        total += int(result.get("total", 0))
        items.extend(result.get("items", []))
    return {"total": total, "items": items[:limit]}