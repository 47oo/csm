"""F019 集群内资源关键字搜索的聚合业务行为。

在 F018 的匹配语义（范围前置、字段清单、子串包含、大小写折叠）之上，按
「**命中项 + 其关联链**」组装单一扁平列表：

1. 范围推导**复用** F010 唯一公开入口
   ``app.resource_views.service.get_related_resources``：对每台活跃 BareMetal
   ``B`` 取其锚定组 ``G(B) = {B} ∪ get_related_resources(B)``（与 R-QUERY-003
   「含间接」定义同源）。本模块**不重写**关联推导，也**不出现任何软删谓词**：
   活跃过滤只经既有 repository 与 ``resource_views`` 传递（ADR-0004）。
2. 命中项 = 自身 ``matched_fields`` 非空的资源；每个命中项一个组织单元
   （首行 ``HIT``，其余 ``RELATED``），单元内按 ``(type rank, id)`` 排序，
   跨单元**不去重**。
3. 单元排序键 = 命中类别（标识字段优先）→ ``resource_type`` 固定序 → ``id``；
   按**单元级**切片分页（同一单元不被拆散），``total`` = 单元全量数。
4. ``derivation_path`` 仅在**单元内已物化**的 canonical ``*Read`` 上按已确认的
   关系方向推导，不判定成员资格，不发起额外数据库查询。

匹配在已物化候选集上执行（Python 大小写折叠子串包含），不做 SQL 过滤 / 索引
下推；排序 / 分组仅用于实现稳定性，不构成相似度 / 打分式相关性排序。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.bare_metals.repository import BareMetalRepository
from app.bare_metals.schemas import BareMetalRead
from app.clusters import service as clusters_service
from app.common.pagination import MAX_PAGE_SIZE, PageParams
from app.resource_views.service import get_related_resources
from app.search.fields import SEARCHABLE_FIELDS
from app.search.schemas import (
    ResourceRef,
    SearchResourceType,
    SearchResultRole,
    SearchResultRow,
)
from app.services.schemas import CARRIER_RANK

#: 单次分页读取的窗口大小（沿用既有分页上限）。
_WINDOW = MAX_PAGE_SIZE

#: 物化 / 排序用的资源类型固定序（内部确定性，非产品排序承诺）。
_TYPE_RANK: dict[SearchResourceType, int] = {
    resource_type: rank for rank, resource_type in enumerate(SearchResourceType)
}

#: 标识字段集合：命中字段含其一即归入优先命中类别（AC-A6）。
_IDENTITY_FIELDS = frozenset({"hostname", "name", "ip_address"})

#: 资源身份键 ``(resource_type, id)``。
_Key = tuple[SearchResourceType, int]


def _snapshot(fetch: Callable[[PageParams], tuple[list[Any], int]]) -> list[Any]:
    """经既有分页过滤枚举**全部**匹配活跃行（完整快照，不静默截断）。

    ``fetch`` **必须**是不会在父行缺失时抛 not-found 的 repository canonical
    过滤函数（如 ``BareMetalRepository.list_active``）。
    """
    items, total = fetch(PageParams(page=1, page_size=_WINDOW))
    collected = list(items)
    page = 2
    while len(collected) < total and items:
        items, _ = fetch(PageParams(page=page, page_size=_WINDOW))
        collected.extend(items)
        page += 1
    return collected


def _matched_fields(resource_type: SearchResourceType, resource: Any, keyword: str) -> list[str]:
    """返回按契约声明顺序排列的命中字段名（``None`` 跳过，大小写折叠子串包含）。"""
    folded = keyword.lower()
    matched: list[str] = []
    for field in SEARCHABLE_FIELDS[resource_type]:
        value = getattr(resource, field)
        if value is None:
            continue
        if folded in str(value).lower():
            matched.append(field)
    return matched


def _ref(key: _Key) -> ResourceRef:
    """把资源身份键转为契约的 :class:`ResourceRef`。"""
    return ResourceRef(resource_type=key[0], id=key[1])


def _hit_category(fields: list[str]) -> int:
    """命中类别：``0`` = 命中标识字段之一；``1`` = 仅命中描述性字段（AC-A6）。"""
    return 0 if _IDENTITY_FIELDS.intersection(fields) else 1


def _parent_key(key: _Key, group: set[_Key], reads: dict[_Key, Any]) -> _Key | None:
    """单元内父资源键（仅用已物化对象与已确认关系方向；``BARE_METAL`` 无父）。"""
    resource_type, _ = key
    read = reads[key]
    if resource_type == SearchResourceType.BARE_METAL:
        return None
    if resource_type == SearchResourceType.NETWORK_INTERFACE:
        return (SearchResourceType.BARE_METAL, read.bare_metal_id)
    if resource_type == SearchResourceType.IP_ADDRESS:
        return (SearchResourceType.NETWORK_INTERFACE, read.network_interface_id)
    if resource_type == SearchResourceType.VIRTUAL_MACHINE:
        return (SearchResourceType.BARE_METAL, read.bare_metal_id)
    if resource_type == SearchResourceType.CONTAINER:
        return (SearchResourceType(read.carrier_type.value), read.carrier_id)

    # SERVICE：取本组内、``(carrier_type rank, carrier_id)`` 最小的载体为父。
    in_group = [
        carrier
        for carrier in read.carriers
        if (SearchResourceType(carrier.carrier_type.value), carrier.carrier_id) in group
    ]
    carrier = min(in_group, key=lambda item: (CARRIER_RANK[item.carrier_type], item.carrier_id))
    return (SearchResourceType(carrier.carrier_type.value), carrier.carrier_id)


def _path_up(key: _Key, root: int, group: set[_Key], reads: dict[_Key, Any]) -> list[ResourceRef]:
    """``[key, parent(key), …, (BARE_METAL, root)]``（仅用单元内已物化对象）。"""
    path = [_ref(key)]
    current = key
    while current != (SearchResourceType.BARE_METAL, root):
        parent = _parent_key(current, group, reads)
        if parent is None:
            break
        path.append(_ref(parent))
        current = parent
    return path


def _derivation_path(
    hit_key: _Key, key: _Key, root: int, group: set[_Key], reads: dict[_Key, Any]
) -> list[ResourceRef]:
    """从本单元命中项到本行的确定性简单路径（首 = 命中项，末 = 本行）。

    两条上行到根 ``root`` 的路径取最近公共祖先拼接，避免命中项与关联行有
    祖孙关系时重复途经节点（契约示例 ``IP → NIC`` 即要求最短简单路径）。
    """
    up_hit = _path_up(hit_key, root, group, reads)
    up_row = _path_up(key, root, group, reads)
    row_pos = {(ref.resource_type, ref.id): index for index, ref in enumerate(up_row)}
    for index, ref in enumerate(up_hit):
        lca_pos = row_pos.get((ref.resource_type, ref.id))
        if lca_pos is not None:
            return up_hit[: index + 1] + list(reversed(up_row[:lca_pos]))
    # 不可达（同一锚定组内不应发生）：退化为两端通过根的拼接。
    return up_hit + list(reversed(up_row))[1:]


def _materialize(
    session: Session, cluster_id: int
) -> tuple[dict[_Key, Any], dict[int, set[_Key]], dict[_Key, set[int]]]:
    """物化每台活跃 BareMetal 的锚定组 ``G(B)``（复用 ``get_related_resources``）。

    返回 ``(reads, group_keys, anchor_of)``：

    - ``reads``：``{ (type, id): canonical *Read }``（全候选集已物化对象）。
    - ``group_keys``：``{ bare_metal_id: G(B) 的资源键集合 }``（含 ``B`` 自身）。
    - ``anchor_of``：``{ (type, id): 含有该资源的 BareMetal id 集合 }``。
    """
    reads: dict[_Key, Any] = {}
    group_keys: dict[int, set[_Key]] = {}
    anchor_of: dict[_Key, set[int]] = {}

    bare_metal_repo = BareMetalRepository(session)
    rows = _snapshot(lambda params: bare_metal_repo.list_active(params, cluster_id=cluster_id))

    for row in rows:
        bare_metal = BareMetalRead.model_validate(row)
        bare_metal_key = (SearchResourceType.BARE_METAL, bare_metal.id)
        reads[bare_metal_key] = bare_metal

        related = get_related_resources(session, bare_metal.id)
        group: set[_Key] = {bare_metal_key}
        for resource_type, items in (
            (SearchResourceType.NETWORK_INTERFACE, related.network_interfaces.items),
            (SearchResourceType.IP_ADDRESS, related.ip_addresses.items),
            (SearchResourceType.VIRTUAL_MACHINE, related.virtual_machines.items),
            (SearchResourceType.CONTAINER, related.containers.items),
            (SearchResourceType.SERVICE, related.services.items),
        ):
            for item in items:
                key = (resource_type, item.id)
                reads[key] = item
                group.add(key)

        group_keys[bare_metal.id] = group
        for key in group:
            anchor_of.setdefault(key, set()).add(bare_metal.id)

    return reads, group_keys, anchor_of


def search_cluster_resources(
    session: Session, cluster_id: int, keyword: str, params: PageParams
) -> tuple[list[SearchResultRow], int]:
    """在单个 Cluster 范围内聚合搜索，返回 ``(本页扁平行, 单元全量数)``。

    1. ``clusters_service.get_cluster_by_id``：Cluster 不存在 / 已逻辑删除 →
       ``NotFoundError``（**唯一 404 网关**，先于范围派生；子资源缺失绝不 404）。
    2. 物化锚定组（F010 复用）→ 逐字段子串匹配得命中项集合。
    3. 每个命中项一个单元（首行 ``HIT``，其余 ``RELATED``），跨单元不去重。
    4. 单元按 ``(命中类别, type rank, id)`` 全序化 → 单元级切片分页。
    """
    clusters_service.get_cluster_by_id(session, cluster_id)

    reads, group_keys, anchor_of = _materialize(session, cluster_id)
    matched = {key: _matched_fields(key[0], reads[key], keyword) for key in reads}

    hits = [key for key, fields in matched.items() if fields]
    hits.sort(key=lambda key: (_hit_category(matched[key]), _TYPE_RANK[key[0]], key[1]))

    units: list[list[SearchResultRow]] = []
    for hit_key in hits:
        anchor_ids = anchor_of[hit_key]
        chain: set[_Key] = set()
        for bare_metal_id in anchor_ids:
            chain |= group_keys[bare_metal_id]

        related_keys = sorted(
            (key for key in chain if key != hit_key),
            key=lambda key: (_TYPE_RANK[key[0]], key[1]),
        )

        unit: list[SearchResultRow] = [
            SearchResultRow(
                resource_type=hit_key[0],
                id=hit_key[1],
                role=SearchResultRole.HIT,
                group_key=_ref(hit_key),
                matched_fields=matched[hit_key],
                derivation_path=None,
                resource=reads[hit_key],
            )
        ]
        for key in related_keys:
            # 本行的根：同时含有命中项与本行的最小 BareMetal id（契约 §4.3）。
            root = min(anchor_ids & anchor_of[key])
            unit.append(
                SearchResultRow(
                    resource_type=key[0],
                    id=key[1],
                    role=SearchResultRole.RELATED,
                    group_key=_ref(hit_key),
                    matched_fields=matched[key],
                    derivation_path=_derivation_path(hit_key, key, root, group_keys[root], reads),
                    resource=reads[key],
                )
            )
        units.append(unit)

    page_units = units[params.offset : params.offset + params.limit]
    items = [row for unit in page_units for row in unit]
    return items, len(units)
