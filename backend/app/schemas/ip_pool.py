"""IPPool request/response schemas (Contract §2/§3/§4/§6).

IPPool is an independent object: ``network`` is nested as ``{id, name, cidr}``,
``start_address``/``end_address`` are serialised as their PostgreSQL text form.
``created_at`` / ``updated_at`` / ``deleted_at`` are serialised as ISO-8601 UTC
with an explicit ``+00:00`` offset. ``name_key`` and ``address_range`` are
internal columns and never exposed; ``metadata`` is not accepted or exposed
(I-6).

``name`` is normalised in the schema (trim / non-empty / no Cc/Cf / 1-255 code
points, internal ordinary spaces preserved). The address value-domain checks
(CIDR containment, ordering) are deliberately performed in the Service layer
(not here) so the Contract §6 validation order is preserved; these schemas only
enforce the field shape.

PATCH uses ``exclude_unset`` semantics: omitted fields keep their value, and an
explicit ``null`` only clears a nullable field. The route rejects explicit nulls
for non-nullable fields (``name``/``start_address``/``end_address``/
``allocation_mode``) and undeclared/read-only fields (``network``/``network_id``/
``id``/``name_key``/``address_range``/``metadata``) are rejected as extras.
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
    field_validator,
)

from app.core.errors import ValidationError as AppValidationError
from app.models.ip_pool import IPPool
from app.models.network import Network
from app.services import normalization

AllocationMode = Literal["MANUAL", "AUTO", "RESERVED"]
DeletedMode = Literal["exclude", "include", "only"]
SortField = Literal[
    "name",
    "start_address",
    "end_address",
    "allocation_mode",
    "created_at",
    "updated_at",
]
SortOrder = Literal["asc", "desc"]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _addr_str(value) -> str | None:  # noqa: ANN001
    """Render a psycopg ``ipaddress``/string address as its text form."""
    return None if value is None else str(value)


class _IPPoolNameMixin(BaseModel):
    @field_validator("name", mode="before", check_fields=False)
    @classmethod
    def _validate_name(cls, value):  # noqa: ANN001
        if value is None:
            return None
        try:
            return normalization.normalize_ip_pool_name(value)
        except AppValidationError as exc:
            fields = exc.details.get("fields") or []
            message = fields[0]["message"] if fields else exc.message
            raise ValueError(message) from exc


class IPPoolCreateRequest(_IPPoolNameMixin):
    model_config = ConfigDict(extra="forbid")

    network: str
    name: str
    start_address: str
    end_address: str
    allocation_mode: AllocationMode = "MANUAL"
    description: str | None = None


class IPPoolUpdateRequest(_IPPoolNameMixin):
    """PATCH body: omitted fields keep their value; read-only fields rejected."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str | None = None
    start_address: str | None = None
    end_address: str | None = None
    allocation_mode: AllocationMode | None = None
    description: str | None = None


class NetworkNested(BaseModel):
    id: uuid.UUID
    name: str
    cidr: str


class IPPoolOut(BaseModel):
    id: uuid.UUID
    network: NetworkNested
    name: str
    start_address: str
    end_address: str
    allocation_mode: str
    description: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @field_serializer("created_at", "updated_at", "deleted_at")
    def _serialize_timestamp(self, value: datetime | None) -> str | None:
        return None if value is None else _iso_utc(value)


class IPPoolListResponse(BaseModel):
    items: list[IPPoolOut]
    page: int
    page_size: int
    total: int


class IPPoolEnvelope(BaseModel):
    ip_pool: IPPoolOut


def build_ip_pool_out(ip_pool: IPPool, network: Network | None) -> IPPoolOut:
    """Serialise an IPPool ORM object with its expanded Network.

    ``network`` is looked up including soft-deleted rows so an IPPool whose
    Network was later soft-deleted still exposes id/name/cidr.
    """
    return IPPoolOut(
        id=ip_pool.id,
        network=NetworkNested(
            id=ip_pool.network_id,
            name=network.name if network is not None else "",
            cidr=_addr_str(network.cidr) if network is not None else "",
        ),
        name=ip_pool.name,
        start_address=_addr_str(ip_pool.start_address) or "",
        end_address=_addr_str(ip_pool.end_address) or "",
        allocation_mode=ip_pool.allocation_mode,
        description=ip_pool.description,
        version=ip_pool.version,
        created_at=ip_pool.created_at,
        updated_at=ip_pool.updated_at,
        deleted_at=ip_pool.deleted_at,
    )