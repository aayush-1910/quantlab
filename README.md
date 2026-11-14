# QUANTLAB

A quantitative research and decision-support platform for Indian listed equities (NSE cash
equities first). The goal is a trustworthy, reproducible environment for testing market
hypotheses, and rejecting them when the evidence does not support them.

The full product and engineering specification is
[QUANTLAB_CODEX_MASTER_SPEC.md](QUANTLAB_CODEX_MASTER_SPEC.md). It is the source of truth.

> QUANTLAB is research software. It makes no claim of returns, profitability or predictive
> accuracy, and it is not investment advice.

## Current status: Phase 1 (market data foundation)

What exists today:

| Piece | State |
|---|---|
| FastAPI app: health, readiness, instruments, daily bars, dataset provenance | Working, tested |
| Typed settings with safe execution defaults | Working, tested |
| Instrument master with stable internal IDs and effective-dated symbols | Working, tested |
| Provider boundary with two adapters: `SYNTHETIC_TEST_DATA` generator and user-supplied CSV | Working, tested |
| Ingestion: immutable raw layer, validation with quarantine, versioned snapshots with manifests and checksums | Working, tested |
| Idempotent re-ingestion and snapshot reproduction from raw data | Working, tested |
| Alembic migrations (audit log, market-data catalog) | Applied and reverted on PostgreSQL 16 in tests |
| Next.js shell with an Overview page that reads the health endpoint | Working, tested. Shows no market data yet |
| Docker Compose (PostgreSQL only) | Written. **Not yet run** by the author of this change (no Docker daemon available) |
| GitHub Actions CI | Written. **Not yet observed running** |

**No real market data is included or connected.** No licensed provider has been integrated;
the only way to load real data today is to supply your own CSV files, and you are
responsible for having the right to use them. The synthetic generator produces made-up
instruments and prices for development only.

Known limitations of the data layer (details in the
[data dictionary](docs/data_dictionary/daily-bars.md)):

- No exchange trading calendar: holidays cannot be told apart from missing bars.
- No corporate actions, index constituents or fundamentals. Adjustment basis is whatever the
  data supplier declares; it is recorded, not verified.
- No authentication. Do not expose the API beyond localhost.

What does **not** exist: market explorer UI, backtesting, ML, portfolio/risk, the AI
analyst, paper trading and any broker connectivity. There is no order-placement code of any
kind, and the API has only read (GET) routes. The application refuses to start if
`EXECUTION_MODE` asks for paper, broker or live modes, because those are not implemented
(see [ADR 0003](docs/adr/0003-safe-by-default-execution-mode.md)).

## Prerequisites

- Python 3.12+ (developed on 3.14) and [uv](https://docs.astral.sh/uv/)
- Node.js 24 with corepack (bundled), which provides the pinned pnpm
- Docker, for the local PostgreSQL. On Windows, Docker Desktop needs WSL 2
  (`wsl --install` from an administrator terminal, then reboot)

## Setup

```sh
# 1. Configuration (placeholders only; .env is git-ignored)
cp .env.example .env

# 2. Python dependencies
uv sync

# 3. Web dependencies (prefix with `corepack` if pnpm is not on your PATH)
pnpm install

# 4. Database (container listens on host port 5433, leaving 5432 free
#    for any PostgreSQL installed directly on your machine)
docker compose up -d postgres
uv run alembic upgrade head
```

## Run

```sh
uv run uvicorn apps.api.main:app --reload     # API  -> http://localhost:8000/api/v1/health
pnpm web:dev                                  # Web  -> http://localhost:3000
```

The API serves interactive docs at `http://localhost:8000/docs`. The health endpoint and the
web shell do not need the database; every other route does.

## Loading data

Data lands in the lake under `DATA_DIR` (default `./data`, git-ignored) and in PostgreSQL.

```sh
# Development data: generated, labelled SYNTHETIC_TEST_DATA, never real prices
uv run python -m quantlab.data.cli ingest-synthetic

# Your own files: a directory with instruments.csv and daily_bars.csv
# (format: docs/data_dictionary/daily-bars.md)
uv run python -m quantlab.data.cli ingest-csv path/to/dir \
    --source-id my_vendor_eod \
    --licence-reference "Vendor X agreement, 2026-10" \
    --dataset-version 2026-11-13 \
    --adjustment-basis UNADJUSTED

uv run python -m quantlab.data.cli snapshots
uv run python -m quantlab.data.cli reproduce synthetic_fixture.daily_bars-v1
```

Running the same ingestion twice writes nothing the second time. A changed file produces a
new snapshot version; earlier versions stay readable. `reproduce` rebuilds a snapshot from
its raw files and compares checksums.

Then query it:

```text
GET /api/v1/instruments?q=SYNTH
GET /api/v1/market/bars?instrument_id=<id>&dataset_id=synthetic_fixture.daily_bars&start=2024-01-01&end=2024-01-31
GET /api/v1/datasets/snapshots/synthetic_fixture.daily_bars-v1
GET /api/v1/datasets/snapshots/synthetic_fixture.daily_bars-v1/quarantine
GET /api/v1/datasets/ingestion-runs
```

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

Tests that need PostgreSQL (migrations, ingestion, market-data API) are skipped unless
`QUANTLAB_TEST_DATABASE_URL` points at a **disposable** PostgreSQL database: they truncate
and drop its tables. CI provides one. Without it, only the pure unit tests run.

## Layout

```text
apps/api/             FastAPI entry point, routes and API tests
apps/web/             Next.js (App Router) frontend
quantlab/common/      Settings and database engine
quantlab/data/        Market data: providers, validation, storage (catalog + lake), ingestion, query, CLI
database/migrations/  Alembic migrations, written by hand
tests/                Cross-cutting Python tests (unit, integration)
docs/                 Architecture overview, ADRs and the data dictionary
```

Directories for later modules are created when their phase begins, not before.

## Rules that always apply

- Never commit secrets, broker credentials, account identifiers or licensed market data.
- Synthetic fixtures must be labelled `SYNTHETIC_TEST_DATA` and never appear in performance reports.
- No live order placement without the separate, explicitly approved Phase 9 milestone.

## Documentation

- [System overview](docs/architecture/system-overview.md)
- [Architecture decision records](docs/adr/)
- [Data dictionary: instruments, daily bars, snapshots](docs/data_dictionary/daily-bars.md)
