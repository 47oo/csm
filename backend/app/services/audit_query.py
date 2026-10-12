"""Audit query business service (Contract §2, DR-213/DR-214/DR-215).

Read-only: the service never writes an audit row, never mutates an object and is
idempotent. All validation that is not expressible as a FastAPI query type
(operator normalisation/length, ``object_id``/``object_type`` co-occurrence,
``created_from <= created_to``) is enforced here as 422 ``VALIDATION_ERROR``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.audit_log import AuditLog

SORT_FIELDS = ("created_at",)
ORDERS = ("asc", "desc")


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _as_utc(value: datetime) -> datetime:
    """Treat a timezone-naive ISO-8601 value as UTC (Contract §1)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def list_audit(
    db: Session,
    *,
    operator: str | None = None,
    object_type: str | None = None,
    object_id: uuid.UUID | None = None,
    action: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[AuditLog], int]:
    """Return the filtered page of audit rows plus the filtered total."""
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")

    normalized_operator: str | None = None
    if operator is not None:
        if not isinstance(operator, str):
            raise _field_error("operator", "operator must be a string")
        trimmed = operator.strip()
        if not trimmed:
            raise _field_error("operator", "operator must not be blank")
        if len(trimmed) > 64:
            raise _field_error("operator", "operator must be at most 64 characters")
        normalized_operator = trimmed.lower()

    if object_id is not None and object_type is None:
        raise _field_error("object_id", "object_id requires object_type")

    if created_from is not None and created_to is not None:
        if _as_utc(created_from) > _as_utc(created_to):
            raise _field_error(
                "created_to", "created_to must not be earlier than created_from"
            )

    filters = []
    if normalized_operator is not None:
        filters.append(AuditLog.operator_username == normalized_operator)
    if object_type is not None:
        filters.append(AuditLog.object_type == object_type)
    if object_id is not None:
        filters.append(AuditLog.object_id == object_id)
    if action is not None:
        filters.append(AuditLog.action == action)
    if created_from is not None:
        filters.append(AuditLog.created_at >= _as_utc(created_from))
    if created_to is not None:
        filters.append(AuditLog.created_at <= _as_utc(created_to))

    created_at_order = (
        AuditLog.created_at.desc() if order == "desc" else AuditLog.created_at.asc()
    )
    statement = (
        select(AuditLog)
        .where(*filters)
        .order_by(created_at_order, AuditLog.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(AuditLog).where(*filters)

    items = list(db.execute(statement).scalars().all())
    total = int(db.execute(total_statement).scalar_one())
    return items, total