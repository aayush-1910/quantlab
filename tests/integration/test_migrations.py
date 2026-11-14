"""Migration checks.

The offline test renders SQL without a database and always runs. The online test
applies migrations to a real PostgreSQL and runs only when QUANTLAB_TEST_DATABASE_URL
is set (CI sets it; see .github/workflows/ci.yml). It must point at a disposable
database: the test downgrades to base, dropping all migrated tables.
"""

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from conftest import TEST_DATABASE_URL
from conftest import alembic_config as _config
from quantlab.common.settings import get_settings
from quantlab.data.storage import tables


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
        inspector = inspect(engine)
        assert "audit_events" in inspector.get_table_names()
        # The hand-written migrations and the query-side table definitions must agree.
        migrated = {
            name: {column["name"] for column in inspector.get_columns(name)}
            for name in inspector.get_table_names()
            if name != "alembic_version"
        }
        defined = {
            table.name: {column.name for column in table.columns}
            for table in tables.metadata.sorted_tables
        }
        assert migrated == defined

        command.upgrade(_config(), "head")  # re-applying is a no-op

        command.downgrade(_config(), "base")
        assert "audit_events" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        get_settings.cache_clear()
