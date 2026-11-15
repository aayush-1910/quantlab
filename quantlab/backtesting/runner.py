"""Run a strategy and its benchmark on a published snapshot and assemble a report.

The report always carries the snapshot it ran on, the cost model, the execution
assumptions and the limitations that apply, so the numbers cannot be read without them.
A completed backtest is not a validated strategy (spec section 2.3).
"""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from quantlab.backtesting.costs import CostModel, ZeroCostModel
from quantlab.backtesting.engine import BacktestConfig, BacktestResult, run_backtest
from quantlab.backtesting.metrics import (
    PerformanceMetrics,
    RelativeMetrics,
    TradingMetrics,
    gross_performance,
    net_performance,
    relative,
    trading,
)
from quantlab.backtesting.models import PriceBar
from quantlab.backtesting.strategy import Strategy
from quantlab.data.schemas import AdjustmentBasis, DataClassification, SnapshotManifest
from quantlab.data.storage.lake import DataLake


@dataclass(frozen=True)
class BacktestReport:
    strategy_id: str
    benchmark_id: str
    cost_model_id: str
    initial_cash: Decimal
    slippage_bps: Decimal
    max_participation: Decimal | None
    risk_free_rate: float
    snapshot_id: str | None
    snapshot_content_sha256: str | None
    data_classification: str | None
    adjustment_basis: str | None
    instrument_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    net: PerformanceMetrics
    gross: PerformanceMetrics
    trading: TradingMetrics
    benchmark_net: PerformanceMetrics
    benchmark_gross: PerformanceMetrics
    relative: RelativeMetrics

    def to_json_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))  # type: ignore[no-any-return]


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def load_price_bars(
    lake: DataLake,
    manifest: SnapshotManifest,
    instrument_ids: Sequence[str],
    start: date | None = None,
    end: date | None = None,
) -> dict[str, list[PriceBar]]:
    bars: dict[str, list[PriceBar]] = {instrument_id: [] for instrument_id in instrument_ids}
    for instrument_id in instrument_ids:
        for bar in lake.read_bars(manifest, instrument_id, start, end):
            bars[instrument_id].append(
                PriceBar(bar.trading_date, bar.open, bar.high, bar.low, bar.close, bar.volume)
            )
    return bars


ENGINE_LIMITATIONS = (
    "Corporate actions and dividends are not modelled: results are price returns only.",
    "Fills are at the next session's open with fixed slippage; there is no market-impact "
    "model, no price-band or circuit-limit handling and no settlement lag.",
    "The universe is the instruments supplied to the run, not a point-in-time index "
    "membership. If the data holds only instruments that still exist, the result is "
    "survivorship-biased.",
    "A completed backtest is not evidence that a strategy works. There is no out-of-sample "
    "validation or multiple-testing control in this run.",
)


def snapshot_limitations(manifest: SnapshotManifest) -> list[str]:
    notes = []
    if manifest.data_classification is DataClassification.SYNTHETIC_TEST_DATA:
        notes.append(
            "SYNTHETIC_TEST_DATA: prices are generated, not market data. These results "
            "say nothing about any real strategy and must not be reported as performance."
        )
    if manifest.adjustment_basis is AdjustmentBasis.UNADJUSTED:
        notes.append(
            "Prices are unadjusted: any split or bonus in the period appears as a price "
            "jump and is counted as profit or loss."
        )
    elif manifest.adjustment_basis is AdjustmentBasis.UNKNOWN:
        notes.append("The adjustment basis of the prices is unknown.")
    else:
        notes.append(
            "Prices are back-adjusted by the supplier. Adjusted prices and share counts "
            "differ from what was tradable on the day, which distorts fills and volume limits."
        )
    notes.extend(manifest.quality_warnings)
    return notes


def build_report(
    bars: Mapping[str, Sequence[PriceBar]],
    strategy: Strategy,
    benchmark: Strategy,
    cost_model: CostModel,
    config: BacktestConfig,
    *,
    manifest: SnapshotManifest | None = None,
    risk_free_rate: float = 0.0,
) -> tuple[BacktestReport, BacktestResult, BacktestResult]:
    """Run strategy and benchmark under identical data, costs and execution assumptions."""
    result = run_backtest(bars, strategy, cost_model, config)
    benchmark_result = run_backtest(bars, benchmark, cost_model, config)
    limitations = list(ENGINE_LIMITATIONS)
    if isinstance(cost_model, ZeroCostModel):
        limitations.append(
            "No transaction fees were applied: net and gross differ only by slippage."
        )
    if config.execution.max_participation is None:
        limitations.append("No volume limit was applied: orders of any size are assumed to fill.")
    if manifest is not None:
        limitations.extend(snapshot_limitations(manifest))
    report = BacktestReport(
        strategy_id=result.strategy_id,
        benchmark_id=benchmark_result.strategy_id,
        cost_model_id=result.cost_model_id,
        initial_cash=config.initial_cash,
        slippage_bps=config.execution.slippage_bps,
        max_participation=config.execution.max_participation,
        risk_free_rate=risk_free_rate,
        snapshot_id=manifest.snapshot_id if manifest else None,
        snapshot_content_sha256=manifest.content_sha256 if manifest else None,
        data_classification=manifest.data_classification.value if manifest else None,
        adjustment_basis=manifest.adjustment_basis.value if manifest else None,
        instrument_ids=tuple(sorted(bars)),
        limitations=tuple(limitations),
        net=net_performance(result, risk_free_rate),
        gross=gross_performance(result, risk_free_rate),
        trading=trading(result),
        benchmark_net=net_performance(benchmark_result, risk_free_rate),
        benchmark_gross=gross_performance(benchmark_result, risk_free_rate),
        relative=relative(result, benchmark_result),
    )
    return report, result, benchmark_result
