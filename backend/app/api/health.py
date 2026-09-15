"""``GET /api/health``：存活 + 数据库连接可用性（AC-02）。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.common.errors import InternalError
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """轻量数据库探测；成功才返回 200。

    契约：数据库不可达 / 探测失败 → ``500 INTERNAL_ERROR``（统一错误信封）。
    """
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - 探测失败一律映射为 500
        raise InternalError("数据库不可用") from exc
    return HealthResponse(status="ok", database="ok")
