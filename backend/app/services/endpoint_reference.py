"""ServiceEndpoint reference-checker providers (F012, DR-161/DR-162).

Two real providers are registered at import time (the startup import chain runs
through :mod:`app.services.service_endpoint` -> this module):

- the IP side (:func:`register_ip_address_reference_checker`) makes an undeleted
  Endpoint block IP unbind / transfer / release (F010 calls
  :func:`app.services.ip_address_reference.check_ip_address_references`);
- the Service side (:func:`register_service_reference_checker`) makes an
  undeleted Endpoint block Service deletion (F011 calls
  :func:`app.services.service_reference.check_service_references`).

Both return the canonical ``object_type="service_endpoint"`` with
``label=f"{protocol}/{port}"`` (DR-162). The DB only enforces physical-delete
integrity (FK RESTRICT); soft-delete reference protection is this module's
responsibility.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.service_endpoint import ServiceEndpoint
from app.services import ip_address_reference, service_reference

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

OBJECT_TYPE = "service_endpoint"


def _reference_rows(db: "Session", *filters: Any) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            ServiceEndpoint.id,
            ServiceEndpoint.protocol,
            ServiceEndpoint.port,
        ).where(*filters, ServiceEndpoint.deleted_at.is_(None))
    ).all()
    return [
        {
            "object_type": OBJECT_TYPE,
            "object_id": str(row.id),
            "label": f"{row.protocol}/{row.port}",
        }
        for row in rows
    ]


def _undeleted_endpoints_for_ip(
    db: "Session", ip_address_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Undeleted Endpoints referencing an IPAddress (F010 IP-side hook)."""
    return _reference_rows(db, ServiceEndpoint.ip_address_id == ip_address_id)


def _undeleted_endpoints_for_service(
    db: "Session", service_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Undeleted Endpoints referencing a Service (F011 Service-side hook)."""
    return _reference_rows(db, ServiceEndpoint.service_id == service_id)


ip_address_reference.register_ip_address_reference_checker(
    _undeleted_endpoints_for_ip
)
service_reference.register_service_reference_checker(
    _undeleted_endpoints_for_service
)