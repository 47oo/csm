"""F002 资源服务层：名称规范化、网段归属校验、整单序列化与 DB 冲突映射。

业务端点位于 ``router``；本模块只承载可复用的持久化与校验辅助，便于 F006 扩展。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from ..errors import problem
from ..ip_allocation.addressing import ipv4_to_int
from ..models import (
    Cluster,
    IpAddress,
    NetworkInterface,
    NetworkSegment,
    Resource,
    User,
)
from ..search.matching import match_rank, normalize_query

RESOURCE_TYPES = ("bare_metal", "virtual_machine")
STATUSES = ("IDLE", "ALLOC", "DOWN", "UNKNOWN")
DEFAULT_STATUS = "ALLOC"
NAME_MAX = 128

RESOURCE_TYPE_LABELS = {
    "bare_metal": "裸金属",
    "virtual_machine": "虚拟机",
}
STATUS_LABELS = {
    "IDLE": "空闲",
    "ALLOC": "已分配",
    "DOWN": "宕机",
    "UNKNOWN": "未知",
}

# 排序白名单（F003 §4.4）：字段 → (ORM 属性, 是否降序)。
SORT_FIELDS: dict[str, tuple[str, bool]] = {
    "name": ("name", False),
    "-name": ("name", True),
    "updated_at": ("updated_at", False),
    "-updated_at": ("updated_at", True),
    "created_at": ("created_at", False),
    "-created_at": ("created_at", True),
    "status": ("status", False),
    "-status": ("status", True),
}
ALLOWED_SORTS = tuple(SORT_FIELDS)

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


def _interface_out(
    db: Session, interface: NetworkInterface, management_ip_id: int | None
) -> dict[str, Any]:
    segment = None
    if interface.segment_id is not None:
        row = db.get(NetworkSegment, interface.segment_id)
        if row is not None:
            segment = _segment_summary(row)
    ips = db.scalars(
        select(IpAddress).where(IpAddress.interface_id == interface.id)
    ).all()
    ips = sorted(ips, key=lambda row: ipv4_to_int(row.ip))
    return {
        "id": interface.id,
        "name": interface.name,
        "segment_id": interface.segment_id,
        "segment": segment,
        "ips": [
            {
                "id": ip.id,
                "address": ip.ip,
                "segment_id": ip.segment_id,
                "interface_id": ip.interface_id,
                "is_management": ip.id == management_ip_id,
                "created_at": ip.created_at,
            }
            for ip in ips
        ],
        "created_at": interface.created_at,
        "updated_at": interface.updated_at,
    }


def _management_ip_out(
    db: Session, resource: Resource
) -> dict[str, Any] | None:
    if resource.management_ip_id is None:
        return None
    ip = db.get(IpAddress, resource.management_ip_id)
    if ip is None:
        return None
    interface = db.get(NetworkInterface, ip.interface_id)
    return {
        "ip_id": ip.id,
        "address": ip.ip,
        "interface_id": ip.interface_id,
        "interface_name": interface.name if interface is not None else "",
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
            _interface_out(db, i, resource.management_ip_id)
            for i in fetch_interfaces(db, resource.id)
        ],
        "management_ip": _management_ip_out(db, resource),
        "version": resource.version,
        "created_at": resource.created_at,
        "updated_at": resource.updated_at,
    }


def _list_item(
    resource: Resource,
    cluster: Cluster,
    ip_row: IpAddress | None,
    iface_row: NetworkInterface | None,
) -> dict[str, Any]:
    management_ip: dict[str, Any] | None = None
    if ip_row is not None:
        management_ip = {
            "ip_id": ip_row.id,
            "address": ip_row.ip,
            "interface_id": ip_row.interface_id,
            "interface_name": iface_row.name if iface_row is not None else "",
        }
    return {
        "id": resource.id,
        "name": resource.name,
        "cluster_id": resource.cluster_id,
        "cluster_code": cluster.code,
        "cluster_name": cluster.name,
        "resource_type": resource.resource_type,
        "resource_type_label": RESOURCE_TYPE_LABELS.get(
            resource.resource_type, resource.resource_type
        ),
        "status": resource.status,
        "status_label": STATUS_LABELS.get(resource.status, resource.status),
        "management_ip": management_ip,
        "updated_at": resource.updated_at,
    }


def _match_weight(value: str, needle: str) -> int | None:
    """§8.2 匹配权重：完全(1) > 前缀(2) > 包含(4)；不匹配返回 None。

    自 F008 起复用共享纯函数 :func:`app.search.matching.match_rank`，行为不变。
    """
    return match_rank(value, needle)


def list_resources(
    db: Session,
    *,
    cluster_id: int,
    resource_type: str | None,
    status: str | None,
    q: str | None,
    sort: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """F003 计算资源列表：集群作用域 + 类型/状态筛选 + q 搜索 + 排序 + offset 分页。

    无 ``q`` 走 SQL 排序分页；有 ``q`` 时在集群内全量匹配并按权重排序后再分页。
    管理 IP 与集群列一次 JOIN 取回，IP 搜索批量取回，避免 N+1。
    """
    cluster = db.get(Cluster, cluster_id)
    scope = {
        "cluster_id": cluster_id,
        "cluster_code": cluster.code if cluster is not None else "",
        "cluster_name": cluster.name if cluster is not None else "",
    }

    conditions: list[Any] = [Resource.cluster_id == cluster_id]
    if resource_type is not None:
        conditions.append(Resource.resource_type == resource_type)
    if status is not None:
        conditions.append(Resource.status == status)

    mgmt_ip = aliased(IpAddress)
    mgmt_iface = aliased(NetworkInterface)
    base = (
        select(Resource, Cluster, mgmt_ip, mgmt_iface)
        .join(Cluster, Cluster.id == Resource.cluster_id)
        .outerjoin(mgmt_ip, mgmt_ip.id == Resource.management_ip_id)
        .outerjoin(mgmt_iface, mgmt_iface.id == mgmt_ip.interface_id)
        .where(*conditions)
    )

    normalized = normalize_query(q)
    needle = normalized.lower() if normalized is not None else None

    if needle is None:
        total = (
            db.scalar(select(func.count()).select_from(Resource).where(*conditions))
            or 0
        )
        field, descending = SORT_FIELDS[sort]
        column = getattr(Resource, field)
        order = column.desc() if descending else column.asc()
        rows = db.execute(
            base.order_by(order, Resource.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {
            "items": [_list_item(*row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "scope": scope,
        }

    candidates = db.execute(base).all()
    ip_rows = db.execute(
        select(IpAddress.resource_id, IpAddress.ip).where(
            IpAddress.cluster_id == cluster_id
        )
    ).all()
    ips_by_resource: dict[int, list[str]] = {}
    for resource_id, address in ip_rows:
        ips_by_resource.setdefault(resource_id, []).append(address)

    needle_is_id = needle.isdigit()
    needle_int = int(needle) if needle_is_id else None

    scored: list[tuple[int, Any, Any, Any, Any]] = []
    for resource, cluster_row, ip_row, iface_row in candidates:
        weights: list[int] = []
        weight = _match_weight(resource.name, needle)
        if weight is not None:
            weights.append(weight)
        for address in ips_by_resource.get(resource.id, ()):
            weight = _match_weight(address, needle)
            if weight is not None:
                weights.append(weight)
        if needle_is_id and needle_int == resource.id:
            weights.append(3)
        if weights:
            scored.append((min(weights), resource, cluster_row, ip_row, iface_row))

    scored.sort(key=lambda item: item[1].id)
    field, descending = SORT_FIELDS[sort]
    scored.sort(key=lambda item: getattr(item[1], field), reverse=descending)
    scored.sort(key=lambda item: item[0])

    total = len(scored)
    start = (page - 1) * page_size
    page_slice = scored[start : start + page_size]
    return {
        "items": [
            _list_item(resource, cluster_row, ip_row, iface_row)
            for _, resource, cluster_row, ip_row, iface_row in page_slice
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "scope": scope,
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