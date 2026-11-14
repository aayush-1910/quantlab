# ADR 0005: Market explorer scope and choices

- Status: Accepted
- Date: 2026-11-14

## Context

Phase 2 (spec sections 2.2, 12 and 13) asks for instrument search, a daily chart, benchmark
comparison, a watchlist, a basic screener, and visible data freshness and gaps. The data
layer has daily bars only: no index levels, no index constituents, no trading calendar, no
corporate actions and no users.

## Decision

**Calculations stay in Python.** Coverage, gap ranges, n-session returns, average volume and
the rebased comparison are computed in `quantlab/data/analytics.py` with `Decimal` and
served by the API. The web app formats and plots; it does not compute a displayed value.
Chart positions are the only place decimal strings become floats.

**Comparison, not benchmark.** There is no index data, so the instrument page compares
against any other instrument in the same snapshot, rebased to 100 on the first common
session and restricted to sessions both have. If an index is ingested as an instrument it
can be chosen like any other. The screen says that no index data is loaded.

**The screener universe is the snapshot.** It screens every instrument with a bar on or
before the reference date and says so. It is not a point-in-time index universe; that needs
effective-dated constituents. Metrics use only bars on or before `as_of`. A metric without
enough history is null and never passes a filter on it.

**One shared watchlist.** No authentication exists, so `watchlist_items` has no owner. Its
PUT and DELETE routes are the only write routes in the API.

**Charts are hand-written SVG.** The spec prefers TradingView Lightweight Charts "or
equivalent" and asks for its licence terms to be verified first. A daily line with a volume
panel did not justify taking on that dependency and its attribution requirement yet.
`lib/chart.ts` holds the geometry as tested pure functions; `components/line-chart.tsx`
renders it with a hover and keyboard readout. Revisit when candlesticks, zoom or indicator
overlays are needed.

**The line is cut at gaps.** Sessions are placed by index, so weekends take no width. Where
weekdays are missing, the line breaks and a dashed marker is drawn, instead of a straight
segment implying data that is not there.

**Default dataset in the UI.** The API has no default dataset. The web app picks the first
dataset that is not `SYNTHETIC_TEST_DATA`, falls back to synthetic only when nothing else
exists, and always shows the choice, its classification, source, retrieval time, latest bar
date and price basis.

**Payload validation with zod.** The web app validates every API payload and treats a
mismatch as an error state rather than rendering partial data.

## Not delivered in this phase

- Technical indicator overlays, sector comparison, corporate-action markers and saved
  screens (spec 2.2 and 12.3). The first needs the feature work of Phase 5 or a decision on
  the chart library; the others need data that does not exist yet.
- Browser end-to-end tests in the repository. The screens were exercised with a scripted
  headless-browser run during development, but that script is not part of CI.

## Consequences

- Staleness is measured against today's date and against the dataset's own latest bar, not
  against an exchange calendar, so a long weekend looks like three stale days.
- Returns on `UNADJUSTED` data are wrong across splits and bonuses. Every screen that shows
  a return states the price basis.
