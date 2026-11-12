"""FastAPI entry point. Run with: uv run uvicorn apps.api.main:app --reload"""

from fastapi import FastAPI

from apps.api.routes import health
from quantlab import __version__
from quantlab.common.settings import get_settings

API_V1_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()  # fails fast on unsafe/unsupported configuration
    app = FastAPI(title=f"{settings.app_name} API", version=__version__)
    app.include_router(health.router, prefix=API_V1_PREFIX)
    return app


app = create_app()
