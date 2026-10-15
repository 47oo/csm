"""Audit query schemas (Contract §2).

``AuditRow`` is a read-only projection of an existing ``audit_logs`` row. No
credential/token material is ever part of this schema (the columns themselves do
not exist on the table and the write path only stores whitelisted snapshots).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, field_serializer

from app.models.audit_log import AuditLog

AuditObjectType = Literal[
    "cluster",
    "resource",
    "interface",
    "network",
    "ip_pool",
    "ip_address",
    "service",
    "service_endpoint",
    "user",
    "api_key",
]
AuditAction = Literal["CREATE", "UPDATE", "DELETE", "RESTORE"]
AuditSort = Literal["created_at"]
SortOrder = Literal["asc", "desc"]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class AuditRow(BaseModel):
    id: uuid.UUID
    action: str
    object_type: str
    object_id: uuid.UUID
    operator_user_id: uuid.UUID | None
    operator_username: str
    api_key_label: str | None
    before_data: dict | None
    after_data: dict | None
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _iso_utc(value)


class AuditListResponse(BaseModel):
    items: list[AuditRow]
    page: int
    page_size: int
    total: int


def build_audit_row(row: AuditLog) -> AuditRow:
    """Serialise an audit row; only the table's own non-sensitive columns."""
    return AuditRow(
        id=row.id,
        action=row.action,
        object_type=row.object_type,
        object_id=row.object_id,
        operator_user_id=row.operator_user_id,
        operator_username=row.operator_username,
        api_key_label=row.api_key_label,
        before_data=row.before_data,
        after_data=row.after_data,
        created_at=row.created_at,
    )