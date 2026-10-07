"""Cluster request/response schemas (Contract §2/§3/§4/§6).

``code_key`` is an internal column and never appears here. ``created_at`` /
``updated_at`` / ``deleted_at`` are serialised as ISO-8601 UTC with an explicit
``+00:00`` offset.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.audit_log import AuditLog
from app.models.cluster import Cluster

ClusterStatus = Literal["ACTIVE", "INACTIVE"]
DeletedMode = Literal["exclude", "include", "only"]
SortField = Literal["code", "name", "status", "created_at", "updated_at"]
SortOrder = Literal["asc", "desc"]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class ClusterOut(BaseModel):
    id: uuid.UUID
    code: str
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


class ClusterListResponse(BaseModel):
    items: list[ClusterOut]
    page: int
    page_size: int
    total: int


class ClusterCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    status: ClusterStatus = "ACTIVE"
    description: str | None = None
    metadata: dict = Field(default_factory=dict)


class ClusterUpdateRequest(BaseModel):
    """PATCH body: omitted fields keep their value; ``code`` is not allowed."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str | None = None
    status: ClusterStatus | None = None
    description: str | None = None
    metadata: dict | None = None


class ClusterEnvelope(BaseModel):
    cluster: ClusterOut


class ActivityItem(BaseModel):
    id: uuid.UUID
    action: str
    operator_user_id: uuid.UUID | None
    operator_username: str
    before_data: dict | None
    after_data: dict | None
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _iso_utc(value)


class ActivityListResponse(BaseModel):
    items: list[ActivityItem]
    page: int
    page_size: int
    total: int


def build_cluster_out(cluster: Cluster) -> ClusterOut:
    """Serialise a Cluster ORM object without exposing ``code_key``."""
    return ClusterOut(
        id=cluster.id,
        code=cluster.code,
        name=cluster.name,
        status=cluster.status,
        description=cluster.description,
        metadata=cluster.meta,
        version=cluster.version,
        created_at=cluster.created_at,
        updated_at=cluster.updated_at,
        deleted_at=cluster.deleted_at,
    )


def build_activity_item(row: AuditLog) -> ActivityItem:
    return ActivityItem(
        id=row.id,
        action=row.action,
        operator_user_id=row.operator_user_id,
        operator_username=row.operator_username,
        before_data=row.before_data,
        after_data=row.after_data,
        created_at=row.created_at,
    )