# Backtesting engine

Last updated: 2026-11-15 (Phase 3). Code: `quantlab/backtesting/`.

The engine answers one narrow question: given these daily bars, this strategy, these costs
and these execution assumptions, what would the accounts have looked like. It is
deterministic and has no dependency on the API, the database or any AI component. A
finished backtest is not a validated strategy.

## Timeline

For each session D in the data, in date order:

1. **Fill.** Orders decided after the previous session's close are resolved at D's open.
   Sells first, then buys, each in instrument-ID order.
2. **Value.** The portfolio is valued at D's close.
3. **Decide.** The strategy receives bars up to and including D and returns target weights.
4. **Order.** Targets become whole-share orders, sized with D's close and D's closing
   equity. They become eligible at the next session in the data.

A decision that uses a close can therefore never be filled at that close. The history
handed to a strategy ends at the decision date, so a later bar is not reachable.

## Execution assumptions

| Assumption | Behaviour |
|---|---|
| Fill price | Session open, moved against the order by `slippage_bps` |
| Volume limit | At most `max_participation` of the fill session's volume per order |
| Cash | A buy is cut to what cash covers, fees included. Cash never goes negative |
| Short selling | Not allowed. A sell is cut to the quantity held |
| Missing bar | No bar on the eligible session: the order is rejected |
| Unfilled quantity | Cancelled, not carried forward |
| Share size | Whole shares only |
| Leverage | Target weights must be non-negative and sum to at most 1 |

`slippage_bps` and `max_participation` have no defaults. "No volume limit" has to be chosen
explicitly and is then listed in the report's limitations.

Every order is recorded with its signal date, eligible date, status (`FILLED`,
`PARTIALLY_FILLED`, `REJECTED`, `UNFILLED_NO_LATER_SESSION`) and the reasons any quantity
did not fill.

## Costs

The repository contains no real fee rates. Charges differ by broker, exchange, segment and
date, so a run needs either a cost schedule file or an explicit zero-cost choice.

Per fill of traded value V:

```text
brokerage        = V * brokerage_rate, capped at brokerage_cap_per_order if set
stt              = V * stt_buy_rate (buys) or V * stt_sell_rate (sells)
exchange_charges = V * exchange_rate
sebi_charges     = V * sebi_rate
stamp_duty       = V * stamp_duty_buy_rate, buys only
gst              = gst_rate * (brokerage + exchange_charges + sebi_charges)
```

Each component is rounded half-even to 0.01. Real contract notes aggregate per day and
round differently, so totals will not match a broker's to the paisa.

Schedule file format. Rates are decimal strings, never JSON numbers. A fill dated outside
every entry is an error, not a free trade.

```json
{
  "schedule_id": "my_broker_delivery",
  "version": "2026-11",
  "entries": [
    {
      "effective_from": "2024-10-01",
      "effective_to": null,
      "source_note": "Where each rate came from and the date it was checked",
      "rates": {
        "brokerage_rate": "0",
        "brokerage_cap_per_order": null,
        "stt_buy_rate": "0",
        "stt_sell_rate": "0",
        "exchange_rate": "0",
        "sebi_rate": "0",
        "stamp_duty_buy_rate": "0",
        "gst_rate": "0"
      }
    }
  ]
}
```

The zeros above are placeholders, not rates. Fill them from the broker's and exchange's
current published charges and say so in `source_note`.

## Accounting

Prices are rounded half-even to 4 decimal places and money to 2. A position's average cost
includes buy-side fees. Realized profit on a sell is proceeds minus sell fees minus average
cost times quantity. A held instrument with no bar on a session is valued at its last close
and the session is flagged.

## Metrics

Definitions are in the module docstring of `quantlab/backtesting/metrics.py`. Summary:

- Returns are session-to-session returns of closing equity; annualization uses 252 sessions.
- CAGR uses calendar days / 365.25.
- Sharpe and Sortino take an explicit annual risk-free rate (default 0).
- Drawdown is measured from the running peak, starting at initial cash.
- Win statistics are per sell fill, net of all fees.
- Holding period is first-in first-out, share-weighted, in calendar days.
- Net and gross are both reported. Gross adds fees and slippage back onto the net equity
  curve; it does not re-run the strategy without costs.
- A ratio with a zero denominator or too few observations is reported as null.

The benchmark is run through the same engine with the same data, costs and execution
assumptions. Beta and alpha come from an ordinary least-squares fit of session returns on
the sessions both curves share; with a short sample they are noise.

## Strategies

- `MovingAverageCrossover`: hold an instrument while its fast simple moving average of
  closes is strictly above the slow one. Each held instrument gets a fixed weight of
  1 / universe size. It trades only when signal and holding disagree, so a position is
  not rebalanced while the signal holds.
- `BuyAndHold`: buy fixed weights once and never rebalance. Used as the benchmark.

## Running it

```sh
uv run python -m quantlab.backtesting.cli ma-crossover \
    --dataset-id synthetic_fixture.daily_bars \
    --fast 5 --slow 20 \
    --initial-cash 1000000 \
    --slippage-bps 5 --max-participation 0.1 \
    --zero-costs
```

The output is a JSON report holding the snapshot ID and content checksum, the data
classification, the cost model, the execution assumptions, net and gross metrics, the
benchmark's metrics and the list of limitations that apply to the run.

## Not modelled

- Corporate actions and dividends. Results are price returns. On unadjusted data a split or
  bonus shows up as profit or loss. On supplier-adjusted data, prices and volumes are not
  what was tradable on the day.
- Settlement lag, price bands, circuit limits, auctions and the intraday price path.
- Market impact beyond the fixed slippage.
- Point-in-time universes. The universe is whatever instruments are passed in.
- Delistings. An instrument that stops having bars keeps its last close as its value.
- Walk-forward validation, holdouts and multiple-testing control. Those belong to Phase 4.
