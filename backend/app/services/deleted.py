"""Deleted-object aggregate service (Contract §3, DR-216/DR-217).

Read-only cross-type aggregation over the eight soft-deletable tables. Each
branch selects ``deleted_at IS NOT NULL`` rows; the branches are combined with
``UNION ALL`` and sorted by ``deleted_at`` then ``object_type``/``object_id`` for
a stable order at equal timestamps.

Object-ownership is deliberately resolved without the soft-delete default
filter: the owning Cluster of a deleted Resource is still shown even when that
Cluster is itself soft-deleted (the reference is historical, not a query).
"""

from __future__ import annotations

from sqlalchemy import String, cast, func, literal, select, union_all
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.cluster import Cluster
from app.models.interface import Interface
from app.models.ip_address import IPAddress
from app.models.ip_pool import IPPool
from app.models.network import Network
from app.models.resource import Resource
from app.models.service import Service
from app.models.service_endpoint import ServiceEndpoint
from app.schemas.deleted import ClusterRef, DeletedRecord

SORT_FIELDS = ("deleted_at",)
ORDERS = ("asc", "desc")


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _null_uuid():
    return cast(literal(None), UUID(as_uuid=True))


def _branches():
    """Yield ``(object_type, select_stmt)`` for the eight soft-deletable types."""
    c = Cluster.__table__
    r = Resource.__table__
    i = Interface.__table__
    n = Network.__table__
    p = IPPool.__table__
    a = IPAddress.__table__
    s = Service.__table__
    e = ServiceEndpoint.__table__

    def base(table, object_type: str, label, cluster_id):
        return select(
            literal(object_type).label("object_type"),
            table.c.id.label("object_id"),
            table.c.version.label("version"),
            label.label("label"),
            cluster_id.label("cluster_id"),
            table.c.deleted_at.label("deleted_at"),
        ).where(table.c.deleted_at.is_not(None))

    yield "cluster", base(c, "cluster", c.c.code, _null_uuid())
    yield "resource", base(r, "resource", r.c.hostname, r.c.cluster_id)
    yield (
        "interface",
        base(i, "interface", i.c.name, r.c.cluster_id).select_from(
            i.join(r, i.c.resource_id == r.c.id)
        ),
    )
    yield "network", base(n, "network", n.c.name, n.c.cluster_id)
    yield (
        "ip_pool",
        base(p, "ip_pool", p.c.name, n.c.cluster_id).select_from(
            p.join(n, p.c.network_id == n.c.id)
        ),
    )
    yield "ip_address", base(
        a, "ip_address", func.host(a.c.address), a.c.cluster_id
    )
    yield (
        "service",
        base(s, "service", s.c.name, r.c.cluster_id).select_from(
            s.join(r, s.c.resource_id == r.c.id)
        ),
    )
    yield (
        "service_endpoint",
        base(
            e,
            "service_endpoint",
            func.concat(e.c.protocol, literal(":"), cast(e.c.port, String)),
            a.c.cluster_id,
        ).select_from(e.join(a, e.c.ip_address_id == a.c.id)),
    )


def list_deleted(
    db: Session,
    *,
    object_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "deleted_at",
    order: str = "desc",
) -> tuple[list[DeletedRecord], int]:
    """Return the aggregate page of soft-deleted objects plus the total."""
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")

    aggregate = union_all(*(statement for _, statement in _branches())).subquery(
        "deleted_objects"
    )
    filters = []
    if object_type is not None:
        filters.append(aggregate.c.object_type == object_type)

    cluster_alias = Cluster.__table__.alias("deleted_cluster")
    deleted_at_order = (
        aggregate.c.deleted_at.desc()
        if order == "desc"
        else aggregate.c.deleted_at.asc()
    )
    statement = (
        select(
            aggregate.c.object_type,
            aggregate.c.object_id,
            aggregate.c.version,
            aggregate.c.label,
            cluster_alias.c.id.label("cluster_id"),
            cluster_alias.c.code.label("cluster_code"),
            cluster_alias.c.name.label("cluster_name"),
            aggregate.c.deleted_at,
        )
        .select_from(
            aggregate.outerjoin(
                cluster_alias, aggregate.c.cluster_id == cluster_alias.c.id
            )
        )
        .where(*filters)
        .order_by(
            deleted_at_order,
            aggregate.c.object_type.asc(),
            aggregate.c.object_id.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(aggregate).where(*filters)

    options = {"include_deleted": True}
    rows = db.execute(statement, execution_options=options).all()
    total = int(
        db.execute(total_statement, execution_options=options).scalar_one()
    )

    records = [
        DeletedRecord(
            object_type=row.object_type,
            object_id=row.object_id,
            version=int(row.version),
            label=row.label,
            cluster=(
                None
                if row.cluster_id is None
                else ClusterRef(
                    id=row.cluster_id, code=row.cluster_code, name=row.cluster_name
                )
            ),
            deleted_at=row.deleted_at,
        )
        for row in rows
    ]
    return records, total