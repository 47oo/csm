"""IPAddress reference-checker registry (F010 DR-127/DR-139).

Two concerns live here:

- **Endpoint -> IPAddress** (F012): the service calls
  :func:`check_ip_address_references` before unbind / transfer / release. F010
  ships no Endpoint table, so the registry defaults to an empty set; F012
  registers a real checker with :func:`register_ip_address_reference_checker`.
- **IPAddress -> Network / Interface**: an undeleted IP blocks deletion (and a
  cidr/cluster change) of its Network and deletion of its bound Interface
  (§21). These are registered on the shared ``cluster_service`` reference
  registry, matching the F007/F008/F009 pattern. The IPPool allocation source is
  an explicit §12/§21 exception and registers **no** checker.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.ip_address import IPAddress
from app.services import cluster as cluster_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# A checker returns a list of reference descriptors (object_type/object_id/
# label). The empty default means "no reference blocks the operation".
IpAddressReferenceChecker = Callable[["Session", uuid.UUID], list[dict[str, Any]]]

_CHECKERS: list[IpAddressReferenceChecker] = []


def register_ip_address_reference_checker(
    checker: IpAddressReferenceChecker,
) -> None:
    """Register an Endpoint (or later) checker for an IPAddress reference."""
    _CHECKERS.append(checker)


def check_ip_address_references(
    db: "Session", ip_address_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Return undeleted references blocking unbind/transfer/release (empty F010)."""
    references: list[dict[str, Any]] = []
    for checker in _CHECKERS:
        references.extend(checker(db, ip_address_id))
    return references


# --- IPAddress -> Network / Interface (DR-127) ------------------------------


def _undeleted_ip_addresses_for_network(
    db: "Session", network_id: uuid.UUID
) -> list[dict]:
    """Undeleted IPs block Network deletion / cidr / cluster change (§21)."""
    rows = db.execute(
        select(IPAddress.id, IPAddress.address).where(
            IPAddress.network_id == network_id,
            IPAddress.deleted_at.is_(None),
        )
    ).all()
    return [
        {"object_type": "ip_address", "object_id": str(row[0]), "label": str(row[1])}
        for row in rows
    ]


def _undeleted_ip_addresses_for_interface(
    db: "Session", interface_id: uuid.UUID
) -> list[dict]:
    """Undeleted IPs bound to an Interface block its deletion (§21)."""
    rows = db.execute(
        select(IPAddress.id, IPAddress.address).where(
            IPAddress.interface_id == interface_id,
            IPAddress.deleted_at.is_(None),
        )
    ).all()
    return [
        {"object_type": "ip_address", "object_id": str(row[0]), "label": str(row[1])}
        for row in rows
    ]


cluster_service.register_reference_checker(
    "network", _undeleted_ip_addresses_for_network
)
cluster_service.register_reference_checker(
    "interface", _undeleted_ip_addresses_for_interface
)