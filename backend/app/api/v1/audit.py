"""Audit query endpoint (Contract §2, DR-213).

Read-only: the route validates query parameters, enforces ``AUDIT_READ`` and
shapes the response. There is no update/delete/clear endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import Operator
from app.core.db import get_db
from app.core.permissions import Permission, require_permission
from app.schemas.audit import (
    AuditAction,
    AuditListResponse,
    AuditObjectType,
    AuditSort,
    SortOrder,
    build_audit_row,
)
from app.services import audit_query as audit_query_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditListResponse)
def list_audit(
    operator: str | None = Query(default=None),
    object_type: AuditObjectType | None = Query(default=None),
    object_id: uuid.UUID | None = Query(default=None),
    action: AuditAction | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: AuditSort = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    current_operator: Operator = Depends(require_permission(Permission.AUDIT_READ)),
    db: Session = Depends(get_db),
) -> AuditListResponse:
    """Full audit query, AND-combined filters, stable ordering (Contract §2)."""
    del current_operator  # authentication/authorisation is the only use here
    rows, total = audit_query_service.list_audit(
        db,
        operator=operator,
        object_type=object_type,
        object_id=object_id,
        action=action,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return AuditListResponse(
        items=[build_audit_row(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )