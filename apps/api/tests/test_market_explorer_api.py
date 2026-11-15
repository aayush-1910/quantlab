"""HTTP tests for coverage, comparison, screener and watchlist. Data is SYNTHETIC_TEST_DATA.

Fixture, 25 sessions for A (every weekday 1 Jan to 2 Feb 2024, close = 100 + session
index, volume = 1000 * (index + 1)), and for B only 5 sessions with a gap.
"""

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from apps.api.main import create_app
from quantlab.common.db import get_engine
from quantlab.common.settings import Settings, get_settings
from quantlab.data.ingestion.service import ingest_daily_bars
from quantlab.data.providers.csv_file import CsvFileProvider
from quantlab.data.schemas import AdjustmentBasis
from quantlab.data.storage.lake import DataLake

WriteSource = Callable[..., Path]
DATASET = {"dataset_id": "test_csv.daily_bars"}

INSTRUMENTS = (
    "provider_instrument_id,exchange,instrument_type,symbol,name,isin,valid_from,valid_to\n"
    "A,NSE,EQUITY,AAA,Synthetic A Ltd,,2024-01-01,\n"
    "B,NSE,EQUITY,BBB,Synthetic B Ltd,,2024-01-01,\n"
)


def _bars() -> str:
    lines = ["provider_instrument_id,trading_date,open,high,low,close,volume"]
    day, index = date(2024, 1, 1), 0
    while index < 25:
        if day.weekday() < 5:
            close = 100 + index
            lines.append(f"A,{day},{close},{close},{close},{close},{1000 * (index + 1)}")
            index += 1
        day += timedelta(days=1)
    for day_text, close in [
        ("2024-01-01", 50),
        ("2024-01-02", 55),
        ("2024-01-03", 44),
        # Thu 4 Jan to Tue 9 Jan missing: 4 weekdays
        ("2024-01-10", 60),
        ("2024-01-11", 66),
    ]:
        lines.append(f"B,{day_text},{close},{close},{close},{close},500")
    return "\n".join(lines) + "\n"


@pytest.fixture
def client(
    db_engine: Engine, tmp_path: Path, lake: DataLake, write_csv_source: WriteSource
) -> TestClient:
    provider = CsvFileProvider(
        write_csv_source(instruments=INSTRUMENTS, bars=_bars()),
        source_id="test_csv",
        licence_reference="SYNTHETIC_TEST_DATA written by the test suite",
        source_dataset_version="delivery-1",
        adjustment_basis=AdjustmentBasis.UNADJUSTED,
    )
    ingest_daily_bars(provider, db_engine, lake)
    app = create_app()
    settings = Settings(_env_file=None, data_dir=tmp_path / "lake")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_engine] = lambda: db_engine
    return TestClient(app)


@pytest.fixture
def ids(client: TestClient) -> dict[str, str]:
    body = client.get("/api/v1/market/coverage", params=DATASET).json()
    return {
        row["instrument"]["symbol"]: row["instrument"]["instrument_id"]
        for row in body["instruments"]
    }


def test_coverage_reports_range_gaps_and_staleness_per_instrument(client: TestClient) -> None:
    body = client.get("/api/v1/market/coverage", params=DATASET).json()

    assert body["snapshot"]["snapshot_id"] == "test_csv.daily_bars-v1"
    assert body["snapshot"]["data_classification"] == "USER_SUPPLIED"
    assert body["snapshot"]["adjustment_basis"] == "UNADJUSTED"
    assert body["snapshot"]["last_trading_date"] == "2024-02-02"
    assert body["snapshot"]["data_as_of"]
    a, b = body["instruments"]
    assert a["instrument"]["symbol"] == "AAA"
    assert a["instrument"]["name"] == "Synthetic A Ltd"
    assert (a["first_trading_date"], a["last_trading_date"]) == ("2024-01-01", "2024-02-02")
    assert (a["bar_count"], a["missing_weekdays"], a["days_behind_dataset"]) == (25, 0, 0)
    assert (b["first_trading_date"], b["last_trading_date"]) == ("2024-01-01", "2024-01-11")
    # 11 Jan to 2 Feb is 22 calendar days.
    assert (b["bar_count"], b["missing_weekdays"], b["days_behind_dataset"]) == (5, 4, 22)


def test_bars_list_the_gaps_between_returned_bars(client: TestClient, ids: dict[str, str]) -> None:
    body = client.get("/api/v1/market/bars", params={**DATASET, "instrument_id": ids["BBB"]}).json()

    assert body["gaps"] == [{"start": "2024-01-04", "end": "2024-01-09", "missing_weekdays": 4}]


def test_comparison_is_rebased_on_common_sessions_only(
    client: TestClient, ids: dict[str, str]
) -> None:
    body = client.get(
        "/api/v1/market/compare",
        params={**DATASET, "instrument_id": ids["BBB"], "comparison_instrument_id": ids["AAA"]},
    ).json()

    assert body["base"]["symbol"] == "BBB"
    assert body["comparison"]["symbol"] == "AAA"
    assert body["base_date"] == "2024-01-01"
    assert [p["trading_date"] for p in body["points"]] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-10",
        "2024-01-11",
    ]
    # B: 50 -> 66 is 132. A on 11 Jan is session index 8: 108 / 100.
    assert body["points"][-1] == {
        "trading_date": "2024-01-11",
        "base_index": "132.000000",
        "comparison_index": "108.000000",
    }
    assert body["points"][2]["base_index"] == "88.000000"
    assert (body["base_only_sessions"], body["comparison_only_sessions"]) == (0, 4)
    assert body["snapshot"]["snapshot_id"] == "test_csv.daily_bars-v1"


def test_comparison_rejects_the_same_instrument_and_unknown_ones(
    client: TestClient, ids: dict[str, str]
) -> None:
    same = client.get(
        "/api/v1/market/compare",
        params={**DATASET, "instrument_id": ids["AAA"], "comparison_instrument_id": ids["AAA"]},
    )
    unknown = client.get(
        "/api/v1/market/compare",
        params={**DATASET, "instrument_id": ids["AAA"], "comparison_instrument_id": "nope"},
    )

    assert (same.status_code, same.json()["error"]["code"]) == (422, "invalid_comparison")
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "instrument_not_found")


def test_screener_metrics_match_hand_calculation(client: TestClient) -> None:
    body = client.get("/api/v1/market/screener", params=DATASET).json()

    assert body["reference_date"] == "2024-02-02"
    assert body["requested_as_of"] is None
    assert body["universe"] == "ALL_INSTRUMENTS_IN_SNAPSHOT"
    assert (body["universe_count"], body["matched_count"]) == (2, 2)
    assert body["currency"] == "INR"
    a, b = body["rows"]
    # A: last close 124 (index 24). 1d: 124/123, 5d: 124/119, 20d: 124/104.
    assert a["instrument"]["symbol"] == "AAA"
    assert (a["bar_date"], a["is_stale"], a["sessions_available"]) == ("2024-02-02", False, 25)
    assert (a["close"], a["volume"]) == ("124.000000", 25000)
    assert a["return_1d"] == "0.00813008"
    assert a["return_5d"] == "0.04201681"
    assert a["return_20d"] == "0.19230769"
    # Volumes 6000..25000: mean of 20 terms = 15500.
    assert a["avg_volume_20d"] == "15500.00"
    # B: 5 sessions ending 11 Jan. 1d: 66/60. Not enough history for 5d, 20d or the average.
    assert (b["bar_date"], b["is_stale"], b["sessions_available"]) == ("2024-01-11", True, 5)
    assert b["return_1d"] == "0.10000000"
    assert (b["return_5d"], b["return_20d"], b["avg_volume_20d"]) == (None, None, None)


def test_screener_as_of_uses_only_bars_up_to_that_date(client: TestClient) -> None:
    # Saturday 6 Jan: the reference date falls back to Friday 5 Jan.
    body = client.get("/api/v1/market/screener", params={**DATASET, "as_of": "2024-01-06"}).json()

    assert (body["requested_as_of"], body["reference_date"]) == ("2024-01-06", "2024-01-05")
    a, b = body["rows"]
    # A has 5 sessions (closes 100..104): 1d = 104/103, no 5d yet.
    assert (a["close"], a["sessions_available"]) == ("104.000000", 5)
    assert a["return_1d"] == "0.00970874"
    assert a["return_5d"] is None
    # B's last bar on or before 6 Jan is 3 Jan: 44/55.
    assert (b["bar_date"], b["is_stale"], b["close"]) == ("2024-01-03", True, "44.000000")
    assert b["return_1d"] == "-0.20000000"

    empty = client.get("/api/v1/market/screener", params={**DATASET, "as_of": "2023-12-31"}).json()
    assert (empty["reference_date"], empty["rows"]) == (None, [])


@pytest.mark.parametrize(
    ("params", "symbols"),
    [
        ({"min_close": "100"}, ["AAA"]),
        ({"max_close": "70"}, ["BBB"]),
        ({"include_stale": "false"}, ["AAA"]),
        ({"min_return_20d": "0.19"}, ["AAA"]),
        ({"min_return_20d": "0.20"}, []),
        ({"max_return_20d": "1"}, ["AAA"]),  # B's 20d return is null and never passes
        ({"min_avg_volume_20d": "15500"}, ["AAA"]),
        ({"min_avg_volume_20d": "15500.01"}, []),
        ({"sort": "close", "order": "asc"}, ["BBB", "AAA"]),
        ({"sort": "return_1d", "order": "desc"}, ["BBB", "AAA"]),
        ({"sort": "return_20d", "order": "desc"}, ["AAA", "BBB"]),  # nulls last
        ({"sort": "return_20d", "order": "asc"}, ["AAA", "BBB"]),  # nulls last
        ({"sort": "symbol", "order": "desc"}, ["BBB", "AAA"]),
        ({"limit": "1"}, ["AAA"]),
    ],
)
def test_screener_filters_and_sorting(
    client: TestClient, params: dict[str, str], symbols: list[str]
) -> None:
    body = client.get("/api/v1/market/screener", params={**DATASET, **params}).json()

    assert [row["instrument"]["symbol"] for row in body["rows"]] == symbols


def test_screener_errors_use_the_envelope(client: TestClient) -> None:
    no_dataset = client.get("/api/v1/market/screener")
    bad_sort = client.get("/api/v1/market/screener", params={**DATASET, "sort": "alpha"})
    negative = client.get("/api/v1/market/screener", params={**DATASET, "min_close": "-1"})

    assert (no_dataset.status_code, no_dataset.json()["error"]["code"]) == (
        422,
        "snapshot_not_resolved",
    )
    assert bad_sort.json()["error"]["code"] == "validation_error"
    assert negative.json()["error"]["code"] == "validation_error"


def test_watchlist_add_and_remove_are_idempotent(client: TestClient, ids: dict[str, str]) -> None:
    assert client.get("/api/v1/watchlist").json() == {"items": []}

    first = client.put(f"/api/v1/watchlist/{ids['BBB']}")
    client.put(f"/api/v1/watchlist/{ids['AAA']}")
    again = client.put(f"/api/v1/watchlist/{ids['BBB']}")

    assert first.status_code == 200
    items = again.json()["items"]
    assert [item["instrument"]["symbols"][0]["symbol"] for item in items] == ["BBB", "AAA"]
    assert items[0]["added_at"] == first.json()["items"][0]["added_at"]

    removed = client.delete(f"/api/v1/watchlist/{ids['BBB']}")
    removed_again = client.delete(f"/api/v1/watchlist/{ids['BBB']}")

    assert removed.status_code == removed_again.status_code == 200
    assert [i["instrument"]["instrument_id"] for i in removed_again.json()["items"]] == [ids["AAA"]]
    assert client.get("/api/v1/watchlist").json() == removed_again.json()


def test_watchlist_rejects_unknown_instruments(client: TestClient) -> None:
    response = client.put("/api/v1/watchlist/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "instrument_not_found"
    assert client.get("/api/v1/watchlist").json() == {"items": []}
