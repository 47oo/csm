"""F005 网段、保留地址与网关路由（Contract docs/api/F005.md）。

鉴权复用 F013 ``get_current_user`` / ``require_roles``；审计复用 ``app.audit``；
资源历史复用 ``app.resource_history``；地址运算见 ``addressing``。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit, resource_history
from ..db import get_db
from ..errors import problem
from ..models import Cluster, NetworkSegment, SegmentReservedAddress
from ..security.principal import Principal, get_current_user, require_roles
from .addressing import (
    CidrError,
    contains,
    is_ipv4,
    ipv4_to_int,
    normalize_cidr,
    ranges_overlap,
)
from .schemas import (
    NetworkSegmentCreateRequest,
    NetworkSegmentDetail,
    NetworkSegmentListItem,
    NetworkSegmentUpdateRequest,
    PagedNetworkSegments,
    ReservedAddressCreateRequest,
    ReservedAddressList,
    ReservedAddressOut,
)
from .service import (
    SegmentUsage,
    detail,
    fk_delete_problem,
    get_segment_or_404,
    integrity_problem,
    list_item,
    reserved_addresses,
)

router = APIRouter(prefix="/network-segments", tags=["network-segments"])

write_required = require_roles("maintainer", "admin")

_NAME_MAX = 128
_PURPOSE_MAX = 200
_TECHNOLOGY_MAX = 100

_EDITABLE_FIELDS = {
    "name",
    "cidr",
    "purpose",
    "technology",
    "vlan",
    "gateway",
    "auto_alloc_start",
    "auto_alloc_end",
}

_SORT_MAP = {
    "name": NetworkSegment.name.asc(),
    "-name": NetworkSegment.name.desc(),
    "cidr": NetworkSegment.cidr.asc(),
    "-cidr": NetworkSegment.cidr.desc(),
    "created_at": NetworkSegment.created_at.asc(),
    "-created_at": NetworkSegment.created_at.desc(),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _err(field: str, code: str, message: str) -> dict[str, str]:
    return {"field": field, "code": code, "message": message}


def _fail(errors: list[dict[str, str]]):
    raise problem(422, "VALIDATION_ERROR", "字段校验失败", errors=errors)


def _parse_cidr(raw: str) -> tuple[str | None, dict[str, str] | None]:
    try:
        return normalize_cidr(raw), None
    except CidrError as exc:
        return None, _err("cidr", exc.code, exc.message)


def _validate_text(
    value: str | None,
    *,
    field: str,
    code: str,
    max_len: int,
    label: str,
) -> tuple[str | None, dict[str, str] | None]:
    if value is None or not isinstance(value, str):
        return None, _err(field, code, f"{label}不能为空")
    trimmed = value.strip()
    if not trimmed:
        return None, _err(field, code, f"{label}不能为空")
    if len(trimmed) > max_len:
        return None, _err(field, code, f"{label}长度不能超过 {max_len}")
    return trimmed, None


def _validate_ipv4_in_cidr(
    value: str | None,
    *,
    field: str,
    code: str,
    cidr: str,
    label: str,
) -> dict[str, str] | None:
    if value is None:
        return None
    if not is_ipv4(value) or not contains(cidr, value):
        return _err(field, code, f"{label}必须是落在网段 CIDR 内的合法 IPv4")
    return None


def _resolve_auto_range(
    start: str | None,
    end: str | None,
    cidr: str,
) -> tuple[str | None, str | None, list[dict[str, str]]]:
    """返回 (start, end, errors)；两端同为 None 表示未启用。"""
    errors: list[dict[str, str]] = []
    if (start is None) != (end is None):
        errors.append(
            _err("auto_alloc_start", "AUTO_RANGE_INVALID", "自动分配范围两端须同时提供或同时为空")
        )
        return None, None, errors
    if start is None and end is None:
        return None, None, errors
    if not (is_ipv4(start) and is_ipv4(end)):  # type: ignore[arg-type]
        return None, None, [
            _err("auto_alloc_start", "AUTO_RANGE_INVALID", "自动分配范围必须为合法 IPv4")
        ]
    if not contains(cidr, start) or not contains(cidr, end):  # type: ignore[arg-type]
        return None, None, [_err("auto_alloc_start", "AUTO_RANGE_INVALID", "自动分配范围必须落在网段 CIDR 内")]
    if ipv4_to_int(start) > ipv4_to_int(end):  # type: ignore[arg-type]
        return None, None, [_err("auto_alloc_start", "AUTO_RANGE_INVALID", "自动分配起始不能大于结束")]
    return start, end, []


def _validate_vlan(vlan: int | None) -> dict[str, str] | None:
    if vlan is None:
        return None
    if vlan < 1 or vlan > 4094:
        return _err("vlan", "VLAN_INVALID", "VLAN 取值范围为 1–4094")
    return None


# --------------------------------------------------------------------------- #
# 网段本体
# --------------------------------------------------------------------------- #


@router.get("", response_model=PagedNetworkSegments)
def list_segments(
    cluster_id: int | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    q: str | None = Query(None),
    sort: str = Query("name"),
    db: Session = Depends(get_db),
    _user: Principal = Depends(get_current_user),
) -> PagedNetworkSegments:
    if page < 1 or page_size < 1 or page_size > 100:
        raise problem(400, "INVALID_REQUEST", "非法的分页参数")
    if sort not in _SORT_MAP:
        raise problem(400, "INVALID_REQUEST", "非法的排序参数")

    conditions = []
    if cluster_id is not None:
        conditions.append(NetworkSegment.cluster_id == cluster_id)
    if q is not None and q.strip() != "":
        escaped = (
            q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        conditions.append(
            or_(
                NetworkSegment.name.ilike(pattern, escape="\\"),
                NetworkSegment.cidr.ilike(pattern, escape="\\"),
                NetworkSegment.purpose.ilike(pattern, escape="\\"),
                NetworkSegment.technology.ilike(pattern, escape="\\"),
            )
        )

    total = db.scalar(
        select(func.count()).select_from(NetworkSegment).where(*conditions)
    ) or 0
    rows = db.scalars(
        select(NetworkSegment)
        .where(*conditions)
        .order_by(_SORT_MAP[sort], NetworkSegment.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return PagedNetworkSegments(
        items=[NetworkSegmentListItem.model_validate(list_item(db, s)) for s in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=NetworkSegmentDetail, status_code=201)
def create_segment(
    payload: NetworkSegmentCreateRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(write_required),
) -> dict:
    errors: list[dict[str, str]] = []
    name, name_err = _validate_text(
        payload.name, field="name", code="NAME_FORMAT", max_len=_NAME_MAX, label="网段名称"
    )
    if name_err:
        errors.append(name_err)
    cidr, cidr_err = _parse_cidr(payload.cidr)
    if cidr_err:
        errors.append(cidr_err)
    purpose, purpose_err = _validate_text(
        payload.purpose, field="purpose", code="PURPOSE_INVALID", max_len=_PURPOSE_MAX, label="用途"
    )
    if purpose_err:
        errors.append(purpose_err)
    technology, tech_err = _validate_text(
        payload.technology,
        field="technology",
        code="TECHNOLOGY_INVALID",
        max_len=_TECHNOLOGY_MAX,
        label="技术类型",
    )
    if tech_err:
        errors.append(tech_err)
    vlan_err = _validate_vlan(payload.vlan)
    if vlan_err:
        errors.append(vlan_err)
    if errors or cidr is None:
        _fail(errors)

    gateway_err = _validate_ipv4_in_cidr(
        payload.gateway,
        field="gateway",
        code="GATEWAY_OUT_OF_CIDR",
        cidr=cidr,
        label="网关",
    )
    if gateway_err:
        errors.append(gateway_err)
    auto_start, auto_end, auto_errors = _resolve_auto_range(
        payload.auto_alloc_start, payload.auto_alloc_end, cidr
    )
    errors.extend(auto_errors)
    if errors:
        _fail(errors)

    if db.get(Cluster, payload.cluster_id) is None:
        raise problem(404, "CLUSTER_NOT_FOUND", "所属集群不存在")

    now = _utcnow()
    segment = NetworkSegment(
        cluster_id=payload.cluster_id,
        name=name,
        cidr=cidr,
        purpose=purpose,
        technology=technology,
        vlan=payload.vlan,
        gateway=payload.gateway,
        auto_alloc_start=auto_start,
        auto_alloc_end=auto_end,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(segment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise integrity_problem(exc)

    audit.write(
        db,
        user,
        "segment.create",
        "segment",
        str(segment.id),
        segment.name,
        {
            "name": segment.name,
            "cidr": segment.cidr,
            "purpose": segment.purpose,
            "technology": segment.technology,
            "vlan": segment.vlan,
            "gateway": segment.gateway,
            "auto_alloc_start": segment.auto_alloc_start,
            "auto_alloc_end": segment.auto_alloc_end,
        },
    )
    db.commit()
    db.refresh(segment)
    return detail(db, segment)


@router.get("/{segment_id}", response_model=NetworkSegmentDetail)
def get_segment(
    segment_id: int,
    db: Session = Depends(get_db),
    _user: Principal = Depends(get_current_user),
) -> dict:
    segment = get_segment_or_404(db, segment_id)
    return detail(db, segment)


@router.patch("/{segment_id}", response_model=NetworkSegmentDetail)
def update_segment(
    segment_id: int,
    payload: NetworkSegmentUpdateRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(write_required),
) -> dict:
    extra = set((payload.model_extra or {}).keys())
    if extra:
        raise problem(400, "INVALID_REQUEST", "请求包含不可修改字段")
    provided = payload.model_fields_set & _EDITABLE_FIELDS
    if not provided:
        raise problem(
            400,
            "INVALID_REQUEST",
            "无可修改字段",
            errors=[_err("request", "NO_FIELDS", "至少提供一个可修改字段")],
        )

    segment = get_segment_or_404(db, segment_id)

    errors: list[dict[str, str]] = []
    new_name = segment.name
    new_cidr = segment.cidr
    new_purpose = segment.purpose
    new_technology = segment.technology
    new_vlan = segment.vlan
    new_gateway = segment.gateway
    new_auto_start = segment.auto_alloc_start
    new_auto_end = segment.auto_alloc_end
    cidr_changed = False

    if "name" in provided:
        if payload.name is None:
            errors.append(_err("name", "NAME_FORMAT", "网段名称不能为空"))
        else:
            value, err = _validate_text(
                payload.name, field="name", code="NAME_FORMAT", max_len=_NAME_MAX, label="网段名称"
            )
            if err:
                errors.append(err)
            else:
                new_name = value
    if "cidr" in provided:
        if payload.cidr is None:
            errors.append(_err("cidr", "CIDR_INVALID", "CIDR 不能为空"))
        else:
            parsed, err = _parse_cidr(payload.cidr)
            if err:
                errors.append(err)
            else:
                cidr_changed = parsed != segment.cidr
                new_cidr = parsed
    if "purpose" in provided:
        if payload.purpose is None:
            errors.append(_err("purpose", "PURPOSE_INVALID", "用途不能为空"))
        else:
            value, err = _validate_text(
                payload.purpose, field="purpose", code="PURPOSE_INVALID", max_len=_PURPOSE_MAX, label="用途"
            )
            if err:
                errors.append(err)
            else:
                new_purpose = value
    if "technology" in provided:
        if payload.technology is None:
            errors.append(_err("technology", "TECHNOLOGY_INVALID", "技术类型不能为空"))
        else:
            value, err = _validate_text(
                payload.technology,
                field="technology",
                code="TECHNOLOGY_INVALID",
                max_len=_TECHNOLOGY_MAX,
                label="技术类型",
            )
            if err:
                errors.append(err)
            else:
                new_technology = value
    if "vlan" in provided:
        vlan_err = _validate_vlan(payload.vlan)
        if vlan_err:
            errors.append(vlan_err)
        else:
            new_vlan = payload.vlan

    if "gateway" in provided:
        new_gateway = payload.gateway
    if "auto_alloc_start" in provided or "auto_alloc_end" in provided:
        if not ("auto_alloc_start" in provided and "auto_alloc_end" in provided):
            errors.append(
                _err("auto_alloc_start", "AUTO_RANGE_INVALID", "自动分配范围两端须同时提供")
            )
        else:
            start, end, auto_errors = _resolve_auto_range(
                payload.auto_alloc_start, payload.auto_alloc_end, new_cidr
            )
            errors.extend(auto_errors)
            if not auto_errors:
                new_auto_start, new_auto_end = start, end

    if errors:
        _fail(errors)

    # 存在已分配 IP 时禁止改 CIDR（F006 生效；F005 恒为 0）。
    if cidr_changed and SegmentUsage.allocated_count(db, segment.id) > 0:
        raise problem(409, "CIDR_IMMUTABLE", "存在已分配 IP，禁止修改 CIDR")

    if cidr_changed:
        # 既有保留地址须仍落在新 CIDR 内。
        for r in reserved_addresses(db, segment.id):
            if not (contains(new_cidr, r.start_ip) and contains(new_cidr, r.end_ip)):
                _fail([_err("cidr", "RESERVED_OUT_OF_CIDR", "既有保留地址超出新 CIDR，须先删除")])

    gateway_err = _validate_ipv4_in_cidr(
        new_gateway,
        field="gateway",
        code="GATEWAY_OUT_OF_CIDR",
        cidr=new_cidr,
        label="网关",
    )
    if gateway_err:
        _fail([gateway_err])
    auto_start, auto_end, auto_errors = _resolve_auto_range(
        new_auto_start, new_auto_end, new_cidr
    )
    if auto_errors:
        _fail(auto_errors)

    change: dict[str, object] = {}
    for field, old, new in (
        ("name", segment.name, new_name),
        ("cidr", segment.cidr, new_cidr),
        ("purpose", segment.purpose, new_purpose),
        ("technology", segment.technology, new_technology),
        ("vlan", segment.vlan, new_vlan),
        ("gateway", segment.gateway, new_gateway),
        ("auto_alloc_start", segment.auto_alloc_start, auto_start),
        ("auto_alloc_end", segment.auto_alloc_end, auto_end),
    ):
        if old != new:
            change[field] = {"from": old, "to": new}

    now = _utcnow()
    try:
        result = db.execute(
            update(NetworkSegment)
            .where(NetworkSegment.id == segment.id, NetworkSegment.version == payload.version)
            .values(
                name=new_name,
                cidr=new_cidr,
                purpose=new_purpose,
                technology=new_technology,
                vlan=new_vlan,
                gateway=new_gateway,
                auto_alloc_start=auto_start,
                auto_alloc_end=auto_end,
                version=NetworkSegment.version + 1,
                updated_at=now,
            )
        )
    except IntegrityError as exc:
        db.rollback()
        raise integrity_problem(exc)

    if result.rowcount == 0:
        db.rollback()
        raise problem(409, "VERSION_CONFLICT", "网段已被其他人修改，请刷新后重试")

    audit.write(
        db, user, "segment.update", "segment", str(segment.id), new_name, change
    )
    resource_history.write(
        db, user, "update", "segment", str(segment.id), new_name, change
    )
    db.commit()
    db.refresh(segment)
    return detail(db, segment)


@router.delete("/{segment_id}", status_code=204)
def delete_segment(
    segment_id: int,
    confirm: str = Query(...),
    version: int = Query(...),
    db: Session = Depends(get_db),
    user: Principal = Depends(write_required),
) -> None:
    segment = get_segment_or_404(db, segment_id)

    if confirm.strip() != segment.name:
        raise problem(
            422, "DELETE_CONFIRMATION_MISMATCH", "二次确认输入与网段名称不匹配"
        )

    # 事务内锁定父行，串行化删除前置检查。
    db.execute(
        select(NetworkSegment).where(NetworkSegment.id == segment_id).with_for_update()
    )
    db.refresh(segment)

    if reserved_addresses(db, segment.id):
        raise problem(409, "SEGMENT_HAS_RESERVED_ADDRESSES", "仍存保留地址，禁止删除")
    if segment.gateway is not None:
        raise problem(409, "SEGMENT_GATEWAY_NOT_CLEARED", "网关尚未显式清空，禁止删除")

    snapshot = {"name": segment.name, "cidr": segment.cidr}
    # 同一事务先写审计与资源历史，再执行 DELETE。
    audit.write(
        db, user, "segment.delete", "segment", str(segment.id), segment.name, snapshot
    )
    resource_history.write(
        db, user, "delete", "segment", str(segment.id), segment.name, snapshot
    )
    db.flush()

    try:
        result = db.execute(
            delete(NetworkSegment).where(
                NetworkSegment.id == segment_id, NetworkSegment.version == version
            )
        )
    except IntegrityError as exc:
        db.rollback()
        raise fk_delete_problem(exc)

    if result.rowcount == 0:
        db.rollback()
        raise problem(409, "VERSION_CONFLICT", "网段已被其他人修改，请刷新后重试")
    db.commit()


# --------------------------------------------------------------------------- #
# 保留地址 / 网关
# --------------------------------------------------------------------------- #


@router.get("/{segment_id}/reserved-addresses", response_model=ReservedAddressList)
def list_reserved_addresses(
    segment_id: int,
    db: Session = Depends(get_db),
    _user: Principal = Depends(get_current_user),
) -> ReservedAddressList:
    segment = get_segment_or_404(db, segment_id)
    rows = reserved_addresses(db, segment.id)
    return ReservedAddressList(
        items=[
            ReservedAddressOut(
                id=r.id,
                start_ip=r.start_ip,
                end_ip=r.end_ip,
                is_range=r.start_ip != r.end_ip,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )


@router.post(
    "/{segment_id}/reserved-addresses",
    response_model=ReservedAddressOut,
    status_code=201,
)
def create_reserved_address(
    segment_id: int,
    payload: ReservedAddressCreateRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(write_required),
) -> ReservedAddressOut:
    segment = get_segment_or_404(db, segment_id)
    # 事务内锁定父网段，避免与 CIDR 修改竞争导致越界。
    db.execute(
        select(NetworkSegment).where(NetworkSegment.id == segment_id).with_for_update()
    )
    db.refresh(segment)

    start_raw = payload.start_ip
    end_raw = payload.end_ip if payload.end_ip is not None else payload.start_ip

    errors: list[dict[str, str]] = []
    start = end = None
    if not is_ipv4(start_raw):
        errors.append(_err("start_ip", "RESERVED_RANGE_INVALID", "起始地址必须为合法 IPv4"))
    if not is_ipv4(end_raw):
        errors.append(_err("end_ip", "RESERVED_RANGE_INVALID", "结束地址必须为合法 IPv4"))
    if not errors:
        start = ipv4_to_int(start_raw)
        end = ipv4_to_int(end_raw)
        if end < start:
            errors.append(_err("end_ip", "RESERVED_RANGE_INVALID", "结束地址不能小于起始地址"))
        elif not (contains(segment.cidr, start_raw) and contains(segment.cidr, end_raw)):
            errors.append(_err("start_ip", "RESERVED_OUT_OF_CIDR", "保留地址超出所属网段 CIDR"))
        else:
            for existing in reserved_addresses(db, segment.id):
                if ranges_overlap(
                    (start, end),
                    (ipv4_to_int(existing.start_ip), ipv4_to_int(existing.end_ip)),
                ):
                    errors.append(
                        _err("start_ip", "RESERVED_OVERLAP", "保留地址与既有保留范围重叠")
                    )
                    break
    if errors:
        _fail(errors)

    row = SegmentReservedAddress(
        segment_id=segment.id,
        start_ip=start_raw,
        end_ip=end_raw,
        created_at=_utcnow(),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise integrity_problem(exc)

    change = {"reserved_id": row.id, "start_ip": row.start_ip, "end_ip": row.end_ip}
    audit.write(
        db,
        user,
        "segment.reserved_address.create",
        "segment",
        str(segment.id),
        segment.name,
        change,
    )
    resource_history.write(
        db, user, "update", "segment", str(segment.id), segment.name, change
    )
    db.commit()
    db.refresh(row)
    return ReservedAddressOut(
        id=row.id,
        start_ip=row.start_ip,
        end_ip=row.end_ip,
        is_range=row.start_ip != row.end_ip,
        created_at=row.created_at,
    )


@router.delete("/{segment_id}/reserved-addresses/{reserved_id}", status_code=204)
def delete_reserved_address(
    segment_id: int,
    reserved_id: int,
    db: Session = Depends(get_db),
    user: Principal = Depends(write_required),
) -> None:
    segment = get_segment_or_404(db, segment_id)
    row = db.execute(
        select(SegmentReservedAddress).where(
            SegmentReservedAddress.id == reserved_id,
            SegmentReservedAddress.segment_id == segment_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise problem(404, "RESERVED_ADDRESS_NOT_FOUND", "保留地址不存在")

    change = {"reserved_id": row.id, "start_ip": row.start_ip, "end_ip": row.end_ip}
    audit.write(
        db,
        user,
        "segment.reserved_address.delete",
        "segment",
        str(segment.id),
        segment.name,
        change,
    )
    resource_history.write(
        db, user, "update", "segment", str(segment.id), segment.name, change
    )
    db.execute(
        delete(SegmentReservedAddress).where(SegmentReservedAddress.id == reserved_id)
    )
    db.commit()


@router.delete("/{segment_id}/gateway", status_code=204)
def clear_gateway(
    segment_id: int,
    version: int = Query(...),
    db: Session = Depends(get_db),
    user: Principal = Depends(write_required),
) -> None:
    segment = get_segment_or_404(db, segment_id)

    if segment.gateway is None:
        # 幂等：已为空仍返回 204，不再消耗 version。
        return None

    now = _utcnow()
    result = db.execute(
        update(NetworkSegment)
        .where(NetworkSegment.id == segment_id, NetworkSegment.version == version)
        .values(gateway=None, version=NetworkSegment.version + 1, updated_at=now)
    )
    if result.rowcount == 0:
        db.rollback()
        raise problem(409, "VERSION_CONFLICT", "网段已被其他人修改，请刷新后重试")

    change = {"gateway": {"from": segment.gateway, "to": None}}
    audit.write(
        db, user, "segment.gateway.clear", "segment", str(segment.id), segment.name, change
    )
    resource_history.write(
        db, user, "update", "segment", str(segment.id), segment.name, change
    )
    db.commit()