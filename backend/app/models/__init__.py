"""Persistence models.

F002 introduces ``users`` and ``user_sessions``; F003 adds ``clusters`` and the
``audit_logs`` trail; F004 adds ``resources``; F005 adds ``bare_metal_details``;
F006 adds ``virtual_machine_details``; F007 adds ``interfaces``; F008 adds
``networks``; F009 adds ``ip_pools``; F010 adds ``ip_addresses``; F011 adds
``services``; F012 adds ``service_endpoints``; F026 adds
``user_cluster_authorizations``.
"""

from __future__ import annotations

from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.models.bare_metal_detail import BareMetalDetail
from app.models.base import Base, SoftDeleteMixin
from app.models.cluster import Cluster
from app.models.interface import Interface
from app.models.ip_address import IPAddress
from app.models.ip_pool import IPPool
from app.models.network import Network
from app.models.resource import Resource
from app.models.service import Service
from app.models.service_endpoint import ServiceEndpoint
from app.models.session import UserSession
from app.models.user import User, UserStatus
from app.models.user_cluster_authorization import UserClusterAuthorization
from app.models.virtual_machine_detail import VirtualMachineDetail

__all__ = [
    "ApiKey",
    "AuditLog",
    "BareMetalDetail",
    "Base",
    "Cluster",
    "IPAddress",
    "IPPool",
    "Interface",
    "Network",
    "Resource",
    "Service",
    "ServiceEndpoint",
    "SoftDeleteMixin",
    "User",
    "UserClusterAuthorization",
    "UserSession",
    "UserStatus",
    "VirtualMachineDetail",
]