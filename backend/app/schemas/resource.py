"""Resource request/response schemas (Contract §2/§3/§4/§6).

``hostname_key`` is an internal column and never appears here. ``created_at`` /
``updated_at`` / ``deleted_at`` are serialised as ISO-8601 UTC with an explicit
``+00:00`` offset. The owning cluster is nested as ``{id, code, name}``.

The optional nested ``hardware`` object (F005, Contract §2.4) is only valid for
``BARE_METAL`` resources: on create it defaults to an all-null detail, on PATCH
sub-fields follow ``exclude_unset`` semantics, and the Resource response exposes
it as an object (BARE_METAL) or ``null`` (VIRTUAL_MACHINE). No route exposes an
independent hardware endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_serializer,
    field_validator,
)

from app.core.errors import ValidationError as AppValidationError
from app.models.bare_metal_detail import (
    STRING_FIELDS,
    BareMetalDetail,
)
from app.models.cluster import Cluster
from app.models.resource import Resource
from app.services import normalization

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


PositiveHardwareInt = Annotated[StrictInt, Field(ge=1, le=2147483647)]
NonNegativeHardwareInt = Annotated[StrictInt, Field(ge=0, le=2147483647)]


class _HardwareFields(BaseModel):
    """Shared hardware field set (Contract §2.4, D01 §5.4).

    ``StrictInt`` rejects ``true`` / ``"192"`` / ``1.5``; the ``ge``/``le``
    bounds mirror the database CHECKs. Strings are trimmed and re-validated then
    kept verbatim (case preserved, no uniqueness). Unknown keys are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    cpu_model: str | None = None
    gpu_model: str | None = None
    cpu_sockets: PositiveHardwareInt | None = None
    cpu_cores: PositiveHardwareInt | None = None
    memory_mb: PositiveHardwareInt | None = None
    gpu_count: NonNegativeHardwareInt | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator(*STRING_FIELDS, mode="before")
    @classmethod
    def _validate_hardware_string(cls, value, info):  # noqa: ANN001
        if value is None:
            return None
        try:
            return normalization.validate_hardware_string(info.field_name, value)
        except AppValidationError as exc:
            fields = exc.details.get("fields") or []
            message = fields[0]["message"] if fields else exc.message
            raise ValueError(message) from exc


class HardwareIn(_HardwareFields):
    """POST ``hardware`` object (all sub-fields optional, default all-null)."""


class HardwarePatch(_HardwareFields):
    """PATCH ``hardware`` object; sub-fields use ``exclude_unset`` semantics."""


class HardwareOut(_HardwareFields):
    """Resource response ``hardware`` object (BARE_METAL only)."""


def build_hardware_out(detail: BareMetalDetail | None) -> HardwareOut:
    """Serialise a detail row; a missing row yields all-null with metadata {}."""
    if detail is None:
        return HardwareOut()
    return HardwareOut(
        manufacturer=detail.manufacturer,
        model=detail.model,
        serial_number=detail.serial_number,
        cpu_model=detail.cpu_model,
        gpu_model=detail.gpu_model,
        cpu_sockets=detail.cpu_sockets,
        cpu_cores=detail.cpu_cores,
        memory_mb=detail.memory_mb,
        gpu_count=detail.gpu_count,
        metadata=detail.meta,
    )


class ResourceOut(BaseModel):
    id: uuid.UUID
    cluster: ClusterNested
    hostname: str
    resource_type: str
    role: str
    status: str
    description: str | None
    metadata: dict
    hardware: HardwareOut | None
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
    # Omitted -> all-null BARE_METAL detail; explicit null -> 422 (non-optional).
    hardware: HardwareIn = Field(default_factory=HardwareIn)


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
    # hardware itself is never nulled; sub-fields are applied exclude_unset.
    hardware: HardwarePatch | None = None


class ResourceEnvelope(BaseModel):
    resource: ResourceOut


def build_resource_out(
    resource: Resource,
    cluster: Cluster,
    hardware: HardwareOut | None = None,
) -> ResourceOut:
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
        hardware=hardware,
        version=resource.version,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
        deleted_at=resource.deleted_at,
    )