"""IPAddressRange 业务行为：登记 / 列表 / 按 id 读取 / 修正范围 / 逻辑删除。

不负责 HTTP 展示文案；不写入 ``deleted_at``（删除委托系统内唯一软删服务）。

创建路径（``docs/api/f020-ip-address-range.md`` §6.1）：

1. 对父 Cluster 行取共享锁（``FOR SHARE``）并确认活跃；未命中 → ``404``；
2. 严格解析 ``start_ip`` / ``end_ip`` 为数值、校验 ``start <= end``（否则 ``400``）；
3. 应用层重叠预检命中 → 友好 ``409 OVERLAP``；
4. 插入；排它约束 ``ex_ip_address_ranges_active_no_overlap`` 为**最终权威**
   （``23P01`` 经 ``app/common/sqlstate.py`` 通用映射 → ``409``）。

修正路径对目标行取 ``FOR UPDATE``（``FOR UPDATE`` 由统一软删服务负责；本服务使用
``select_active(...).with_for_update()``）后重跑解析 / ``start <= end`` / 重叠校验；
命中冲突 → ``409`` 且**无部分写入**（失败即整事务回滚）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.pagination import PageParams
from app.db.active import select_active
from app.deletion import soft_delete
from app.ip_address_ranges.deletion import IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS
from app.ip_address_ranges.ipv4 import parse_ipv4
from app.ip_address_ranges.repository import IpAddressRangeRepository
from app.ip_address_ranges.schemas import IpAddressRangeCreate, IpAddressRangeUpdate
from app.models.cluster import Cluster
from app.models.ip_address_range import IpAddressRange

_OVERLAP_DETAIL = {
    "row": None,
    "field": None,
    "code": "OVERLAP",
    "message": "同一 Cluster 内已存在与该范围重叠的活跃范围段",
}


def _lock_active_cluster(session: Session, cluster_id: int) -> None:
    """对父 Cluster 行取共享锁（``FOR SHARE``）并确认活跃；未命中 → 404。"""
    stmt = select_active(Cluster).where(Cluster.id == cluster_id).with_for_update(read=True)
    if session.scalars(stmt).one_or_none() is None:
        # 不存在 / 已软删一律 404，不做区分（契约 §3.1）。
        raise NotFoundError()


def _parse_or_400(value: str, field: str) -> int:
    """严格解析 IPv4；非法 → ``400 VALIDATION_ERROR``（``details[].field``）。"""
    try:
        return parse_ipv4(value)
    except ValueError as exc:
        raise ValidationError(
            "IPv4 地址非法",
            details=[{"field": field, "code": "INVALID", "message": str(exc)}],
        ) from exc


def _validate_bounds(start_ip: int, end_ip: int) -> None:
    if start_ip > end_ip:
        raise ValidationError(
            "start_ip 不得大于 end_ip",
            details=[
                {
                    "field": "start_ip",
                    "code": "INVALID",
                    "message": "start_ip 必须小于或等于 end_ip",
                }
            ],
        )


def create_ip_address_range(session: Session, payload: IpAddressRangeCreate) -> IpAddressRange:
    # 1) 对父 Cluster 行取共享锁并确认活跃；未命中 → 404（在任何写入之前）。
    _lock_active_cluster(session, payload.cluster_id)

    # 2) 解析 + start <= end。
    start_ip = _parse_or_400(payload.start_ip, "start_ip")
    end_ip = _parse_or_400(payload.end_ip, "end_ip")
    _validate_bounds(start_ip, end_ip)

    repository = IpAddressRangeRepository(session)
    # 3) 应用层预检仅为友好 409；EXCLUDE 排它约束为最终权威。
    if repository.overlap_exists(payload.cluster_id, start_ip, end_ip):
        raise ConflictError("范围段重叠", details=[dict(_OVERLAP_DETAIL)])

    return repository.create(cluster_id=payload.cluster_id, start_ip=start_ip, end_ip=end_ip)


def list_ip_address_ranges(
    session: Session, params: PageParams, *, cluster_id: int | None = None
) -> tuple[list[IpAddressRange], int]:
    if cluster_id is not None:
        parent = session.scalars(
            select_active(Cluster).where(Cluster.id == cluster_id)
        ).one_or_none()
        if parent is None:
            # 父 Cluster 不存在 / 已软删 → 404；存在但无活跃范围段 → 200 空集。
            raise NotFoundError()
    return IpAddressRangeRepository(session).list_active(params, cluster_id=cluster_id)


def get_ip_address_range_by_id(session: Session, ip_address_range_id: int) -> IpAddressRange:
    ip_address_range = IpAddressRangeRepository(session).get_active(ip_address_range_id)
    if ip_address_range is None:
        # 「不存在」与「已逻辑删除」一律 404，不做区分（契约 §3.3）。
        raise NotFoundError()
    return ip_address_range


def update_ip_address_range(
    session: Session, ip_address_range_id: int, payload: IpAddressRangeUpdate
) -> IpAddressRange:
    # 修正路径：对目标行取 FOR UPDATE 后重跑校验（§6.2）。
    target = session.scalars(
        select_active(IpAddressRange)
        .where(IpAddressRange.id == ip_address_range_id)
        .with_for_update()
    ).one_or_none()
    if target is None:
        raise NotFoundError()

    provided = payload.model_fields_set
    if not provided:
        raise ValidationError("请求体至少需包含一个可变字段")

    for field in provided:
        if getattr(payload, field) is None:
            raise ValidationError(
                f"{field} 不能为空",
                details=[{"field": field, "code": "INVALID", "message": "字段不能为 null"}],
            )

    start_ip = target.start_ip
    end_ip = target.end_ip
    if "start_ip" in provided:
        start_ip = _parse_or_400(payload.start_ip, "start_ip")  # type: ignore[arg-type]
    if "end_ip" in provided:
        end_ip = _parse_or_400(payload.end_ip, "end_ip")  # type: ignore[arg-type]
    _validate_bounds(start_ip, end_ip)

    repository = IpAddressRangeRepository(session)
    if repository.overlap_exists(target.cluster_id, start_ip, end_ip, exclude_id=target.id):
        raise ConflictError("范围段重叠", details=[dict(_OVERLAP_DETAIL)])

    updates = {field: (start_ip if field == "start_ip" else end_ip) for field in provided}
    # 不写 cluster_id（归属不可变）。
    return repository.update(target, updates)


def delete_ip_address_range(session: Session, ip_address_range_id: int) -> IpAddressRange:
    """逻辑删除 IPAddressRange：委托系统内唯一的软删写入路径（F014）。

    删除守卫 ``IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS`` 检查「该 Cluster 内活跃 IP 字面
    落在范围内」；命中 → ``409`` 且不写 ``deleted_at``。
    """
    return soft_delete(
        session,
        IpAddressRange,
        ip_address_range_id,
        active_children=IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS,
    )
