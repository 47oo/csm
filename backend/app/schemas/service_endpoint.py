"""ServiceEndpoint request/response schemas (Contract §2/§3/§4/§6).

ServiceEndpoint is an independent object: ``service`` is nested as
``{id,name,resource{id,hostname}}`` and ``ip_address`` as
``{id,address,network{id,name},interface{id,name}}``; ``created_at`` /
``updated_at`` / ``deleted_at`` are serialised as ISO-8601 UTC with an explicit
``+00:00`` offset. No ``metadata``/``name``/``status``/``listen_address`` and no
raw ``service_id``/``ip_address_id`` are exposed (DR-156).

Value-domain checks that must follow the Contract §6.2 validation order
(``service`` -> ``ip_address`` -> attribution -> ``protocol`` -> ``port`` ->
uniqueness) are deliberately performed in the Service layer: these schemas only
enforce the field shape and reject undeclared/read-only fields.

PATCH uses ``exclude_unset`` semantics: omitted fields keep their value, and an
explicit ``null`` only clears ``description``. The route rejects explicit nulls
for the non-nullable ``protocol``/``port`` and undeclared/read-only fields
(``service``/``service_id``/``ip_address``/``ip_address_id``/``id``/``metadata``)
are rejected as extras.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
)

from app.models.ip_address import IPAddress
from app.models.service import Service
from app.models.service_endpoint import ServiceEndpoint

DeletedMode = Literal["exclude", "include", "only"]
SortField = Literal["protocol", "port", "created_at", "updated_at"]
SortOrder = Literal["asc", "desc"]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _addr_str(value) -> str:  # noqa: ANN001
    """Render a psycopg ``ipaddress``/string address as its text form."""
    return "" if value is None else str(value)


class ServiceEndpointCreateRequest(BaseModel):
    """POST body: ``service``/``ip_address`` are required and immutable."""

    model_config = ConfigDict(extra="forbid")

    service: str
    ip_address: str
    protocol: str
    port: int
    description: str | None = None


class ServiceEndpointUpdateRequest(BaseModel):
    """PATCH body: omitted fields keep their value; immutable fields rejected."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    protocol: str | None = None
    port: int | None = None
    description: str | None = None


class ServiceResourceNested(BaseModel):
    id: uuid.UUID
    hostname: str


class ServiceNested(BaseModel):
    id: uuid.UUID
    name: str
    resource: ServiceResourceNested


class NetworkNested(BaseModel):
    id: uuid.UUID
    name: str


class InterfaceNested(BaseModel):
    id: uuid.UUID
    name: str


class IPAddressNested(BaseModel):
    id: uuid.UUID
    address: str
    network: NetworkNested
    interface: InterfaceNested


class ServiceEndpointOut(BaseModel):
    id: uuid.UUID
    service: ServiceNested
    ip_address: IPAddressNested
    protocol: str
    port: int
    description: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @field_serializer("created_at", "updated_at", "deleted_at")
    def _serialize_timestamp(self, value: datetime | None) -> str | None:
        return None if value is None else _iso_utc(value)


class ServiceEndpointListResponse(BaseModel):
    items: list[ServiceEndpointOut]
    page: int
    page_size: int
    total: int


class ServiceEndpointEnvelope(BaseModel):
    service_endpoint: ServiceEndpointOut


def build_service_endpoint_out(
    endpoint: ServiceEndpoint,
    service: Service | None,
    service_resource,
    ip_address: IPAddress | None,
    network,
    interface,
) -> ServiceEndpointOut:
    """Serialise a ServiceEndpoint with its expanded Service and IPAddress.

    Related lookups include soft-deleted rows so an Endpoint whose Service /
    IPAddress / Interface was later soft-deleted still exposes stable id/name
    values.
    """
    resource = service_resource
    iface = interface
    return ServiceEndpointOut(
        id=endpoint.id,
        service=ServiceNested(
            id=endpoint.service_id,
            name=service.name if service is not None else "",
            resource=ServiceResourceNested(
                id=resource.id if resource is not None else uuid.UUID(int=0),
                hostname=resource.hostname if resource is not None else "",
            ),
        ),
        ip_address=IPAddressNested(
            id=endpoint.ip_address_id,
            address=_addr_str(ip_address.address) if ip_address is not None else "",
            network=NetworkNested(
                id=network.id if network is not None else uuid.UUID(int=0),
                name=network.name if network is not None else "",
            ),
            interface=InterfaceNested(
                id=iface.id if iface is not None else uuid.UUID(int=0),
                name=iface.name if iface is not None else "",
            ),
        ),
        protocol=endpoint.protocol,
        port=endpoint.port,
        description=endpoint.description,
        version=endpoint.version,
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
        deleted_at=endpoint.deleted_at,
    )