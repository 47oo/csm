"""User / account management endpoints (Contract §4, DR-218).

Routes stay thin: parameter validation, ``USER_ADMIN`` enforcement and response
shaping; all account rules live in :mod:`app.services.user`. There is no
self-registration, no physical delete and no password change/reset endpoint.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import Operator
from app.core.db import get_db
from app.core.errors import NotFound
from app.core.permissions import Permission, require_permission
from app.schemas.users import (
    SortOrder,
    UserCreateRequest,
    UserEnvelope,
    UserListResponse,
    UserRole,
    UserSort,
    UserStatusValue,
    UserUpdateRequest,
    build_user_row,
)
from app.services import user as user_service

router = APIRouter(prefix="/users", tags=["users"])


def _parse_uuid(value: str) -> uuid.UUID:
    """A non-UUID path segment is a 404 (Contract §4.2)."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise NotFound() from exc


@router.get("", response_model=UserListResponse)
def list_users(
    role: UserRole | None = Query(default=None),
    status: UserStatusValue | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: UserSort = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    current_operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> UserListResponse:
    """List accounts with role/status/q filters, paging and sorting."""
    del current_operator  # authentication/authorisation is the only use here
    users, total = user_service.list_users(
        db,
        role=role,
        status=status,
        q=q,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return UserListResponse(
        items=[build_user_row(user) for user in users],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=UserEnvelope, status_code=201)
def create_user(
    payload: UserCreateRequest,
    operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> UserEnvelope:
    """Create an account (201) and write a same-transaction CREATE audit row."""
    user = user_service.create_user(
        db,
        operator,
        username=payload.username,
        password=payload.password,
        role=payload.role,
    )
    return UserEnvelope(user=build_user_row(user))


@router.get("/{user_id}", response_model=UserEnvelope)
def get_user(
    user_id: str,
    current_operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> UserEnvelope:
    """Account detail; a non-UUID or unknown id is 404."""
    del current_operator  # authentication/authorisation is the only use here
    user = user_service.get_user(db, _parse_uuid(user_id))
    if user is None:
        raise NotFound()
    return UserEnvelope(user=build_user_row(user))


@router.patch("/{user_id}", response_model=UserEnvelope)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> UserEnvelope:
    """Update role/status with a mandatory ``version`` optimistic lock."""
    user = user_service.update_user(
        db,
        operator,
        _parse_uuid(user_id),
        expected_version=payload.version,
        role=payload.role,
        status=payload.status,
    )
    return UserEnvelope(user=build_user_row(user))