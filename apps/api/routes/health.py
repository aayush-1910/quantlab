from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from apps.api.errors import ApiError
from quantlab import __version__
from quantlab.common.db import get_engine
from quantlab.common.settings import ExecutionMode, Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness only: the process is up and its configuration loaded.

    This does not check PostgreSQL or any other dependency; see `/health/ready`.
    """

    status: Literal["ok"]
    service: str
    version: str
    environment: str
    execution_mode: ExecutionMode


@router.get("/health")
def get_health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.app_env,
        execution_mode=settings.execution_mode,
    )


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["ok"]


@router.get("/health/ready")
def get_readiness(engine: Annotated[Engine, Depends(get_engine)]) -> ReadinessResponse:
    """Ready means the database answers a query. Does not check that migrations are current."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # The driver message can contain the connection URL; never return it.
        raise ApiError(503, "database_unavailable", "The database is not reachable.") from exc
    return ReadinessResponse(status="ready", database="ok")
