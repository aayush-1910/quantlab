"""Deterministic descriptive calculations over published daily bars (Phase 2).

Everything here is computed from one snapshot and uses only bars dated on or before the
stated `as_of`, so the output for a past date does not change when later bars are added.

Conventions:
- A "session" is a date on which the instrument itself has a bar. An n-session return is
  `close[t] / close[t - n] - 1` over the instrument's own sessions. It is a price return on
  the dataset's adjustment basis: on UNADJUSTED data it is wrong across splits and bonuses,
  and it never includes dividends.
- Ratios are rounded half-even to 8 decimal places, rebased index values to 6, average
  volume to 2.
- A metric that needs more history than exists is None, never a partial-window estimate.
"""

import itertools
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

import polars as pl

from quantlab.data.schemas import SnapshotManifest
from quantlab.data.storage.lake import DataLake

RETURN_PLACES = Decimal("0.00000001")
INDEX_PLACES = Decimal("0.000001")
VOLUME_PLACES = Decimal("0.01")
AVERAGE_VOLUME_SESSIONS = 20
RETURN_HORIZONS = (1, 5, 20)
_LOOKBACK_ROWS = max(*RETURN_HORIZONS, AVERAGE_VOLUME_SESSIONS) + 1


@dataclass(frozen=True)
class GapRange:
    """Consecutive weekdays with no bar. Includes exchange holidays (no calendar yet)."""

    start: date
    end: date
    missing_weekdays: int


@dataclass(frozen=True)
class InstrumentCoverage:
    instrument_id: str
    first_trading_date: date
    last_trading_date: date
    bar_count: int
    missing_weekdays: int
    # Calendar days from this instrument's last bar to the dataset's last bar.
    days_behind_dataset: int


@dataclass(frozen=True)
class ScreenRow:
    instrument_id: str
    bar_date: date
    # True when the instrument has no bar on the screen's reference date.
    is_stale: bool
    sessions_available: int
    close: Decimal
    volume: int
    return_1d: Decimal | None
    return_5d: Decimal | None
    return_20d: Decimal | None
    avg_volume_20d: Decimal | None


@dataclass(frozen=True)
class ScreenResult:
    # Latest trading date in the snapshot on or before the requested as_of.
    reference_date: date | None
    rows: tuple[ScreenRow, ...]


@dataclass(frozen=True)
class ComparisonPoint:
    trading_date: date
    base_index: Decimal
    comparison_index: Decimal


@dataclass(frozen=True)
class Comparison:
    base_date: date | None
    points: tuple[ComparisonPoint, ...]
    # Sessions one instrument has and the other lacks, inside the overlapping range.
    base_only_sessions: int
    comparison_only_sessions: int


def weekday_gap_ranges(dates: list[date]) -> list[GapRange]:
    """Runs of missing weekdays between consecutive bar dates. `dates` must be sorted."""
    gaps = []
    for earlier, later in itertools.pairwise(dates):
        missing = []
        day = earlier + timedelta(days=1)
        while day < later:
            if day.weekday() < 5:
                missing.append(day)
            day += timedelta(days=1)
        if missing:
            gaps.append(GapRange(start=missing[0], end=missing[-1], missing_weekdays=len(missing)))
    return gaps


def simple_return(current: Decimal, previous: Decimal) -> Decimal:
    return (current / previous - 1).quantize(RETURN_PLACES, rounding=ROUND_HALF_EVEN)


def session_return(closes: list[Decimal], sessions: int) -> Decimal | None:
    """Return over the last `sessions` sessions of `closes` (oldest first)."""
    if sessions < 1:
        raise ValueError("sessions must be at least 1")
    if len(closes) <= sessions:
        return None
    return simple_return(closes[-1], closes[-1 - sessions])


def average_volume(volumes: list[int], sessions: int) -> Decimal | None:
    """Mean of the last `sessions` volumes, including the latest session."""
    if sessions < 1:
        raise ValueError("sessions must be at least 1")
    if len(volumes) < sessions:
        return None
    window = volumes[-sessions:]
    return (Decimal(sum(window)) / Decimal(sessions)).quantize(
        VOLUME_PLACES, rounding=ROUND_HALF_EVEN
    )


def rebased_comparison(
    base: list[tuple[date, Decimal]], comparison: list[tuple[date, Decimal]]
) -> Comparison:
    """Rebase two close series to 100 on their first common session.

    Only sessions present in both series are returned, so neither line is interpolated.
    """
    base_closes, comparison_closes = dict(base), dict(comparison)
    common = sorted(base_closes.keys() & comparison_closes.keys())
    if not common:
        return Comparison(None, (), 0, 0)
    first, last = common[0], common[-1]
    base_start, comparison_start = base_closes[first], comparison_closes[first]
    points = tuple(
        ComparisonPoint(
            trading_date=day,
            base_index=(base_closes[day] / base_start * 100).quantize(
                INDEX_PLACES, rounding=ROUND_HALF_EVEN
            ),
            comparison_index=(comparison_closes[day] / comparison_start * 100).quantize(
                INDEX_PLACES, rounding=ROUND_HALF_EVEN
            ),
        )
        for day in common
    )
    shared = set(common)
    return Comparison(
        base_date=first,
        points=points,
        base_only_sessions=sum(1 for d in base_closes if first <= d <= last and d not in shared),
        comparison_only_sessions=sum(
            1 for d in comparison_closes if first <= d <= last and d not in shared
        ),
    )


def _weekdays_between(first: date, last: date) -> int:
    days = (last - first).days + 1
    full_weeks, extra = divmod(days, 7)
    return full_weeks * 5 + sum(
        1 for offset in range(extra) if (first + timedelta(days=offset)).weekday() < 5
    )


def snapshot_coverage(lake: DataLake, manifest: SnapshotManifest) -> list[InstrumentCoverage]:
    frame = (
        pl.scan_parquet(lake.bars_path(manifest))
        .group_by("instrument_id")
        .agg(
            pl.col("trading_date").min().alias("first"),
            pl.col("trading_date").max().alias("last"),
            pl.len().alias("bars"),
            (pl.col("trading_date").dt.weekday() <= 5).sum().alias("weekday_bars"),
        )
        .sort("instrument_id")
        .collect()
    )
    dataset_last = manifest.last_trading_date
    return [
        InstrumentCoverage(
            instrument_id=row["instrument_id"],
            first_trading_date=row["first"],
            last_trading_date=row["last"],
            bar_count=row["bars"],
            missing_weekdays=_weekdays_between(row["first"], row["last"]) - row["weekday_bars"],
            days_behind_dataset=(dataset_last - row["last"]).days if dataset_last else 0,
        )
        for row in frame.to_dicts()
    ]


def screen_snapshot(lake: DataLake, manifest: SnapshotManifest, as_of: date | None) -> ScreenResult:
    """One row per instrument that has at least one bar on or before `as_of`."""
    frame = pl.scan_parquet(lake.bars_path(manifest))
    if as_of is not None:
        frame = frame.filter(pl.col("trading_date") <= as_of)
    recent = (
        frame.select("instrument_id", "trading_date", "close", "volume")
        .sort("instrument_id", "trading_date")
        .group_by("instrument_id", maintain_order=True)
        .agg(
            pl.len().alias("sessions"),
            pl.col("trading_date").tail(_LOOKBACK_ROWS),
            pl.col("close").tail(_LOOKBACK_ROWS),
            pl.col("volume").tail(_LOOKBACK_ROWS),
        )
        .collect()
        .to_dicts()
    )
    if not recent:
        return ScreenResult(reference_date=None, rows=())
    reference_date = max(row["trading_date"][-1] for row in recent)
    rows = []
    for row in recent:
        closes: list[Decimal] = row["close"]
        volumes: list[int] = row["volume"]
        bar_date: date = row["trading_date"][-1]
        rows.append(
            ScreenRow(
                instrument_id=row["instrument_id"],
                bar_date=bar_date,
                is_stale=bar_date < reference_date,
                sessions_available=row["sessions"],
                close=closes[-1],
                volume=volumes[-1],
                return_1d=session_return(closes, 1),
                return_5d=session_return(closes, 5),
                return_20d=session_return(closes, 20),
                avg_volume_20d=average_volume(volumes, AVERAGE_VOLUME_SESSIONS),
            )
        )
    return ScreenResult(reference_date=reference_date, rows=tuple(rows))
