"""Aggregate API v1 router.

``api_v1_router`` owns the ``/api/v1`` prefix (DR-03); later Features register
their domain routers here without changing the prefix. This module also imports
all models so that ``Base.metadata`` is fully populated for Alembic autogenerate.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, health
from app import models  # noqa: F401  (populate Base.metadata for autogenerate)

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)