# ADR 0003: Execution mode is safe by default and unimplemented modes are rejected

- Status: Accepted
- Date: 2026-11-12

## Context

Spec section 9.4 defines six operational states and requires `RESEARCH_ONLY` as the
default. Only research foundations exist. If the configuration accepted
`PAPER_TRADING`, `BROKER_READ_ONLY` or `LIVE_APPROVAL_REQUIRED` today, the system would
report a mode it cannot honour, and later code might trust that value.

## Decision

- `ExecutionMode` enumerates all six states so the vocabulary is fixed from the start.
- `Settings` accepts only `RESEARCH_ONLY`, `EXECUTION_DISABLED` and `EMERGENCY_STOP`. Any
  other value fails validation and the API does not start.
- `BROKER_MODE` accepts only `disabled`.
- The supported set is one constant, `SUPPORTED_EXECUTION_MODES`. A mode is added to it
  only in the change that implements and gates that mode (Phase 8 or 9).
- Broker credential variables are not read by the application at all yet, and are left
  out of `.env.example` until a phase needs them.

## Consequences

- A mis-set environment variable produces a startup error, not a silent capability claim.
- Tests assert the default, the rejections, and that no supported mode permits trading.
- This is a configuration guard only. The kill switch, pre-trade checks and approval
  binding in spec section 9 are still to be built before any execution work.
