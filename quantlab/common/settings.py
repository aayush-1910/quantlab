"""Application configuration, loaded from environment variables (and `.env` locally).

Safety posture: this build implements research foundations only. Configuration that
asks for paper trading, broker connectivity or live execution is rejected at startup
rather than silently accepted, so a mis-set environment variable can never imply a
capability that does not exist (spec sections 1.4 and 9.4).
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionMode(StrEnum):
    """Operational states from spec section 9.4."""

    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_TRADING = "PAPER_TRADING"
    BROKER_READ_ONLY = "BROKER_READ_ONLY"
    LIVE_APPROVAL_REQUIRED = "LIVE_APPROVAL_REQUIRED"
    EXECUTION_DISABLED = "EXECUTION_DISABLED"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class BrokerMode(StrEnum):
    DISABLED = "disabled"


# Modes this build can honour. Every one of them blocks order submission.
# Extend only when the corresponding phase (8 or 9) is implemented and gated.
SUPPORTED_EXECUTION_MODES: frozenset[ExecutionMode] = frozenset(
    {
        ExecutionMode.RESEARCH_ONLY,
        ExecutionMode.EXECUTION_DISABLED,
        ExecutionMode.EMERGENCY_STOP,
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "QUANTLAB"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"

    database_url: str = Field(
        default="postgresql+psycopg://quantlab:quantlab@localhost:5433/quantlab",
        repr=False,  # may embed a password; keep it out of logs and tracebacks
    )

    # Root of the file-based data lake (raw, normalized, curated). Git-ignored by default.
    data_dir: Path = Path("data")

    execution_mode: ExecutionMode = ExecutionMode.RESEARCH_ONLY
    broker_mode: BrokerMode = BrokerMode.DISABLED

    @model_validator(mode="after")
    def _reject_unimplemented_execution_modes(self) -> "Settings":
        if self.execution_mode not in SUPPORTED_EXECUTION_MODES:
            supported = ", ".join(sorted(SUPPORTED_EXECUTION_MODES))
            raise ValueError(
                f"EXECUTION_MODE={self.execution_mode.value} is not implemented in this "
                f"build. Supported modes: {supported}."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
