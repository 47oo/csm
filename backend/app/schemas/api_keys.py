"""API Key schemas (Contract §2–§4).

``ApiKeyRow`` never contains ``key_hash`` or the plaintext. The plaintext field
appears **only** on the create (201) envelope and nowhere else.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

ApiKeyStatus = Literal["ACTIVE", "REVOKED", "EXPIRED"]
ApiKeySort = Literal["created_at", "expires_at", "label"]
SortOrder = Literal["asc", "desc"]

VALIDITY_DEFAULT_DAYS = 90
VALIDITY_MIN_DAYS = 1
VALIDITY_MAX_DAYS = 365


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def derive_status(
    revoked_at: datetime | None, expires_at: datetime, *, now: datetime
) -> ApiKeyStatus:
    """Derive the row status: REVOKED > EXPIRED > ACTIVE (Contract §2)."""
    if revoked_at is not None:
        return "REVOKED"
    if expires_at <= now:
        return "EXPIRED"
    return "ACTIVE"


class ApiKeyRow(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    label: str
    status: ApiKeyStatus
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    created_by: uuid.UUID
    created_by_username: str

    @field_serializer("created_at", "expires_at", "revoked_at")
    def _serialize_timestamp(self, value: datetime | None) -> str | None:
        return None if value is None else _iso_utc(value)


class ApiKeyCreateRow(ApiKeyRow):
    """Create response row: adds the one-time ``plaintext``."""

    plaintext: str


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyRow]
    page: int
    page_size: int
    total: int


class ApiKeyEnvelope(BaseModel):
    api_key: ApiKeyRow


class ApiKeyCreateEnvelope(BaseModel):
    api_key: ApiKeyCreateRow


class ApiKeyCreateRequest(BaseModel):
    """Create body. ``validity_days`` default 90; explicit ``null`` -> 422."""

    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    label: str
    validity_days: int = Field(
        default=VALIDITY_DEFAULT_DAYS,
        ge=VALIDITY_MIN_DAYS,
        le=VALIDITY_MAX_DAYS,
        strict=True,
    )


def build_api_key_row(
    api_key,
    *,
    username: str,
    created_by_username: str,
    now: datetime,
) -> ApiKeyRow:
    """Serialise an ``api_keys`` row without any credential material."""
    return ApiKeyRow(
        id=api_key.id,
        user_id=api_key.user_id,
        username=username,
        label=api_key.label,
        status=derive_status(api_key.revoked_at, api_key.expires_at, now=now),
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        revoked_at=api_key.revoked_at,
        created_by=api_key.created_by,
        created_by_username=created_by_username,
    )