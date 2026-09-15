"""FastAPI 应用工厂。

组装：配置 → 引擎 / 会话工厂 → 错误处理 → 路由。
非产品自检面 ``/_foundation/*`` 仅在 dev / test 挂载。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health as health_api
from app.common.error_handlers import register_error_handlers
from app.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory
from app.foundation.router import router as foundation_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    engine = create_db_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="CSM API", version="0.1.0", lifespan=lifespan)

    app.state.settings = settings
    app.state.engine = engine
    app.state.db_sessionmaker = create_session_factory(engine)

    register_error_handlers(app)

    # 产品 API 面（F012 仅 health）。
    app.include_router(health_api.router, prefix="/api")

    # 非产品自检面：仅 dev / test；生产配置下不注册（404）。
    if settings.foundation_enabled:
        app.include_router(foundation_router)

    return app


app = create_app()
