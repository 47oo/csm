"""F013 global search (Contract §2, DR-171..DR-178).

Read-only cross-domain search over four typed row sets:

- ``resource``  <- ``resources.hostname`` (ASCII-lower normalised key),
- ``cluster``   <- ``clusters.code_key`` (ASCII-upper) and ``clusters.name``,
- ``ip_address``<- ``ip_addresses.address`` **exact** IPv4 match only,
- ``service``   <- ``services.name_key`` (ASCII-lower).

The row type is part of the dedup key ``(object_type, id)``: ``ip_address`` and
``service`` hits embed their owning ``resource`` instead of synthesising an
extra ``resource`` row (DR-174). Ordering is ``similarity DESC -> object_type
fixed order -> id ASC`` (DR-175); the similarity value itself is never exposed.

Matching uses ``ILIKE '%q%'`` (accelerated by the F013 GIN trigram indexes for
q >= 3 characters); correctness never depends on the index. IP matching is
exact equality (no prefix/trigram fallback, Contract §8.5).

Candidate collection is done per object type and merged in Python; phase-1
volumes are bounded and this keeps the four differently-typed rows readable and
the soft-delete/include semantics uniform. Pagination is applied after the
global merge so ``total`` is exact and paging is stable.
"""

from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import cast, case, func, select
from sqlalchemy.dialects.postgresql import INET

from app.core.errors import ValidationError
from app.models.cluster import Cluster
from app.models.interface import Interface
from app.models.ip_address import IPAddress
from app.models.network import Network
from app.models.resource import Resource
from app.models.service import Service
from app.schemas.search import (
    SearchClusterNested,
    SearchClusterObject,
    SearchIPAddressObject,
    SearchInterfaceNested,
    SearchItem,
    SearchNetworkNested,
    SearchRelatedInterface,
    SearchRelatedIPAddress,
    SearchResourceObject,
    SearchResourceRelated,
    SearchServiceObject,
)
from app.services import normalization, scope_filters

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

Q_MAX_LENGTH = 255
OBJECT_TYPES = ("resource", "cluster", "ip_address", "service")
DELETED_MODES = ("exclude", "include", "only")

# F018 DR-321: at most this many association rows per resource are returned;
# ``related_total`` still carries the pre-truncation count.
RELATED_LIMIT = 10

_TYPE_ORDER = {"resource": 0, "cluster": 1, "ip_address": 2, "service": 3}


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_options(include_deleted: bool) -> dict[str, Any]:
    return {"include_deleted": True} if include_deleted else {}


def validate_q(q: str) -> str:
    """Trim and validate the mandatory search string (Contract §2.5)."""
    if not isinstance(q, str):
        raise _field_error("q", "q is required")
    text = q.strip()
    if not text:
        raise _field_error("q", "q must not be blank")
    if len(text) > Q_MAX_LENGTH:
        raise _field_error("q", f"q must be at most {Q_MAX_LENGTH} characters")
    return text


@dataclass
class _Candidate:
    object_type: str
    object_id: uuid.UUID
    matched_field: str
    matched_value: str
    score: float
    payload: Any


def _apply_deleted(statement, model, deleted: str):  # noqa: ANN001
    """Add an explicit ``only`` filter; ``exclude`` relies on the default filter."""
    if deleted == "only":
        return statement.where(model.deleted_at.is_not(None))
    return statement


def _resource_candidates(
    db: "Session", q_text: str, deleted: str, scope=None
) -> list[_Candidate]:
    q_norm = normalization.hostname_key(q_text)
    pattern = f"%{_escape_like(q_norm)}%"
    score = func.similarity(Resource.hostname, q_norm)
    statement = select(Resource, score).where(
        Resource.hostname.ilike(pattern, escape="\\"),
        scope_filters.cluster_predicate(scope, Resource.cluster_id),
    )
    statement = _apply_deleted(statement, Resource, deleted)
    rows = db.execute(
        statement, execution_options=_query_options(deleted != "exclude")
    ).all()
    return [
        _Candidate("resource", row[0].id, "hostname", row[0].hostname, float(row[1]), row[0])
        for row in rows
    ]


def _cluster_candidates(
    db: "Session", q_text: str, deleted: str, scope=None
) -> list[_Candidate]:
    q_code = normalization.code_key(q_text)
    code_pattern = f"%{_escape_like(q_code)}%"
    name_pattern = f"%{_escape_like(q_text)}%"
    code_hit = Cluster.code_key.ilike(code_pattern, escape="\\")
    name_hit = Cluster.name.ilike(name_pattern, escape="\\")
    score = case(
        (code_hit, func.similarity(Cluster.code_key, q_code)),
        else_=func.similarity(Cluster.name, q_text),
    )
    statement = select(Cluster, score, code_hit.label("code_hit")).where(
        code_hit | name_hit,
        scope_filters.cluster_predicate(scope, Cluster.id),
    )
    statement = _apply_deleted(statement, Cluster, deleted)
    rows = db.execute(
        statement, execution_options=_query_options(deleted != "exclude")
    ).all()
    candidates: list[_Candidate] = []
    for cluster, row_score, is_code in rows:
        if is_code:
            field, value = "code", cluster.code
        else:
            field, value = "name", cluster.name
        candidates.append(
            _Candidate("cluster", cluster.id, field, value, float(row_score), cluster)
        )
    return candidates


def _ip_candidate_address(q_text: str) -> str | None:
    """Return a canonical bare IPv4 host address, or ``None`` if ``q`` is not one."""
    if "/" in q_text:
        return None
    try:
        address = ipaddress.ip_address(q_text)
    except ValueError:
        return None
    if address.version != 4:
        return None
    return str(address)


def _ip_candidates(
    db: "Session", q_text: str, deleted: str, scope=None
) -> list[_Candidate]:
    address = _ip_candidate_address(q_text)
    if address is None:
        return []
    statement = select(IPAddress).where(
        IPAddress.address == cast(address, INET),
        scope_filters.cluster_predicate(scope, IPAddress.cluster_id),
    )
    statement = _apply_deleted(statement, IPAddress, deleted)
    rows = db.execute(
        statement, execution_options=_query_options(deleted != "exclude")
    ).scalars().all()
    return [
        _Candidate("ip_address", ip.id, "address", str(ip.address), 1.0, ip)
        for ip in rows
    ]


def _service_candidates(
    db: "Session", q_text: str, deleted: str, scope=None
) -> list[_Candidate]:
    q_norm = normalization.service_name_key(q_text)
    pattern = f"%{_escape_like(q_norm)}%"
    score = func.similarity(Service.name_key, q_norm)
    statement = select(Service, score).where(
        Service.name_key.ilike(pattern, escape="\\"),
        scope_filters.service_parent_predicate(scope),
    )
    statement = _apply_deleted(statement, Service, deleted)
    rows = db.execute(
        statement, execution_options=_query_options(deleted != "exclude")
    ).all()
    return [
        _Candidate("service", row[0].id, "name", row[0].name, float(row[1]), row[0])
        for row in rows
    ]


def _load_related(
    db: "Session", resource_ids: set[uuid.UUID], deleted: str, scope=None
) -> dict[uuid.UUID, tuple[list[SearchResourceRelated], int]]:
    """Load ``resource.related`` for the given result-row Resource IDs (F018).

    One bounded JOIN query (no N+1) over ``interfaces -> ip_addresses ->
    networks`` ordered by ``interface.name COLLATE "C" -> ip_address.address
    (PG ``inet`` numeric order) -> ip_address.id`` (DR-319/DR-322). Soft-delete
    follows the result-row ``deleted`` mode: ``exclude`` filters deleted
    associations, ``include``/``only`` show them (endpoint already gates
    ``VIEW_DELETED``). It deliberately does **not** reuse the ``_build_items``
    loader that unconditionally passes ``include_deleted=True`` (DR-323).

    Returns ``{resource_id: (related[:10], pre-truncation total)}``.
    """
    if not resource_ids:
        return {}
    include_deleted = deleted != "exclude"
    statement = (
        select(
            Interface.resource_id,
            Interface.id,
            Interface.name,
            Interface.interface_type,
            IPAddress.id,
            IPAddress.address,
            Network.id,
            Network.name,
        )
        .select_from(Interface)
        .join(IPAddress, IPAddress.interface_id == Interface.id)
        .join(Network, Network.id == IPAddress.network_id)
        .where(
            Interface.resource_id.in_(resource_ids),
            scope_filters.cluster_predicate(scope, Network.cluster_id),
        )
        .order_by(
            Interface.resource_id,
            Interface.name.collate("C"),
            IPAddress.address,
            IPAddress.id,
        )
    )
    if not include_deleted:
        statement = statement.where(
            Interface.deleted_at.is_(None),
            IPAddress.deleted_at.is_(None),
            Network.deleted_at.is_(None),
        )
    rows = db.execute(
        statement, execution_options=_query_options(include_deleted)
    ).all()

    related: dict[uuid.UUID, list[SearchResourceRelated]] = {}
    totals: dict[uuid.UUID, int] = {}
    for (
        resource_id,
        interface_id,
        interface_name,
        interface_type,
        ip_id,
        address,
        network_id,
        network_name,
    ) in rows:
        totals[resource_id] = totals.get(resource_id, 0) + 1
        bucket = related.setdefault(resource_id, [])
        if len(bucket) < RELATED_LIMIT:
            bucket.append(
                SearchResourceRelated(
                    id=ip_id,
                    interface=SearchRelatedInterface(
                        id=interface_id,
                        name=interface_name,
                        interface_type=interface_type,
                    ),
                    ip_address=SearchRelatedIPAddress(
                        id=ip_id, address=str(address)
                    ),
                    network=SearchNetworkNested(id=network_id, name=network_name),
                )
            )
    return {rid: (related.get(rid, []), totals[rid]) for rid in totals}


def _build_items(
    db: "Session",
    candidates: list[_Candidate],
    deleted: str = "exclude",
    scope=None,
) -> list[SearchItem]:
    resource_candidates = [c for c in candidates if c.object_type == "resource"]
    cluster_candidates = [c for c in candidates if c.object_type == "cluster"]
    ip_candidates = [c for c in candidates if c.object_type == "ip_address"]
    service_candidates = [c for c in candidates if c.object_type == "service"]

    ip_objects = {c.payload.id: c.payload for c in ip_candidates}
    interface_objs: dict[uuid.UUID, Interface] = {}
    interface_ids = {ip.interface_id for ip in ip_objects.values() if ip.interface_id}
    if interface_ids:
        interface_objs = {
            row.id: row
            for row in db.execute(
                select(Interface).where(Interface.id.in_(interface_ids)),
                execution_options={"include_deleted": True},
            ).scalars().all()
        }

    # F018: association data is only attached to ``object_type="resource"``
    # result rows; embedded resources keep ``related``/``related_total`` null.
    related_by_resource = _load_related(
        db, {c.payload.id for c in resource_candidates}, deleted, scope
    )

    resource_ids: set[uuid.UUID] = {c.payload.id for c in resource_candidates}
    resource_ids |= {c.payload.resource_id for c in service_candidates}
    resource_ids |= {iface.resource_id for iface in interface_objs.values()}
    resource_objs: dict[uuid.UUID, Resource] = {}
    if resource_ids:
        resource_objs = {
            row.id: row
            for row in db.execute(
                select(Resource).where(Resource.id.in_(resource_ids)),
                execution_options={"include_deleted": True},
            ).scalars().all()
        }

    network_objs: dict[uuid.UUID, Network] = {}
    network_ids = {ip.network_id for ip in ip_objects.values()}
    if network_ids:
        network_objs = {
            row.id: row
            for row in db.execute(
                select(Network).where(Network.id.in_(network_ids)),
                execution_options={"include_deleted": True},
            ).scalars().all()
        }

    cluster_ids: set[uuid.UUID] = {c.payload.id for c in cluster_candidates}
    cluster_ids |= {r.cluster_id for r in resource_objs.values()}
    cluster_objs: dict[uuid.UUID, Cluster] = {}
    if cluster_ids:
        cluster_objs = {
            row.id: row
            for row in db.execute(
                select(Cluster).where(Cluster.id.in_(cluster_ids)),
                execution_options={"include_deleted": True},
            ).scalars().all()
        }

    def _resource_object(
        resource: Resource,
        related: list[SearchResourceRelated] | None = None,
        related_total: int | None = None,
    ) -> SearchResourceObject:
        cluster = cluster_objs.get(resource.cluster_id)
        return SearchResourceObject(
            id=resource.id,
            hostname=resource.hostname,
            resource_type=resource.resource_type,
            role=resource.role,
            status=resource.status,
            cluster=SearchClusterNested(
                id=resource.cluster_id,
                code=cluster.code if cluster is not None else "",
                name=cluster.name if cluster is not None else "",
            ),
            related=related,
            related_total=related_total,
        )

    items: list[SearchItem] = []
    for candidate in candidates:
        if candidate.object_type == "resource":
            resource = candidate.payload
            related, related_total = related_by_resource.get(resource.id, ([], 0))
            items.append(
                SearchItem(
                    object_type="resource",
                    id=resource.id,
                    matched_field="hostname",
                    matched_value=candidate.matched_value,
                    resource=_resource_object(resource, related, related_total),
                )
            )
        elif candidate.object_type == "cluster":
            cluster = candidate.payload
            items.append(
                SearchItem(
                    object_type="cluster",
                    id=cluster.id,
                    matched_field=candidate.matched_field,
                    matched_value=candidate.matched_value,
                    cluster=SearchClusterObject(
                        id=cluster.id,
                        code=cluster.code,
                        name=cluster.name,
                        status=cluster.status,
                    ),
                )
            )
        elif candidate.object_type == "ip_address":
            ip = candidate.payload
            interface = interface_objs.get(ip.interface_id) if ip.interface_id else None
            network = network_objs.get(ip.network_id)
            resource = (
                resource_objs.get(interface.resource_id) if interface is not None else None
            )
            items.append(
                SearchItem(
                    object_type="ip_address",
                    id=ip.id,
                    matched_field="address",
                    matched_value=str(ip.address),
                    ip_address=SearchIPAddressObject(
                        id=ip.id,
                        address=str(ip.address),
                        network=SearchNetworkNested(
                            id=ip.network_id,
                            name=network.name if network is not None else "",
                        ),
                        interface=(
                            SearchInterfaceNested(id=interface.id, name=interface.name)
                            if interface is not None
                            else None
                        ),
                    ),
                    resource=(
                        _resource_object(resource) if resource is not None else None
                    ),
                )
            )
        else:  # service
            service = candidate.payload
            resource = resource_objs.get(service.resource_id)
            items.append(
                SearchItem(
                    object_type="service",
                    id=service.id,
                    matched_field="name",
                    matched_value=candidate.matched_value,
                    service=SearchServiceObject(
                        id=service.id, name=service.name, status=service.status
                    ),
                    resource=(
                        _resource_object(resource) if resource is not None else None
                    ),
                )
            )
    return items


def search(
    db: "Session",
    *,
    q: str,
    object_type: str | None = None,
    deleted: str = "exclude",
    page: int = 1,
    page_size: int = 20,
    scope=None,
) -> tuple[list[SearchItem], int]:
    """Run the global search and return the visible page plus the exact total."""
    q_text = validate_q(q)
    if object_type is not None and object_type not in OBJECT_TYPES:
        raise _field_error("type", "type is not a supported object type")
    if deleted not in DELETED_MODES:
        raise _field_error("deleted", "deleted must be exclude, include or only")
    if page < 1:
        raise _field_error("page", "page must be >= 1")
    if page_size < 1 or page_size > 100:
        raise _field_error("page_size", "page_size must be between 1 and 100")

    candidates: list[_Candidate] = []
    if object_type in (None, "resource"):
        candidates.extend(_resource_candidates(db, q_text, deleted, scope))
    if object_type in (None, "cluster"):
        candidates.extend(_cluster_candidates(db, q_text, deleted, scope))
    if object_type in (None, "ip_address"):
        candidates.extend(_ip_candidates(db, q_text, deleted, scope))
    if object_type in (None, "service"):
        candidates.extend(_service_candidates(db, q_text, deleted, scope))

    # Dedup by (object_type, id): one typed row per matched object (DR-174).
    unique: dict[tuple[str, uuid.UUID], _Candidate] = {}
    for candidate in candidates:
        unique[(candidate.object_type, candidate.object_id)] = candidate

    ordered = sorted(
        unique.values(),
        key=lambda c: (-c.score, _TYPE_ORDER[c.object_type], str(c.object_id)),
    )
    total = len(ordered)
    offset = (page - 1) * page_size
    page_candidates = ordered[offset : offset + page_size]
    return _build_items(db, page_candidates, deleted, scope), total