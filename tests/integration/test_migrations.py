"""Migration checks.

The offline test renders SQL without a database and always runs. The online test
applies migrations to a real PostgreSQL and runs only when QUANTLAB_TEST_DATABASE_URL
is set (CI sets it; see .github/workflows/ci.yml). It must point at a disposable
database: the test downgrades to base, dropping all migrated tables.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from quantlab.common.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("QUANTLAB_TEST_DATABASE_URL")


def _config() -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "database" / "migrations"))
    return config


def test_migration_history_has_a_single_head() -> None:
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_migrations_render_offline_sql(capsys: pytest.CaptureFixture[str]) -> None:
    command.upgrade(_config(), "head", sql=True)

    sql = capsys.readouterr().out
    assert "CREATE TABLE audit_events" in sql
    assert "JSONB" in sql


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="QUANTLAB_TEST_DATABASE_URL not set")
def test_migrations_apply_and_revert_on_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()
    engine = create_engine(TEST_DATABASE_URL)
    try:
        command.upgrade(_config(), "head")
        assert "audit_events" in inspect(engine).get_table_names()

        command.upgrade(_config(), "head")  # re-applying is a no-op

        command.downgrade(_config(), "base")
        assert "audit_events" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        get_settings.cache_clear()
