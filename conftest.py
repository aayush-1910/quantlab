"""Shared fixtures. Database tests need QUANTLAB_TEST_DATABASE_URL to point at a
DISPOSABLE PostgreSQL database: its tables are truncated and migrations are reverted."""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from quantlab.common.db import get_engine
from quantlab.common.settings import get_settings
from quantlab.data.storage.lake import DataLake

REPO_ROOT = Path(__file__).resolve().parent
TEST_DATABASE_URL = os.environ.get("QUANTLAB_TEST_DATABASE_URL")

# All fixture market data in tests is SYNTHETIC_TEST_DATA: invented instruments and prices.
INSTRUMENTS_CSV = (
    "provider_instrument_id,exchange,instrument_type,symbol,name,isin,valid_from,valid_to\n"
    "T1,NSE,EQUITY,TESTONE,Synthetic Test One Ltd,,2024-01-01,\n"
    "T2,NSE,EQUITY,TESTTWO,Synthetic Test Two Ltd,,2024-01-01,\n"
)
BARS_CSV = (
    "provider_instrument_id,trading_date,open,high,low,close,volume,turnover\n"
    "T1,2024-01-01,100.00,102.00,99.00,101.00,1000,100500.00\n"
    "T1,2024-01-02,101.00,103.50,100.50,103.00,1500,\n"
    "T1,2024-01-03,103.00,104.00,101.00,102.00,1200,123000.00\n"
    "T2,2024-01-01,50.00,51.00,49.50,50.50,800,40200.00\n"
    "T2,2024-01-02,50.50,52.00,50.00,51.75,900,46000.00\n"
)


def alembic_config() -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "database" / "migrations"))
    return config


@pytest.fixture
def db_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    if TEST_DATABASE_URL is None:
        pytest.skip("QUANTLAB_TEST_DATABASE_URL not set")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()
    get_engine.cache_clear()
    command.upgrade(alembic_config(), "head")
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE audit_events, ingestion_runs, dataset_snapshots, raw_objects, "
                "provider_instrument_ids, instrument_symbols, instruments RESTART IDENTITY CASCADE"
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()
        get_settings.cache_clear()
        get_engine.cache_clear()


@pytest.fixture
def lake(tmp_path: Path) -> DataLake:
    return DataLake(tmp_path / "lake")


@pytest.fixture
def write_csv_source(tmp_path: Path) -> Callable[..., Path]:
    def _write(
        name: str = "source", instruments: str = INSTRUMENTS_CSV, bars: str = BARS_CSV
    ) -> Path:
        directory = tmp_path / name
        directory.mkdir(exist_ok=True)
        (directory / "instruments.csv").write_text(instruments, encoding="utf-8", newline="")
        (directory / "daily_bars.csv").write_text(bars, encoding="utf-8", newline="")
        return directory

    return _write
