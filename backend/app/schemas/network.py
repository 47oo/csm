"""Network request/response schemas (Contract §2/§3/§4/§6).

Network is an independent object: ``cluster`` is nested as ``{id, code, name}``,
``cidr``/``gateway`` are serialised as their PostgreSQL text form (``gateway``
``null`` when unset). ``created_at`` / ``updated_at`` / ``deleted_at`` are
serialised as ISO-8601 UTC with an explicit ``+00:00`` offset. ``name_key`` is an
internal column and never exposed.

``name`` is normalised (trim / non-empty / no Cc/Cf / 1-255 code points, internal
ordinary spaces preserved). The ``cidr``/``gateway`` value-domain checks are
deliberately performed in the Service layer (not here) so the Contract §6
validation order (cluster -> name uniqueness -> cidr/gateway) is preserved;
these schemas only enforce the field shape.

PATCH uses ``exclude_unset`` semantics: omitted fields keep their value, and an
explicit ``null`` only clears a nullable field. The route rejects explicit nulls
for non-nullable fields (``name``/``cluster``/``cidr``/``status``/
``auto_allocate``/``metadata``) and undeclared/read-only fields are rejected as
extras.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_serializer,
    field_validator,
)

from app.core.errors import ValidationError as AppValidationError
from app.models.cluster import Cluster
from app.models.network import Network
from app.services import normalization

NetworkStatus = Literal["ACTIVE", "INACTIVE"]
DeletedMode = Literal["exclude", "include", "only"]
SortField = Literal["name", "cidr", "status", "created_at", "updated_at"]
SortOrder = Literal["asc", "desc"]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _addr_str(value) -> str | None:  # noqa: ANN001
    """Render a psycopg ``ipaddress``/string network address as its text form."""
    return None if value is None else str(value)


class _NetworkNameMixin(BaseModel):
    @field_validator("name", mode="before", check_fields=False)
    @classmethod
    def _validate_name(cls, value):  # noqa: ANN001
        if value is None:
            return None
        try:
            return normalization.normalize_network_name(value)
        except AppValidationError as exc:
            fields = exc.details.get("fields") or []
            message = fields[0]["message"] if fields else exc.message
            raise ValueError(message) from exc


class NetworkCreateRequest(_NetworkNameMixin):
    model_config = ConfigDict(extra="forbid")

    cluster: str
    name: str
    cidr: str
    gateway: str | None = None
    status: NetworkStatus = "ACTIVE"
    auto_allocate: StrictBool = False
    description: str | None = None
    metadata: dict = Field(default_factory=dict)


class NetworkUpdateRequest(_NetworkNameMixin):
    """PATCH body: omitted fields keep their value; ``id``/``name_key`` rejected."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    cluster: str | None = None
    name: str | None = None
    cidr: str | None = None
    gateway: str | None = None
    status: NetworkStatus | None = None
    auto_allocate: StrictBool | None = None
    description: str | None = None
    metadata: dict | None = None


class ClusterNested(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class NetworkOut(BaseModel):
    id: uuid.UUID
    cluster: ClusterNested
    name: str
    cidr: str
    gateway: str | None
    status: str
    auto_allocate: bool
    description: str | None
    metadata: dict
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @field_serializer("created_at", "updated_at", "deleted_at")
    def _serialize_timestamp(self, value: datetime | None) -> str | None:
        return None if value is None else _iso_utc(value)


class NetworkListResponse(BaseModel):
    items: list[NetworkOut]
    page: int
    page_size: int
    total: int


class NetworkEnvelope(BaseModel):
    network: NetworkOut


def build_network_out(network: Network, cluster: Cluster | None) -> NetworkOut:
    """Serialise a Network ORM object with its expanded Cluster.

    ``cluster`` is looked up including soft-deleted rows so a Network whose
    Cluster was later soft-deleted still exposes id/code/name.
    """
    return NetworkOut(
        id=network.id,
        cluster=ClusterNested(
            id=network.cluster_id,
            code=cluster.code if cluster is not None else "",
            name=cluster.name if cluster is not None else "",
        ),
        name=network.name,
        cidr=_addr_str(network.cidr) or "",
        gateway=_addr_str(network.gateway),
        status=network.status,
        auto_allocate=network.auto_allocate,
        description=network.description,
        metadata=network.meta,
        version=network.version,
        created_at=network.created_at,
        updated_at=network.updated_at,
        deleted_at=network.deleted_at,
    )