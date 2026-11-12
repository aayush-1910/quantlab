# ADR 0001: Modular monolith in a monorepo, grown by phase

- Status: Accepted
- Date: 2026-11-12

## Context

The specification (sections 3.1 and 4) calls for a modular monolith with a Next.js
frontend, a FastAPI API and a shared Python domain package, and warns against scaffolding
empty structure upfront.

## Decision

- One repository. `apps/api` (HTTP layer), `apps/web` (frontend), `quantlab/` (domain and
  application code), `database/migrations`, `tests/`, `docs/`.
- `apps/api` contains only HTTP concerns and depends on `quantlab`. `quantlab` never
  imports from `apps`.
- Directories for a module are created in the phase that implements it. No empty
  placeholder packages.

## Consequences

- The repository does not yet match the full tree in spec section 4; that is intentional.
- Module boundaries are convention for now. If they start to erode, add an import-linter
  check rather than splitting services.
