"""FastAPI 应用工厂。

组装：配置 → 引擎 / 会话工厂 → 错误处理 → 路由。

F001 已彻底移除 F012 的非产品自检面；应用只暴露 ``/api`` 下的产品面。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health as health_api
from app.auth.middleware import AuthMiddleware
from app.auth.router import router as auth_router
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

    # F015：生产环境关闭框架默认文档面（/docs /redoc /openapi.json）。它们位于
    # 认证边界（/api）之外，未认证可达并暴露完整 API schema；dev / test 保持开启。
    docs_enabled = settings.environment != "prod"
    app = FastAPI(
        title="CSM API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.db_sessionmaker = create_session_factory(engine)

    register_error_handlers(app)

    # F013 认证边界：ASGI 中间件在**路由之前**生效，fail-closed 保护全部
    # /api/*（唯一豁免 POST /api/auth/login）。必须在 include_router 前注册。
    app.add_middleware(AuthMiddleware)

    # 产品 API 面：health + clusters + auth。全部位于 /api 前缀下。
    app.include_router(health_api.router, prefix="/api")
    app.include_router(clusters_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")

    return app


app = create_app()
