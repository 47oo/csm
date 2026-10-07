"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.csrf import CsrfMiddleware
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    """Build the CSM backend application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="CSM Backend",
        version="0.1.0",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
    )
    register_exception_handlers(app)
    app.add_middleware(CsrfMiddleware)
    app.include_router(api_v1_router)
    return app


app = create_app()