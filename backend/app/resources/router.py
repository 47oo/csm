"""F002 计算资源登记、网卡与真实删除路由（Contract docs/api/F002.md）。

鉴权复用 F013 ``get_current_user`` / ``require_roles``；审计复用 ``app.audit``；
资源历史复用 ``app.resource_history``；网段读取复用 F005 模型。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit, resource_history
from ..db import get_db
from ..errors import problem
from ..models import NetworkInterface, Resource
from ..security.principal import Principal, get_current_user, require_roles
from .schemas import (
    ResourceCreateRequest,
    ResourceFormDetail,
    ResourceUpdateRequest,
)
from .service import (
    DEFAULT_STATUS,
    INTERFACE_OPS,
    RESOURCE_TYPES,
    STATUSES,
    err,
    fetch_interfaces,
    find_by_cluster_name,
    get_cluster_or_404,
    get_resource_or_404,
    name_exists_problem,
    resolve_segment,
    resource_detail,
    resource_write_problem,
    utcnow,
    validate_name,
)

router = APIRouter(prefix="/resources", tags=["resources"])

write_required = require_roles("maintainer", "admin")


def _fail_validation(errors: list[dict[str, str]]) -> None:
    raise problem(422, "VALIDATION_ERROR", "字段校验失败", errors=errors)


def _created_snapshot(resource: Resource, interfaces: list[tuple[str, int | None]]):
    return {
        "cluster_id": resource.cluster_id,
        "name": resource.name,
        "resource_type": resource.resource_type,
        "status": resource.status,
        "interfaces": [
            {"name": name, "segment_id": segment_id} for name, segment_id in interfaces
        ],
    }


@router.post("", response_model=ResourceFormDetail, status_code=201)
def create_resource(
    payload: ResourceCreateRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(write_required),
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    name, name_err = validate_name(payload.name, field="name", code="NAME_FORMAT")
    if name_err:
        errors.append(name_err)

    resource_type = payload.resource_type
    if resource_type not in RESOURCE_TYPES:
        errors.append(
            err(
                "resource_type",
                "RESOURCE_TYPE_INVALID",
                "资源类型必须为 bare_metal 或 virtual_machine",
            )
        )

    status = payload.status if payload.status is not None else DEFAULT_STATUS
    if status not in STATUSES:
        errors.append(err("status", "STATUS_INVALID", "状态取值非法"))

    raw_interfaces = payload.interfaces or []
    resolved: list[tuple[str, int | None]] = []
    seen: dict[str, int] = {}
    for index, item in enumerate(raw_interfaces):
        interface_name, interface_err = validate_name(
            item.name, field=f"interfaces[{index}].name", code="INTERFACE_NAME_FORMAT"
        )
        if interface_err:
            errors.append(interface_err)
        elif interface_name in seen:
            errors.append(
                err(
                    f"interfaces[{index}].name",
                    "INTERFACE_NAME_DUPLICATE_IN_PAYLOAD",
                    "同一请求内接口名不得重复",
                )
            )
        else:
            seen[interface_name] = index
        resolved.append((interface_name or "", item.segment_id))

    if errors:
        _fail_validation(errors)

    get_cluster_or_404(db, payload.cluster_id)

    segment_errors: list[dict[str, str]] = []
    for index, (_, segment_id) in enumerate(resolved):
        segment_err = resolve_segment(
            db, segment_id, payload.cluster_id, f"interfaces[{index}].segment_id"
        )
        if segment_err:
            segment_errors.append(segment_err)
    if segment_errors:
        _fail_validation(segment_errors)

    existing = find_by_cluster_name(db, payload.cluster_id, name)
    if existing is not None:
        raise name_exists_problem(existing)

    now = utcnow()
    resource = Resource(
        cluster_id=payload.cluster_id,
        name=name,
        resource_type=resource_type,
        status=status,
        status_updated_by=user.user_id,
        status_updated_at=now,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(resource)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise resource_write_problem(exc)

    for interface_name, segment_id in resolved:
        db.add(
            NetworkInterface(
                resource_id=resource.id,
                cluster_id=resource.cluster_id,
                name=interface_name,
                segment_id=segment_id,
                created_at=now,
                updated_at=now,
            )
        )
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise resource_write_problem(exc)

    audit.write(
        db,
        user,
        "resource.create",
        "resource",
        str(resource.id),
        resource.name,
        _created_snapshot(resource, resolved),
    )
    db.commit()
    db.refresh(resource)
    return resource_detail(db, resource)


@router.get("/{resource_id}", response_model=ResourceFormDetail)
def get_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    _user: Principal = Depends(get_current_user),
) -> dict[str, Any]:
    resource = get_resource_or_404(db, resource_id)
    return resource_detail(db, resource)


@router.patch("/{resource_id}", response_model=ResourceFormDetail)
def update_resource(
    resource_id: int,
    payload: ResourceUpdateRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(write_required),
) -> dict[str, Any]:
    resource = get_resource_or_404(db, resource_id)

    extras = payload.model_extra or {}
    if (
        "resource_type" in extras
        and extras["resource_type"] != resource.resource_type
    ):
        raise problem(
            400,
            "INVALID_REQUEST",
            "资源类型创建后不可修改",
            errors=[
                err(
                    "resource_type",
                    "RESOURCE_TYPE_IMMUTABLE",
                    "资源类型创建后不可修改",
                )
            ],
        )
    if "cluster_id" in extras and extras["cluster_id"] != resource.cluster_id:
        raise problem(
            400,
            "INVALID_REQUEST",
            "所属集群创建后不可修改",
            errors=[
                err(
                    "cluster_id",
                    "RESOURCE_CLUSTER_IMMUTABLE",
                    "所属集群创建后不可修改",
                )
            ],
        )

    fields = payload.model_fields_set
    name_provided = "name" in fields
    status_provided = "status" in fields
    interface_ops = payload.interfaces or []

    if not name_provided and not status_provided and not interface_ops:
        raise problem(
            400,
            "INVALID_REQUEST",
            "无可修改字段",
            errors=[err("request", "NO_FIELDS", "至少提供一个可修改字段")],
        )

    errors: list[dict[str, str]] = []

    old_name = resource.name
    old_status = resource.status

    new_name = old_name
    if name_provided:
        if payload.name is None:
            errors.append(err("name", "NAME_FORMAT", "资源名称不能为空"))
        else:
            new_name, name_err = validate_name(
                payload.name, field="name", code="NAME_FORMAT"
            )
            if name_err:
                errors.append(name_err)

    new_status = old_status
    status_changed = False
    if status_provided:
        if payload.status is None or payload.status not in STATUSES:
            errors.append(err("status", "STATUS_INVALID", "状态取值非法"))
        else:
            status_changed = payload.status != old_status
            new_status = payload.status

    existing = {i.id: i for i in fetch_interfaces(db, resource.id)}
    deleted_ids: set[int] = set()
    creates: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []

    for index, item in enumerate(interface_ops):
        op = item.op
        if op not in INTERFACE_OPS:
            raise problem(
                400,
                "INVALID_REQUEST",
                "非法的网卡操作",
                errors=[
                    err(
                        f"interfaces[{index}].op",
                        "INVALID_INTERFACE_OP",
                        "网卡 op 必须为 create/update/delete",
                    )
                ],
            )
        if op == "create":
            if item.name is None:
                errors.append(
                    err(
                        f"interfaces[{index}].name",
                        "INTERFACE_NAME_FORMAT",
                        "接口名不能为空",
                    )
                )
                create_name = None
            else:
                create_name, create_err = validate_name(
                    item.name,
                    field=f"interfaces[{index}].name",
                    code="INTERFACE_NAME_FORMAT",
                )
                if create_err:
                    errors.append(create_err)
            creates.append(
                {
                    "index": index,
                    "name": create_name,
                    "segment_id": item.segment_id,
                }
            )
        elif op == "update":
            target = existing.get(item.id) if item.id is not None else None
            if target is None:
                errors.append(
                    err(
                        f"interfaces[{index}].id",
                        "INTERFACE_NOT_FOUND",
                        "网卡不存在或不属于该资源",
                    )
                )
                continue
            update_name: str | None = None
            if "name" in item.model_fields_set:
                if item.name is None:
                    errors.append(
                        err(
                            f"interfaces[{index}].name",
                            "INTERFACE_NAME_FORMAT",
                            "接口名不能为空",
                        )
                    )
                else:
                    update_name, update_err = validate_name(
                        item.name,
                        field=f"interfaces[{index}].name",
                        code="INTERFACE_NAME_FORMAT",
                    )
                    if update_err:
                        errors.append(update_err)
            updates.append(
                {
                    "index": index,
                    "interface": target,
                    "name": update_name,
                    "name_given": "name" in item.model_fields_set,
                    "segment_given": "segment_id" in item.model_fields_set,
                    "segment_id": item.segment_id,
                }
            )
        else:  # delete
            target = existing.get(item.id) if item.id is not None else None
            if target is None:
                errors.append(
                    err(
                        f"interfaces[{index}].id",
                        "INTERFACE_NOT_FOUND",
                        "网卡不存在或不属于该资源",
                    )
                )
            else:
                deleted_ids.add(target.id)

    if errors:
        _fail_validation(errors)

    # 网段存在性/同集群校验。
    segment_errors: list[dict[str, str]] = []
    for create in creates:
        segment_err = resolve_segment(
            db,
            create["segment_id"],
            resource.cluster_id,
            f"interfaces[{create['index']}].segment_id",
        )
        if segment_err:
            segment_errors.append(segment_err)
    for update_item in updates:
        if update_item["segment_given"] and update_item["segment_id"] is not None:
            segment_err = resolve_segment(
                db,
                update_item["segment_id"],
                resource.cluster_id,
                f"interfaces[{update_item['index']}].segment_id",
            )
            if segment_err:
                segment_errors.append(segment_err)
    if segment_errors:
        _fail_validation(segment_errors)

    # payload 内接口名重复 → 422。
    payload_names: list[tuple[int, str]] = [
        (c["index"], c["name"]) for c in creates if c["name"] is not None
    ]
    payload_names += [
        (u["index"], u["name"])
        for u in updates
        if u["name_given"] and u["name"] is not None
    ]
    seen: dict[str, int] = {}
    duplicate_errors: list[dict[str, str]] = []
    for index, candidate in payload_names:
        if candidate in seen:
            duplicate_errors.append(
                err(
                    f"interfaces[{index}].name",
                    "INTERFACE_NAME_DUPLICATE_IN_PAYLOAD",
                    "同一请求内接口名不得重复",
                )
            )
        else:
            seen[candidate] = index
    if duplicate_errors:
        _fail_validation(duplicate_errors)

    # 与既有（未被本次删除/改名的）网卡接口名冲突 → 409。
    updated_ids = {u["interface"].id for u in updates}
    final_names: list[str] = [
        iface.name
        for iface in existing.values()
        if iface.id not in deleted_ids and iface.id not in updated_ids
    ]
    final_names += [c["name"] for c in creates if c["name"] is not None]
    final_names += [
        (u["name"] if u["name_given"] and u["name"] is not None else u["interface"].name)
        for u in updates
    ]
    if len(set(final_names)) != len(final_names):
        raise problem(409, "INTERFACE_NAME_TAKEN", "同一资源下接口名重复")

    if name_provided and new_name != old_name:
        conflict = find_by_cluster_name(
            db, resource.cluster_id, new_name, exclude_id=resource.id
        )
        if conflict is not None:
            raise name_exists_problem(conflict)

    # 整单单事务：先乐观锁更新资源本体，再显式增/改/删网卡。
    now = utcnow()
    values: dict[str, Any] = {
        "name": new_name,
        "status": new_status,
        "version": Resource.version + 1,
        "updated_at": now,
    }
    if status_changed:
        # BQ-AA：仅状态变更刷新来源操作者与状态时间；非状态编辑不动这两列。
        values["status_updated_by"] = user.user_id
        values["status_updated_at"] = now

    try:
        result = db.execute(
            update(Resource)
            .where(Resource.id == resource.id, Resource.version == payload.version)
            .values(**values)
        )
    except IntegrityError as exc:
        db.rollback()
        raise resource_write_problem(exc)
    if result.rowcount == 0:
        db.rollback()
        raise problem(409, "VERSION_CONFLICT", "资源已被其他人修改，请刷新后重试")

    try:
        # 先删（释放接口名），再改，再增。
        if deleted_ids:
            db.execute(
                delete(NetworkInterface).where(
                    NetworkInterface.resource_id == resource.id,
                    NetworkInterface.id.in_(deleted_ids),
                )
            )
        for update_item in updates:
            target: NetworkInterface = update_item["interface"]
            iface_values: dict[str, Any] = {}
            if update_item["name_given"] and update_item["name"] is not None:
                iface_values["name"] = update_item["name"]
            if update_item["segment_given"]:
                iface_values["segment_id"] = update_item["segment_id"]
            if iface_values:
                iface_values["updated_at"] = now
                db.execute(
                    update(NetworkInterface)
                    .where(
                        NetworkInterface.id == target.id,
                        NetworkInterface.resource_id == resource.id,
                    )
                    .values(**iface_values)
                )
        for create in creates:
            db.add(
                NetworkInterface(
                    resource_id=resource.id,
                    cluster_id=resource.cluster_id,
                    name=create["name"],
                    segment_id=create["segment_id"],
                    created_at=now,
                    updated_at=now,
                )
            )
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise resource_write_problem(exc)

    change: dict[str, Any] = {}
    if new_name != old_name:
        change["name"] = {"from": old_name, "to": new_name}
    if status_changed:
        change["status"] = {"from": old_status, "to": new_status}
    if creates or updates or deleted_ids:
        change["interfaces"] = {
            "created": [
                {"name": c["name"], "segment_id": c["segment_id"]} for c in creates
            ],
            "updated": [
                {
                    "id": u["interface"].id,
                    "name": (
                        u["name"]
                        if u["name_given"] and u["name"] is not None
                        else u["interface"].name
                    ),
                    "segment_id": (
                        u["segment_id"]
                        if u["segment_given"]
                        else u["interface"].segment_id
                    ),
                }
                for u in updates
            ],
            "deleted": [
                {"id": existing[i].id, "name": existing[i].name}
                for i in deleted_ids
            ],
        }

    audit.write(
        db, user, "resource.update", "resource", str(resource.id), new_name, change
    )
    resource_history.write(
        db, user, "update", "resource", str(resource.id), new_name, change
    )
    db.commit()
    db.refresh(resource)
    return resource_detail(db, resource)


@router.delete("/{resource_id}", status_code=204)
def delete_resource(
    resource_id: int,
    confirm: str = Query(..., description="二次确认：去空格后须等于资源名称"),
    version: int = Query(..., description="乐观锁版本"),
    db: Session = Depends(get_db),
    user: Principal = Depends(write_required),
) -> None:
    resource = get_resource_or_404(db, resource_id)

    if confirm.strip() != resource.name:
        raise problem(
            422,
            "DELETE_CONFIRMATION_MISMATCH",
            "二次确认输入与资源名称不匹配",
        )

    interface_count = db.scalar(
        select(func.count())
        .select_from(NetworkInterface)
        .where(NetworkInterface.resource_id == resource_id)
    )
    if interface_count:
        raise problem(409, "RESOURCE_HAS_INTERFACES", "仍存网卡，禁止真实删除")

    snapshot = {
        "cluster_id": resource.cluster_id,
        "name": resource.name,
        "resource_type": resource.resource_type,
        "status": resource.status,
    }
    # 同一事务先写审计与资源历史，再执行 DELETE。
    audit.write(
        db,
        user,
        "resource.delete",
        "resource",
        str(resource.id),
        resource.name,
        snapshot,
    )
    resource_history.write(
        db,
        user,
        "delete",
        "resource",
        str(resource.id),
        resource.name,
        snapshot,
    )
    db.flush()

    try:
        result = db.execute(
            delete(Resource).where(
                Resource.id == resource_id, Resource.version == version
            )
        )
    except IntegrityError as exc:
        db.rollback()
        raise resource_write_problem(exc)

    if result.rowcount == 0:
        db.rollback()
        raise problem(409, "VERSION_CONFLICT", "资源已被其他人修改，请刷新后重试")

    db.commit()