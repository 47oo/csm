"""F002 计算资源登记、网卡与真实删除路由（Contract docs/api/F002.md）。

F006 扩展：同一资源表单事务内应用 ``interfaces[].ips`` 与管理 IP；网段读取复用
F005 模型，IP 选址/排除/管理 IP 解析复用 ``app.ip_allocation``。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit, resource_history
from ..db import get_db
from ..errors import problem
from ..ip_allocation.addressing import ipv4_to_int
from ..ip_allocation.service import (
    AUTO,
    MANUAL,
    PlannedIp,
    allocate_specs,
    conflicting_ips,
    existing_ips_for_resource,
    ip_write_conflict_problem,
)
from ..models import IpAddress, NetworkInterface, NetworkSegment, Resource
from ..network_segments.service import SegmentUsage
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


def _fail_validation(errors: list[dict[str, Any]]) -> None:
    raise problem(422, "VALIDATION_ERROR", "字段校验失败", errors=errors)


def _raise_ip_conflicts(
    db: Session, cluster_id: int, conflict_errors: list[dict[str, Any]]
) -> None:
    addresses = {e["address"] for e in conflict_errors if "address" in e}
    conflicts = conflicting_ips(db, cluster_id, addresses) if addresses else []
    primary = next(
        (e for e in conflict_errors if e["code"] == "IP_ALREADY_IN_USE"),
        conflict_errors[0],
    )
    errors = [
        {k: v for k, v in item.items() if k != "address"}
        for item in conflict_errors
    ]
    extra = {"conflicts": conflicts} if conflicts else None
    raise problem(409, primary["code"], primary["message"], errors=errors, extra=extra)


def _create_snapshot(
    resource: Resource,
    resolved: list[dict[str, Any]],
    planned_by_interface: dict[int, list[PlannedIp]],
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "cluster_id": resource.cluster_id,
        "name": resource.name,
        "resource_type": resource.resource_type,
        "status": resource.status,
        "interfaces": [
            {
                "name": item["name"],
                "segment_id": item["segment_id"],
                "ips": [
                    {"address": p.address, "mode": p.mode}
                    for p in planned_by_interface.get(item["index"], [])
                ],
            }
            for item in resolved
        ],
    }
    return snapshot


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
    resolved: list[dict[str, Any]] = []
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
        resolved.append(
            {
                "index": index,
                "name": interface_name or "",
                "segment_id": item.segment_id,
                "ips": list(item.ips or []),
            }
        )

    if errors:
        _fail_validation(errors)

    get_cluster_or_404(db, payload.cluster_id)

    segment_errors: list[dict[str, str]] = []
    for item in resolved:
        segment_err = resolve_segment(
            db,
            item["segment_id"],
            payload.cluster_id,
            f"interfaces[{item['index']}].segment_id",
        )
        if segment_err:
            segment_errors.append(segment_err)
    if segment_errors:
        _fail_validation(segment_errors)

    existing = find_by_cluster_name(db, payload.cluster_id, name)
    if existing is not None:
        raise name_exists_problem(existing)

    # --- F006：IP 选址与校验（整单前置，失败不落任何行） ---
    in_use = SegmentUsage.allocated_ip_nums(db, payload.cluster_id)
    planned_by_interface: dict[int, list[PlannedIp]] = {}
    validation_errors: list[dict[str, Any]] = []
    conflict_errors: list[dict[str, Any]] = []
    for item in resolved:
        specs = item["ips"]
        if not specs:
            continue
        if item["segment_id"] is None:
            for ip_index in range(len(specs)):
                validation_errors.append(
                    err(
                        f"interfaces[{item['index']}].ips[{ip_index}]",
                        "SEGMENT_NOT_SELECTED",
                        "分配 IP 前须先选择网段",
                    )
                )
            continue
        segment = db.get(NetworkSegment, item["segment_id"])
        planned, v_errors, c_errors = allocate_specs(
            db,
            segment=segment,
            specs=[
                (ip_index, spec.mode, spec.address)
                for ip_index, spec in enumerate(specs)
            ],
            in_use=in_use,
            field_prefix=f"interfaces[{item['index']}]",
        )
        planned_by_interface[item["index"]] = planned
        validation_errors.extend(v_errors)
        conflict_errors.extend(c_errors)
    if validation_errors:
        _fail_validation(validation_errors)
    if conflict_errors:
        _raise_ip_conflicts(db, payload.cluster_id, conflict_errors)

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
        raise resource_write_problem(
            exc, db, cluster_id=payload.cluster_id, name=name
        )

    interface_objs: dict[int, NetworkInterface] = {}
    for item in resolved:
        interface = NetworkInterface(
            resource_id=resource.id,
            cluster_id=resource.cluster_id,
            name=item["name"],
            segment_id=item["segment_id"],
            created_at=now,
            updated_at=now,
        )
        db.add(interface)
        interface_objs[item["index"]] = interface
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise resource_write_problem(
            exc, db, cluster_id=payload.cluster_id, name=name
        )

    # F006-RV-01：创建路径无「同事务先删后建同址」需求，故不将
    # uq_ip_addresses_cluster_ip 延迟到提交；唯一性在受保护的 flush 触发，
    # 并发/交错争用同一地址时映射为 409（手动 IP_ALREADY_IN_USE 附 conflicts /
    # 自动 NO_AVAILABLE_ADDRESS）而非 500。
    created_by_interface: dict[int, list[tuple[str, IpAddress]]] = {}
    automatic = False
    manual = False
    planned_addresses = {
        p.address
        for planned in planned_by_interface.values()
        for p in planned
    }
    try:
        for item in resolved:
            planned = planned_by_interface.get(item["index"], [])
            if not planned:
                continue
            interface = interface_objs[item["index"]]
            for p in planned:
                ip_row = IpAddress(
                    interface_id=interface.id,
                    resource_id=resource.id,
                    cluster_id=resource.cluster_id,
                    segment_id=interface.segment_id,
                    ip=p.address,
                    created_at=now,
                )
                db.add(ip_row)
                created_by_interface.setdefault(item["index"], []).append(
                    (p.address, ip_row)
                )
                automatic = automatic or p.mode == AUTO
                manual = manual or p.mode == MANUAL
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        prob = ip_write_conflict_problem(
            db,
            exc,
            cluster_id=payload.cluster_id,
            candidate_addresses=planned_addresses,
            automatic=automatic and not manual,
        )
        if prob is not None:
            raise prob
        raise resource_write_problem(
            exc, db, cluster_id=payload.cluster_id, name=name
        )

    # 管理 IP（创建仅支持 {interface_index, address}）。
    management_snapshot: dict[str, Any] | None = None
    if payload.management_ip is not None:
        ref = payload.management_ip
        match: IpAddress | None = None
        if ref.interface_index is not None and ref.address is not None:
            for address, obj in created_by_interface.get(ref.interface_index, []):
                if address == ref.address:
                    match = obj
                    break
        if match is None:
            db.rollback()
            raise problem(422, "MANAGEMENT_IP_INVALID", "管理 IP 不属于本资源有效 IP")
        resource.management_ip_id = match.id
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise problem(422, "MANAGEMENT_IP_INVALID", "管理 IP 不属于本资源有效 IP") from None
        management_snapshot = {"address": match.ip}

    snapshot = _create_snapshot(resource, resolved, planned_by_interface)
    if management_snapshot is not None:
        snapshot["management_ip"] = management_snapshot
    audit.write(
        db,
        user,
        "resource.create",
        "resource",
        str(resource.id),
        resource.name,
        snapshot,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        prob = ip_write_conflict_problem(
            db,
            exc,
            cluster_id=payload.cluster_id,
            candidate_addresses=planned_addresses,
            automatic=automatic and not manual,
        )
        if prob is not None:
            raise prob
        raise resource_write_problem(
            exc, db, cluster_id=payload.cluster_id, name=name
        )
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
    cluster_id = resource.cluster_id

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
    management_provided = "management_ip" in fields
    interface_ops = payload.interfaces or []

    if (
        not name_provided
        and not status_provided
        and not interface_ops
        and not management_provided
    ):
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

    existing_ifaces = {i.id: i for i in fetch_interfaces(db, resource.id)}
    existing_ips = {ip.id: ip for ip in existing_ips_for_resource(db, resource.id)}
    existing_ips_by_interface: dict[int, list[IpAddress]] = defaultdict(list)
    for ip_row in existing_ips.values():
        existing_ips_by_interface[ip_row.interface_id].append(ip_row)

    deleted_ids: set[int] = set()
    deleted_ip_ids: set[int] = set()
    creates: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    interface_deletes: list[dict[str, Any]] = []
    action_by_index: dict[int, dict[str, Any]] = {}

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
        ip_ops = list(item.ips or [])
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
            action = {
                "index": index,
                "name": create_name,
                "segment_id": item.segment_id,
                "ips": ip_ops,
            }
            creates.append(action)
            action_by_index[index] = action
        elif op == "update":
            target = existing_ifaces.get(item.id) if item.id is not None else None
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
            action = {
                "index": index,
                "interface": target,
                "name": update_name,
                "name_given": "name" in item.model_fields_set,
                "segment_given": "segment_id" in item.model_fields_set,
                "segment_id": item.segment_id,
                "ips": ip_ops,
                "delete_ip_ids": set(),
                "create_specs": [],
            }
            updates.append(action)
            action_by_index[index] = action
            for ip_index, ip_op in enumerate(ip_ops):
                if ip_op.op == "delete":
                    ip_target = (
                        existing_ips.get(ip_op.id) if ip_op.id is not None else None
                    )
                    if (
                        ip_target is None
                        or ip_target.interface_id != target.id
                    ):
                        errors.append(
                            err(
                                f"interfaces[{index}].ips[{ip_index}].id",
                                "IP_NOT_FOUND",
                                "IP 不存在或不属于该网卡",
                            )
                        )
                    else:
                        deleted_ip_ids.add(ip_target.id)
                        action["delete_ip_ids"].add(ip_target.id)
                elif ip_op.op == "create":
                    action["create_specs"].append(ip_index)
                else:
                    raise problem(
                        400,
                        "INVALID_REQUEST",
                        "非法的 IP 操作",
                        errors=[
                            err(
                                f"interfaces[{index}].ips[{ip_index}].op",
                                "INVALID_INTERFACE_OP",
                                "IP op 必须为 create/delete",
                            )
                        ],
                    )
        else:  # delete interface
            target = existing_ifaces.get(item.id) if item.id is not None else None
            if target is None:
                errors.append(
                    err(
                        f"interfaces[{index}].id",
                        "INTERFACE_NOT_FOUND",
                        "网卡不存在或不属于该资源",
                    )
                )
                continue
            delete_ip_ids: set[int] = set()
            for ip_index, ip_op in enumerate(ip_ops):
                if ip_op.op != "delete":
                    raise problem(
                        400,
                        "INVALID_REQUEST",
                        "非法的 IP 操作",
                        errors=[
                            err(
                                f"interfaces[{index}].ips[{ip_index}].op",
                                "INVALID_INTERFACE_OP",
                                "删除网卡仅允许删除 IP",
                            )
                        ],
                    )
                ip_target = (
                    existing_ips.get(ip_op.id) if ip_op.id is not None else None
                )
                if ip_target is None or ip_target.interface_id != target.id:
                    errors.append(
                        err(
                            f"interfaces[{index}].ips[{ip_index}].id",
                            "IP_NOT_FOUND",
                            "IP 不存在或不属于该网卡",
                        )
                    )
                else:
                    deleted_ip_ids.add(ip_target.id)
                    delete_ip_ids.add(ip_target.id)
            deleted_ids.add(target.id)
            action = {
                "index": index,
                "interface": target,
                "delete_ip_ids": delete_ip_ids,
            }
            interface_deletes.append(action)
            action_by_index[index] = action

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
        for iface in existing_ifaces.values()
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

    # --- F006：网卡改段/删除前置 + IP 选址 ---
    structural_errors: list[dict[str, str]] = []
    for action in interface_deletes:
        target: NetworkInterface = action["interface"]
        remaining = [
            ip
            for ip in existing_ips_by_interface.get(target.id, [])
            if ip.id not in action["delete_ip_ids"]
        ]
        if remaining:
            raise problem(409, "INTERFACE_HAS_IPS", "网卡仍有 IP，禁止删除")
    for action in updates:
        target = action["interface"]
        final_segment = (
            action["segment_id"] if action["segment_given"] else target.segment_id
        )
        if action["segment_given"] and final_segment != target.segment_id:
            remaining = [
                ip
                for ip in existing_ips_by_interface.get(target.id, [])
                if ip.id not in action["delete_ip_ids"]
            ]
            if remaining:
                raise problem(
                    422,
                    "INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE",
                    "改网段前须释放该网卡旧 IP",
                )
        if action["create_specs"] and final_segment is None:
            for ip_index in action["create_specs"]:
                structural_errors.append(
                    err(
                        f"interfaces[{action['index']}].ips[{ip_index}]",
                        "SEGMENT_NOT_SELECTED",
                        "分配 IP 前须先选择网段",
                    )
                )
    for action in creates:
        if action["ips"] and action["segment_id"] is None:
            for ip_index in range(len(action["ips"])):
                structural_errors.append(
                    err(
                        f"interfaces[{action['index']}].ips[{ip_index}]",
                        "SEGMENT_NOT_SELECTED",
                        "分配 IP 前须先选择网段",
                    )
                )
    if structural_errors:
        _fail_validation(structural_errors)

    allocated = SegmentUsage.allocated_ip_nums(db, cluster_id)
    deleted_nums = {ipv4_to_int(existing_ips[i].ip) for i in deleted_ip_ids}
    in_use = allocated - deleted_nums

    planned_by_action: dict[int, list[PlannedIp]] = {}
    validation_errors: list[dict[str, Any]] = []
    conflict_errors: list[dict[str, Any]] = []
    for action in creates:
        if not action["ips"]:
            continue
        segment = db.get(NetworkSegment, action["segment_id"])
        planned, v_errors, c_errors = allocate_specs(
            db,
            segment=segment,
            specs=[
                (ip_index, spec.mode, spec.address)
                for ip_index, spec in enumerate(action["ips"])
            ],
            in_use=in_use,
            field_prefix=f"interfaces[{action['index']}]",
        )
        planned_by_action[action["index"]] = planned
        validation_errors.extend(v_errors)
        conflict_errors.extend(c_errors)
    for action in updates:
        specs = [
            (ip_index, action["ips"][ip_index].mode, action["ips"][ip_index].address)
            for ip_index in action["create_specs"]
        ]
        if not specs:
            continue
        final_segment_id = (
            action["segment_id"] if action["segment_given"] else action["interface"].segment_id
        )
        segment = db.get(NetworkSegment, final_segment_id)
        planned, v_errors, c_errors = allocate_specs(
            db,
            segment=segment,
            specs=specs,
            in_use=in_use,
            field_prefix=f"interfaces[{action['index']}]",
        )
        planned_by_action[action["index"]] = planned
        validation_errors.extend(v_errors)
        conflict_errors.extend(c_errors)
    if validation_errors:
        _fail_validation(validation_errors)
    if conflict_errors:
        _raise_ip_conflicts(db, cluster_id, conflict_errors)

    # --- F006：管理 IP 解析 ---
    current_mgmt_id = resource.management_ip_id
    management_removed = False
    if current_mgmt_id is not None:
        current_ip = existing_ips.get(current_mgmt_id)
        if current_ip is not None:
            if current_mgmt_id in deleted_ip_ids or current_ip.interface_id in deleted_ids:
                management_removed = True
        else:
            management_removed = True
    if management_removed and not management_provided:
        raise problem(
            422,
            "MANAGEMENT_IP_REQUIRED",
            "删除管理 IP 或其网卡前须同次显式清空或重选管理 IP",
        )

    new_target: tuple[str, Any] | None = None
    if management_provided:
        ref = payload.management_ip
        if ref is None:
            new_target = ("clear", None)
        elif ref.ip_id is not None:
            ip_row = existing_ips.get(ref.ip_id)
            if (
                ip_row is None
                or ip_row.resource_id != resource.id
                or ref.ip_id in deleted_ip_ids
            ):
                raise problem(422, "MANAGEMENT_IP_INVALID", "管理 IP 不属于本资源有效 IP")
            new_target = ("existing", ref.ip_id)
        elif ref.interface_index is not None and ref.address is not None:
            action = action_by_index.get(ref.interface_index)
            matched: tuple[str, Any] | None = None
            if action is not None:
                planned = planned_by_action.get(ref.interface_index, [])
                if any(p.address == ref.address for p in planned):
                    matched = ("planned", ref.interface_index, ref.address)
                else:
                    target_iface = action.get("interface")
                    if target_iface is not None:
                        for ip_row in existing_ips_by_interface.get(target_iface.id, []):
                            if (
                                ip_row.ip == ref.address
                                and ip_row.id not in deleted_ip_ids
                            ):
                                matched = ("existing", ip_row.id)
                                break
            if matched is None:
                raise problem(422, "MANAGEMENT_IP_INVALID", "管理 IP 不属于本资源有效 IP")
            new_target = matched
        else:
            raise problem(422, "MANAGEMENT_IP_INVALID", "管理 IP 引用非法")

    # --- 整单单事务：乐观锁更新资源本体，再应用网卡/IP/管理 IP ---
    now = utcnow()
    values: dict[str, Any] = {
        "name": new_name,
        "status": new_status,
        "version": Resource.version + 1,
        "updated_at": now,
    }
    if status_changed:
        values["status_updated_by"] = user.user_id
        values["status_updated_at"] = now
    if new_target is not None:
        if new_target[0] == "existing":
            values["management_ip_id"] = new_target[1]
        else:
            values["management_ip_id"] = None

    try:
        result = db.execute(
            update(Resource)
            .where(Resource.id == resource.id, Resource.version == payload.version)
            .values(**values)
        )
    except IntegrityError as exc:
        db.rollback()
        raise resource_write_problem(exc, db, cluster_id=cluster_id, name=new_name)
    if result.rowcount == 0:
        db.rollback()
        raise problem(409, "VERSION_CONFLICT", "资源已被其他人修改，请刷新后重试")

    db.execute(
        text("SET CONSTRAINTS uq_network_interfaces_resource_name DEFERRED")
    )
    db.execute(text("SET CONSTRAINTS uq_ip_addresses_cluster_ip DEFERRED"))

    automatic = any(
        p.mode == AUTO for planned in planned_by_action.values() for p in planned
    )
    manual = any(
        p.mode == MANUAL for planned in planned_by_action.values() for p in planned
    )
    planned_addresses = {
        p.address for planned in planned_by_action.values() for p in planned
    }
    created_by_action: dict[int, list[tuple[str, IpAddress]]] = {}
    phase = "ip_delete"
    try:
        # 1) 删除所有显式释放的 IP。
        if deleted_ip_ids:
            db.execute(
                delete(IpAddress).where(
                    IpAddress.resource_id == resource.id,
                    IpAddress.id.in_(deleted_ip_ids),
                )
            )
        # 2) 删除网卡（其 IP 已在上一步释放）。
        phase = "interface_delete"
        if deleted_ids:
            db.execute(
                delete(NetworkInterface).where(
                    NetworkInterface.resource_id == resource.id,
                    NetworkInterface.id.in_(deleted_ids),
                )
            )
        # 3) 更新网卡（改名/改段）。
        phase = "interface_update"
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
        # 4) 新建网卡。
        new_interface_by_action: dict[int, NetworkInterface] = {}
        for create in creates:
            interface = NetworkInterface(
                resource_id=resource.id,
                cluster_id=resource.cluster_id,
                name=create["name"],
                segment_id=create["segment_id"],
                created_at=now,
                updated_at=now,
            )
            db.add(interface)
            new_interface_by_action[create["index"]] = interface
        db.flush()
        # 5) 新建 IP。
        phase = "ip_create"
        for action_index, planned in planned_by_action.items():
            action = action_by_index[action_index]
            if action_index in new_interface_by_action:
                interface = new_interface_by_action[action_index]
            else:
                interface = action["interface"]
            for p in planned:
                ip_row = IpAddress(
                    interface_id=interface.id,
                    resource_id=resource.id,
                    cluster_id=resource.cluster_id,
                    segment_id=interface.segment_id,
                    ip=p.address,
                    created_at=now,
                )
                db.add(ip_row)
                created_by_action.setdefault(action_index, []).append(
                    (p.address, ip_row)
                )
        db.flush()
        # 6) 设置指向本请求新建 IP 的管理 IP。
        phase = "management"
        if new_target is not None and new_target[0] == "planned":
            _, interface_index, address = new_target
            match = next(
                (
                    obj
                    for addr, obj in created_by_action.get(interface_index, [])
                    if addr == address
                ),
                None,
            )
            if match is None:
                db.rollback()
                raise problem(
                    422, "MANAGEMENT_IP_INVALID", "管理 IP 不属于本资源有效 IP"
                )
            resource.management_ip_id = match.id
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        prob = ip_write_conflict_problem(
            db,
            exc,
            cluster_id=cluster_id,
            candidate_addresses=planned_addresses,
            automatic=automatic and not manual,
            phase=phase,
        )
        if prob is not None:
            raise prob
        raise resource_write_problem(exc, db, cluster_id=cluster_id, name=new_name)

    # --- 审计 / 历史 ---
    change: dict[str, Any] = {}
    if new_name != old_name:
        change["name"] = {"from": old_name, "to": new_name}
    if status_changed:
        change["status"] = {"from": old_status, "to": new_status}

    deleted_ip_map = {
        ip_id: existing_ips[ip_id] for ip_id in deleted_ip_ids if ip_id in existing_ips
    }
    interfaces_change: dict[str, Any] = {}
    if creates:
        interfaces_change["created"] = [
            {
                "name": c["name"],
                "segment_id": c["segment_id"],
                "ips": [
                    {"address": p.address, "mode": p.mode}
                    for p in planned_by_action.get(c["index"], [])
                ],
            }
            for c in creates
        ]
    if updates:
        interfaces_change["updated"] = [
            {
                "id": u["interface"].id,
                "name": (
                    u["name"]
                    if u["name_given"] and u["name"] is not None
                    else u["interface"].name
                ),
                "segment_id": (
                    u["segment_id"] if u["segment_given"] else u["interface"].segment_id
                ),
                "ips": {
                    "created": [
                        {"address": p.address, "mode": p.mode}
                        for p in planned_by_action.get(u["index"], [])
                    ],
                    "deleted": [
                        {"ip_id": ip_id, "address": deleted_ip_map[ip_id].ip}
                        for ip_id in u["delete_ip_ids"]
                        if ip_id in deleted_ip_map
                    ],
                },
            }
            for u in updates
        ]
    if deleted_ids:
        interfaces_change["deleted"] = [
            {
                "id": action["interface"].id,
                "name": action["interface"].name,
                "ips": [
                    {"ip_id": ip_id, "address": deleted_ip_map[ip_id].ip}
                    for ip_id in action["delete_ip_ids"]
                    if ip_id in deleted_ip_map
                ],
            }
            for action in interface_deletes
        ]
    if interfaces_change:
        change["interfaces"] = interfaces_change
    if new_target is not None:
        old_mgmt = (
            deleted_ip_map[current_mgmt_id].ip
            if current_mgmt_id in deleted_ip_map
            else (existing_ips[current_mgmt_id].ip if current_mgmt_id in existing_ips else None)
        )
        new_mgmt: str | None
        if new_target[0] == "existing":
            new_mgmt = existing_ips[new_target[1]].ip
        elif new_target[0] == "planned":
            new_mgmt = new_target[2]
        else:
            new_mgmt = None
        change["management_ip"] = {"from": old_mgmt, "to": new_mgmt}

    audit.write(
        db, user, "resource.update", "resource", str(resource.id), new_name, change
    )
    resource_history.write(
        db, user, "update", "resource", str(resource.id), new_name, change
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        prob = ip_write_conflict_problem(
            db,
            exc,
            cluster_id=cluster_id,
            candidate_addresses=planned_addresses,
            automatic=automatic and not manual,
        )
        if prob is not None:
            raise prob
        raise resource_write_problem(exc, db, cluster_id=cluster_id, name=new_name)
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