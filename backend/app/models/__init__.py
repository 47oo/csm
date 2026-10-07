"""Persistence models.

F002 introduces ``users`` and ``user_sessions``; F003 adds ``clusters`` and the
``audit_logs`` trail; F004 adds ``resources``; F005 adds ``bare_metal_details``.
"""

from __future__ import annotations

from app.models.audit_log import AuditLog
from app.models.bare_metal_detail import BareMetalDetail
from app.models.base import Base, SoftDeleteMixin
from app.models.cluster import Cluster
from app.models.resource import Resource
from app.models.session import UserSession
from app.models.user import User, UserStatus

__all__ = [
    "AuditLog",
    "BareMetalDetail",
    "Base",
    "Cluster",
    "Resource",
    "SoftDeleteMixin",
    "User",
    "UserSession",
    "UserStatus",
]