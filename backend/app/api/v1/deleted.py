"""Deleted-object aggregate endpoint (Contract §3, DR-216/DR-217).

Read-only across the eight soft-deletable object types; recovery reuses each
domain's own ``.../restore`` endpoint (there is no unified write endpoint).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import Operator
from app.core.db import get_db
from app.core.permissions import Permission, require_permission
from app.schemas.deleted import (
    DeletedListResponse,
    DeletedObjectType,
    DeletedSort,
    SortOrder,
    build_deleted_item,
)
from app.services import deleted as deleted_service

router = APIRouter(prefix="/deleted", tags=["deleted"])


@router.get("", response_model=DeletedListResponse)
def list_deleted(
    object_type: DeletedObjectType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: DeletedSort = Query(default="deleted_at"),
    order: SortOrder = Query(default="desc"),
    current_operator: Operator = Depends(require_permission(Permission.VIEW_DELETED)),
    db: Session = Depends(get_db),
) -> DeletedListResponse:
    """Aggregate soft-deleted objects with stable ordering (Contract §3)."""
    del current_operator  # authentication/authorisation is the only use here
    records, total = deleted_service.list_deleted(
        db,
        object_type=object_type,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return DeletedListResponse(
        items=[build_deleted_item(record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
    )