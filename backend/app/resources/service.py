"""F002 资源服务层：名称规范化、网段归属校验、整单序列化与 DB 冲突映射。

业务端点位于 ``router``；本模块只承载可复用的持久化与校验辅助，便于 F006 扩展。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..errors import problem
from ..models import Cluster, NetworkInterface, NetworkSegment, Resource, User

RESOURCE_TYPES = ("bare_metal", "virtual_machine")
STATUSES = ("IDLE", "ALLOC", "DOWN", "UNKNOWN")
DEFAULT_STATUS = "ALLOC"
NAME_MAX = 128

INTERFACE_OPS = ("create", "update", "delete")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def err(field: str, code: str, message: str) -> dict[str, str]:
    return {"field": field, "code": code, "message": message}


def trim(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def validate_name(
    raw: Any, *, field: str, code: str
) -> tuple[str | None, dict[str, str] | None]:
    """去首尾空格并校验非空、长度；返回 (规范化名称, 错误)。"""
    name = trim(raw)
    if not isinstance(name, str) or name == "":
        return None, err(field, code, "名称不能为空")
    if len(name) > NAME_MAX:
        return None, err(field, code, f"名称长度不能超过 {NAME_MAX}")
    return name, None


def get_resource_or_404(db: Session, resource_id: int) -> Resource:
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise problem(404, "RESOURCE_NOT_FOUND", "资源不存在")
    return resource


def get_cluster_or_404(db: Session, cluster_id: int) -> Cluster:
    cluster = db.get(Cluster, cluster_id)
    if cluster is None:
        raise problem(404, "CLUSTER_NOT_FOUND", "集群不存在")
    return cluster


def resolve_segment(
    db: Session, segment_id: int | None, cluster_id: int, field: str
) -> dict[str, str] | None:
    """校验网段存在且与本资源同集群；返回错误（无则 None）。"""
    if segment_id is None:
        return None
    segment = db.get(NetworkSegment, segment_id)
    if segment is None:
        return err(field, "INTERFACE_SEGMENT_INVALID", "网段不存在")
    if segment.cluster_id != cluster_id:
        return err(
            field, "INTERFACE_SEGMENT_CLUSTER_MISMATCH", "网段必须与本资源同集群"
        )
    return None


def fetch_interfaces(db: Session, resource_id: int) -> list[NetworkInterface]:
    return list(
        db.scalars(
            select(NetworkInterface)
            .where(NetworkInterface.resource_id == resource_id)
            .order_by(NetworkInterface.name.asc(), NetworkInterface.id.asc())
        ).all()
    )


def _segment_summary(segment: NetworkSegment) -> dict[str, Any]:
    return {
        "id": segment.id,
        "name": segment.name,
        "cidr": segment.cidr,
        "purpose": segment.purpose,
        "technology": segment.technology,
        "vlan": segment.vlan,
        "gateway": segment.gateway,
    }


def _interface_out(db: Session, interface: NetworkInterface) -> dict[str, Any]:
    segment = None
    if interface.segment_id is not None:
        row = db.get(NetworkSegment, interface.segment_id)
        if row is not None:
            segment = _segment_summary(row)
    return {
        "id": interface.id,
        "name": interface.name,
        "segment_id": interface.segment_id,
        "segment": segment,
        "created_at": interface.created_at,
        "updated_at": interface.updated_at,
    }


def resource_detail(db: Session, resource: Resource) -> dict[str, Any]:
    cluster = db.get(Cluster, resource.cluster_id)
    username: str | None = None
    if resource.status_updated_by is not None:
        actor = db.get(User, resource.status_updated_by)
        username = actor.username if actor is not None else None
    return {
        "id": resource.id,
        "cluster_id": resource.cluster_id,
        "cluster_code": cluster.code if cluster is not None else "",
        "cluster_name": cluster.name if cluster is not None else "",
        "name": resource.name,
        "resource_type": resource.resource_type,
        "status": resource.status,
        "status_updated_by": resource.status_updated_by,
        "status_updated_by_username": username,
        "status_updated_at": resource.status_updated_at,
        "interfaces": [
            _interface_out(db, i) for i in fetch_interfaces(db, resource.id)
        ],
        "version": resource.version,
        "created_at": resource.created_at,
        "updated_at": resource.updated_at,
    }


def find_by_cluster_name(
    db: Session, cluster_id: int, name: str, *, exclude_id: int | None = None
) -> Resource | None:
    conditions = [Resource.cluster_id == cluster_id, Resource.name == name]
    if exclude_id is not None:
        conditions.append(Resource.id != exclude_id)
    return db.scalars(select(Resource).where(*conditions)).first()


def name_exists_problem(existing: Resource):
    return problem(
        409,
        "RESOURCE_NAME_EXISTS",
        "同集群已存在同名资源",
        extra={
            "existing_resource_id": existing.id,
            "existing_resource_type": existing.resource_type,
        },
    )


def constraint_name(exc: IntegrityError) -> str:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", "") or ""


def resource_write_problem(
    exc: IntegrityError,
    db: Session | None = None,
    *,
    cluster_id: int | None = None,
    name: str | None = None,
):
    """资源/网卡写入的 DB 完整性冲突 → Contract 错误语义（并发兜底）。

    ``uq_resources_cluster_name``（23505）的兜底需与前置查重路径一致地带上
    ``existing_resource_id``/``existing_resource_type`` 扩展成员：传入 ``db`` 与
    冲突坐标（``cluster_id``/``name``，此时调用方应已 ``rollback``）后，在本事务
    外重新查询仍存同名资源并回填（F002-R-07）。
    """
    name_ = constraint_name(exc)
    if "uq_resources_cluster_name" in name_:
        extra: dict[str, Any] | None = None
        if db is not None and cluster_id is not None and name is not None:
            existing = find_by_cluster_name(db, cluster_id, name)
            if existing is not None:
                extra = {
                    "existing_resource_id": existing.id,
                    "existing_resource_type": existing.resource_type,
                }
        return problem(
            409, "RESOURCE_NAME_EXISTS", "同集群已存在同名资源", extra=extra
        )
    if "uq_network_interfaces_resource_name" in name_:
        return problem(409, "INTERFACE_NAME_TAKEN", "同一资源下接口名重复")
    if "fk_network_interfaces_segment" in name_:
        return problem(
            422,
            "VALIDATION_ERROR",
            "字段校验失败",
            errors=[
                err(
                    "interfaces",
                    "INTERFACE_SEGMENT_INVALID",
                    "网段无效或与本资源不同集群",
                )
            ],
        )
    if "fk_network_interfaces_resource" in name_:
        return problem(409, "RESOURCE_HAS_INTERFACES", "仍存网卡，禁止真实删除")
    if "fk_resources_cluster" in name_:
        return problem(
            409, "CLUSTER_HAS_ASSOCIATIONS", "集群仍有关联资源，禁止真实删除"
        )
    if "chk_network_interfaces_name" in name_:
        return problem(
            422,
            "VALIDATION_ERROR",
            "字段校验失败",
            errors=[err("interfaces", "INTERFACE_NAME_FORMAT", "接口名不满足约束")],
        )
    if "chk_resources_name" in name_:
        return problem(
            422,
            "VALIDATION_ERROR",
            "字段校验失败",
            errors=[err("name", "NAME_FORMAT", "资源名不满足约束")],
        )
    return problem(
        422,
        "VALIDATION_ERROR",
        "字段校验失败",
        errors=[err("request", "VALIDATION_ERROR", "数据不满足数据库约束")],
    )