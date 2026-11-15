import Link from "next/link";

import { LineChart } from "@/components/line-chart";
import { EmptyState, ErrorPanel, NoDatasets, Panel, ProvenanceBar } from "@/components/ui";
import { WatchButton } from "@/components/watch-button";
import { breakIndices } from "@/lib/chart";
import { daysBefore, formatCount, formatPrice, roundDecimal } from "@/lib/format";
import {
  chooseDataset,
  getBars,
  getComparison,
  getCoverage,
  getInstrument,
  getWatchlist,
  latestPerDataset,
  listSnapshots,
} from "@/lib/market";
import { href, single, type SearchParams } from "@/lib/params";

export const dynamic = "force-dynamic";

// Categorical slots 1 and 2 of the chart palette, validated on the panel surface.
const SERIES_1 = "#3987e5";
const SERIES_2 = "#d95926";

const RANGES = [
  { key: "3m", label: "3 months", days: 92 },
  { key: "1y", label: "1 year", days: 366 },
  { key: "all", label: "All", days: null },
] as const;

export default async function InstrumentPage({
  params,
  searchParams,
}: {
  params: Promise<{ instrumentId: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { instrumentId } = await params;
  const query = await searchParams;
  const compareId = single(query, "compare");
  const range = RANGES.find((r) => r.key === single(query, "range")) ?? RANGES[2];

  const [snapshots, instrument, watchlist] = await Promise.all([
    listSnapshots(),
    getInstrument(instrumentId),
    getWatchlist(),
  ]);
  const back = (
    <Link href="/markets" className="text-muted hover:text-ink text-xs">
      Markets
    </Link>
  );
  if (!snapshots.ok || !instrument.ok) {
    return (
      <div className="space-y-6">
        {back}
        <ErrorPanel what="Datasets" result={snapshots} />
        <ErrorPanel what="Instrument" result={instrument} />
      </div>
    );
  }
  const datasets = latestPerDataset(snapshots.data.snapshots);
  const selected = chooseDataset(datasets, single(query, "dataset"));
  if (!selected) {
    return (
      <div className="space-y-6">
        {back}
        <NoDatasets />
      </div>
    );
  }
  const datasetId = selected.dataset_id;
  const start =
    range.days !== null && selected.last_trading_date
      ? daysBefore(selected.last_trading_date, range.days)
      : undefined;

  const [bars, coverage, comparison] = await Promise.all([
    getBars({ instrumentId, datasetId, start }),
    getCoverage(datasetId),
    compareId && compareId !== instrumentId
      ? getComparison({ instrumentId, comparisonInstrumentId: compareId, datasetId, start })
      : Promise.resolve(null),
  ]);

  const symbols = instrument.data.symbols;
  const current = symbols.at(-1);
  const watched = watchlist.ok
    ? watchlist.data.items.some((item) => item.instrument.instrument_id === instrumentId)
    : false;
  const self = (overrides: Record<string, string | undefined>) =>
    href(`/markets/${instrumentId}`, {
      dataset: datasetId,
      range: range.key === "all" ? undefined : range.key,
      compare: compareId,
      ...overrides,
    });
  const others = coverage.ok
    ? coverage.data.instruments.filter((row) => row.instrument.instrument_id !== instrumentId)
    : [];
  const series = bars.ok ? bars.data.bars : [];
  const dates = series.map((bar) => bar.trading_date);
  const latest = series.at(-1);

  return (
    <div className="space-y-6">
      {back}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-mono text-xl font-semibold">{current?.symbol ?? instrumentId}</h1>
          <p className="text-muted mt-1">
            {current?.name ? `${current.name} · ` : ""}
            {instrument.data.exchange} · {instrument.data.instrument_type} · quoted in{" "}
            {instrument.data.currency}
          </p>
        </div>
        <WatchButton instrumentId={instrumentId} watched={watched} />
      </header>

      <ProvenanceBar
        datasets={datasets}
        selected={selected}
        hrefFor={(dataset) => self({ dataset, compare: undefined })}
        now={new Date()}
      />

      <Panel
        title="Daily close and volume"
        aside={
          <span className="flex gap-1">
            {RANGES.map((r) => (
              <Link
                key={r.key}
                href={self({ range: r.key === "all" ? undefined : r.key })}
                aria-current={r.key === range.key ? "true" : undefined}
                className={`rounded border px-2 py-0.5 ${
                  r.key === range.key ? "border-accent text-ink" : "border-line hover:text-ink"
                }`}
              >
                {r.label}
              </Link>
            ))}
          </span>
        }
      >
        {!bars.ok ? (
          <div className="p-4">
            <ErrorPanel what="Bars" result={bars} />
          </div>
        ) : series.length === 0 ? (
          <EmptyState>
            This dataset has no bars for this instrument
            {start ? ` on or after ${start}` : ""}.
          </EmptyState>
        ) : (
          <>
            <LineChart
              title={`${current?.symbol ?? "Instrument"} close`}
              dates={dates}
              series={[
                {
                  key: "close",
                  label: "Close",
                  color: SERIES_1,
                  values: series.map((bar) => Number(bar.close)),
                  display: series.map((bar) => formatPrice(bar.close)),
                },
              ]}
              breaks={[...breakIndices(dates, bars.data.gaps)]}
              yLabel={`Close, ${bars.data.currency} per share, ${bars.data.adjustment_basis} basis. Daily, ${dates[0]} to ${dates.at(-1)}. Dashed lines mark missing weekdays.`}
              fields={[
                { label: "Open", values: series.map((bar) => formatPrice(bar.open)) },
                { label: "High", values: series.map((bar) => formatPrice(bar.high)) },
                { label: "Low", values: series.map((bar) => formatPrice(bar.low)) },
              ]}
              bars={{
                label: "Volume, shares",
                values: series.map((bar) => bar.volume),
                display: series.map((bar) => formatCount(bar.volume)),
              }}
            />
            <dl className="border-line grid grid-cols-2 gap-4 border-t px-4 py-3 md:grid-cols-4">
              <div>
                <dt className="text-muted text-xs">Sessions shown</dt>
                <dd className="font-mono">{formatCount(series.length)}</dd>
              </div>
              <div>
                <dt className="text-muted text-xs">Latest bar</dt>
                <dd className="font-mono">{latest?.trading_date}</dd>
              </div>
              <div>
                <dt className="text-muted text-xs">Latest close ({bars.data.currency})</dt>
                <dd className="font-mono">{formatPrice(latest?.close ?? null)}</dd>
              </div>
              <div>
                <dt className="text-muted text-xs">Missing weekdays</dt>
                <dd className={`font-mono ${bars.data.gaps.length ? "text-warn" : ""}`}>
                  {formatCount(bars.data.gaps.reduce((sum, gap) => sum + gap.missing_weekdays, 0))}
                </dd>
              </div>
            </dl>
          </>
        )}
      </Panel>

      {bars.ok && bars.data.gaps.length > 0 ? (
        <Panel
          title="Gaps in this history"
          aside="Weekdays with no bar. Includes exchange holidays: no trading calendar is integrated"
        >
          <ul className="divide-line divide-y">
            {bars.data.gaps.map((gap) => (
              <li key={gap.start} className="flex justify-between px-4 py-2 font-mono text-xs">
                <span>
                  {gap.start === gap.end ? gap.start : `${gap.start} to ${gap.end}`}
                </span>
                <span className="text-warn">
                  {gap.missing_weekdays} {gap.missing_weekdays === 1 ? "weekday" : "weekdays"}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <Panel
        title="Comparison"
        aside="Against another instrument in this dataset. No index data is loaded"
      >
        <form action={`/markets/${instrumentId}`} method="get" className="flex flex-wrap gap-2 px-4 py-3">
          <input type="hidden" name="dataset" value={datasetId} />
          {range.key !== "all" ? <input type="hidden" name="range" value={range.key} /> : null}
          <label htmlFor="compare" className="text-muted self-center text-xs">
            Compare with
          </label>
          <select
            id="compare"
            name="compare"
            defaultValue={compareId ?? ""}
            className="border-line bg-base rounded border px-2 py-1.5"
          >
            <option value="">None</option>
            {others.map((row) => (
              <option key={row.instrument.instrument_id} value={row.instrument.instrument_id}>
                {row.instrument.symbol ?? row.instrument.instrument_id}
                {row.instrument.name ? ` · ${row.instrument.name}` : ""}
              </option>
            ))}
          </select>
          <button type="submit" className="border-line hover:border-accent rounded border px-3">
            Apply
          </button>
        </form>
        {comparison === null ? null : !comparison.ok ? (
          <div className="px-4 pb-4">
            <ErrorPanel what="Comparison" result={comparison} />
          </div>
        ) : comparison.data.points.length === 0 ? (
          <EmptyState>These two instruments have no session in common in this range.</EmptyState>
        ) : (
          <>
            <LineChart
              title="Rebased close"
              dates={comparison.data.points.map((p) => p.trading_date)}
              series={[
                {
                  key: "base",
                  label: comparison.data.base.symbol ?? "Base",
                  color: SERIES_1,
                  values: comparison.data.points.map((p) => Number(p.base_index)),
                  display: comparison.data.points.map((p) => roundDecimal(p.base_index, 2)),
                },
                {
                  key: "comparison",
                  label: comparison.data.comparison.symbol ?? "Comparison",
                  color: SERIES_2,
                  values: comparison.data.points.map((p) => Number(p.comparison_index)),
                  display: comparison.data.points.map((p) => roundDecimal(p.comparison_index, 2)),
                },
              ]}
              yLabel={`Close rebased to 100 on ${comparison.data.base_date}. Price only (no dividends), ${comparison.data.snapshot.adjustment_basis} basis. Only sessions both instruments have.`}
            />
            {comparison.data.base_only_sessions + comparison.data.comparison_only_sessions > 0 ? (
              <p className="border-line text-warn border-t px-4 py-3 text-xs">
                Left out because only one instrument has a bar:{" "}
                {comparison.data.base_only_sessions} session(s) of{" "}
                {comparison.data.base.symbol} and {comparison.data.comparison_only_sessions} of{" "}
                {comparison.data.comparison.symbol}.
              </p>
            ) : null}
          </>
        )}
      </Panel>

      {series.length > 0 && bars.ok ? (
        <Panel title="Bars" aside={`Most recent ${Math.min(series.length, 20)} of ${series.length} shown`}>
          <div className="overflow-x-auto">
            <table className="w-full text-right font-mono text-xs">
              <thead className="text-muted font-sans">
                <tr className="border-line border-b">
                  <th className="px-4 py-2 text-left font-normal">Date</th>
                  <th className="px-4 py-2 font-normal">Open</th>
                  <th className="px-4 py-2 font-normal">High</th>
                  <th className="px-4 py-2 font-normal">Low</th>
                  <th className="px-4 py-2 font-normal">Close</th>
                  <th className="px-4 py-2 font-normal">Volume (shares)</th>
                  <th className="px-4 py-2 font-normal">Turnover ({bars.data.currency})</th>
                </tr>
              </thead>
              <tbody>
                {series
                  .slice(-20)
                  .reverse()
                  .map((bar) => (
                    <tr key={bar.trading_date} className="border-line border-b last:border-b-0">
                      <td className="px-4 py-1.5 text-left">{bar.trading_date}</td>
                      <td className="px-4 py-1.5">{formatPrice(bar.open)}</td>
                      <td className="px-4 py-1.5">{formatPrice(bar.high)}</td>
                      <td className="px-4 py-1.5">{formatPrice(bar.low)}</td>
                      <td className="px-4 py-1.5">{formatPrice(bar.close)}</td>
                      <td className="px-4 py-1.5">{formatCount(bar.volume)}</td>
                      <td className="px-4 py-1.5">{formatPrice(bar.turnover)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      <Panel title="Symbol history" aside={`Internal ID ${instrument.data.instrument_id}`}>
        <ul className="divide-line divide-y">
          {symbols.map((period) => (
            <li
              key={`${period.source_id}-${period.valid_from}`}
              className="flex flex-wrap justify-between gap-2 px-4 py-2 text-xs"
            >
              <span>
                <span className="font-mono">{period.symbol}</span>
                {period.name ? <span className="text-muted"> · {period.name}</span> : null}
                {period.isin ? <span className="text-muted"> · ISIN {period.isin}</span> : null}
              </span>
              <span className="text-muted font-mono">
                {period.valid_from} to {period.valid_to ?? "present"} · source {period.source_id}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
