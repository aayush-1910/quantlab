# Data dictionary: descriptive market analytics

Last updated: 2026-11-14 (Phase 2). Implemented in `quantlab/data/analytics.py`.

All values come from one snapshot. A "session" is a date on which the instrument itself has
a bar.

| Value | Definition | Rounding | Null when |
|---|---|---|---|
| `return_1d`, `return_5d`, `return_20d` | `close[t] / close[t - n] - 1` over the instrument's own sessions, as a ratio (0.05 = 5%) | half-even, 8 places | fewer than n + 1 sessions on or before the reference date |
| `avg_volume_20d` | mean share volume of the last 20 sessions, latest included | half-even, 2 places | fewer than 20 sessions |
| `base_index`, `comparison_index` | `close[t] / close[first common session] * 100` | half-even, 6 places | no common session |
| `missing_weekdays` | Monday to Friday dates with no bar between an instrument's first and last bar | exact | never |
| `days_behind_dataset` | calendar days from the instrument's last bar to the snapshot's last bar | exact | never |
| `is_stale` | the instrument has no bar on the screen's reference date | | never |

`reference_date` is the latest trading date in the snapshot on or before the requested
`as_of` (or the latest overall when no `as_of` is given).

## What these numbers are not

- They are price returns on the snapshot's adjustment basis. They exclude dividends, and on
  `UNADJUSTED` data they are wrong across splits and bonuses.
- `missing_weekdays` includes exchange holidays, because no trading calendar is integrated.
- They are descriptive. Nothing here is a signal, a backtest result or evidence of
  predictability.
