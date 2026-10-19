"""API Key management endpoints (Contract §4, DR-311).

Routes stay thin: validation via schemas, ``USER_ADMIN`` enforcement and response
shaping; all business rules live in :mod:`app.services.api_key`. Every endpoint
reuses the ``USER_ADMIN`` capability — no new permission or role is introduced.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import Operator
from app.core.db import get_db
from app.core.errors import NotFound
from app.core.permissions import Permission, require_permission
from app.schemas.api_keys import (
    ApiKeyCreateEnvelope,
    ApiKeyCreateRequest,
    ApiKeyCreateRow,
    ApiKeyEnvelope,
    ApiKeyListResponse,
    ApiKeySort,
    ApiKeyStatus,
    SortOrder,
    build_api_key_row,
)
from app.services import api_key as api_key_service

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def _parse_uuid(value: str) -> uuid.UUID:
    """A non-UUID path segment is a 404 (Contract §4.2/§4.4)."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise NotFound() from exc


@router.get("", response_model=ApiKeyListResponse)
def list_api_keys(
    user_id: uuid.UUID | None = Query(default=None),
    status: ApiKeyStatus | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: ApiKeySort = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    current_operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> ApiKeyListResponse:
    """List keys with user/status/q filters, paging and sorting."""
    del current_operator  # authentication/authorisation is the only use here
    rows, total = api_key_service.list_api_keys(
        db,
        user_id=user_id,
        status=status,
        q=q,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    now = datetime.now(timezone.utc)
    return ApiKeyListResponse(
        items=[
            build_api_key_row(
                api_key, username=username, created_by_username=creator, now=now
            )
            for api_key, username, creator in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=ApiKeyCreateEnvelope, status_code=201)
def create_api_key(
    payload: ApiKeyCreateRequest,
    operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> ApiKeyCreateEnvelope:
    """Create a key (201) and return the plaintext exactly once."""
    api_key, username, creator, plaintext = api_key_service.create_api_key(
        db,
        operator,
        user_id=payload.user_id,
        label=payload.label,
        validity_days=payload.validity_days,
    )
    now = datetime.now(timezone.utc)
    row = build_api_key_row(
        api_key, username=username, created_by_username=creator, now=now
    )
    create_row = ApiKeyCreateRow(**row.model_dump(), plaintext=plaintext)
    return ApiKeyCreateEnvelope(api_key=create_row)


@router.get("/{api_key_id}", response_model=ApiKeyEnvelope)
def get_api_key(
    api_key_id: str,
    current_operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> ApiKeyEnvelope:
    """Key detail; a non-UUID or unknown id is 404."""
    del current_operator  # authentication/authorisation is the only use here
    row = api_key_service.get_api_key(db, _parse_uuid(api_key_id))
    if row is None:
        raise NotFound()
    api_key, username, creator = row
    now = datetime.now(timezone.utc)
    return ApiKeyEnvelope(
        api_key=build_api_key_row(
            api_key, username=username, created_by_username=creator, now=now
        )
    )


@router.post("/{api_key_id}/revoke", response_model=ApiKeyEnvelope)
def revoke_api_key(
    api_key_id: str,
    operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> ApiKeyEnvelope:
    """Revoke a key (200). Already-revoked is 409 ``already_revoked``."""
    api_key, username, creator = api_key_service.revoke_api_key(
        db, operator, _parse_uuid(api_key_id)
    )
    now = datetime.now(timezone.utc)
    return ApiKeyEnvelope(
        api_key=build_api_key_row(
            api_key, username=username, created_by_username=creator, now=now
        )
    )