"""集群登记、身份、真实删除保护与集群本体权限审计路由（Contract docs/api/F001.md）。

鉴权复用 F013 的 ``get_current_user`` / ``require_roles``；审计复用 ``app.audit``；
受管对象历史复用 ``app.resource_history``。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit, resource_history
from ..db import get_db
from ..errors import problem
from ..models import Cluster, ReservedClusterCode
from ..security.principal import Principal, get_current_user, require_roles
from .normalize import normalize_cluster_code
from .schemas import (
    ClusterCreateRequest,
    ClusterDetailOut,
    ClusterListItemOut,
    ClusterUpdateRequest,
    PagedClusters,
)

router = APIRouter(prefix="/clusters", tags=["clusters"])

admin_required = require_roles("admin")
delete_required = require_roles("maintainer", "admin")

_CODE_RE = re.compile(r"^[A-Z0-9]{1,32}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff]{1,64}$")
_CODE_MESSAGE = "集群 code 规范化后仅允许大写字母与数字，长度 1–32"
_NAME_MESSAGE = "集群名称仅允许字母、中文、下划线或数字，长度 1–64"
_PURPOSE_MESSAGE = "用途不能为空，且长度不超过 200"

_SORT_MAP = {
    "code": Cluster.code.asc(),
    "-code": Cluster.code.desc(),
    "name": Cluster.name.asc(),
    "-name": Cluster.name.desc(),
    "created_at": Cluster.created_at.asc(),
    "-created_at": Cluster.created_at.desc(),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _code_format_error() -> dict[str, str]:
    return {"field": "code", "code": "CODE_FORMAT", "message": _CODE_MESSAGE}


def _name_format_error() -> dict[str, str]:
    return {"field": "name", "code": "NAME_FORMAT", "message": _NAME_MESSAGE}


def _purpose_error() -> dict[str, str]:
    return {"field": "purpose", "code": "PURPOSE_INVALID", "message": _PURPOSE_MESSAGE}


def _purpose_valid(purpose: str) -> bool:
    return bool(purpose.strip()) and len(purpose) <= 200


def _get_cluster_or_404(db: Session, cluster_id: int) -> Cluster:
    cluster = db.get(Cluster, cluster_id)
    if cluster is None:
        raise problem(404, "CLUSTER_NOT_FOUND", "集群不存在")
    return cluster


def _is_fk_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    state = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return state == "23503"


def _cluster_change(cluster: Cluster) -> dict[str, str]:
    return {"code": cluster.code, "name": cluster.name, "purpose": cluster.purpose}


@router.get("", response_model=PagedClusters)
def list_clusters(
    page: int = Query(1),
    page_size: int = Query(20),
    q: str | None = Query(None),
    sort: str = Query("code"),
    db: Session = Depends(get_db),
    _user: Principal = Depends(get_current_user),
) -> PagedClusters:
    if page < 1 or page_size < 1 or page_size > 100:
        raise problem(400, "INVALID_REQUEST", "非法的分页参数")
    if sort not in _SORT_MAP:
        raise problem(400, "INVALID_REQUEST", "非法的排序参数")

    conditions = []
    if q is not None and q.strip() != "":
        escaped = (
            q.strip()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        conditions.append(
            or_(
                Cluster.code.ilike(pattern, escape="\\"),
                Cluster.name.ilike(pattern, escape="\\"),
            )
        )

    total = db.scalar(select(func.count()).select_from(Cluster).where(*conditions))
    items = (
        db.scalars(
            select(Cluster)
            .where(*conditions)
            .order_by(_SORT_MAP[sort], Cluster.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )
    return PagedClusters(
        items=[ClusterListItemOut.model_validate(c) for c in items],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ClusterDetailOut, status_code=201)
def create_cluster(
    payload: ClusterCreateRequest,
    db: Session = Depends(get_db),
    admin: Principal = Depends(admin_required),
) -> Cluster:
    errors = []
    normalized = normalize_cluster_code(payload.code)
    if not _CODE_RE.match(normalized):
        errors.append(_code_format_error())
    if not _NAME_RE.match(payload.name):
        errors.append(_name_format_error())
    if not _purpose_valid(payload.purpose):
        errors.append(_purpose_error())
    if errors:
        raise problem(422, "VALIDATION_ERROR", "字段校验失败", errors=errors)

    now = _utcnow()
    display_code = payload.code.strip()

    # 同事务先写保留标识表：冲突（含已真实删除集群用过的 code）→ 409。
    db.add(ReservedClusterCode(code_key=normalized))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise problem(409, "CLUSTER_CODE_TAKEN", "集群 code 已被占用，且不可复用")

    cluster = Cluster(
        code=display_code,
        name=payload.name,
        purpose=payload.purpose,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(cluster)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or ""
        if "uq_clusters_name" in constraint:
            raise problem(409, "CLUSTER_NAME_TAKEN", "集群名称已被占用")
        raise problem(409, "CLUSTER_CODE_TAKEN", "集群 code 已被占用，且不可复用")

    audit.write(
        db,
        admin,
        "cluster.create",
        "cluster",
        str(cluster.id),
        cluster.code,
        _cluster_change(cluster),
    )
    db.commit()
    db.refresh(cluster)
    return cluster


@router.get("/{cluster_id}", response_model=ClusterDetailOut)
def get_cluster(
    cluster_id: int,
    db: Session = Depends(get_db),
    _user: Principal = Depends(get_current_user),
) -> Cluster:
    return _get_cluster_or_404(db, cluster_id)


@router.patch("/{cluster_id}", response_model=ClusterDetailOut)
def update_cluster(
    cluster_id: int,
    payload: ClusterUpdateRequest,
    db: Session = Depends(get_db),
    admin: Principal = Depends(admin_required),
) -> Cluster:
    extra_fields = set((payload.model_extra or {}).keys())
    if "code" in extra_fields:
        raise problem(
            400,
            "INVALID_REQUEST",
            "集群 code 创建后不可修改",
            errors=[
                {
                    "field": "code",
                    "code": "CODE_IMMUTABLE",
                    "message": "集群 code 创建后不可修改",
                }
            ],
        )
    if extra_fields:
        raise problem(400, "INVALID_REQUEST", "请求包含不可修改字段")
    if payload.name is None and payload.purpose is None:
        raise problem(
            400,
            "INVALID_REQUEST",
            "无可修改字段",
            errors=[
                {
                    "field": "request",
                    "code": "NO_FIELDS",
                    "message": "至少提供 name 或 purpose 之一",
                }
            ],
        )

    errors = []
    if payload.name is not None and not _NAME_RE.match(payload.name):
        errors.append(_name_format_error())
    if payload.purpose is not None and not _purpose_valid(payload.purpose):
        errors.append(_purpose_error())
    if errors:
        raise problem(422, "VALIDATION_ERROR", "字段校验失败", errors=errors)

    cluster = _get_cluster_or_404(db, cluster_id)

    new_name = cluster.name
    new_purpose = cluster.purpose
    change: dict[str, object] = {}
    if payload.name is not None and payload.name != cluster.name:
        change["name"] = {"from": cluster.name, "to": payload.name}
        new_name = payload.name
    if payload.purpose is not None and payload.purpose != cluster.purpose:
        change["purpose"] = {"from": cluster.purpose, "to": payload.purpose}
        new_purpose = payload.purpose

    now = _utcnow()
    try:
        result = db.execute(
            update(Cluster)
            .where(Cluster.id == cluster_id, Cluster.version == payload.version)
            .values(
                name=new_name,
                purpose=new_purpose,
                version=Cluster.version + 1,
                updated_at=now,
            )
        )
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or ""
        if "uq_clusters_name" in constraint:
            raise problem(409, "CLUSTER_NAME_TAKEN", "集群名称已被占用")
        raise

    if result.rowcount == 0:
        db.rollback()
        raise problem(409, "VERSION_CONFLICT", "集群已被其他人修改，请刷新后重试")

    audit.write(
        db,
        admin,
        "cluster.update",
        "cluster",
        str(cluster_id),
        cluster.code,
        change,
    )
    resource_history.write(
        db,
        admin,
        "update",
        "cluster",
        str(cluster_id),
        cluster.code,
        change,
    )
    db.commit()
    db.refresh(cluster)
    return cluster


@router.delete("/{cluster_id}", status_code=204)
def delete_cluster(
    cluster_id: int,
    confirm: str = Query(..., description="二次确认：集群名称或 code"),
    version: int = Query(..., description="乐观锁版本"),
    db: Session = Depends(get_db),
    user: Principal = Depends(delete_required),
) -> None:
    cluster = _get_cluster_or_404(db, cluster_id)

    if (
        confirm.strip() != cluster.name
        and normalize_cluster_code(confirm) != cluster.code_key
    ):
        raise problem(
            422,
            "DELETE_CONFIRMATION_MISMATCH",
            "二次确认输入与集群名称或 code 不匹配",
        )

    snapshot = _cluster_change(cluster)
    # 同一事务先写审计与资源历史，再执行 DELETE。
    audit.write(
        db,
        user,
        "cluster.delete",
        "cluster",
        str(cluster_id),
        cluster.code,
        snapshot,
    )
    resource_history.write(
        db,
        user,
        "delete",
        "cluster",
        str(cluster_id),
        cluster.code,
        snapshot,
    )
    db.flush()

    try:
        result = db.execute(
            delete(Cluster).where(
                Cluster.id == cluster_id, Cluster.version == version
            )
        )
    except IntegrityError as exc:
        db.rollback()
        if _is_fk_violation(exc):
            raise problem(
                409,
                "CLUSTER_HAS_ASSOCIATIONS",
                "集群仍有关联资源，禁止真实删除",
            )
        raise

    if result.rowcount == 0:
        db.rollback()
        raise problem(409, "VERSION_CONFLICT", "集群已被其他人修改，请刷新后重试")

    db.commit()