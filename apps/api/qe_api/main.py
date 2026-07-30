"""FastAPI application factory for the QE Copilot API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qe_api import API_VERSION
from qe_api.errors import register_error_handlers
from qe_api.health import router as health_router
from qe_api.middleware import CorrelationIdMiddleware
from qe_api.routers.v1 import router as v1_router
from qe_common.config import get_settings
from qe_observability import configure_logging


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging()

    app = FastAPI(
        title="QE Copilot API",
        version=API_VERSION,
        description="AI-Powered Test Generation and Defect Triage Platform",
        openapi_url="/openapi.json",
        docs_url="/docs",
    )

    app.add_middleware(CorrelationIdMiddleware)
    # The web app calls the API cross-origin. Origins are configured explicitly
    # rather than wildcarded, because requests carry an Authorization header.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(v1_router)

    app.state.settings = settings
    return app


app = create_app()

__all__ = ["app", "create_app"]
