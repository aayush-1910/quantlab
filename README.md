# QUANTLAB

A quantitative research platform for Indian listed equities (NSE cash equities first).
Research software only: no claim of returns and not investment advice.

Specification: [QUANTLAB_CODEX_MASTER_SPEC.md](QUANTLAB_CODEX_MASTER_SPEC.md)

## Status

Built: market data ingestion with validation and versioned snapshots, an instrument master,
a read API, a web app with a market explorer and a stock screener, and a deterministic
daily-bar backtesting engine with a moving-average baseline strategy (command line only).

Not built: experiment registry, walk-forward validation, machine learning, portfolio and
risk, the AI analyst, paper trading and broker connectivity. There is no order-placement
code.

No real market data and no real fee rates are included. Load your own CSV files or the
synthetic test generator, and supply your own cost schedule for backtests.

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

## Backtest

```sh
uv run python -m quantlab.backtesting.cli ma-crossover \
    --dataset-id synthetic_fixture.daily_bars \
    --fast 5 --slow 20 --initial-cash 1000000 \
    --slippage-bps 5 --max-participation 0.1 --zero-costs
```

Prints a JSON report with net and gross metrics, a buy-and-hold benchmark, the assumptions
used and the limitations that apply. A finished backtest is not a validated strategy. See
[docs/research_methodology/backtesting.md](docs/research_methodology/backtesting.md).

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
- [Backtesting methodology](docs/research_methodology/backtesting.md)
