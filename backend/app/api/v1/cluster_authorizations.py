"""Cluster authorization endpoints (F026 Contract §3–§7).

Three ADMIN-only endpoints. Routes are thin: path/query validation, permission
enforcement and response shaping; business rules live in
:mod:`app.services.cluster_authorization`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.auth import Operator
from app.core.db import get_db
from app.core.errors import NotFound, ValidationError
from app.core.permissions import Permission, require_permission
from app.schemas.cluster_authorizations import (
    AuthorizationSort,
    AuthorizationStatus,
    ClusterAuthorizationCreateRequest,
    ClusterAuthorizationEnvelope,
    ClusterAuthorizationListResponse,
    SortOrder,
    build_cluster_authorization_row,
)
from app.services import cluster_authorization as authorization_service

router = APIRouter(tags=["cluster-authorizations"])

_ALLOWED_QUERY_PARAMS = {
    "status",
    "cluster_id",
    "q",
    "page",
    "page_size",
    "sort",
    "order",
}


def _parse_uuid(value: str) -> uuid.UUID:
    """A non-UUID path segment is a 404 (Contract §5.2 P-1)."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise NotFound() from exc


def _reject_unknown_query(request: Request) -> None:
    unknown = sorted(set(request.query_params.keys()) - _ALLOWED_QUERY_PARAMS)
    if unknown:
        raise ValidationError(
            details={
                "fields": [
                    {"field": name, "message": "unknown query parameter"}
                    for name in unknown
                ]
            }
        )


def _row(row) -> ClusterAuthorizationEnvelope:
    authorization, user, cluster, granted_by_username, revoked_by_username = row
    return ClusterAuthorizationEnvelope(
        cluster_authorization=build_cluster_authorization_row(
            authorization,
            user=user,
            cluster=cluster,
            granted_by_username=granted_by_username,
            revoked_by_username=revoked_by_username,
        )
    )


@router.get(
    "/users/{user_id}/cluster-authorizations",
    response_model=ClusterAuthorizationListResponse,
)
def list_cluster_authorizations(
    user_id: str,
    request: Request,
    status: AuthorizationStatus | None = Query(default=None),
    cluster_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: AuthorizationSort = Query(default="granted_at"),
    order: SortOrder = Query(default="desc"),
    current_operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> ClusterAuthorizationListResponse:
    del current_operator  # authentication/authorisation is the only use here
    _reject_unknown_query(request)
    rows, total = authorization_service.list_authorizations(
        db,
        user_id=_parse_uuid(user_id),
        status=status,
        cluster_id=cluster_id,
        q=q,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return ClusterAuthorizationListResponse(
        items=[_row(row).cluster_authorization for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/users/{user_id}/cluster-authorizations",
    response_model=ClusterAuthorizationEnvelope,
    status_code=201,
)
def grant_cluster_authorization(
    user_id: str,
    payload: ClusterAuthorizationCreateRequest,
    operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> ClusterAuthorizationEnvelope:
    row = authorization_service.grant_authorization(
        db,
        operator,
        user_id=_parse_uuid(user_id),
        cluster_id=payload.cluster_id,
    )
    return _row(row)


@router.post(
    "/cluster-authorizations/{authorization_id}/revoke",
    response_model=ClusterAuthorizationEnvelope,
)
def revoke_cluster_authorization(
    authorization_id: str,
    operator: Operator = Depends(require_permission(Permission.USER_ADMIN)),
    db: Session = Depends(get_db),
) -> ClusterAuthorizationEnvelope:
    row = authorization_service.revoke_authorization(
        db,
        operator,
        _parse_uuid(authorization_id),
    )
    return _row(row)
