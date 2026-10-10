"""IPAddress request/response schemas (Contract §2/§3/§4/§6).

IPAddress is an independent object: ``network``/``cluster``/``interface``/
``ip_pool`` are nested; ``created_at``/``updated_at``/``deleted_at`` are
serialised as ISO-8601 UTC with an explicit ``+00:00`` offset. ``network_id`` /
``cluster_id`` / ``metadata`` are never exposed (DR-123).

``address`` is normalised (a bare IPv4 host address, no mask/CIDR) and the
value-domain checks (CIDR containment, network/broadcast, disabled/gateway/
RESERVED) are deliberately performed in the Service layer so the Contract §6
validation order is preserved; these schemas only enforce the field shape.

POST intentionally rejects ``interface`` (allocation and binding are separate,
DR-137). PATCH uses ``exclude_unset`` semantics; an explicit ``null`` only
clears a nullable field and ``network``/``address``/``cluster_id``/``ip_pool``/
``id`` are rejected as extras.
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

from app.models.cluster import Cluster
from app.models.ip_address import IPAddress
from app.models.ip_pool import IPPool
from app.models.network import Network

DeletedMode = Literal["exclude", "include", "only"]
SortField = Literal["address", "created_at", "updated_at"]
SortOrder = Literal["asc", "desc"]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _addr_str(value) -> str | None:  # noqa: ANN001
    """Render a psycopg ``ipaddress``/string address as its text form."""
    return None if value is None else str(value)


class IPAddressCreateRequest(BaseModel):
    """Manual allocation: creates an unbound IP (interface is a separate PATCH).

    ``address`` is validated in the Service layer so the Contract §6.2 order
    (network -> lock -> ACTIVE -> address) is preserved; this schema only
    enforces the body shape and rejects undeclared/read-only fields.
    """

    model_config = ConfigDict(extra="forbid")

    network: str
    address: str
    description: str | None = None


class IPAddressAutoAllocateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network: str
    ip_pool: str
    description: str | None = None


class IPAddressUpdateRequest(BaseModel):
    """PATCH body: omitted fields keep their value; immutable fields rejected."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    interface: uuid.UUID | None = None
    description: str | None = None


class NetworkNested(BaseModel):
    id: uuid.UUID
    name: str
    cidr: str


class ClusterNested(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class InterfaceResourceNested(BaseModel):
    id: uuid.UUID
    hostname: str


class InterfaceNested(BaseModel):
    id: uuid.UUID
    name: str
    resource: InterfaceResourceNested


class IPPoolNested(BaseModel):
    id: uuid.UUID
    name: str


class IPAddressOut(BaseModel):
    id: uuid.UUID
    network: NetworkNested
    cluster: ClusterNested
    address: str
    interface: InterfaceNested | None
    ip_pool: IPPoolNested | None
    description: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @field_serializer("created_at", "updated_at", "deleted_at")
    def _serialize_timestamp(self, value: datetime | None) -> str | None:
        return None if value is None else _iso_utc(value)


class IPAddressListResponse(BaseModel):
    items: list[IPAddressOut]
    page: int
    page_size: int
    total: int


class IPAddressEnvelope(BaseModel):
    ip_address: IPAddressOut


def build_ip_address_out(
    ip_address: IPAddress,
    network: Network | None,
    cluster: Cluster | None,
    interface,
    resource,
    ip_pool: IPPool | None,
) -> IPAddressOut:
    """Serialise an IPAddress ORM object with its expanded related objects.

    Related lookups include soft-deleted rows so an IP whose Network/Interface
    was later soft-deleted still exposes stable id/name values.
    """
    interface_out: InterfaceNested | None = None
    if interface is not None:
        interface_out = InterfaceNested(
            id=interface.id,
            name=interface.name,
            resource=InterfaceResourceNested(
                id=interface.resource_id,
                hostname=resource.hostname if resource is not None else "",
            ),
        )
    return IPAddressOut(
        id=ip_address.id,
        network=NetworkNested(
            id=ip_address.network_id,
            name=network.name if network is not None else "",
            cidr=_addr_str(network.cidr) if network is not None else "",
        ),
        cluster=ClusterNested(
            id=ip_address.cluster_id,
            code=cluster.code if cluster is not None else "",
            name=cluster.name if cluster is not None else "",
        ),
        address=_addr_str(ip_address.address) or "",
        interface=interface_out,
        ip_pool=(
            IPPoolNested(id=ip_pool.id, name=ip_pool.name)
            if ip_pool is not None
            else None
        ),
        description=ip_address.description,
        version=ip_address.version,
        created_at=ip_address.created_at,
        updated_at=ip_address.updated_at,
        deleted_at=ip_address.deleted_at,
    )


# --- capacity (§6.9) --------------------------------------------------------


class CapacityNetworkNested(BaseModel):
    id: uuid.UUID
    name: str
    cidr: str
    status: str
    auto_allocate: bool


class CapacityIpPoolNested(BaseModel):
    id: uuid.UUID
    name: str
    start_address: str
    end_address: str


class NetworkCapacityBlock(BaseModel):
    network: CapacityNetworkNested
    allocatable_total: int
    occupied: int
    remaining: int


class AutoPoolCapacityBlock(BaseModel):
    ip_pool: CapacityIpPoolNested
    allocatable_total: int
    occupied: int
    remaining: int


class NetworkCapacityResponse(BaseModel):
    network_capacity: NetworkCapacityBlock
    auto_pools: list[AutoPoolCapacityBlock]