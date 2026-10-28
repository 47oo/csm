"""F013 Dashboard endpoint (Contract §3).

Read-only; READ for all roles. No ``deleted`` parameter: counts and capacity are
always the undeleted scope. Routes stay thin and delegate to
:mod:`app.services.dashboard`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.access_scope import AccessScope, get_access_scope
from app.core.auth import Operator
from app.core.db import get_db
from app.core.permissions import Permission, require_permission
from app.schemas.dashboard import DashboardResponse
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operator: Operator = Depends(require_permission(Permission.READ)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    """Global counts + per-Network capacity (Contract §3); ``counts`` is global."""
    data = dashboard_service.get_dashboard(
        db, page=page, page_size=page_size, scope=scope
    )
    networks = data["networks"]
    return DashboardResponse(
        counts=data["counts"],
        networks={
            "items": networks["items"],
            "page": page,
            "page_size": page_size,
            "total": networks["total"],
        },
    )