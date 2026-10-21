"""Cluster access scope (F026, Contract §9.6; DB-D420).

The scope is a request-level projection of the authorization facts:

* ADMIN -> ``unrestricted`` (never reads authorization rows);
* non-ADMIN -> the set of Cluster ids with an ACTIVE authorization whose Cluster
  is not soft-deleted (an empty set means deny-by-default).

F026 deliberately does **not** wire this dependency into any existing business
route; F027 will consume it. Resolution runs once per request, is not cached
across requests, and uses the request's own Session so a grant/revoke/role change
is visible on the next request (including API Keys).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import ColumnElement, false, select, true
from sqlalchemy.orm import Session

from app.core.auth import Operator, get_current_operator
from app.core.db import get_db
from app.core.permissions import Role
from app.models.cluster import Cluster
from app.models.user_cluster_authorization import UserClusterAuthorization


@dataclass(frozen=True)
class AccessScope:
    """Resolved cluster visibility for one request."""

    unrestricted: bool
    cluster_ids: frozenset[uuid.UUID]

    def allows(self, cluster_id: uuid.UUID) -> bool:
        if self.unrestricted:
            return True
        return cluster_id in self.cluster_ids

    def cluster_predicate(self, column: ColumnElement[bool]):
        """SQL predicate for a Cluster id column (F027 consumer)."""
        if self.unrestricted:
            return true()
        if not self.cluster_ids:
            return false()
        return column.in_(self.cluster_ids)

    def sorted_cluster_ids(self) -> list[uuid.UUID]:
        return sorted(self.cluster_ids)


def resolve_access_scope(db: Session, operator: Operator) -> AccessScope:
    """Resolve the operator's scope from committed state (no caching)."""
    if operator.role is Role.ADMIN:
        return AccessScope(unrestricted=True, cluster_ids=frozenset())

    statement = (
        select(UserClusterAuthorization.cluster_id)
        .join(Cluster, Cluster.id == UserClusterAuthorization.cluster_id)
        .where(
            UserClusterAuthorization.user_id == operator.user_id,
            UserClusterAuthorization.revoked_at.is_(None),
            Cluster.deleted_at.is_(None),
        )
        .distinct()
    )
    cluster_ids = frozenset(db.execute(statement).scalars().all())
    return AccessScope(unrestricted=False, cluster_ids=cluster_ids)


def get_access_scope(
    request: Request,
    operator: Operator = Depends(get_current_operator),
    db: Session = Depends(get_db),
) -> AccessScope:
    """FastAPI dependency: resolve once per request and reuse on the request."""
    cached = getattr(request.state, "access_scope", None)
    if isinstance(cached, AccessScope):
        return cached
    scope = resolve_access_scope(db, operator)
    request.state.access_scope = scope
    return scope
