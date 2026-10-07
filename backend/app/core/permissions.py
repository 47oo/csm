"""Enumerations and permission matrix (requirements §23, DR-09).

Roles are stored in the database as ``varchar`` + CHECK (DB-D15); these Python
``StrEnum`` members map directly to the stored values. The permission mapping is
explicit (a ``frozenset`` per role); no implicit inheritance is assumed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from fastapi import Depends

from app.core.errors import Forbidden

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.core.auth import Operator


class Role(StrEnum):
    """Base roles of phase 1 (requirements §23)."""

    VIEWER = "VIEWER"
    EDITOR = "EDITOR"
    ADMIN = "ADMIN"


class Permission(StrEnum):
    """Capabilities derived row-by-row from the §23 permission matrix."""

    READ = "READ"
    VIEW_ACTIVITY = "VIEW_ACTIVITY"
    WRITE = "WRITE"
    IMPORT = "IMPORT"
    DELETE_OBJECT = "DELETE_OBJECT"
    RELEASE_IP = "RELEASE_IP"
    VIEW_DELETED = "VIEW_DELETED"
    RESTORE = "RESTORE"
    USER_ADMIN = "USER_ADMIN"
    AUDIT_READ = "AUDIT_READ"


# §23 access matrix. VIEWER: read/activity. EDITOR: + write/import
# (unbinding is WRITE; releasing an IP is RELEASE_IP and stays ADMIN-only).
# ADMIN: everything, including object deletion/release/restore and user/audit.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(
        {
            Permission.READ,
            Permission.VIEW_ACTIVITY,
        }
    ),
    Role.EDITOR: frozenset(
        {
            Permission.READ,
            Permission.VIEW_ACTIVITY,
            Permission.WRITE,
            Permission.IMPORT,
        }
    ),
    Role.ADMIN: frozenset(Permission),
}


def permissions_for(role: Role) -> list[str]:
    """Return the role's capabilities sorted for stable API responses."""
    return sorted(permission.value for permission in ROLE_PERMISSIONS[role])


def role_has_permission(role: Role, permission: Permission) -> bool:
    """Return whether ``role`` grants ``permission``."""
    return permission in ROLE_PERMISSIONS[role]


def require_permission(permission: Permission) -> Callable[..., "Operator"]:
    """FastAPI dependency factory enforcing a single capability.

    Authentication is resolved first (``get_current_operator``); a missing or
    invalid session yields 401 AUTH_REQUIRED. An authenticated operator whose
    role lacks ``permission`` yields 403 FORBIDDEN (details.reason=permission).
    Business routers mount this from F003 onward; F002 exercises it through a
    test-mounted route using this very production dependency (TD-2 R1).
    """
    # Imported lazily to keep ``auth`` -> ``permissions`` (Role) acyclic.
    from app.core.auth import get_current_operator

    def dependency(operator: "Operator" = Depends(get_current_operator)) -> "Operator":
        if not role_has_permission(operator.role, permission):
            raise Forbidden(reason="permission")
        return operator

    return dependency