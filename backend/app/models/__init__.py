"""Persistence models.

F002 introduces ``users`` and ``user_sessions``; F003 adds ``clusters`` and the
``audit_logs`` trail; F004 adds ``resources``; F005 adds ``bare_metal_details``;
F006 adds ``virtual_machine_details``; F007 adds ``interfaces``.
"""

from __future__ import annotations

from app.models.audit_log import AuditLog
from app.models.bare_metal_detail import BareMetalDetail
from app.models.base import Base, SoftDeleteMixin
from app.models.cluster import Cluster
from app.models.interface import Interface
from app.models.resource import Resource
from app.models.session import UserSession
from app.models.user import User, UserStatus
from app.models.virtual_machine_detail import VirtualMachineDetail

__all__ = [
    "AuditLog",
    "BareMetalDetail",
    "Base",
    "Cluster",
    "Interface",
    "Resource",
    "SoftDeleteMixin",
    "User",
    "UserSession",
    "UserStatus",
    "VirtualMachineDetail",
]