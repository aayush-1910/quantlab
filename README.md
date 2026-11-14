# QUANTLAB

A quantitative research platform for Indian listed equities (NSE cash equities first).
Research software only: no claim of returns and not investment advice.

Specification: [QUANTLAB_CODEX_MASTER_SPEC.md](QUANTLAB_CODEX_MASTER_SPEC.md)

## Status

Built: market data ingestion with validation and versioned snapshots, an instrument master,
a read API, and a web app with a market explorer and a stock screener.

Not built: backtesting, machine learning, portfolio and risk, the AI analyst, paper trading
and broker connectivity. There is no order-placement code.

No real market data is included. Load your own CSV files or the synthetic test generator.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 24 with pnpm
- PostgreSQL (a container is provided through Docker Compose)

## Setup

```sh
uv sync
pnpm install
docker compose up -d postgres
uv run alembic upgrade head
```

Configuration is read from environment variables or a local `.env` file. The defaults work
with the Compose database. The variables are defined in `quantlab/common/settings.py`.

## Run

```sh
uv run uvicorn apps.api.main:app --reload     # http://localhost:8000/docs
pnpm web:dev                                  # http://localhost:3000
```

## Load data

```sh
# Generated test data, labelled SYNTHETIC_TEST_DATA
uv run python -m quantlab.data.cli ingest-synthetic

# Your own files: a directory with instruments.csv and daily_bars.csv
uv run python -m quantlab.data.cli ingest-csv path/to/dir \
    --source-id my_vendor_eod \
    --licence-reference "Vendor X agreement, 2026-10" \
    --dataset-version 2026-11-13 \
    --adjustment-basis UNADJUSTED
```

The CSV format is described in [docs/data_dictionary/daily-bars.md](docs/data_dictionary/daily-bars.md).

## Checks

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest

pnpm --filter @quantlab/web lint
pnpm --filter @quantlab/web typecheck
pnpm --filter @quantlab/web test
pnpm --filter @quantlab/web build
```

Database tests run only when `QUANTLAB_TEST_DATABASE_URL` points at a disposable PostgreSQL
database. They truncate and drop its tables.

## Documentation

- [System overview](docs/architecture/system-overview.md)
- [Architecture decision records](docs/adr/)
- [Data dictionary](docs/data_dictionary/)
