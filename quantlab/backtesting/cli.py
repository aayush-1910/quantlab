"""Backtest command line. Run with: uv run python -m quantlab.backtesting.cli --help

Prints a JSON report. This is a research tool: it never places orders.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path

from quantlab.backtesting.costs import CostModel, CostModelError, ZeroCostModel, load_cost_schedule
from quantlab.backtesting.engine import BacktestConfig, BacktestInputError, ExecutionConfig
from quantlab.backtesting.runner import build_report, load_price_bars
from quantlab.backtesting.strategy import BuyAndHold, MovingAverageCrossover
from quantlab.common.db import get_engine
from quantlab.common.settings import get_settings
from quantlab.data.query import SnapshotLookupError, resolve_snapshot
from quantlab.data.storage.lake import DataLake, LakeIntegrityError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantlab.backtesting.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ma = commands.add_parser("ma-crossover", help="Moving-average crossover vs equal-weight hold")
    source = ma.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset-id", help="Use the latest snapshot of this dataset")
    source.add_argument("--snapshot-id", help="Use exactly this snapshot")
    ma.add_argument("--fast", type=int, required=True)
    ma.add_argument("--slow", type=int, required=True)
    ma.add_argument("--start", type=date.fromisoformat)
    ma.add_argument("--end", type=date.fromisoformat)
    ma.add_argument("--initial-cash", type=Decimal, required=True, help="INR")
    ma.add_argument("--slippage-bps", type=Decimal, required=True)
    ma.add_argument(
        "--max-participation",
        required=True,
        help="Fraction of session volume per order, e.g. 0.1, or 'none' for no limit",
    )
    costs = ma.add_mutually_exclusive_group(required=True)
    costs.add_argument("--cost-schedule", type=Path, help="JSON cost schedule file")
    costs.add_argument("--zero-costs", action="store_true", help="Apply no fees (stated in report)")
    ma.add_argument("--risk-free-rate", type=float, default=0.0, help="Annual, e.g. 0.065")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    lake = DataLake(get_settings().data_dir)
    try:
        cost_model: CostModel = (
            ZeroCostModel() if args.zero_costs else load_cost_schedule(args.cost_schedule)
        )
        participation = (
            None if args.max_participation.lower() == "none" else Decimal(args.max_participation)
        )
        config = BacktestConfig(
            initial_cash=args.initial_cash,
            execution=ExecutionConfig(args.slippage_bps, participation),
        )
        with get_engine().connect() as conn:
            manifest = resolve_snapshot(conn, args.snapshot_id, args.dataset_id)
        universe = list(manifest.instrument_ids)
        bars = load_price_bars(lake, manifest, universe, args.start, args.end)
        weight = Decimal(1) / Decimal(len(universe))
        report, _, _ = build_report(
            bars,
            MovingAverageCrossover(universe, args.fast, args.slow),
            BuyAndHold(dict.fromkeys(universe, weight)),
            cost_model,
            config,
            manifest=manifest,
            risk_free_rate=args.risk_free_rate,
        )
    except (
        BacktestInputError,
        CostModelError,
        SnapshotLookupError,
        LakeIntegrityError,
        ValueError,
        ArithmeticError,
    ) as exc:
        print(f"backtest failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report.to_json_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
