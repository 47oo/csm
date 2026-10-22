"""F013 global search endpoint (Contract §2, six query parameters).

Read-only; READ for all roles. ``deleted=include|only`` additionally requires
VIEW_DELETED (ADMIN). Routes stay thin: permission check, response shaping and
delegation to :mod:`app.services.search`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.access_scope import AccessScope, get_access_scope
from app.core.auth import Operator
from app.core.db import get_db
from app.core.errors import Forbidden
from app.core.permissions import Permission, require_permission, role_has_permission
from app.schemas.search import DeletedMode, ObjectType, SearchListResponse
from app.services import search as search_service

router = APIRouter(prefix="/search", tags=["search"])


def _require_view_deleted(operator: Operator) -> None:
    if not role_has_permission(operator.role, Permission.VIEW_DELETED):
        raise Forbidden(reason="permission")


@router.get("", response_model=SearchListResponse)
def global_search(
    q: str = Query(description="Mandatory search string (trimmed, 1-255 code points)"),
    object_type: ObjectType | None = Query(default=None, alias="type"),
    deleted: DeletedMode = Query(default="exclude"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operator: Operator = Depends(require_permission(Permission.READ)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> SearchListResponse:
    """Cross-domain typed search (Contract §2); empty ``q`` -> 422 field ``q``."""
    if deleted in ("include", "only"):
        _require_view_deleted(operator)
    items, total = search_service.search(
        db,
        q=q,
        object_type=object_type,
        deleted=deleted,
        page=page,
        page_size=page_size,
        scope=scope,
    )
    return SearchListResponse(
        items=items, page=page, page_size=page_size, total=total
    )