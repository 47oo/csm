"""ServiceEndpoint business service (Contract §2–§9, DR-155..DR-170).

All ServiceEndpoint rules live here: the ``service``/``ip_address`` live-reference
validation, the same-Resource attribution check (the IP must be bound to an
Interface whose Resource equals the Service's Resource, DR-158), the same-IP
undeleted ``(protocol, port)`` listener uniqueness (DR-159), ``protocol``/``port``
value domains (DR-160), list filtering/sorting/pagination, the optimistic-lock
conditional UPDATE, soft delete / restore with the deterministic re-check
priority and the audit trail (same Session, same commit). Routes only translate
HTTP.

Cross-object wiring (DR-161): F012 registers the two real reference providers in
:mod:`app.services.endpoint_reference` — the IP side blocks unbind / transfer /
release of an IP referenced by an undeleted Endpoint, and the Service side blocks
deletion of a Service referenced by an undeleted Endpoint. Both return the
canonical ``object_type="service_endpoint"`` (DR-162).

Soft-delete semantics (Contract §5): the Session-level ``with_loader_criteria``
filter hides ``deleted_at IS NOT NULL`` rows by default; callers opt in with
``include_deleted=True``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    AppError,
    Conflict,
    NotFound,
    ValidationError,
    VersionConflict,
)
from app.models.interface import Interface
from app.models.ip_address import IPAddress
from app.models.network import Network
from app.models.resource import Resource
from app.models.service import Service
from app.models.service_endpoint import VALID_PROTOCOLS, ServiceEndpoint
from app.services import audit, scope_filters
# Importing the reference providers here guarantees registration on the startup
# import chain (DR-161): routes import this service module, which registers the
# IP-side and Service-side Endpoint checkers before any request is served.
from app.services import endpoint_reference  # noqa: F401

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator

OBJECT_TYPE = "service_endpoint"
DELETED_MODES = ("exclude", "include", "only")
SORT_FIELDS = ("protocol", "port", "created_at", "updated_at")
ORDERS = ("asc", "desc")

_SORT_COLUMNS = {
    "protocol": ServiceEndpoint.protocol,
    "port": ServiceEndpoint.port,
    "created_at": ServiceEndpoint.created_at,
    "updated_at": ServiceEndpoint.updated_at,
}

# Non-nullable PATCH fields that must not receive an explicit JSON null.
NON_NULLABLE_PATCH_FIELDS = ("protocol", "port")


# --- helpers ----------------------------------------------------------------


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _query_options(include_deleted: bool) -> dict[str, Any]:
    return {"include_deleted": True} if include_deleted else {}


def _load_service(db: "Session", service_id: uuid.UUID) -> Service | None:
    return (
        db.execute(
            select(Service).where(Service.id == service_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )


def _load_ip_address(db: "Session", ip_address_id: uuid.UUID) -> IPAddress | None:
    return (
        db.execute(
            select(IPAddress).where(IPAddress.id == ip_address_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )


def _load_interface(db: "Session", interface_id: uuid.UUID) -> Interface | None:
    return (
        db.execute(
            select(Interface).where(Interface.id == interface_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )


def _load_resource(db: "Session", resource_id: uuid.UUID) -> Resource | None:
    return (
        db.execute(
            select(Resource).where(Resource.id == resource_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )


def _resolve_uuid(reference: Any, field: str) -> uuid.UUID:
    """Parse a POST ``service``/``ip_address`` UUID (else 422 field error)."""
    if not isinstance(reference, str) or not reference.strip():
        raise _field_error(field, f"{field} is required")
    value = reference.strip()
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise _field_error(field, f"{field} must be a valid UUID") from exc


def resolve_service(db: "Session", reference: Any, *, scope=None) -> Service:
    """Resolve a POST ``service`` UUID to an undeleted Service (Contract §2.1).

    Missing / non-UUID / nonexistent / soft-deleted all yield 422 with
    ``field:"service"``. The lookup includes soft-deleted rows so a deleted
    Service is reported as a field error rather than silently ignored.
    """
    service_id = _resolve_uuid(reference, "service")
    service = _load_service(db, service_id)
    resource = _load_resource(db, service.resource_id) if service is not None else None
    if (
        service is None
        or service.deleted_at is not None
        or resource is None
        or resource.deleted_at is not None
        or not scope_filters.normalize(scope).allows(resource.cluster_id)
    ):
        raise _field_error("service", "service does not exist or is not selectable")
    return service


def resolve_ip_address(db: "Session", reference: Any, *, scope=None) -> IPAddress:
    """Resolve a POST ``ip_address`` UUID to an undeleted IPAddress (Contract §2.1).

    Missing / non-UUID / nonexistent / soft-deleted all yield 422 with
    ``field:"ip_address"``.
    """
    ip_address_id = _resolve_uuid(reference, "ip_address")
    ip_address = _load_ip_address(db, ip_address_id)
    if (
        ip_address is None
        or ip_address.deleted_at is not None
        or not scope_filters.normalize(scope).allows(ip_address.cluster_id)
    ):
        raise _field_error(
            "ip_address", "ip_address does not exist or is not selectable"
        )
    return ip_address


def _validate_protocol(value: Any) -> str:
    if value not in VALID_PROTOCOLS:
        raise _field_error("protocol", "protocol must be TCP or UDP")
    return value


def _validate_port(value: Any) -> int:
    # The API path already rejects non-integers via the schema ``StrictInt``
    # (Contract §2.2), so ``bool`` / ``str`` / ``float`` never reach here from
    # HTTP. This guard stays as defense-in-depth for direct service-layer
    # callers (e.g. imports / internal workflows): ``bool`` is an ``int``
    # subclass, so it must be rejected explicitly rather than coerced to 0/1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise _field_error("port", "port must be an integer between 1 and 65535")
    if not 1 <= value <= 65535:
        raise _field_error("port", "port must be between 1 and 65535")
    return value


def _validate_attribution(db: "Session", service: Service, ip_address: IPAddress) -> None:
    """Require the IP bound to an Interface of the Service's Resource (DR-158).

    Unbound IP / missing or soft-deleted Interface / cross-Resource all map to
    422 ``field:"ip_address"`` (Contract §2.1/§6.2).
    """
    if ip_address.interface_id is None:
        raise _field_error(
            "ip_address", "ip_address must be bound to an interface"
        )
    interface = _load_interface(db, ip_address.interface_id)
    if interface is None or interface.deleted_at is not None:
        raise _field_error(
            "ip_address", "ip_address interface does not exist or is not selectable"
        )
    if interface.resource_id != service.resource_id:
        raise _field_error(
            "ip_address",
            "ip_address interface must belong to the service resource",
        )


def _duplicate_exists(
    db: "Session",
    ip_address_id: uuid.UUID,
    protocol: str,
    port: int,
    *,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    filters = [
        ServiceEndpoint.ip_address_id == ip_address_id,
        ServiceEndpoint.protocol == protocol,
        ServiceEndpoint.port == port,
        ServiceEndpoint.deleted_at.is_(None),
    ]
    if exclude_id is not None:
        filters.append(ServiceEndpoint.id != exclude_id)
    return db.execute(select(ServiceEndpoint.id).where(*filters)).first() is not None


def _raise_unique_conflict(
    ip_address_id: uuid.UUID, protocol: str, port: int
) -> None:
    raise Conflict(
        "unique_conflict",
        field="port",
        ip_address_id=str(ip_address_id),
        protocol=protocol,
        port=port,
    )


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    """Map a database integrity failure to a clean app error (caller rolled back).

    The partial unique index is the documented concurrent listener race (409
    ``unique_conflict``); the attribution trigger's ``restrict_violation`` maps
    to 422 ``field:"ip_address"`` (Contract §6.2, never a 500). Any other
    CHECK/FK failure means application validation and the database diverged and
    is surfaced as a clean 422.
    """
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    text = str(exc)
    if "uq_service_endpoints_ip_protocol_port" in constraint or (
        "uq_service_endpoints_ip_protocol_port" in text
    ):
        # The original row is gone; report a generic listener conflict.
        return Conflict("unique_conflict", field="port")
    if (
        "must be bound to an interface" in text
        or "must belong to the service resource" in text
        or "fn_service_endpoints_attribution" in text
    ):
        return _field_error("ip_address", "attribution rejected by the database")
    return ValidationError(
        message="service_endpoint write rejected by a database constraint"
    )


def service_endpoint_snapshot(endpoint: ServiceEndpoint) -> dict[str, Any]:
    """Whitelisted snapshot handed to :mod:`app.services.audit` (Contract §8)."""
    return {
        "service_id": str(endpoint.service_id),
        "ip_address_id": str(endpoint.ip_address_id),
        "protocol": endpoint.protocol,
        "port": endpoint.port,
        "description": endpoint.description,
    }


# --- reads ------------------------------------------------------------------


def list_service_endpoints(
    db: "Session",
    *,
    service_id: uuid.UUID | None = None,
    ip_address_id: uuid.UUID | None = None,
    protocol: str | None = None,
    deleted: str = "exclude",
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
    scope=None,
) -> tuple[list[ServiceEndpoint], int]:
    """Return the visible page of service endpoints plus the filtered total."""
    if deleted not in DELETED_MODES:
        raise _field_error("deleted", "deleted must be exclude, include or only")
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")
    if protocol is not None:
        _validate_protocol(protocol)

    filters = [scope_filters.service_predicate(scope)]
    if service_id is not None:
        filters.append(ServiceEndpoint.service_id == service_id)
    if ip_address_id is not None:
        filters.append(ServiceEndpoint.ip_address_id == ip_address_id)
    if protocol is not None:
        filters.append(ServiceEndpoint.protocol == protocol)
    if deleted == "only":
        filters.append(ServiceEndpoint.deleted_at.is_not(None))

    include_deleted = deleted in ("include", "only")
    execution_options = _query_options(include_deleted)

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    offset = (page - 1) * page_size

    statement = (
        select(ServiceEndpoint)
        .where(*filters)
        .order_by(ordered, ServiceEndpoint.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    total_statement = (
        select(func.count()).select_from(ServiceEndpoint).where(*filters)
    )

    items = list(
        db.execute(statement, execution_options=execution_options).scalars().all()
    )
    total = int(
        db.execute(total_statement, execution_options=execution_options).scalar_one()
    )
    return items, total


def get_service_endpoint(
    db: "Session",
    endpoint_id: uuid.UUID,
    *,
    include_deleted: bool = False,
    scope=None,
) -> ServiceEndpoint | None:
    """Return an endpoint, hidden by the soft-delete filter unless requested."""
    statement = select(ServiceEndpoint).where(
        ServiceEndpoint.id == endpoint_id,
        scope_filters.service_predicate(scope),
    )
    return (
        db.execute(statement, execution_options=_query_options(include_deleted))
        .scalars()
        .first()
    )


def services_for(
    db: "Session", service_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Service]:
    """Batch-load owning Services (including soft-deleted) for serialisation."""
    ids = set(service_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Service).where(Service.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def resources_for(
    db: "Session", resource_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Resource]:
    """Batch-load Services' Resources (including soft-deleted)."""
    ids = set(resource_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Resource).where(Resource.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def ip_addresses_for(
    db: "Session", ip_address_ids: list[uuid.UUID]
) -> dict[uuid.UUID, IPAddress]:
    """Batch-load referenced IPAddresses (including soft-deleted)."""
    ids = set(ip_address_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(IPAddress).where(IPAddress.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def networks_for(
    db: "Session", network_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Network]:
    """Batch-load IPAddresses' Networks (including soft-deleted)."""
    ids = set(network_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Network).where(Network.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def interfaces_for(
    db: "Session", interface_ids: list[uuid.UUID | None]
) -> dict[uuid.UUID, Interface]:
    """Batch-load bound Interfaces (including soft-deleted)."""
    ids = {iid for iid in interface_ids if iid is not None}
    if not ids:
        return {}
    rows = db.execute(
        select(Interface).where(Interface.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def list_activity(
    db: "Session",
    endpoint_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    """Return this endpoint's audit rows (ascending by created_at then id)."""
    from app.models.audit_log import AuditLog

    filters = [
        AuditLog.object_type == OBJECT_TYPE,
        AuditLog.object_id == endpoint_id,
    ]
    statement = (
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(AuditLog).where(*filters)
    items = list(db.execute(statement).scalars().all())
    total = int(db.execute(total_statement).scalar_one())
    return items, total


# --- writes -----------------------------------------------------------------


def create_service_endpoint(
    db: "Session",
    operator: "Operator | None",
    *,
    service: Any,
    ip_address: Any,
    protocol: str,
    port: int,
    description: str | None = None,
    scope=None,
) -> ServiceEndpoint:
    """Create a ServiceEndpoint (Contract §6.2 order, DR-157/158/159/160).

    service (422) -> ip_address (422, exists and undeleted) -> attribution (422)
    -> protocol (422) -> port (422) -> same-IP listener uniqueness (409) -> write
    + CREATE Audit -> 201. The partial unique index arbitrates a concurrent
    listener race atomically.
    """
    service_row = resolve_service(db, service, scope=scope)
    ip_row = resolve_ip_address(db, ip_address, scope=scope)
    _validate_attribution(db, service_row, ip_row)
    validated_protocol = _validate_protocol(protocol)
    validated_port = _validate_port(port)

    if _duplicate_exists(db, ip_row.id, validated_protocol, validated_port):
        _raise_unique_conflict(ip_row.id, validated_protocol, validated_port)

    endpoint = ServiceEndpoint(
        service_id=service_row.id,
        ip_address_id=ip_row.id,
        protocol=validated_protocol,
        port=validated_port,
        description=description,
    )
    db.add(endpoint)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent create lost the race
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    audit.record(
        db,
        operator,
        action="CREATE",
        object_type=OBJECT_TYPE,
        object_id=endpoint.id,
        before=None,
        after=service_endpoint_snapshot(endpoint),
    )
    db.commit()
    return endpoint


def update_service_endpoint(
    db: "Session",
    operator: "Operator | None",
    endpoint_id: uuid.UUID,
    *,
    expected_version: int,
    changes: dict[str, Any],
    scope=None,
) -> ServiceEndpoint:
    """Partial update (``description``/``protocol``/``port``) with optimistic lock.

    Contract §6.4 order: visibility (404) -> version (409) -> value domain (422)
    -> listener uniqueness on a protocol/port change (409, excluding self) ->
    write + UPDATE Audit -> 200. ``service``/``ip_address`` are immutable.
    """
    endpoint = get_service_endpoint(db, endpoint_id, scope=scope)
    if endpoint is None:
        raise NotFound()
    if endpoint.version != expected_version:
        raise VersionConflict(endpoint.version)

    values: dict[str, Any] = {}
    if "protocol" in changes:
        values["protocol"] = _validate_protocol(changes["protocol"])
    if "port" in changes:
        values["port"] = _validate_port(changes["port"])

    if "protocol" in values or "port" in values:
        new_protocol = values.get("protocol", endpoint.protocol)
        new_port = values.get("port", endpoint.port)
        if _duplicate_exists(
            db,
            endpoint.ip_address_id,
            new_protocol,
            new_port,
            exclude_id=endpoint_id,
        ):
            _raise_unique_conflict(endpoint.ip_address_id, new_protocol, new_port)

    if "description" in changes:
        values["description"] = changes["description"]

    before = service_endpoint_snapshot(endpoint)
    values["version"] = ServiceEndpoint.version + 1
    values["updated_at"] = func.now()

    try:
        result = db.execute(
            update(ServiceEndpoint)
            .where(
                ServiceEndpoint.id == endpoint_id,
                ServiceEndpoint.version == expected_version,
                ServiceEndpoint.deleted_at.is_(None),
            )
            .values(**values)
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, endpoint_id)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(endpoint)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=endpoint.id,
        before=before,
        after=service_endpoint_snapshot(endpoint),
    )
    db.commit()
    return endpoint


def delete_service_endpoint(
    db: "Session",
    operator: "Operator | None",
    endpoint_id: uuid.UUID,
    *,
    expected_version: int,
    scope=None,
) -> None:
    """Soft delete (no cascade); no child object references an Endpoint.

    Contract §6.5 order: object (404) -> version (409) -> soft delete.
    """
    endpoint = get_service_endpoint(db, endpoint_id, scope=scope)
    if endpoint is None:
        raise NotFound()
    if endpoint.version != expected_version:
        raise VersionConflict(endpoint.version)

    before = service_endpoint_snapshot(endpoint)
    result = db.execute(
        update(ServiceEndpoint)
        .where(
            ServiceEndpoint.id == endpoint_id,
            ServiceEndpoint.version == expected_version,
            ServiceEndpoint.deleted_at.is_(None),
        )
        .values(
            deleted_at=func.now(),
            version=ServiceEndpoint.version + 1,
            updated_at=func.now(),
        )
    )
    if result.rowcount == 0:
        _raise_update_conflict(db, endpoint_id)

    db.flush()
    db.refresh(endpoint)
    audit.record(
        db,
        operator,
        action="DELETE",
        object_type=OBJECT_TYPE,
        object_id=endpoint.id,
        before=before,
        after=None,
    )
    db.commit()


def restore_service_endpoint(
    db: "Session",
    operator: "Operator | None",
    endpoint_id: uuid.UUID,
    *,
    expected_version: int,
    scope=None,
) -> ServiceEndpoint:
    """Restore a soft-deleted ServiceEndpoint (Contract §6.6, DR-166).

    Deterministic priority: find incl. deleted (404) -> not deleted (409
    ``not_deleted``) -> version (409) -> listener uniqueness (409
    ``unique_conflict``) -> Service dependency (409 ``dependency_deleted``) ->
    IPAddress dependency (409 ``dependency_deleted``) -> Interface dependency
    (409 ``dependency_deleted``) -> attribution (422 field="ip_address") ->
    restore. A failed restore never overwrites the newer object; no cascade.
    """
    endpoint = get_service_endpoint(
        db, endpoint_id, include_deleted=True, scope=scope
    )
    if endpoint is None:
        raise NotFound()
    if endpoint.deleted_at is None:
        raise Conflict.not_deleted()
    if endpoint.version != expected_version:
        raise VersionConflict(endpoint.version)

    if _duplicate_exists(
        db,
        endpoint.ip_address_id,
        endpoint.protocol,
        endpoint.port,
        exclude_id=endpoint_id,
    ):
        _raise_unique_conflict(
            endpoint.ip_address_id, endpoint.protocol, endpoint.port
        )

    service = _load_service(db, endpoint.service_id)
    if service is None or service.deleted_at is not None:
        raise Conflict.dependency_deleted(
            [{"object_type": "service", "object_id": str(endpoint.service_id)}]
        )

    ip_address = _load_ip_address(db, endpoint.ip_address_id)
    if ip_address is None or ip_address.deleted_at is not None:
        raise Conflict.dependency_deleted(
            [{"object_type": "ip_address", "object_id": str(endpoint.ip_address_id)}]
        )

    if ip_address.interface_id is None:
        raise _field_error(
            "ip_address", "ip_address is no longer bound to an interface"
        )
    interface = _load_interface(db, ip_address.interface_id)
    if interface is None or interface.deleted_at is not None:
        raise Conflict.dependency_deleted(
            [
                {
                    "object_type": "interface",
                    "object_id": str(ip_address.interface_id),
                }
            ]
        )
    if interface.resource_id != service.resource_id:
        raise _field_error(
            "ip_address",
            "ip_address interface no longer belongs to the service resource",
        )

    before = service_endpoint_snapshot(endpoint)
    try:
        result = db.execute(
            update(ServiceEndpoint)
            .where(
                ServiceEndpoint.id == endpoint_id,
                ServiceEndpoint.version == expected_version,
                ServiceEndpoint.deleted_at.is_not(None),
            )
            .values(
                deleted_at=None,
                version=ServiceEndpoint.version + 1,
                updated_at=func.now(),
            )
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, endpoint_id, include_deleted=True)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(endpoint)
    audit.record(
        db,
        operator,
        action="RESTORE",
        object_type=OBJECT_TYPE,
        object_id=endpoint.id,
        before=before,
        after=service_endpoint_snapshot(endpoint),
    )
    db.commit()
    return endpoint


def _raise_update_conflict(
    db: "Session", endpoint_id: uuid.UUID, *, include_deleted: bool = True
) -> None:
    """Translate a conditional-UPDATE rowcount of 0 into 404 or 409."""
    current_version = db.execute(
        select(ServiceEndpoint.version).where(ServiceEndpoint.id == endpoint_id),
        execution_options=_query_options(include_deleted),
    ).scalar_one_or_none()
    if current_version is None:
        raise NotFound()
    raise VersionConflict(int(current_version))