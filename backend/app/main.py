"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.router import api_v1_router


def create_app() -> FastAPI:
    """Build the CSM backend application."""
    app = FastAPI(
        title="CSM Backend",
        version="0.1.0",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
    )
    app.include_router(api_v1_router)
    return app


app = create_app()