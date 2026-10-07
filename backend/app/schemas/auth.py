"""Authentication request/response schemas (Contract §4).

Responses are built from ORM objects through these schemas; ``password_hash`` is
never part of any schema, so it cannot leak into a response body.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, field_serializer, field_validator

from app.core.permissions import Role, permissions_for
from app.models.user import User
from app.services.auth import is_valid_username, normalize_username


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("username is required")
        normalized = normalize_username(value)
        if not is_valid_username(normalized):
            raise ValueError("username format is invalid")
        return normalized

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("password is required")
        return value


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    role: str
    status: str
    permissions: list[str]


class LoginResponse(BaseModel):
    user: UserOut
    expires_at: datetime

    @field_serializer("expires_at")
    def _serialize_expires_at(self, value: datetime) -> str:
        """Render absolute UTC as ISO-8601 with an explicit +00:00 offset."""
        return value.astimezone(timezone.utc).isoformat()


class MeResponse(BaseModel):
    user: UserOut


def build_user_out(user: User) -> UserOut:
    """Serialise a user without any credential material and with sorted caps."""
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        status=user.status,
        permissions=permissions_for(Role(user.role)),
    )