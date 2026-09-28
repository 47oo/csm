"""F008 统一搜索匹配模块（``app.search``）。

统一「模糊搜索 + 排序」的匹配规则，供各 list 端点复用。

规则见 ``docs/api/F008.md`` §1 与 ``docs/architecture/F008-unified-search.md`` §3：

- **归一**：去首尾空格；去空格后为空（含仅空白）视为不搜索。
- **大小写**：英文不区分大小写（Python ``lower`` / DB ``lower``）。
- **权重 rank**：完全匹配 ``1`` < 前缀匹配 ``2`` < 包含匹配 ``4``；多列命中取最小。
  计算资源 ID 精确匹配的 ``3`` 由资源端点单独附加（沿用 F003 既有定义）。
- **特殊字符**：``%``/``_``/``\\`` 作为普通字符，需 ``LIKE`` 转义（先转义 ``\\``）。

本模块为**纯函数**，不访问数据库、不承载业务规则。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func

#: rank 阶梯（数值越小越优先）。
RANK_EXACT = 1
RANK_PREFIX = 2
RANK_RESOURCE_ID = 3
RANK_CONTAINS = 4

#: ``LIKE ... ESCAPE`` 使用的转义字符，与各端点既有实现一致。
LIKE_ESCAPE = "\\"


def normalize_query(q: str | None) -> str | None:
    """去首尾空格；结果为空（``None``/空串/仅空白）返回 ``None``。

    大小写不在此处折叠；匹配函数与 SQL 表达式按英文不区分大小写比较。
    """
    if q is None:
        return None
    stripped = q.strip()
    return stripped or None


def escape_like(needle: str) -> str:
    """将 ``needle`` 中的 ``LIKE`` 元字符转义为字面量。

    顺序必须为 ``\\`` → ``%`` → ``_``：先转义反斜杠，避免后续插入的转义
    反斜杠被二次转义。
    """
    return needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_pattern(needle: str) -> str:
    """返回「包含匹配」的 ``LIKE`` 模式 ``%escaped%``（未折叠大小写）。"""
    return f"%{escape_like(needle)}%"


def match_rank(value: str, needle: str) -> int | None:
    """对单个值计算匹配 rank；不匹配返回 ``None``。

    - 完全匹配 → :data:`RANK_EXACT`（1）；
    - 前缀匹配 → :data:`RANK_PREFIX`（2）；
    - 包含匹配 → :data:`RANK_CONTAINS`（4）。

    英文不区分大小写；``needle`` 可含任意大小写（内部折叠）。
    """
    lowered = value.lower()
    lowered_needle = needle.lower()
    if lowered == lowered_needle:
        return RANK_EXACT
    if lowered.startswith(lowered_needle):
        return RANK_PREFIX
    if lowered_needle in lowered:
        return RANK_CONTAINS
    return None


def rank_case(*columns: Any, needle: str) -> Any:
    """返回对多列取**最小 rank** 的 SQLAlchemy ``case()`` 排序表达式。

    每列按完全(1) / 前缀(2) / else(4) 计算，再取最小值；比较使用 ``lower()``，
    ``needle`` 经 ``LIKE`` 转义。用于集群、网段等端点在有 ``q`` 时的 SQL 排序，
    过滤条件仍由调用方既有 ``ILIKE`` 负责（包含语义不变）。

    调用方须保证列值非空；PostgreSQL ``least`` 忽略 ``NULL``，故空列不影响
    其它列的 rank。
    """
    if not columns:
        raise ValueError("rank_case 至少需要一列")

    lowered_needle = needle.lower()
    prefix_pattern = f"{escape_like(lowered_needle)}%"
    contains_pattern = like_pattern(lowered_needle)

    ranks = [
        case(
            (func.lower(column) == lowered_needle, RANK_EXACT),
            (
                func.lower(column).like(prefix_pattern, escape=LIKE_ESCAPE),
                RANK_PREFIX,
            ),
            else_=RANK_CONTAINS,
        )
        for column in columns
    ]
    if len(ranks) == 1:
        return ranks[0]
    return func.least(*ranks)


__all__ = [
    "LIKE_ESCAPE",
    "RANK_CONTAINS",
    "RANK_EXACT",
    "RANK_PREFIX",
    "RANK_RESOURCE_ID",
    "escape_like",
    "like_pattern",
    "match_rank",
    "normalize_query",
    "rank_case",
]