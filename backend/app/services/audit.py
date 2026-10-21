"""Audit write path (D02 §1.4, DR-21/DR-22).

The business Service calls :func:`record` inside its own Session and commits the
business write and the audit row together: an exception rolls both back, so a
failed write never leaves an audit trace (§22/A7). Snapshots use an explicit
per-object whitelist, so credentials/tokens/secrets can never be recorded.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.models.audit_log import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator

# object_type -> ordered auditable field names. Only these keys (when present)
# are serialised into before_data/after_data.
AUDITABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "cluster": ("code", "name", "status", "description", "metadata"),
    "resource": (
        "cluster_id",
        "hostname",
        "resource_type",
        "role",
        "status",
        "description",
        "metadata",
        "hardware",
        "virtual_machine",
    ),
    "interface": (
        "resource_id",
        "name",
        "interface_type",
        "mac_address",
        "speed_mbps",
        "mtu",
        "parent_interface_id",
        "enabled",
        "description",
        "metadata",
    ),
    "network": (
        "cluster_id",
        "name",
        "cidr",
        "gateway",
        "status",
        "auto_allocate",
        "description",
        "metadata",
    ),
    "ip_pool": (
        "network_id",
        "name",
        "start_address",
        "end_address",
        "allocation_mode",
        "description",
    ),
    "ip_address": (
        "network_id",
        "cluster_id",
        "address",
        "interface_id",
        "ip_pool_id",
        "description",
    ),
    "service": (
        "resource_id",
        "name",
        "status",
        "description",
        "metadata",
    ),
    "service_endpoint": (
        "service_id",
        "ip_address_id",
        "protocol",
        "port",
        "description",
    ),
    # F015/O-6: account events. Snapshots are deliberately limited to the
    # non-sensitive profile fields; password material is never auditable.
    "user": ("username", "role", "status"),
    # F017/DR-316: API Key lifecycle. Never contains ``key_hash``/plaintext.
    "api_key": ("user_id", "label", "expires_at", "revoked_at"),
    # F026: cluster authorization lifecycle. No credentials or account secrets.
    "user_cluster_authorization": (
        "user_id",
        "cluster_id",
        "granted_at",
        "granted_by",
        "revoked_at",
        "revoked_by",
    ),
}


def _snapshot(object_type: str, values: dict[str, Any] | None) -> dict | None:
    """Project ``values`` onto the object type's auditable whitelist."""
    if values is None:
        return None
    allowed = AUDITABLE_FIELDS.get(object_type, ())
    return {key: values[key] for key in allowed if key in values}


def record(
    db: "Session",
    operator: "Operator | None",
    *,
    action: str,
    object_type: str,
    object_id: uuid.UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """Stage an append-only audit row in ``db`` (caller commits)."""
    row = AuditLog(
        operator_user_id=operator.user_id if operator is not None else None,
        operator_username=operator.username if operator is not None else "system",
        api_key_label=operator.api_key_label if operator is not None else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before_data=_snapshot(object_type, before),
        after_data=_snapshot(object_type, after),
    )
    db.add(row)
    return row