"""F008 ``app.search.matching`` 纯函数单元测试（真实 PostgreSQL 执行 SQL rank）。

覆盖归一、转义、单值 rank 与 SQL ``rank_case``；无端点依赖。
"""

from __future__ import annotations

from sqlalchemy import literal, select

from app.db import SessionLocal
from app.search.matching import (
    RANK_CONTAINS,
    RANK_EXACT,
    RANK_PREFIX,
    escape_like,
    like_pattern,
    match_rank,
    normalize_query,
    rank_case,
)


# --- 归一 -------------------------------------------------------------------


def test_normalize_query() -> None:
    assert normalize_query(None) is None
    assert normalize_query("") is None
    assert normalize_query("   ") is None
    assert normalize_query("  web  ") == "web"
    assert normalize_query("  Web  ") == "Web"
    assert normalize_query("a b") == "a b"


# --- 转义 -------------------------------------------------------------------


def test_escape_like_literal_metacharacters() -> None:
    assert escape_like("web") == "web"
    assert escape_like("a%b") == "a\\%b"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("a\\b") == "a\\\\b"
    # 顺序：先转义反斜杠，故反斜杠+百分号得到三个反斜杠 + 百分号。
    assert escape_like("\\%") == "\\\\\\%"
    assert escape_like("\\_") == "\\\\\\_"


def test_like_pattern_wraps_escaped_needle() -> None:
    assert like_pattern("web") == "%web%"
    assert like_pattern("a_b") == "%a\\_b%"
    assert like_pattern("50%") == "%50\\%%"


# --- 单值 rank --------------------------------------------------------------


def test_match_rank_exact_prefix_contains() -> None:
    assert match_rank("web", "web") == RANK_EXACT
    assert match_rank("website", "web") == RANK_PREFIX
    assert match_rank("myweb", "web") == RANK_CONTAINS
    assert match_rank("abc", "web") is None


def test_match_rank_case_insensitive_and_trimmed_needle() -> None:
    assert match_rank("WEB", "web") == RANK_EXACT
    assert match_rank("WebServer", "web") == RANK_PREFIX
    assert match_rank("MYWEB", "web") == RANK_CONTAINS
    # needle 可含任意大小写（内部折叠）。
    assert match_rank("web", "WEB") == RANK_EXACT


def test_match_rank_metacharacters_are_literal() -> None:
    assert match_rank("a%b", "a%b") == RANK_EXACT
    assert match_rank("a%b", "a%") == RANK_PREFIX
    assert match_rank("a_b", "a_b") == RANK_EXACT
    # 通配符不生效：``a_c`` 不匹配 ``abc``。
    assert match_rank("abc", "a_c") is None
    assert match_rank("abc", "a%c") is None
    # IPv4 部分匹配。
    assert match_rank("192.168.1.10", "192.168") == RANK_PREFIX
    assert match_rank("192.168.1.10", "168.1.") == RANK_CONTAINS


# --- SQL rank_case ----------------------------------------------------------


def _rank(*values: str, needle: str) -> int | None:
    with SessionLocal() as db:
        return db.scalar(
            select(rank_case(*(literal(v) for v in values), needle=needle))
        )


def test_rank_case_single_column() -> None:
    assert _rank("web", needle="web") == RANK_EXACT
    assert _rank("website", needle="web") == RANK_PREFIX
    assert _rank("myweb", needle="web") == RANK_CONTAINS
    assert _rank("abc", needle="web") == RANK_CONTAINS  # else 分支


def test_rank_case_case_insensitive() -> None:
    assert _rank("WEB", needle="web") == RANK_EXACT
    assert _rank("WebSite", needle="web") == RANK_PREFIX


def test_rank_case_takes_minimum_across_columns() -> None:
    # 第一列包含(4)、第二列完全(1) → 1。
    assert _rank("myweb", "web", needle="web") == RANK_EXACT
    # 第一列前缀(2)、第二列包含(4) → 2。
    assert _rank("website", "myweb", needle="web") == RANK_PREFIX
    # 两列都包含 → 4。
    assert _rank("myweb", "aweb", needle="web") == RANK_CONTAINS


def test_rank_case_metacharacters_are_literal() -> None:
    assert _rank("a_b", needle="a_b") == RANK_EXACT
    assert _rank("abc", needle="a_b") == RANK_CONTAINS  # 不命中视为 else=4
    assert _rank("50%", needle="50%") == RANK_EXACT