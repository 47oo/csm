"""Interface business service (Contract §2–§9, DR-72..DR-85).

All Interface rules live here: name/mac normalisation, owning-Resource lookup and
locking, parent correctness (same Resource / non-self / acyclic), list
filtering/sorting/pagination, optimistic-lock conditional UPDATE, soft delete /
restore, uniqueness re-checks and the audit trail (same Session, same commit).
Routes only translate HTTP.

Concurrency (DR-85): create and a parent change lock the target ``resources``
row ``SELECT ... FOR UPDATE`` (the same lock order as Resource soft delete /
F006 rehost, DR-71) *before* the recursive ancestor check, serialising parent
changes within one Resource; the ``trg_interfaces_parent_valid`` trigger is the
database backstop. The ``uq_interfaces_resource_id_name`` partial unique index
arbitrates concurrent same-name creates.

Soft-delete semantics (Contract §5): the Session-level ``with_loader_criteria``
filter hides ``deleted_at IS NOT NULL`` rows by default; callers opt in with
``include_deleted=True``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
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
from app.models.interface import VALID_INTERFACE_TYPES, Interface
from app.models.resource import Resource
from app.services import audit, normalization
from app.services import cluster as cluster_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator

OBJECT_TYPE = "interface"
DELETED_MODES = ("exclude", "include", "only")
SORT_FIELDS = (
    "name",
    "interface_type",
    "speed_mbps",
    "mtu",
    "created_at",
    "updated_at",
)
ORDERS = ("asc", "desc")
INT_MAX = 2147483647

# ``parent_interface`` request field -> DB column. The error path uses the
# request field name (Contract §2.3).
PARENT_FIELD = "parent_interface"

_SORT_COLUMNS = {
    "name": Interface.name,
    "interface_type": Interface.interface_type,
    "speed_mbps": Interface.speed_mbps,
    "mtu": Interface.mtu,
    "created_at": Interface.created_at,
    "updated_at": Interface.updated_at,
}


# --- helpers ----------------------------------------------------------------


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _validate_interface_type(value: Any) -> str:
    if value not in VALID_INTERFACE_TYPES:
        raise _field_error(
            "interface_type",
            "interface_type must be one of PHYSICAL, VIRTUAL, BOND, BRIDGE, "
            "VLAN, LOOPBACK, OTHER",
        )
    return value


def _validate_metadata(metadata: Any) -> dict:
    if not isinstance(metadata, dict):
        raise _field_error("metadata", "metadata must be a JSON object")
    return metadata


def _validate_positive_int(field: str, value: Any) -> int | None:
    """Strict integer range check; ``bool`` is not an ``int`` here."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _field_error(field, f"{field} must be an integer")
    if value < 1 or value > INT_MAX:
        raise _field_error(field, f"{field} must be between 1 and {INT_MAX}")
    return value


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_options(include_deleted: bool) -> dict[str, Any]:
    return {"include_deleted": True} if include_deleted else {}


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    """Map an unexpected database integrity failure to a clean app error.

    A ``uq_interfaces_resource_id_name`` partial-unique violation is the
    documented concurrent same-name race and becomes 409
    ``Conflict{unique_conflict, field:"name"}``. Any other CHECK/FK/trigger
    failure means application validation and the database diverged; it is
    surfaced as a clean 422 instead of an unhandled 500. The caller must have
    rolled back first.
    """
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    if "uq_interfaces_resource_id_name" in constraint or (
        "uq_interfaces_resource_id_name" in str(exc)
    ):
        return Conflict.unique_conflict("name")
    return ValidationError(message="interface write rejected by a database constraint")


def _lock_resource(db: "Session", resource_id: uuid.UUID) -> Resource:
    """Lock the owning Resource row and require it undeleted (DR-85/DR-71).

    The lock is taken *before* the parent ancestor check so concurrent parent
    changes within one Resource serialise; it also serialises with a concurrent
    Resource soft delete (which locks the same row before its reference check)
    and with a concurrent Interface create that targets the same Resource.
    """
    resource = (
        db.execute(
            select(Resource).where(Resource.id == resource_id).with_for_update(),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )
    if resource is None or resource.deleted_at is not None:
        raise _field_error(
            "resource", "resource does not exist or is not selectable"
        )
    return resource


def _validate_parent(
    db: "Session",
    parent_id: uuid.UUID | None,
    *,
    resource_id: uuid.UUID,
    child_id: uuid.UUID | None,
) -> None:
    """Validate a non-null parent: exists, same Resource, undeleted, acyclic.

    All failures are 422 with ``field="parent_interface"``. ``child_id`` is the
    row being updated (``None`` on create); the ancestor walk from the parent
    rejects a chain that reaches it. A missing referenced row is reported here
    (before the FK) so the API returns 422 rather than a raw FK error.
    """
    if parent_id is None:
        return
    if child_id is not None and parent_id == child_id:
        raise _field_error(
            PARENT_FIELD, "parent_interface must not reference itself"
        )
    parent = (
        db.execute(
            select(Interface).where(Interface.id == parent_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )
    if parent is None:
        raise _field_error(PARENT_FIELD, "parent_interface does not exist")
    if parent.resource_id != resource_id:
        raise _field_error(
            PARENT_FIELD, "parent_interface must belong to the same resource"
        )
    if parent.deleted_at is not None:
        raise _field_error(
            PARENT_FIELD, "parent_interface must not be soft-deleted"
        )

    # Ancestor walk (bounded by a visited set) rejects a cycle through child_id.
    current = parent.parent_interface_id
    visited: set[uuid.UUID] = set()
    while current is not None:
        if child_id is not None and current == child_id:
            raise _field_error(
                PARENT_FIELD, "parent_interface chain must not form a cycle"
            )
        if current in visited:
            break
        visited.add(current)
        row = db.execute(
            select(Interface.parent_interface_id).where(Interface.id == current),
            execution_options={"include_deleted": True},
        ).first()
        if row is None:
            break
        current = row[0]


def interface_snapshot(interface: Interface) -> dict[str, Any]:
    """Whitelisted snapshot handed to :mod:`app.services.audit` (Contract §8)."""
    return {
        "resource_id": str(interface.resource_id),
        "name": interface.name,
        "interface_type": interface.interface_type,
        "mac_address": interface.mac_address,
        "speed_mbps": interface.speed_mbps,
        "mtu": interface.mtu,
        "parent_interface_id": (
            str(interface.parent_interface_id)
            if interface.parent_interface_id is not None
            else None
        ),
        "enabled": interface.enabled,
        "description": interface.description,
        "metadata": interface.meta,
    }


# --- reference / dependency checker registration (DR-80/DR-82) --------------
# F007 registers on ``resource``: an undeleted Interface blocks deletion of its
# Resource (narrows F004 DELETE /resources). On ``interface`` it registers the
# undeleted child-Interface checker (DR-80 parent delete protection) and the
# reserved F010 IPAddress checker (empty until F010 ships).


def _undeleted_interface_references(db: "Session", resource_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(Interface.id, Interface.name).where(
            Interface.resource_id == resource_id,
            Interface.deleted_at.is_(None),
        )
    ).all()
    return [
        {"object_type": "interface", "object_id": str(row.id), "label": row.name}
        for row in rows
    ]


def _undeleted_child_interface_references(
    db: "Session", interface_id: uuid.UUID
) -> list[dict]:
    rows = db.execute(
        select(Interface.id, Interface.name).where(
            Interface.parent_interface_id == interface_id,
            Interface.deleted_at.is_(None),
        )
    ).all()
    return [
        {"object_type": "interface", "object_id": str(row.id), "label": row.name}
        for row in rows
    ]


def _undeleted_ip_address_references(
    db: "Session", interface_id: uuid.UUID
) -> list[dict]:
    """F010 reserved call point: no IPAddress table exists in F007 (DR-82).

    Kept as an explicit registered checker returning an empty set so the delete
    path already calls into the interface reference set and F010 only has to
    fill this in (it does not need to rewire the registry).
    """
    return []


cluster_service.register_reference_checker(
    "resource", _undeleted_interface_references
)
cluster_service.register_reference_checker(
    "interface", _undeleted_child_interface_references
)
cluster_service.register_reference_checker(
    "interface", _undeleted_ip_address_references
)


# --- reads ------------------------------------------------------------------


def list_interfaces(
    db: "Session",
    *,
    resource_id: uuid.UUID | None = None,
    interface_type: str | None = None,
    enabled: bool | None = None,
    q: str | None = None,
    parent_interface_id: uuid.UUID | None = None,
    deleted: str = "exclude",
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[Interface], int]:
    """Return the visible page of interfaces plus the filtered total."""
    if deleted not in DELETED_MODES:
        raise _field_error("deleted", "deleted must be exclude, include or only")
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")
    if interface_type is not None:
        _validate_interface_type(interface_type)

    filters = []
    if resource_id is not None:
        filters.append(Interface.resource_id == resource_id)
    if interface_type is not None:
        filters.append(Interface.interface_type == interface_type)
    if enabled is not None:
        filters.append(Interface.enabled.is_(enabled))
    if parent_interface_id is not None:
        filters.append(Interface.parent_interface_id == parent_interface_id)
    if q is not None and q.strip():
        # Case-sensitive substring; special LIKE characters are escaped.
        pattern = f"%{_escape_like(q)}%"
        filters.append(Interface.name.like(pattern, escape="\\"))
    if deleted == "only":
        filters.append(Interface.deleted_at.is_not(None))

    include_deleted = deleted in ("include", "only")
    execution_options = _query_options(include_deleted)

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    offset = (page - 1) * page_size

    statement = (
        select(Interface)
        .where(*filters)
        .order_by(ordered, Interface.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(Interface).where(*filters)

    items = list(
        db.execute(statement, execution_options=execution_options).scalars().all()
    )
    total = int(
        db.execute(total_statement, execution_options=execution_options).scalar_one()
    )
    return items, total


def get_interface(
    db: "Session", interface_id: uuid.UUID, *, include_deleted: bool = False
) -> Interface | None:
    """Return an interface, hidden by the soft-delete filter unless requested."""
    statement = select(Interface).where(Interface.id == interface_id)
    return (
        db.execute(statement, execution_options=_query_options(include_deleted))
        .scalars()
        .first()
    )


def resources_for(
    db: "Session", resource_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Resource]:
    """Batch-load owning Resources (including soft-deleted) for serialisation."""
    ids = set(resource_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Resource).where(Resource.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def parents_for(
    db: "Session", parent_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Interface]:
    """Batch-load parent Interfaces (including soft-deleted) for serialisation."""
    ids = {pid for pid in parent_ids if pid is not None}
    if not ids:
        return {}
    rows = db.execute(
        select(Interface).where(Interface.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def list_activity(
    db: "Session",
    interface_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    """Return this interface's audit rows (ascending by created_at then id)."""
    from app.models.audit_log import AuditLog

    filters = [
        AuditLog.object_type == OBJECT_TYPE,
        AuditLog.object_id == interface_id,
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


@dataclass
class PreparedInterface:
    """Fully validated Interface values ready to be staged (DR-417).

    Produced by :func:`prepare_interface` (validation, owning-Resource lock,
    parent check and same-Resource name uniqueness); persisted without
    re-running validation by :func:`stage_interface`. F023 import builds the
    same object after its aggregation-friendly per-row validation and stages it
    inside a per-resource SAVEPOINT.
    """

    resource_id: uuid.UUID
    name: str
    interface_type: str
    mac_address: str | None
    speed_mbps: int | None
    mtu: int | None
    parent_interface_id: uuid.UUID | None
    enabled: bool
    description: str | None
    meta: dict


def prepare_interface(
    db: "Session",
    *,
    resource: uuid.UUID,
    name: str,
    interface_type: str = "OTHER",
    mac_address: str | None = None,
    speed_mbps: int | None = None,
    mtu: int | None = None,
    parent_interface: uuid.UUID | None = None,
    enabled: bool = True,
    description: str | None = None,
    metadata: dict | None = None,
) -> PreparedInterface:
    """Validate and normalise an Interface (no write, no commit; DR-417).

    Preserves the create order exactly: body/normalisation (422) -> owning
    Resource lock + selectability (422) -> parent (422) -> same-Resource
    undeleted name uniqueness (409). The same non-committing core backs the
    ordinary API and F023 import; ``create_interface`` is a thin wrapper.
    """
    normalized_name = normalization.normalize_interface_name(name)
    validated_type = _validate_interface_type(interface_type)
    normalized_mac = (
        None
        if mac_address is None
        else normalization.normalize_mac_address(mac_address)
    )
    validated_speed = _validate_positive_int("speed_mbps", speed_mbps)
    validated_mtu = _validate_positive_int("mtu", mtu)
    meta = _validate_metadata({} if metadata is None else metadata)

    resource_row = _lock_resource(db, resource)

    if parent_interface is not None:
        _validate_parent(
            db, parent_interface, resource_id=resource_row.id, child_id=None
        )

    duplicate = db.execute(
        select(Interface.id).where(
            Interface.resource_id == resource_row.id,
            Interface.name == normalized_name,
            Interface.deleted_at.is_(None),
        )
    ).first()
    if duplicate is not None:
        raise Conflict.unique_conflict("name")

    return PreparedInterface(
        resource_id=resource_row.id,
        name=normalized_name,
        interface_type=validated_type,
        mac_address=normalized_mac,
        speed_mbps=validated_speed,
        mtu=validated_mtu,
        parent_interface_id=parent_interface,
        enabled=enabled,
        description=description,
        meta=meta,
    )


def stage_interface(
    db: "Session", operator: "Operator | None", prepared: PreparedInterface
) -> Interface:
    """Persist a prepared Interface + CREATE audit (no commit; DR-417).

    Flushes so the generated id/constraints are visible; an ``IntegrityError``
    propagates to the caller, which owns rollback (API: whole-transaction in
    :func:`create_interface`; import: the per-resource SAVEPOINT).
    """
    interface = Interface(
        resource_id=prepared.resource_id,
        name=prepared.name,
        interface_type=prepared.interface_type,
        mac_address=prepared.mac_address,
        speed_mbps=prepared.speed_mbps,
        mtu=prepared.mtu,
        parent_interface_id=prepared.parent_interface_id,
        enabled=prepared.enabled,
        description=prepared.description,
        meta=prepared.meta,
    )
    db.add(interface)
    db.flush()

    audit.record(
        db,
        operator,
        action="CREATE",
        object_type=OBJECT_TYPE,
        object_id=interface.id,
        before=None,
        after=interface_snapshot(interface),
    )
    return interface


def create_interface(
    db: "Session",
    operator: "Operator | None",
    *,
    resource: uuid.UUID,
    name: str,
    interface_type: str = "OTHER",
    mac_address: str | None = None,
    speed_mbps: int | None = None,
    mtu: int | None = None,
    parent_interface: uuid.UUID | None = None,
    enabled: bool = True,
    description: str | None = None,
    metadata: dict | None = None,
) -> Interface:
    """Create an Interface; validated per Contract §6.2 order.

    Body (422) -> owning Resource (422) -> parent (422) -> same-Resource
    undeleted name uniqueness (409) -> write + CREATE Audit -> 201. The owning
    Resource row is locked before the parent ancestor check (DR-85). Thin
    wrapper around :func:`prepare_interface` + :func:`stage_interface`
    (DR-417): it commits on success and translates an unexpected
    ``IntegrityError``.
    """
    prepared = prepare_interface(
        db,
        resource=resource,
        name=name,
        interface_type=interface_type,
        mac_address=mac_address,
        speed_mbps=speed_mbps,
        mtu=mtu,
        parent_interface=parent_interface,
        enabled=enabled,
        description=description,
        metadata=metadata,
    )
    try:
        interface = stage_interface(db, operator, prepared)
    except IntegrityError as exc:  # concurrent create lost the race
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.commit()
    return interface


def update_interface(
    db: "Session",
    operator: "Operator | None",
    interface_id: uuid.UUID,
    *,
    expected_version: int,
    changes: dict[str, Any],
) -> Interface:
    """Partial update with optimistic locking; ``resource``/``id`` immutable.

    Contract §6.4 order: visibility (404) -> parent change (422) -> version
    (409) -> name uniqueness (409) -> write + UPDATE Audit -> 200. ``changes``
    uses ``exclude_unset`` semantics (only the supplied keys are applied); an
    explicit ``null`` clears a nullable field.
    """
    interface = get_interface(db, interface_id)
    if interface is None:
        raise NotFound()

    # Parent change is validated before the version check (DR-85 lock order).
    if PARENT_FIELD in changes:
        _lock_resource(db, interface.resource_id)
        new_parent = changes[PARENT_FIELD]
        if new_parent is not None:
            _validate_parent(
                db,
                new_parent,
                resource_id=interface.resource_id,
                child_id=interface_id,
            )

    if interface.version != expected_version:
        raise VersionConflict(interface.version)

    values: dict[str, Any] = {}
    if "name" in changes:
        normalized_name = normalization.normalize_interface_name(changes["name"])
        duplicate = db.execute(
            select(Interface.id).where(
                Interface.resource_id == interface.resource_id,
                Interface.name == normalized_name,
                Interface.deleted_at.is_(None),
                Interface.id != interface_id,
            )
        ).first()
        if duplicate is not None:
            raise Conflict.unique_conflict("name")
        values["name"] = normalized_name
    if "interface_type" in changes:
        values["interface_type"] = _validate_interface_type(changes["interface_type"])
    if "mac_address" in changes:
        mac = changes["mac_address"]
        values["mac_address"] = (
            None if mac is None else normalization.normalize_mac_address(mac)
        )
    if "speed_mbps" in changes:
        values["speed_mbps"] = _validate_positive_int(
            "speed_mbps", changes["speed_mbps"]
        )
    if "mtu" in changes:
        values["mtu"] = _validate_positive_int("mtu", changes["mtu"])
    if PARENT_FIELD in changes:
        values["parent_interface_id"] = changes[PARENT_FIELD]
    if "enabled" in changes:
        values["enabled"] = bool(changes["enabled"])
    if "description" in changes:
        values["description"] = changes["description"]
    if "metadata" in changes:
        values["meta"] = _validate_metadata(changes["metadata"])

    before = interface_snapshot(interface)
    values["version"] = Interface.version + 1
    values["updated_at"] = func.now()

    try:
        result = db.execute(
            update(Interface)
            .where(
                Interface.id == interface_id,
                Interface.version == expected_version,
                Interface.deleted_at.is_(None),
            )
            .values(**values)
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, interface_id)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(interface)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=interface.id,
        before=before,
        after=interface_snapshot(interface),
    )
    db.commit()
    return interface


def delete_interface(
    db: "Session",
    operator: "Operator | None",
    interface_id: uuid.UUID,
    *,
    expected_version: int,
) -> None:
    """Soft delete (no cascade); blocked by undeleted references (DR-80/DR-82).

    Contract §6.5 order: object (404) -> version (409) -> references (409) ->
    soft delete. The owning Resource row is locked before the reference check so
    a concurrent child-Interface create serialises (DR-85).
    """
    interface = get_interface(db, interface_id)
    if interface is None:
        raise NotFound()
    if interface.version != expected_version:
        raise VersionConflict(interface.version)

    _lock_resource(db, interface.resource_id)

    references = cluster_service.check_references(db, OBJECT_TYPE, interface_id)
    if references:
        raise Conflict.reference_exists(references)

    before = interface_snapshot(interface)
    result = db.execute(
        update(Interface)
        .where(
            Interface.id == interface_id,
            Interface.version == expected_version,
            Interface.deleted_at.is_(None),
        )
        .values(
            deleted_at=func.now(),
            version=Interface.version + 1,
            updated_at=func.now(),
        )
    )
    if result.rowcount == 0:
        _raise_update_conflict(db, interface_id)

    db.flush()
    db.refresh(interface)
    audit.record(
        db,
        operator,
        action="DELETE",
        object_type=OBJECT_TYPE,
        object_id=interface.id,
        before=before,
        after=None,
    )
    db.commit()


def restore_interface(
    db: "Session",
    operator: "Operator | None",
    interface_id: uuid.UUID,
    *,
    expected_version: int,
) -> Interface:
    """Restore a soft-deleted Interface; rechecks name -> Resource -> parent.

    Contract §6.6: a live same-Resource name (409 ``unique_conflict``) takes
    precedence over an invalid owning Resource or parent (409
    ``dependency_deleted``); a failed restore never overwrites the newer object.
    """
    interface = get_interface(db, interface_id, include_deleted=True)
    if interface is None:
        raise NotFound()
    if interface.deleted_at is None:
        raise Conflict.not_deleted()
    if interface.version != expected_version:
        raise VersionConflict(interface.version)

    duplicate = db.execute(
        select(Interface.id).where(
            Interface.resource_id == interface.resource_id,
            Interface.name == interface.name,
            Interface.deleted_at.is_(None),
            Interface.id != interface_id,
        )
    ).first()
    if duplicate is not None:
        raise Conflict.unique_conflict("name")

    resource = (
        db.execute(
            select(Resource).where(Resource.id == interface.resource_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )
    if resource is None or resource.deleted_at is not None:
        raise Conflict.dependency_deleted(
            [{"object_type": "resource", "object_id": str(interface.resource_id)}]
        )

    if interface.parent_interface_id is not None:
        parent = (
            db.execute(
                select(Interface).where(Interface.id == interface.parent_interface_id),
                execution_options={"include_deleted": True},
            )
            .scalars()
            .first()
        )
        if (
            parent is None
            or parent.deleted_at is not None
            or parent.resource_id != interface.resource_id
        ):
            raise Conflict.dependency_deleted(
                [
                    {
                        "object_type": "interface",
                        "object_id": str(interface.parent_interface_id),
                    }
                ]
            )

    before = interface_snapshot(interface)
    try:
        result = db.execute(
            update(Interface)
            .where(
                Interface.id == interface_id,
                Interface.version == expected_version,
                Interface.deleted_at.is_not(None),
            )
            .values(
                deleted_at=None,
                version=Interface.version + 1,
                updated_at=func.now(),
            )
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, interface_id, include_deleted=True)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(interface)
    audit.record(
        db,
        operator,
        action="RESTORE",
        object_type=OBJECT_TYPE,
        object_id=interface.id,
        before=before,
        after=interface_snapshot(interface),
    )
    db.commit()
    return interface


def _raise_update_conflict(
    db: "Session", interface_id: uuid.UUID, *, include_deleted: bool = True
) -> None:
    """Translate a conditional-UPDATE rowcount of 0 into 404 or 409."""
    current_version = db.execute(
        select(Interface.version).where(Interface.id == interface_id),
        execution_options=_query_options(include_deleted),
    ).scalar_one_or_none()
    if current_version is None:
        raise NotFound()
    raise VersionConflict(int(current_version))