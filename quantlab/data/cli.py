"""Market-data command line. Run with: uv run python -m quantlab.data.cli --help"""

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from quantlab.common.db import get_engine
from quantlab.common.settings import get_settings
from quantlab.data.ingestion.service import (
    IngestionFailedError,
    SnapshotNotFoundError,
    ingest_daily_bars,
    reproduce_snapshot,
)
from quantlab.data.providers.base import MarketDataProvider, ProviderDataError
from quantlab.data.providers.csv_file import CsvFileProvider
from quantlab.data.providers.synthetic import SyntheticFixtureProvider
from quantlab.data.schemas import AdjustmentBasis, DataClassification
from quantlab.data.storage import catalog
from quantlab.data.storage.lake import DataLake


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantlab.data.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    synthetic = commands.add_parser(
        "ingest-synthetic", help="Ingest generated SYNTHETIC_TEST_DATA (not market data)"
    )
    synthetic.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 1))
    synthetic.add_argument("--end", type=date.fromisoformat, default=date(2024, 3, 29))
    synthetic.add_argument("--instruments", type=int, default=3)
    synthetic.add_argument("--seed", type=int, default=7)

    csv = commands.add_parser("ingest-csv", help="Ingest user-supplied CSV files")
    csv.add_argument("directory", type=Path, help="Contains instruments.csv and daily_bars.csv")
    csv.add_argument("--source-id", required=True, help="e.g. my_vendor_eod")
    csv.add_argument(
        "--licence-reference", required=True, help="Where your right to use this data comes from"
    )
    csv.add_argument("--dataset-version", required=True, help="Your label for this delivery")
    csv.add_argument(
        "--adjustment-basis", required=True, choices=[basis.value for basis in AdjustmentBasis]
    )
    csv.add_argument(
        "--classification",
        default=DataClassification.USER_SUPPLIED.value,
        choices=[DataClassification.USER_SUPPLIED.value, DataClassification.LICENSED.value],
    )

    commands.add_parser("snapshots", help="List published snapshots")
    reproduce = commands.add_parser(
        "reproduce", help="Rebuild a snapshot from raw data and compare checksums"
    )
    reproduce.add_argument("snapshot_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = get_engine()
    lake = DataLake(get_settings().data_dir)

    if args.command == "snapshots":
        with engine.connect() as conn:
            for manifest in catalog.list_snapshots(conn):
                print(
                    f"{manifest.snapshot_id}  {manifest.data_classification.value}  "
                    f"{manifest.first_trading_date}..{manifest.last_trading_date}  "
                    f"records={manifest.record_count} quarantined={manifest.quarantined_count}"
                )
        return 0

    if args.command == "reproduce":
        try:
            report = reproduce_snapshot(args.snapshot_id, engine, lake)
        except SnapshotNotFoundError:
            print(f"snapshot not found: {args.snapshot_id}", file=sys.stderr)
            return 2
        print(f"recorded: {report.recorded_content_sha256}")
        print(f"stored:   {report.stored_content_sha256}")
        print(f"rebuilt:  {report.rebuilt_content_sha256}")
        for problem in report.problems:
            print(f"problem:  {problem}")
        print("MATCH" if report.matches else "MISMATCH")
        return 0 if report.matches else 1

    provider: MarketDataProvider
    if args.command == "ingest-synthetic":
        provider = SyntheticFixtureProvider(args.start, args.end, args.instruments, args.seed)
    else:
        provider = CsvFileProvider(
            args.directory,
            source_id=args.source_id,
            licence_reference=args.licence_reference,
            source_dataset_version=args.dataset_version,
            adjustment_basis=AdjustmentBasis(args.adjustment_basis),
            data_classification=DataClassification(args.classification),
        )
    try:
        result = ingest_daily_bars(provider, engine, lake)
    except (IngestionFailedError, ProviderDataError, ValueError) as exc:
        print(f"ingestion failed: {exc}", file=sys.stderr)
        return 1
    manifest = result.manifest
    print("already ingested, nothing written" if result.already_ingested else "published")
    print(f"snapshot:    {manifest.snapshot_id} ({manifest.data_classification.value})")
    print(f"records:     {manifest.record_count}")
    print(f"quarantined: {manifest.quarantined_count}")
    for warning in manifest.quality_warnings:
        print(f"warning:     {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
