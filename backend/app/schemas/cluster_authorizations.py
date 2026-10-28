"""Cluster authorization schemas (F026 Contract §2–§5)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer

from app.models.cluster import Cluster
from app.models.user import User
from app.models.user_cluster_authorization import UserClusterAuthorization

AuthorizationStatus = Literal["ACTIVE", "REVOKED"]
AuthorizationSort = Literal["granted_at", "revoked_at"]
SortOrder = Literal["asc", "desc"]


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


class UserRef(BaseModel):
    id: uuid.UUID
    username: str
    role: str
    status: str


class ClusterRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: str
    deleted_at: datetime | None

    @field_serializer("deleted_at")
    def _serialize_deleted_at(self, value: datetime | None) -> str | None:
        return _iso_utc(value)


class ClusterAuthorizationRow(BaseModel):
    id: uuid.UUID
    user: UserRef
    cluster: ClusterRef
    status: AuthorizationStatus
    effective: bool
    granted_at: datetime
    granted_by: uuid.UUID | None
    granted_by_username: str | None
    revoked_at: datetime | None
    revoked_by: uuid.UUID | None
    revoked_by_username: str | None

    @field_serializer("granted_at", "revoked_at")
    def _serialize_timestamps(self, value: datetime | None) -> str | None:
        return _iso_utc(value)


class ClusterAuthorizationListResponse(BaseModel):
    items: list[ClusterAuthorizationRow]
    page: int
    page_size: int
    total: int


class ClusterAuthorizationEnvelope(BaseModel):
    cluster_authorization: ClusterAuthorizationRow


class ClusterAuthorizationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: uuid.UUID


def build_cluster_authorization_row(
    authorization: UserClusterAuthorization,
    *,
    user: User,
    cluster: Cluster,
    granted_by_username: str | None,
    revoked_by_username: str | None,
) -> ClusterAuthorizationRow:
    status: AuthorizationStatus = (
        "ACTIVE" if authorization.revoked_at is None else "REVOKED"
    )
    return ClusterAuthorizationRow(
        id=authorization.id,
        user=UserRef(
            id=user.id,
            username=user.username,
            role=user.role,
            status=user.status,
        ),
        cluster=ClusterRef(
            id=cluster.id,
            code=cluster.code,
            name=cluster.name,
            status=cluster.status,
            deleted_at=cluster.deleted_at,
        ),
        status=status,
        effective=status == "ACTIVE" and cluster.deleted_at is None,
        granted_at=authorization.granted_at,
        granted_by=authorization.granted_by,
        granted_by_username=granted_by_username,
        revoked_at=authorization.revoked_at,
        revoked_by=authorization.revoked_by,
        revoked_by_username=revoked_by_username,
    )
