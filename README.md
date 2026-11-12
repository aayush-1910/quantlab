# QUANTLAB

A quantitative research and decision-support platform for Indian listed equities (NSE cash
equities first). The goal is a trustworthy, reproducible environment for testing market
hypotheses, and rejecting them when the evidence does not support them.

The full product and engineering specification is
[QUANTLAB_CODEX_MASTER_SPEC.md](QUANTLAB_CODEX_MASTER_SPEC.md). It is the source of truth.

> QUANTLAB is research software. It makes no claim of returns, profitability or predictive
> accuracy, and it is not investment advice.

## Current status: Phase 0 (engineering foundation)

What exists today:

| Piece | State |
|---|---|
| FastAPI app with `GET /api/v1/health` | Working, tested |
| Typed settings with safe execution defaults | Working, tested |
| Next.js shell with an Overview page that reads the health endpoint | Working, tested |
| Alembic migrations (baseline: `audit_events` table) | Written; SQL rendering tested. **Not yet applied to a real PostgreSQL** on a developer machine |
| Docker Compose (PostgreSQL only) | Written. **Not yet run** (Docker was unavailable when it was authored) |
| GitHub Actions CI | Written. **Not yet run** (no remote repository yet) |

What does **not** exist: market data, instruments, backtesting, ML, portfolio/risk, the AI
analyst, paper trading and any broker connectivity. There is no order-placement code of any
kind. The application refuses to start if `EXECUTION_MODE` asks for paper, broker or live
modes, because those are not implemented (see [ADR 0003](docs/adr/0003-safe-by-default-execution-mode.md)).

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
web shell do not need the database.

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

One migration test applies and reverts migrations on a real database. It is skipped unless
`QUANTLAB_TEST_DATABASE_URL` points at a **disposable** PostgreSQL database (it drops the
migrated tables). CI provides one.

## Layout

```text
apps/api/             FastAPI entry point, routes and API tests
apps/web/             Next.js (App Router) frontend
quantlab/             Python domain and application packages (currently: common/settings)
database/migrations/  Alembic migrations, written by hand
tests/                Cross-cutting Python tests (unit, integration)
docs/                 Architecture overview and ADRs
```

Directories for later modules are created when their phase begins, not before.

## Rules that always apply

- Never commit secrets, broker credentials, account identifiers or licensed market data.
- Synthetic fixtures must be labelled `SYNTHETIC_TEST_DATA` and never appear in performance reports.
- No live order placement without the separate, explicitly approved Phase 9 milestone.

## Documentation

- [System overview](docs/architecture/system-overview.md)
- [Architecture decision records](docs/adr/)
