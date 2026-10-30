"""F013 Dashboard aggregation (Contract §3, DR-181..DR-183, DR-188).

Global undeleted counts (including ``INACTIVE`` rows) plus a paginated list of
undeleted Networks carrying their F010 capacity. Capacity is **consumed** from
:mod:`app.services.ip_capacity` (``network_capacity`` / ``auto_pools_capacity``)
— this module never recomputes the §20 formula and never clamps ``remaining``.

Read-only: no writes, no Audit, no side effects. ``counts`` is global and is not
affected by the ``page``/``page_size`` of the ``networks`` list.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models.cluster import Cluster
from app.models.network import Network
from app.models.resource import Resource
from app.services import ip_capacity, scope_filters

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _counts(db: "Session", scope=None) -> dict[str, int]:
    """Return the visible undeleted counts (INACTIVE rows included)."""
    clusters = int(
        db.execute(
            select(func.count())
            .select_from(Cluster)
            .where(scope_filters.cluster_predicate(scope, Cluster.id))
        ).scalar_one()
    )
    resources = int(
        db.execute(
            select(func.count())
            .select_from(Resource)
            .where(scope_filters.cluster_predicate(scope, Resource.cluster_id))
        ).scalar_one()
    )
    bare_metal = int(
        db.execute(
            select(func.count())
            .select_from(Resource)
            .where(
                Resource.resource_type == "BARE_METAL",
                scope_filters.cluster_predicate(scope, Resource.cluster_id),
            )
        ).scalar_one()
    )
    virtual_machines = int(
        db.execute(
            select(func.count())
            .select_from(Resource)
            .where(
                Resource.resource_type == "VIRTUAL_MACHINE",
                scope_filters.cluster_predicate(scope, Resource.cluster_id),
            )
        ).scalar_one()
    )
    networks = int(
        db.execute(
            select(func.count())
            .select_from(Network)
            .where(scope_filters.cluster_predicate(scope, Network.cluster_id))
        ).scalar_one()
    )
    return {
        "clusters": clusters,
        "resources": resources,
        "bare_metal": bare_metal,
        "virtual_machines": virtual_machines,
        "networks": networks,
    }


def _page_networks(
    db: "Session", page: int, page_size: int, scope=None
) -> tuple[list[Network], int]:
    scope_filter = scope_filters.cluster_predicate(scope, Network.cluster_id)
    statement = (
        select(Network)
        .where(scope_filter)
        .order_by(Network.created_at.desc(), Network.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_statement = (
        select(func.count()).select_from(Network).where(scope_filter)
    )
    items = list(db.execute(statement).scalars().all())
    total = int(db.execute(total_statement).scalar_one())
    return items, total


def _clusters_for(
    db: "Session", cluster_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Cluster]:
    ids = set(cluster_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Cluster).where(Cluster.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def get_dashboard(
    db: "Session", *, page: int = 1, page_size: int = 20, scope=None
) -> dict[str, Any]:
    """Return ``counts`` and the paginated ``networks`` block (Contract §3)."""
    counts = _counts(db, scope)
    networks, total = _page_networks(db, page, page_size, scope)
    cluster_map = _clusters_for(db, [network.cluster_id for network in networks])
    # F039: one pre-fetch for the whole page; the per-row calls below only
    # assemble §20 values from it (no per-Network / per-pool statements).
    context = ip_capacity.load_capacity_context(db, networks)

    items: list[dict[str, Any]] = []
    for network in networks:
        cluster = cluster_map.get(network.cluster_id)
        capacity = ip_capacity.network_capacity(db, network, context=context)
        auto_pools = ip_capacity.auto_pools_capacity(db, network, context=context)
        items.append(
            {
                "network": {
                    "id": network.id,
                    "name": network.name,
                    "cidr": str(network.cidr),
                    "status": network.status,
                    "auto_allocate": network.auto_allocate,
                    "cluster": {
                        "id": network.cluster_id,
                        "code": cluster.code if cluster is not None else "",
                        "name": cluster.name if cluster is not None else "",
                    },
                },
                "capacity": {
                    "allocatable_total": capacity["allocatable_total"],
                    "occupied": capacity["occupied"],
                    "remaining": capacity["remaining"],
                },
                "auto_pools": [
                    {
                        "ip_pool": {
                            "id": pool["ip_pool"].id,
                            "name": pool["ip_pool"].name,
                            "start_address": str(pool["ip_pool"].start_address),
                            "end_address": str(pool["ip_pool"].end_address),
                        },
                        "allocatable_total": pool["allocatable_total"],
                        "occupied": pool["occupied"],
                        "remaining": pool["remaining"],
                    }
                    for pool in auto_pools
                ],
            }
        )
    return {"counts": counts, "networks": {"items": items, "total": total}}