# ADR 0006: Backtesting engine design

- Status: Accepted
- Date: 2026-11-15

## Context

Phase 3 (spec sections 6.3, 6.6 and 13) needs a deterministic, event-driven backtester with
order, position and cash accounting, execution and cost models, benchmark comparison,
metrics and a moving-average baseline. Its results must match hand-calculated toy cases and
a close-derived signal must not fill at the same close.

## Decision

- **Pure library.** `quantlab/backtesting` imports nothing from the API, the database or
  any AI code. Only `runner.py` and `cli.py` touch the data lake, to load bars.
- **Strategies return target weights, not orders.** The engine owns sizing, timing and
  fills, so no strategy can give itself a better fill. Long only, no leverage.
- **Decide at close, fill at the next session's open.** There is no option to fill at the
  signal's own close.
- **No implicit execution assumptions.** Slippage and the volume limit are required
  inputs. A run needs a cost schedule or an explicit zero-cost choice.
- **No fee rates in the repository.** The cost model is a versioned, effective-dated
  schedule the user supplies with a source note. Tests use invented rates labelled as such.
  This follows the spec's instruction not to hardcode rates or present unverified ones.
- **Exact accounting, float statistics.** Cash, prices, fees and positions are `Decimal`
  with stated rounding. Ratios such as Sharpe use floats.
- **Unfilled quantity is cancelled.** A strategy that still wants the position asks again
  at the next close. This keeps order state simple and every outcome visible.
- **Gross is net plus costs added back**, not a second simulation, and is described that
  way wherever it is shown.
- **The benchmark runs through the same engine** with the same costs and execution.

## Not delivered in this phase

- Splits and dividends. The Phase 3 exit criterion says "where supported"; there is no
  corporate-action data, so they are not supported and every report says so.
- An API route or web screen for backtests. Experiment specifications, the run registry and
  reports are Phase 4; exposing runs before they are recorded would invite unrecorded
  parameter mining.
- Strategy families beyond the moving-average baseline.

## Consequences

- The engine loops in Python over sessions. That is fine for daily bars over a few hundred
  instruments and has not been benchmarked beyond the test fixtures.
- Results on today's data are price-return only and carry the survivorship and adjustment
  caveats of whatever dataset is supplied.
