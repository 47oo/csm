"""F018 集群内资源关键字搜索的业务行为。

范围推导**复用** F010 的唯一公开入口
``app.resource_views.service.get_related_resources``：命中范围 =
该 Cluster 下每台活跃 BareMetal ``B`` 的 ``{B} ∪ get_related_resources(B)``
（与 R-QUERY-003「含间接」定义同源）。本模块**不重写**关联推导，也**不出现
任何软删谓词**：活跃过滤只经既有 repository 与 ``resource_views`` 传递
（ADR-0004）。

匹配在**已物化**的候选集上执行（Python 大小写折叠子串包含），不做 SQL 过滤 /
索引下推；result 顺序按 ``(resource_type rank, id)`` 物化仅用于分页稳定，
不构成产品排序承诺、不构成分组。
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
from app.search.schemas import SearchResourceType, SearchResultItem

#: 单次分页读取的窗口大小（沿用既有分页上限）。
_WINDOW = MAX_PAGE_SIZE

#: 物化 rank：与 :class:`SearchResourceType` 声明顺序一致。
_TYPE_RANK: dict[SearchResourceType, int] = {
    resource_type: rank for rank, resource_type in enumerate(SearchResourceType)
}


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


def _candidates(session: Session, cluster_id: int) -> list[tuple[SearchResourceType, Any]]:
    """物化该 Cluster 的搜索候选集：每台活跃 BareMetal 的 ``{B} ∪ Related(B)``。"""
    bare_metal_repo = BareMetalRepository(session)
    rows = _snapshot(lambda params: bare_metal_repo.list_active(params, cluster_id=cluster_id))

    candidates: list[tuple[SearchResourceType, Any]] = []
    for row in rows:
        bare_metal = BareMetalRead.model_validate(row)
        candidates.append((SearchResourceType.BARE_METAL, bare_metal))

        related = get_related_resources(session, bare_metal.id)
        candidates.extend(
            (SearchResourceType.NETWORK_INTERFACE, item)
            for item in related.network_interfaces.items
        )
        candidates.extend(
            (SearchResourceType.IP_ADDRESS, item) for item in related.ip_addresses.items
        )
        candidates.extend(
            (SearchResourceType.VIRTUAL_MACHINE, item) for item in related.virtual_machines.items
        )
        candidates.extend((SearchResourceType.CONTAINER, item) for item in related.containers.items)
        candidates.extend((SearchResourceType.SERVICE, item) for item in related.services.items)
    return candidates


def search_cluster_resources(
    session: Session, cluster_id: int, keyword: str, params: PageParams
) -> tuple[list[SearchResultItem], int]:
    """在单个 Cluster 范围内搜索，返回 ``(本页结果, 全量命中数)``。

    1. ``clusters_service.get_cluster_by_id``：Cluster 不存在 / 已逻辑删除 →
       ``NotFoundError``（**唯一 404 网关**，先于范围派生；子资源缺失绝不 404）。
    2. 物化候选集（F010 复用）→ 逐字段子串匹配 → 按 ``(resource_type, id)`` 去重。
    3. 按 ``(resource_type rank, id)`` 物化 → 切片分页；``total`` 为全量命中数。
    """
    clusters_service.get_cluster_by_id(session, cluster_id)

    by_key: dict[tuple[SearchResourceType, int], SearchResultItem] = {}
    for resource_type, resource in _candidates(session, cluster_id):
        matched = _matched_fields(resource_type, resource, keyword)
        if not matched:
            continue
        key = (resource_type, resource.id)
        if key in by_key:
            continue
        by_key[key] = SearchResultItem(
            resource_type=resource_type,
            id=resource.id,
            matched_fields=matched,
            resource=resource,
        )

    ordered = sorted(by_key.values(), key=lambda item: (_TYPE_RANK[item.resource_type], item.id))
    page_items = ordered[params.offset : params.offset + params.limit]
    return page_items, len(ordered)
