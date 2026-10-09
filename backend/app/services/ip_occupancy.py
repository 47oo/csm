"""IP occupancy provider registry (DR-109/DR-110, I-5).

F009 ships no IP data (IPAddress ships in F010), so the "an address in the
changed range is already allocated" rule (§12.1) is delegated to a small
provider registry. F009 registers :class:`NullIpOccupancyProvider` (empty set);
F010 registers the real provider backed by ``ip_addresses``. The Service layer
calls :func:`check_occupancy` while holding ``_lock_network``
(``networks`` row ``FOR UPDATE``) so a check serialises with F010 allocation
(which must take the same lock).

A provider returns ``{"total": int, "items": [...]}`` where ``total`` is the
number of undeleted IPs in the (closed) ``[start, end]`` range and ``items`` is
a preview of at most ``limit`` conflict descriptors::

    {"object_type": "ip_address", "object_id": str, "address": str,
     "bound": bool, "interface_id": str | None, "resource_id": str | None,
     "resource_hostname": str | None}

The caller maps a non-zero ``total`` to a 409 ``address_in_use`` conflict. The
registry holds a list of providers so later Features can append without
rewiring call sites; providers are expected to be disjoint (F009 contributes an
empty set).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

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
    """F009 default: no IPAddress data exists yet, so the set is empty."""

    def occupancy(
        self,
        db: "Session",
        network_id: uuid.UUID,
        start_address: str,
        end_address: str,
        limit: int,
    ) -> dict[str, Any]:
        return {"total": 0, "items": []}


_PROVIDERS: list[IpOccupancyProvider] = [NullIpOccupancyProvider()]


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