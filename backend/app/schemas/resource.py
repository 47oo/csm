"""Resource request/response schemas (Contract §2/§3/§4/§6).

``hostname_key`` is an internal column and never appears here. ``created_at`` /
``updated_at`` / ``deleted_at`` are serialised as ISO-8601 UTC with an explicit
``+00:00`` offset. The owning cluster is nested as ``{id, code, name}``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.cluster import Cluster
from app.models.resource import Resource

ResourceType = Literal["BARE_METAL", "VIRTUAL_MACHINE"]
ResourceRole = Literal[
    "COMPUTE", "LOGIN", "MANAGEMENT", "STORAGE", "SERVICE", "GPU", "OTHER"
]
ResourceStatus = Literal["IDLE", "ALLOC", "DOWN", "UNKNOWN"]
DeletedMode = Literal["exclude", "include", "only"]
SortField = Literal[
    "hostname", "resource_type", "role", "status", "created_at", "updated_at"
]
SortOrder = Literal["asc", "desc"]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class ClusterNested(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class ResourceOut(BaseModel):
    id: uuid.UUID
    cluster: ClusterNested
    hostname: str
    resource_type: str
    role: str
    status: str
    description: str | None
    metadata: dict
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @field_serializer("created_at", "updated_at", "deleted_at")
    def _serialize_timestamp(self, value: datetime | None) -> str | None:
        return None if value is None else _iso_utc(value)


class ResourceListResponse(BaseModel):
    items: list[ResourceOut]
    page: int
    page_size: int
    total: int


class ResourceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster: str
    hostname: str
    resource_type: ResourceType
    role: ResourceRole = "OTHER"
    status: ResourceStatus = "UNKNOWN"
    description: str | None = None
    metadata: dict = Field(default_factory=dict)


class ResourceUpdateRequest(BaseModel):
    """PATCH body: omitted fields keep their value; immutable fields rejected.

    ``cluster``/``resource_type`` (and any other undeclared/read-only field) are
    rejected as extras -> 422. ``hostname``/``role``/``status``/``metadata`` must
    not be explicitly null (the route turns those into 422); only
    ``description`` may be nulled to clear it.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    hostname: str | None = None
    role: ResourceRole | None = None
    status: ResourceStatus | None = None
    description: str | None = None
    metadata: dict | None = None


class ResourceEnvelope(BaseModel):
    resource: ResourceOut


def build_resource_out(resource: Resource, cluster: Cluster) -> ResourceOut:
    """Serialise a Resource ORM object without exposing ``hostname_key``."""
    return ResourceOut(
        id=resource.id,
        cluster=ClusterNested(id=cluster.id, code=cluster.code, name=cluster.name),
        hostname=resource.hostname,
        resource_type=resource.resource_type,
        role=resource.role,
        status=resource.status,
        description=resource.description,
        metadata=resource.meta,
        version=resource.version,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
        deleted_at=resource.deleted_at,
    )