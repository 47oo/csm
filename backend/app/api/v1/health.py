"""Operational health endpoints (architecture §1.4).

These are NOT business API contract; responses are intentionally minimal and
never include connection strings or credentials.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def liveness() -> dict[str, str]:
    """Liveness probe: does not touch the database."""
    return {"status": "ok", "service": "csm-backend"}


@router.get("/ready")
def readiness(db: Session = Depends(get_db)):
    """Readiness probe: executes ``SELECT 1``.

    Returns 200 when the database is reachable, 503 with a fixed body otherwise.
    The error body never exposes the connection string.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "db": "down"},
        )
    return {"status": "ready", "db": "up"}