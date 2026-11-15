"""Backtest on a published snapshot. Uses PostgreSQL and SYNTHETIC_TEST_DATA only."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine

from quantlab.backtesting import cli
from quantlab.backtesting.costs import ZeroCostModel
from quantlab.backtesting.engine import BacktestConfig, BacktestResult, ExecutionConfig
from quantlab.backtesting.runner import BacktestReport, build_report, load_price_bars
from quantlab.backtesting.strategy import BuyAndHold, MovingAverageCrossover
from quantlab.common.settings import get_settings
from quantlab.data.ingestion.service import ingest_daily_bars
from quantlab.data.providers.synthetic import SyntheticFixtureProvider
from quantlab.data.storage.lake import DataLake

CONFIG = BacktestConfig(Decimal("1000000"), ExecutionConfig(Decimal("5"), Decimal("0.1")))


def test_report_carries_provenance_assumptions_and_limitations(
    db_engine: Engine, lake: DataLake
) -> None:
    manifest = ingest_daily_bars(SyntheticFixtureProvider(), db_engine, lake).manifest
    universe = list(manifest.instrument_ids)
    bars = load_price_bars(lake, manifest, universe)
    weight = Decimal(1) / Decimal(len(universe))

    def run() -> tuple[BacktestReport, BacktestResult, BacktestResult]:
        return build_report(
            bars,
            MovingAverageCrossover(universe, 5, 20),
            BuyAndHold(dict.fromkeys(universe, weight)),
            ZeroCostModel(),
            CONFIG,
            manifest=manifest,
        )

    report, result, benchmark = run()
    again, _, _ = run()

    assert report == again  # deterministic end to end
    assert report.snapshot_id == manifest.snapshot_id
    assert report.snapshot_content_sha256 == manifest.content_sha256
    assert report.data_classification == "SYNTHETIC_TEST_DATA"
    assert report.adjustment_basis == "UNADJUSTED"
    assert report.cost_model_id == "zero-costs"
    assert (report.slippage_bps, report.max_participation) == (Decimal("5"), Decimal("0.1"))
    assert report.instrument_ids == tuple(sorted(universe))
    assert report.net.sessions == report.benchmark_net.sessions == 65
    assert report.net.start_date == manifest.first_trading_date
    assert report.net.end_date == manifest.last_trading_date
    assert any("SYNTHETIC_TEST_DATA" in note for note in report.limitations)
    assert any("No transaction fees" in note for note in report.limitations)
    assert any("survivorship" in note for note in report.limitations)
    assert any("not evidence" in note for note in report.limitations)
    # Slippage is the only cost, so gross is at least net for both runs.
    assert report.gross.final_equity >= report.net.final_equity
    assert report.benchmark_gross.final_equity >= report.benchmark_net.final_equity
    assert report.trading.fills == len(result.fills) > 0
    assert len(benchmark.fills) == len(universe)
    assert report.relative.sessions == 65
    json.dumps(report.to_json_dict())  # serializable as is


def test_cli_prints_a_json_report_and_requires_explicit_cost_and_execution_choices(
    db_engine: Engine,
    lake: DataLake,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ingest_daily_bars(SyntheticFixtureProvider(), db_engine, lake)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "lake"))
    get_settings.cache_clear()
    base = [
        "ma-crossover",
        "--dataset-id",
        "synthetic_fixture.daily_bars",
        "--fast",
        "5",
        "--slow",
        "20",
        "--initial-cash",
        "1000000",
    ]

    code = cli.main([*base, "--slippage-bps", "5", "--max-participation", "none", "--zero-costs"])
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert report["strategy_id"] == "ma-crossover(fast=5,slow=20,n=3)"
    assert report["max_participation"] is None
    assert Decimal(report["net"]["final_equity"]) > 0  # money is serialized as a string
    assert any("No volume limit" in note for note in report["limitations"])

    for incomplete in (
        [*base, "--max-participation", "0.1", "--zero-costs"],  # no slippage stated
        [*base, "--slippage-bps", "5", "--zero-costs"],  # no volume limit stated
        [*base, "--slippage-bps", "5", "--max-participation", "0.1"],  # no cost model stated
    ):
        with pytest.raises(SystemExit):
            cli.main(incomplete)

    assert (
        cli.main(
            [
                *base[:2],
                "missing.daily_bars",
                *base[3:],
                "--slippage-bps",
                "5",
                "--max-participation",
                "0.1",
                "--zero-costs",
            ]
        )
        == 1
    )
    assert "backtest failed" in capsys.readouterr().err
