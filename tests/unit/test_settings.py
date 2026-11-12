import pytest
from pydantic import ValidationError

from quantlab.common.settings import (
    SUPPORTED_EXECUTION_MODES,
    ExecutionMode,
    Settings,
)


def _settings(**env: str) -> Settings:
    """Build settings from explicit values only, ignoring any local .env file."""
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


def test_default_execution_mode_is_research_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXECUTION_MODE", raising=False)
    monkeypatch.delenv("BROKER_MODE", raising=False)

    settings = _settings()

    assert settings.execution_mode is ExecutionMode.RESEARCH_ONLY
    assert settings.broker_mode == "disabled"


def test_execution_mode_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTION_MODE", "EMERGENCY_STOP")

    assert _settings().execution_mode is ExecutionMode.EMERGENCY_STOP


@pytest.mark.parametrize("mode", sorted(set(ExecutionMode) - SUPPORTED_EXECUTION_MODES))
def test_unimplemented_execution_modes_are_rejected(mode: ExecutionMode) -> None:
    with pytest.raises(ValidationError, match="not implemented in this build"):
        _settings(execution_mode=mode.value)


def test_no_supported_mode_permits_trading() -> None:
    trading_modes = {
        ExecutionMode.PAPER_TRADING,
        ExecutionMode.BROKER_READ_ONLY,
        ExecutionMode.LIVE_APPROVAL_REQUIRED,
    }

    assert SUPPORTED_EXECUTION_MODES.isdisjoint(trading_modes)


def test_unknown_execution_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(execution_mode="LIVE")


def test_broker_mode_other_than_disabled_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(broker_mode="live")


def test_database_url_is_not_in_repr() -> None:
    settings = _settings(database_url="postgresql+psycopg://user:s3cret-value@db:5432/x")

    assert "s3cret-value" not in repr(settings)
