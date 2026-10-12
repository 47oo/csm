"""Deleted-object aggregate schemas (Contract §3).

``DeletedItem`` is a derived, read-only view across the eight soft-deletable
object types (``user`` is excluded: accounts are disabled, never deleted). It
carries the stable UUID, the current ``version`` (for the owning domain's
``.../restore?version=`` endpoint) and a human label; the delete operator is
deliberately NOT exposed (O-7).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, field_serializer

DeletedObjectType = Literal[
    "cluster",
    "resource",
    "interface",
    "network",
    "ip_pool",
    "ip_address",
    "service",
    "service_endpoint",
]
DeletedSort = Literal["deleted_at"]
SortOrder = Literal["asc", "desc"]

DELETED_OBJECT_TYPES: tuple[str, ...] = (
    "cluster",
    "resource",
    "interface",
    "network",
    "ip_pool",
    "ip_address",
    "service",
    "service_endpoint",
)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class ClusterRef:
    """Owning-cluster reference shown on a deleted item (``null`` for Cluster)."""

    id: uuid.UUID
    code: str
    name: str


@dataclass(frozen=True)
class DeletedRecord:
    """Row shape produced by the aggregate query and consumed by the schema."""

    object_type: str
    object_id: uuid.UUID
    version: int
    label: str
    cluster: ClusterRef | None
    deleted_at: datetime


class DeletedClusterRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class DeletedItem(BaseModel):
    object_type: str
    object_id: uuid.UUID
    version: int
    label: str
    cluster: DeletedClusterRef | None
    deleted_at: datetime

    @field_serializer("deleted_at")
    def _serialize_deleted_at(self, value: datetime) -> str:
        return _iso_utc(value)


class DeletedListResponse(BaseModel):
    items: list[DeletedItem]
    page: int
    page_size: int
    total: int


def build_deleted_item(record: DeletedRecord) -> DeletedItem:
    """Serialise an aggregate row into the Contract ``DeletedItem`` shape."""
    cluster = (
        None
        if record.cluster is None
        else DeletedClusterRef(
            id=record.cluster.id, code=record.cluster.code, name=record.cluster.name
        )
    )
    return DeletedItem(
        object_type=record.object_type,
        object_id=record.object_id,
        version=record.version,
        label=record.label,
        cluster=cluster,
        deleted_at=record.deleted_at,
    )