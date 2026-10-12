"""User / account management schemas (Contract §4).

``UserRow`` never contains ``password_hash`` or any credential material; there is
no schema field for it and no endpoint returns the credential store. Request
schemas are ``extra="forbid"`` so read-only/unknown fields (including
``username``/``password_hash`` on PATCH) are rejected with 422.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.models.user import User

UserRole = Literal["VIEWER", "EDITOR", "ADMIN"]
UserStatusValue = Literal["ACTIVE", "DISABLED"]
UserSort = Literal["username", "role", "status", "created_at", "updated_at"]
SortOrder = Literal["asc", "desc"]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class UserRow(BaseModel):
    id: uuid.UUID
    username: str
    role: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_timestamp(self, value: datetime) -> str:
        return _iso_utc(value)


class UserListResponse(BaseModel):
    items: list[UserRow]
    page: int
    page_size: int
    total: int


class UserEnvelope(BaseModel):
    user: UserRow


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    role: UserRole


class UserUpdateRequest(BaseModel):
    """PATCH body: ``version`` is mandatory; at least one of role/status."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    role: UserRole | None = None
    status: UserStatusValue | None = None

    @model_validator(mode="after")
    def _require_change(self) -> "UserUpdateRequest":
        if self.role is None and self.status is None:
            raise ValueError("at least one of role or status is required")
        return self


def build_user_row(user: User) -> UserRow:
    """Serialise a user without any credential material."""
    return UserRow(
        id=user.id,
        username=user.username,
        role=user.role,
        status=user.status,
        version=user.version,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )