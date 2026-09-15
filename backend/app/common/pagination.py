"""分页约定（docs/api/api-conventions.md §3、架构 Handoff PROPOSED #3）。

``page`` 从 1 起、默认 1；``page_size`` 默认 50、上限 200。非法值由 FastAPI /
Pydantic 校验，经统一校验处理器返回 ``400 VALIDATION_ERROR`` 且带 ``details[].field``。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class PageParams(BaseModel):
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def page_params(
    page: Annotated[int, Query(ge=1, description="从 1 起，默认 1")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="默认 50，上限 200")
    ] = DEFAULT_PAGE_SIZE,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


class Page[ItemT](BaseModel):
    items: list[ItemT]
    total: int
    page: int
    page_size: int
