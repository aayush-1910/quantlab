from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from quantlab import __version__
from quantlab.common.settings import ExecutionMode, Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness only: the process is up and its configuration loaded.

    This does not check PostgreSQL or any other dependency; a readiness
    endpoint will be added when the API first depends on the database.
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
