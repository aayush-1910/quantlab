# ADR 0002: Python and frontend tooling

- Status: Accepted
- Date: 2026-11-12

## Context

Phase 0 needs locked dependencies and lint, type and test checks that run the same locally
and in CI.

## Decision

**Python**

- `uv` with `pyproject.toml` and a committed `uv.lock`. `.python-version` pins 3.14, the
  version the checks were run on; `requires-python` allows 3.12+.
- The project is not built as a wheel (`tool.uv.package = false`). The repository root is
  on the import path, so `apps.api` and `quantlab` import directly. A wheel would otherwise
  have to carve `apps/api` out of a directory that also holds the frontend.
- `ruff` for formatting and linting (including the bandit-derived `S` rules), `mypy`
  in strict mode, `pytest`.
- Alembic for migrations, written by hand. There are no ORM models yet, so autogenerate
  is not configured.

**Frontend**

- pnpm workspace, version pinned through `packageManager` and run via corepack.
- Next.js 16 (App Router), Tailwind CSS 4, ESLint with `eslint-config-next`, Vitest.
- TypeScript is held at 6.0.x and ESLint at 9.x because `eslint-config-next` 16.4 and
  `typescript-eslint` 8 do not yet declare support for TypeScript 7 or ESLint 10.
- shadcn/ui and a charting library are deferred until a screen needs them.

## Consequences

- Commands are run from the repository root.
- ESLint 9 is marked deprecated upstream; revisit both pins when `eslint-config-next`
  supports the newer majors.
- Starlette's test client warns that `httpx` is deprecated in favour of `httpx2`. This is
  left as a warning until that replacement has been reviewed.
