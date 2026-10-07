"""Resource request/response schemas (Contract §2/§3/§4/§6).

``hostname_key`` is an internal column and never appears here. ``created_at`` /
``updated_at`` / ``deleted_at`` are serialised as ISO-8601 UTC with an explicit
``+00:00`` offset. The owning cluster is nested as ``{id, code, name}``.

The optional nested ``hardware`` object (F005, Contract §2.4) is only valid for
``BARE_METAL`` resources: on create it defaults to an all-null detail, on PATCH
sub-fields follow ``exclude_unset`` semantics, and the Resource response exposes
it as an object (BARE_METAL) or ``null`` (VIRTUAL_MACHINE). No route exposes an
independent hardware endpoint.

The optional nested ``virtual_machine`` object (F006, Contract §2.5) is only
valid for ``VIRTUAL_MACHINE`` resources: on create it is required with a
non-null ``host_resource_id``, on PATCH sub-fields follow ``exclude_unset``
semantics, and the response exposes it as an object (VM) or ``null``
(BARE_METAL). It has no independent metadata key (DR-69).
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
from app.models.virtual_machine_detail import VirtualMachineDetail
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


class HostNested(BaseModel):
    """The VM's host Resource, expanded to ``{id, hostname}`` (Contract §2.5)."""

    id: uuid.UUID
    hostname: str


class _VirtualMachineFields(BaseModel):
    """Shared VirtualMachine field set (Contract §2.5, D01 §5.5).

    ``StrictInt`` rejects ``true`` / ``"4"`` / ``1.5``; ``vcpu``/``memory_mb``
    are positive, ``disk_gb`` non-negative (0 means "explicitly no disk"), and
    the bounds mirror the database CHECKs. ``hypervisor`` is trimmed then kept
    verbatim (case preserved, no enum). Unknown keys, including a VM-level
    ``metadata`` key, are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    vcpu: PositiveHardwareInt | None = None
    memory_mb: PositiveHardwareInt | None = None
    disk_gb: NonNegativeHardwareInt | None = None
    hypervisor: str | None = None

    @field_validator("hypervisor", mode="before")
    @classmethod
    def _validate_hypervisor(cls, value, info):  # noqa: ANN001
        if value is None:
            return None
        try:
            return normalization.validate_descriptive_string(
                f"virtual_machine.{info.field_name}", value, max_length=255
            )
        except AppValidationError as exc:
            fields = exc.details.get("fields") or []
            message = fields[0]["message"] if fields else exc.message
            raise ValueError(message) from exc


class VirtualMachineIn(_VirtualMachineFields):
    """POST ``virtual_machine`` object; ``host_resource_id`` is required."""

    host_resource_id: uuid.UUID


class VirtualMachinePatch(_VirtualMachineFields):
    """PATCH ``virtual_machine`` object; sub-fields use ``exclude_unset``.

    ``host_resource_id`` is optional (omitted = keep the current Host) but an
    explicit ``null`` is rejected with 422 by the route before reaching here.
    """

    host_resource_id: uuid.UUID | None = None


class VirtualMachineOut(_VirtualMachineFields):
    """Resource response ``virtual_machine`` object (VIRTUAL_MACHINE only)."""

    host_resource_id: uuid.UUID
    host: HostNested


def build_virtual_machine_out(
    detail: VirtualMachineDetail | None, host: Resource | None
) -> VirtualMachineOut | None:
    """Serialise a VM detail row with its expanded host.

    The host is looked up including soft-deleted rows so a VM whose Host was
    later soft-deleted still exposes its id/hostname (Contract §2.5).
    """
    if detail is None:
        return None
    return VirtualMachineOut(
        host_resource_id=detail.host_resource_id,
        host=HostNested(
            id=detail.host_resource_id,
            hostname=host.hostname if host is not None else "",
        ),
        vcpu=detail.vcpu,
        memory_mb=detail.memory_mb,
        disk_gb=detail.disk_gb,
        hypervisor=detail.hypervisor,
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
    virtual_machine: VirtualMachineOut | None
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
    # Omitted -> no VM detail (BARE_METAL); required for VIRTUAL_MACHINE (422).
    virtual_machine: VirtualMachineIn | None = None


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
    # virtual_machine itself is never nulled; sub-fields are exclude_unset.
    virtual_machine: VirtualMachinePatch | None = None


class ResourceEnvelope(BaseModel):
    resource: ResourceOut


def build_resource_out(
    resource: Resource,
    cluster: Cluster,
    hardware: HardwareOut | None = None,
    virtual_machine: VirtualMachineOut | None = None,
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
        virtual_machine=virtual_machine,
        version=resource.version,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
        deleted_at=resource.deleted_at,
    )