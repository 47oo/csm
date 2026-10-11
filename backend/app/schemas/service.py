"""Service request/response schemas (Contract §2/§3/§4/§6).

Service is an independent object: ``resource`` is nested as ``{id, hostname}``.
``created_at`` / ``updated_at`` / ``deleted_at`` are serialised as ISO-8601 UTC
with an explicit ``+00:00`` offset. ``name_key`` is an internal column and never
exposed.

``name`` normalisation (trim / non-empty / no Cc/Cf / 1-255 code points, internal
ordinary spaces preserved) is deliberately performed in the Service layer so the
Contract §6.2/§6.4 validation order (resource before name) is preserved; these
schemas only enforce the field shape.

PATCH uses ``exclude_unset`` semantics: omitted fields keep their value, and an
explicit ``null`` only clears ``description``. The route rejects explicit nulls
for non-nullable fields (``name``/``status``/``metadata``) and
undeclared/read-only fields (``resource``/``resource_id``/``id``/``name_key``)
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

from app.models.resource import Resource
from app.models.service import Service

ServiceStatus = Literal["RUNNING", "STOPPED", "UNKNOWN"]
DeletedMode = Literal["exclude", "include", "only"]
SortField = Literal["name", "status", "created_at", "updated_at"]
SortOrder = Literal["asc", "desc"]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class ServiceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource: str
    name: str
    status: ServiceStatus = "UNKNOWN"
    description: str | None = None
    metadata: dict = Field(default_factory=dict)


class ServiceUpdateRequest(BaseModel):
    """PATCH body: omitted fields keep their value; read-only fields rejected."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str | None = None
    status: ServiceStatus | None = None
    description: str | None = None
    metadata: dict | None = None


class ResourceNested(BaseModel):
    id: uuid.UUID
    hostname: str


class ServiceOut(BaseModel):
    id: uuid.UUID
    resource: ResourceNested
    name: str
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


class ServiceListResponse(BaseModel):
    items: list[ServiceOut]
    page: int
    page_size: int
    total: int


class ServiceEnvelope(BaseModel):
    service: ServiceOut


def build_service_out(service: Service, resource: Resource | None) -> ServiceOut:
    """Serialise a Service ORM object with its expanded Resource.

    ``resource`` is looked up including soft-deleted rows so a Service whose
    Resource was later soft-deleted still exposes id/hostname.
    """
    return ServiceOut(
        id=service.id,
        resource=ResourceNested(
            id=service.resource_id,
            hostname=resource.hostname if resource is not None else "",
        ),
        name=service.name,
        status=service.status,
        description=service.description,
        metadata=service.meta,
        version=service.version,
        created_at=service.created_at,
        updated_at=service.updated_at,
        deleted_at=service.deleted_at,
    )