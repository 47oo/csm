"""FastAPI 应用工厂。

组装：配置 → 引擎 / 会话工厂 → 错误处理 → 路由。

F001 已彻底移除 F012 的非产品自检面；应用只暴露 ``/api`` 下的产品面。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health as health_api
from app.clusters.router import router as clusters_router
from app.common.error_handlers import register_error_handlers
from app.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory


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

    # 产品 API 面：health + clusters。全部位于 /api 前缀下。
    app.include_router(health_api.router, prefix="/api")
    app.include_router(clusters_router, prefix="/api")

    return app


app = create_app()
