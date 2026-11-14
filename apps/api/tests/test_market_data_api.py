"""HTTP tests for the market-data routes. All data is SYNTHETIC_TEST_DATA."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from apps.api.main import create_app
from conftest import BARS_CSV
from quantlab.common.db import get_engine
from quantlab.common.settings import Settings, get_settings
from quantlab.data.ingestion.service import IngestionFailedError, ingest_daily_bars
from quantlab.data.providers.csv_file import CsvFileProvider
from quantlab.data.providers.synthetic import SyntheticFixtureProvider
from quantlab.data.schemas import AdjustmentBasis
from quantlab.data.storage.lake import DataLake

WriteSource = Callable[..., Path]


def _provider(directory: Path) -> CsvFileProvider:
    return CsvFileProvider(
        directory,
        source_id="test_csv",
        licence_reference="SYNTHETIC_TEST_DATA written by the test suite",
        source_dataset_version="delivery-1",
        adjustment_basis=AdjustmentBasis.UNADJUSTED,
    )


@pytest.fixture
def client(db_engine: Engine, tmp_path: Path) -> TestClient:
    app = create_app()
    settings = Settings(_env_file=None, data_dir=tmp_path / "lake")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_engine] = lambda: db_engine
    return TestClient(app)


@pytest.fixture
def ingested(
    client: TestClient, db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> str:
    """Ingests the CSV fixture with one bad row; returns the internal ID of TESTONE."""
    bars = BARS_CSV + "T2,2024-01-03,51.75,52.00,51.00,abc,700,\n"
    ingest_daily_bars(_provider(write_csv_source(bars=bars)), db_engine, lake)
    body = client.get("/api/v1/instruments", params={"q": "TESTONE"}).json()
    return str(body["instruments"][0]["instrument_id"])


def test_instrument_search_and_detail(client: TestClient, ingested: str) -> None:
    listing = client.get("/api/v1/instruments").json()
    assert [i["symbols"][0]["symbol"] for i in listing["instruments"]] == ["TESTONE", "TESTTWO"]

    detail = client.get(f"/api/v1/instruments/{ingested}").json()
    assert detail["exchange"] == "NSE"
    assert detail["instrument_type"] == "EQUITY"
    assert detail["currency"] == "INR"
    assert detail["symbols"] == [
        {
            "symbol": "TESTONE",
            "name": "Synthetic Test One Ltd",
            "isin": None,
            "valid_from": "2024-01-01",
            "valid_to": None,
            "source_id": "test_csv",
        }
    ]

    before_listing = client.get("/api/v1/instruments", params={"as_of": "2023-12-31"}).json()
    assert before_listing["instruments"] == []
    assert before_listing["as_of"] == "2023-12-31"


def test_bars_carry_provenance_units_and_exact_decimals(client: TestClient, ingested: str) -> None:
    response = client.get(
        "/api/v1/market/bars",
        params={
            "instrument_id": ingested,
            "dataset_id": "test_csv.daily_bars",
            "start": "2024-01-02",
            "end": "2024-01-02",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_id"] == "test_csv.daily_bars-v1"
    assert body["source_id"] == "test_csv"
    assert body["data_classification"] == "USER_SUPPLIED"
    assert body["adjustment_basis"] == "UNADJUSTED"
    assert (body["frequency"], body["currency"]) == ("1d", "INR")
    assert body["data_as_of"]
    assert body["count"] == 1
    assert body["bars"] == [
        {
            "trading_date": "2024-01-02",
            "open": "101.000000",
            "high": "103.500000",
            "low": "100.500000",
            "close": "103.000000",
            "volume": 1500,
            "turnover": None,
        }
    ]
    assert body["gaps"] == []
    assert any("quarantined" in warning for warning in body["quality_warnings"])


def test_bars_can_be_pinned_to_an_exact_snapshot(
    client: TestClient,
    ingested: str,
    db_engine: Engine,
    lake: DataLake,
    write_csv_source: WriteSource,
) -> None:
    corrected = BARS_CSV.replace("101.00,103.50", "101.00,103.75")
    ingest_daily_bars(_provider(write_csv_source(bars=corrected)), db_engine, lake)
    params = {"instrument_id": ingested, "start": "2024-01-02", "end": "2024-01-02"}

    latest = client.get(
        "/api/v1/market/bars", params={**params, "dataset_id": "test_csv.daily_bars"}
    ).json()
    pinned = client.get(
        "/api/v1/market/bars", params={**params, "snapshot_id": "test_csv.daily_bars-v1"}
    ).json()

    assert (latest["snapshot_id"], latest["bars"][0]["high"]) == (
        "test_csv.daily_bars-v2",
        "103.750000",
    )
    assert (pinned["snapshot_id"], pinned["bars"][0]["high"]) == (
        "test_csv.daily_bars-v1",
        "103.500000",
    )


def test_synthetic_data_is_never_served_without_its_label(
    client: TestClient, ingested: str, db_engine: Engine, lake: DataLake
) -> None:
    ingest_daily_bars(SyntheticFixtureProvider(), db_engine, lake)
    synthetic_id = client.get("/api/v1/instruments", params={"q": "SYNTH001"}).json()[
        "instruments"
    ][0]["instrument_id"]

    body = client.get(
        "/api/v1/market/bars",
        params={"instrument_id": synthetic_id, "dataset_id": "synthetic_fixture.daily_bars"},
    ).json()
    assert body["data_classification"] == "SYNTHETIC_TEST_DATA"
    assert body["count"] == 65

    # A real-data dataset has no bars for a synthetic instrument, and vice versa.
    crossed = client.get(
        "/api/v1/market/bars",
        params={"instrument_id": synthetic_id, "dataset_id": "test_csv.daily_bars"},
    ).json()
    assert crossed["count"] == 0


@pytest.mark.parametrize(
    ("params", "status", "code"),
    [
        (
            {"instrument_id": "nope", "dataset_id": "test_csv.daily_bars"},
            404,
            "instrument_not_found",
        ),
        ({"instrument_id": "ID"}, 422, "snapshot_not_resolved"),
        ({"instrument_id": "ID", "dataset_id": "missing.daily_bars"}, 404, "snapshot_not_resolved"),
        ({"instrument_id": "ID", "snapshot_id": "missing-v1"}, 404, "snapshot_not_resolved"),
        (
            {"instrument_id": "ID", "dataset_id": "x", "start": "2024-02-01", "end": "2024-01-01"},
            422,
            "invalid_date_range",
        ),
        ({"instrument_id": "ID", "dataset_id": "x", "start": "yesterday"}, 422, "validation_error"),
        ({}, 422, "validation_error"),
    ],
)
def test_bar_errors_use_the_error_envelope(
    client: TestClient, ingested: str, params: dict[str, str], status: int, code: str
) -> None:
    resolved = {k: ingested if v == "ID" else v for k, v in params.items()}

    response = client.get("/api/v1/market/bars", params=resolved)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["message"]


def test_unknown_routes_and_instruments_use_the_error_envelope(client: TestClient) -> None:
    assert client.get("/api/v1/nope").json() == {
        "error": {"code": "http_error", "message": "Not Found"}
    }
    missing = client.get("/api/v1/instruments/nope")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "instrument_not_found"


def test_snapshot_manifest_and_quarantine_are_inspectable(
    client: TestClient, ingested: str
) -> None:
    listing = client.get("/api/v1/datasets/snapshots").json()["snapshots"]
    assert [s["snapshot_id"] for s in listing] == ["test_csv.daily_bars-v1"]

    manifest = client.get("/api/v1/datasets/snapshots/test_csv.daily_bars-v1").json()
    assert manifest["licence_reference"].startswith("SYNTHETIC_TEST_DATA")
    assert manifest["source_dataset_version"] == "delivery-1"
    assert manifest["schema_version"] == "1"
    assert (manifest["record_count"], manifest["quarantined_count"]) == (5, 1)
    assert len(manifest["content_sha256"]) == 64
    assert all(len(ref["sha256"]) == 64 and ref["retrieved_at"] for ref in manifest["raw_objects"])

    quarantine = client.get("/api/v1/datasets/snapshots/test_csv.daily_bars-v1/quarantine").json()
    assert quarantine["total"] == 1
    assert quarantine["records"][0]["source_record_id"] == "daily_bars.csv:line 7"
    assert quarantine["records"][0]["reasons"] == ["close: not a number"]
    assert quarantine["records"][0]["raw_fields"]["close"] == "abc"

    assert client.get("/api/v1/datasets/snapshots/nope").json()["error"]["code"] == (
        "snapshot_not_found"
    )


def test_failed_runs_and_their_quarantine_are_inspectable(
    client: TestClient, db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> None:
    bars = (
        "provider_instrument_id,trading_date,open,high,low,close,volume\nT1,2024-01-01,x,1,1,1,1\n"
    )
    with pytest.raises(IngestionFailedError):
        ingest_daily_bars(_provider(write_csv_source(bars=bars)), db_engine, lake)

    (run,) = client.get("/api/v1/datasets/ingestion-runs").json()["runs"]
    assert run["status"] == "FAILED"
    assert "no valid records" in run["error"]
    assert run["snapshot_id"] is None

    report = client.get(f"/api/v1/datasets/ingestion-runs/{run['run_id']}/quarantine").json()
    assert report["total"] == 1
    assert report["records"][0]["reasons"] == ["open: not a number"]
    assert client.get("/api/v1/datasets/snapshots").json() == {"snapshots": []}


def test_readiness_reports_database_state_without_leaking_the_url(client: TestClient) -> None:
    assert client.get("/api/v1/health/ready").json() == {"status": "ready", "database": "ok"}

    unreachable = create_engine(
        "postgresql+psycopg://user:s3cret-value@127.0.0.1:1/none",
        connect_args={"connect_timeout": 1},
    )
    client.app.dependency_overrides[get_engine] = lambda: unreachable  # type: ignore[attr-defined]

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "s3cret-value" not in response.text


def test_the_only_write_routes_are_the_watchlist(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    writes = {
        (path, method)
        for path, operations in paths.items()
        for method in operations
        if method != "get"
    }
    assert writes == {
        ("/api/v1/watchlist/{instrument_id}", "put"),
        ("/api/v1/watchlist/{instrument_id}", "delete"),
    }
