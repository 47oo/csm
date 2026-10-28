"""F027 scope predicates for business services (requirements §23.2).

The request-level :class:`app.core.access_scope.AccessScope` is the single
authority for Cluster visibility.  Every business read/write path applies one
of the predicates below to the objects it already queries; there is no second
resolver and no cache.  ``scope=None`` is only used by direct service callers
(tests/imports) and behaves as unrestricted, exactly like an ADMIN request.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, exists, select, true

from app.core.access_scope import AccessScope
from app.models.interface import Interface
from app.models.ip_pool import IPPool
from app.models.resource import Resource
from app.models.service import Service
from app.models.service_endpoint import ServiceEndpoint


def normalize(scope: AccessScope | None) -> AccessScope:
    """Return an explicit scope; internal ``None`` means unrestricted.

    HTTP routes always pass a real ``AccessScope``; ``None`` is only for direct
    service/test calls. New HTTP code must not rely on this default.
    """
    return scope if scope is not None else AccessScope(True, frozenset())


def cluster_predicate(scope: AccessScope | None, column: ColumnElement[bool]):
    return normalize(scope).cluster_predicate(column)


def interface_parent_predicate(scope: AccessScope | None):
    """Interfaces belong to their owning Resource's Cluster."""
    scoped = normalize(scope)
    if scoped.unrestricted:
        return true()
    return exists(
        select(Resource.id).where(
            Resource.id == Interface.resource_id,
            Resource.deleted_at.is_(None),
            scoped.cluster_predicate(Resource.cluster_id),
        )
    )


def service_parent_predicate(scope: AccessScope | None):
    """Services belong to an owning Resource's Cluster."""
    scoped = normalize(scope)
    if scoped.unrestricted:
        return true()
    return Service.resource_id.in_(
        select(Resource.id).where(
            Resource.deleted_at.is_(None),
            scoped.cluster_predicate(Resource.cluster_id),
        )
    )


def pool_predicate(scope: AccessScope | None):
    """Pools belong to a Network's Cluster."""
    scoped = normalize(scope)
    if scoped.unrestricted:
        return true()
    from app.models.network import Network

    return exists(
        select(Network.id).where(
            Network.id == IPPool.network_id,
            Network.deleted_at.is_(None),
            scoped.cluster_predicate(Network.cluster_id),
        )
    )


def service_predicate(scope: AccessScope | None):
    """Endpoints belong to a Service's owning Resource Cluster."""
    scoped = normalize(scope)
    if scoped.unrestricted:
        return true()
    return exists(
        select(Service.id)
        .select_from(Service)
        .join(Resource, Resource.id == Service.resource_id)
        .where(
            Service.id == ServiceEndpoint.service_id,
            Service.deleted_at.is_(None),
            Resource.deleted_at.is_(None),
            scoped.cluster_predicate(Resource.cluster_id),
        )
    )
