"""Interface request/response schemas (Contract §2/§3/§4/§6).

Interface is an independent object: ``resource`` is nested as ``{id, hostname}``
and ``parent_interface`` as ``{id, name} | null``. ``created_at`` / ``updated_at``
/ ``deleted_at`` are serialised as ISO-8601 UTC with an explicit ``+00:00``
offset. ``name`` is normalised (trim / non-empty / no internal whitespace or
Cc/Cf / 1-64 code points) but case is preserved; ``mac_address`` is trimmed and
kept verbatim (no format regex, no uniqueness).

PATCH uses ``exclude_unset`` semantics: omitted fields keep their value, and an
explicit ``null`` only clears a nullable field. The route rejects explicit nulls
for non-nullable fields (``name``/``interface_type``/``enabled``/``metadata``)
and ``resource``/``id``/read-only fields are rejected as extras.
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
from app.models.interface import Interface
from app.services import normalization

InterfaceType = Literal[
    "PHYSICAL", "VIRTUAL", "BOND", "BRIDGE", "VLAN", "LOOPBACK", "OTHER"
]
DeletedMode = Literal["exclude", "include", "only"]
SortField = Literal[
    "name", "interface_type", "speed_mbps", "mtu", "created_at", "updated_at"
]
SortOrder = Literal["asc", "desc"]

PositiveInt = Annotated[StrictInt, Field(ge=1, le=2147483647)]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _normalize_or_value_error(field: str, value, normalizer):  # noqa: ANN001
    """Run a normalisation helper and surface its message as a Pydantic error."""
    if value is None:
        return None
    try:
        return normalizer(value)
    except AppValidationError as exc:
        fields = exc.details.get("fields") or []
        message = fields[0]["message"] if fields else exc.message
        raise ValueError(message) from exc


class _InterfaceNameMixin(BaseModel):
    @field_validator("name", mode="before", check_fields=False)
    @classmethod
    def _validate_name(cls, value):  # noqa: ANN001
        return _normalize_or_value_error(
            "name", value, normalization.normalize_interface_name
        )

    @field_validator("mac_address", mode="before", check_fields=False)
    @classmethod
    def _validate_mac(cls, value):  # noqa: ANN001
        return _normalize_or_value_error(
            "mac_address", value, normalization.normalize_mac_address
        )


class InterfaceCreateRequest(_InterfaceNameMixin):
    model_config = ConfigDict(extra="forbid")

    resource: uuid.UUID
    name: str
    interface_type: InterfaceType = "OTHER"
    mac_address: str | None = None
    speed_mbps: PositiveInt | None = None
    mtu: PositiveInt | None = None
    parent_interface: uuid.UUID | None = None
    enabled: bool = True
    description: str | None = None
    metadata: dict = Field(default_factory=dict)


class InterfaceUpdateRequest(_InterfaceNameMixin):
    """PATCH body: omitted fields keep their value; ``resource`` is immutable."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str | None = None
    interface_type: InterfaceType | None = None
    mac_address: str | None = None
    speed_mbps: PositiveInt | None = None
    mtu: PositiveInt | None = None
    parent_interface: uuid.UUID | None = None
    enabled: bool | None = None
    description: str | None = None
    metadata: dict | None = None


class ResourceNested(BaseModel):
    id: uuid.UUID
    hostname: str


class ParentInterfaceNested(BaseModel):
    id: uuid.UUID
    name: str


class InterfaceOut(BaseModel):
    id: uuid.UUID
    resource: ResourceNested
    name: str
    interface_type: str
    mac_address: str | None
    speed_mbps: int | None
    mtu: int | None
    parent_interface: ParentInterfaceNested | None
    enabled: bool
    description: str | None
    metadata: dict
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @field_serializer("created_at", "updated_at", "deleted_at")
    def _serialize_timestamp(self, value: datetime | None) -> str | None:
        return None if value is None else _iso_utc(value)


class InterfaceListResponse(BaseModel):
    items: list[InterfaceOut]
    page: int
    page_size: int
    total: int


class InterfaceEnvelope(BaseModel):
    interface: InterfaceOut


def build_interface_out(
    interface: Interface,
    resource,
    parent: Interface | None,
) -> InterfaceOut:
    """Serialise an Interface ORM object with its expanded Resource/parent.

    ``resource`` is looked up including soft-deleted rows so the owning Resource
    is still shown for a soft-deleted Interface (the Resource cannot normally be
    deleted while an undeleted Interface points at it).
    """
    return InterfaceOut(
        id=interface.id,
        resource=ResourceNested(
            id=interface.resource_id,
            hostname=resource.hostname if resource is not None else "",
        ),
        name=interface.name,
        interface_type=interface.interface_type,
        mac_address=interface.mac_address,
        speed_mbps=interface.speed_mbps,
        mtu=interface.mtu,
        parent_interface=(
            ParentInterfaceNested(id=parent.id, name=parent.name)
            if parent is not None
            else None
        ),
        enabled=interface.enabled,
        description=interface.description,
        metadata=interface.meta,
        version=interface.version,
        created_at=interface.created_at,
        updated_at=interface.updated_at,
        deleted_at=interface.deleted_at,
    )