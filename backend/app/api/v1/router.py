"""Aggregate API v1 router.

``api_v1_router`` owns the ``/api/v1`` prefix (DR-03); later Features register
their domain routers here without changing the prefix. This module also imports
all models so that ``Base.metadata`` is fully populated for Alembic autogenerate.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    clusters,
    dashboard,
    health,
    imports,
    interfaces,
    ip_addresses,
    ip_pools,
    networks,
    resources,
    search,
    service_endpoints,
    services,
)
from app import models  # noqa: F401  (populate Base.metadata for autogenerate)

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(clusters.router)
api_v1_router.include_router(resources.router)
api_v1_router.include_router(interfaces.router)
api_v1_router.include_router(networks.router)
api_v1_router.include_router(ip_pools.router)
api_v1_router.include_router(ip_addresses.router)
api_v1_router.include_router(ip_addresses.capacity_router)
api_v1_router.include_router(services.router)
api_v1_router.include_router(service_endpoints.router)
api_v1_router.include_router(search.router)
api_v1_router.include_router(dashboard.router)
api_v1_router.include_router(imports.router)