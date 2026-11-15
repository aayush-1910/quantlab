import Link from "next/link";

import { EmptyState, ErrorPanel, NoDatasets, Panel, ProvenanceBar } from "@/components/ui";
import { WatchButton } from "@/components/watch-button";
import { formatCount } from "@/lib/format";
import {
  chooseDataset,
  getCoverage,
  getWatchlist,
  latestPerDataset,
  listSnapshots,
  searchInstruments,
} from "@/lib/market";
import { href, single, type SearchParams } from "@/lib/params";

export const dynamic = "force-dynamic";

export default async function MarketsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const query = single(params, "q");
  const snapshots = await listSnapshots();

  const header = (
    <header>
      <h1 className="text-xl font-semibold">Markets</h1>
      <p className="text-muted mt-1">
        Instruments in one published dataset, with how complete each one&apos;s history is.
      </p>
    </header>
  );
  if (!snapshots.ok) {
    return (
      <div className="space-y-6">
        {header}
        <ErrorPanel what="Datasets" result={snapshots} />
      </div>
    );
  }
  const datasets = latestPerDataset(snapshots.data.snapshots);
  const selected = chooseDataset(datasets, single(params, "dataset"));
  if (!selected) {
    return (
      <div className="space-y-6">
        {header}
        <NoDatasets />
      </div>
    );
  }
  const datasetId = selected.dataset_id;

  const [coverage, watchlist, matches] = await Promise.all([
    getCoverage(datasetId),
    getWatchlist(),
    query ? searchInstruments(query) : Promise.resolve(null),
  ]);

  const watched = new Set(
    watchlist.ok ? watchlist.data.items.map((item) => item.instrument.instrument_id) : [],
  );
  const matchedIds = matches?.ok
    ? new Set(matches.data.instruments.map((i) => i.instrument_id))
    : null;
  const allRows = coverage.ok ? coverage.data.instruments : [];
  const rows = matchedIds
    ? allRows.filter((row) => matchedIds.has(row.instrument.instrument_id))
    : allRows;
  const inDataset = new Set(allRows.map((row) => row.instrument.instrument_id));
  const elsewhere = matches?.ok
    ? matches.data.instruments.filter((i) => !inDataset.has(i.instrument_id))
    : [];
  const watchedRows = allRows.filter((row) => watched.has(row.instrument.instrument_id));

  return (
    <div className="space-y-6">
      {header}
      <ProvenanceBar
        datasets={datasets}
        selected={selected}
        hrefFor={(dataset) => href("/markets", { dataset, q: query })}
        now={new Date()}
      />

      <Panel title="Watchlist" aside="One shared list; there are no user accounts yet">
        {!watchlist.ok ? (
          <div className="p-4">
            <ErrorPanel what="Watchlist" result={watchlist} />
          </div>
        ) : watchlist.data.items.length === 0 ? (
          <EmptyState>Nothing watched. Use the Watch button on any instrument.</EmptyState>
        ) : (
          <ul className="flex flex-wrap gap-2 px-4 py-3">
            {watchlist.data.items.map(({ instrument }) => {
              const row = watchedRows.find(
                (r) => r.instrument.instrument_id === instrument.instrument_id,
              );
              const symbol = row?.instrument.symbol ?? instrument.symbols.at(-1)?.symbol ?? "?";
              return (
                <li key={instrument.instrument_id}>
                  {row ? (
                    <Link
                      href={href(`/markets/${instrument.instrument_id}`, { dataset: datasetId })}
                      className="border-line hover:border-accent block rounded border px-2 py-1 font-mono text-xs"
                    >
                      {symbol}
                    </Link>
                  ) : (
                    <span
                      className="border-line text-muted block rounded border px-2 py-1 font-mono text-xs"
                      title="No bars for this instrument in the selected dataset"
                    >
                      {symbol} (not in this dataset)
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <Panel
        title="Instruments"
        aside={
          coverage.ok
            ? `${rows.length} of ${allRows.length} in ${coverage.data.snapshot.snapshot_id}`
            : undefined
        }
      >
        <form action="/markets" method="get" className="border-line flex gap-2 border-b px-4 py-3">
          <input type="hidden" name="dataset" value={datasetId} />
          <label htmlFor="q" className="sr-only">
            Search by symbol or name
          </label>
          <input
            id="q"
            name="q"
            type="search"
            defaultValue={query ?? ""}
            placeholder="Symbol or name, including former symbols"
            maxLength={100}
            className="border-line bg-base w-full max-w-md rounded border px-2 py-1.5"
          />
          <button type="submit" className="border-line hover:border-accent rounded border px-3">
            Search
          </button>
          {query ? (
            <Link
              href={href("/markets", { dataset: datasetId })}
              className="text-muted hover:text-ink self-center text-xs"
            >
              Clear
            </Link>
          ) : null}
        </form>
        {!coverage.ok ? (
          <div className="p-4">
            <ErrorPanel what="Instrument coverage" result={coverage} />
          </div>
        ) : matches && !matches.ok ? (
          <div className="p-4">
            <ErrorPanel what="Search" result={matches} />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState>
            {query ? `No instrument in this dataset matches "${query}".` : "This dataset is empty."}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="text-muted text-xs">
                <tr className="border-line border-b">
                  <th className="px-4 py-2 font-normal">Symbol</th>
                  <th className="px-4 py-2 font-normal">Name</th>
                  <th className="px-4 py-2 font-normal">First bar</th>
                  <th className="px-4 py-2 font-normal">Last bar</th>
                  <th className="px-4 py-2 text-right font-normal">Bars</th>
                  <th className="px-4 py-2 text-right font-normal">
                    <abbr title="Weekdays with no bar inside the instrument's date range. Includes exchange holidays: no trading calendar is integrated.">
                      Missing weekdays
                    </abbr>
                  </th>
                  <th className="px-4 py-2 font-normal">
                    <span className="sr-only">Watch</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.instrument.instrument_id} className="border-line border-b last:border-b-0">
                    <td className="px-4 py-2 font-mono">
                      <Link
                        href={href(`/markets/${row.instrument.instrument_id}`, {
                          dataset: datasetId,
                        })}
                        className="text-accent hover:underline"
                      >
                        {row.instrument.symbol ?? "(no symbol on last bar date)"}
                      </Link>
                    </td>
                    <td className="px-4 py-2">{row.instrument.name ?? ""}</td>
                    <td className="px-4 py-2 font-mono">{row.first_trading_date}</td>
                    <td className="px-4 py-2 font-mono">
                      {row.last_trading_date}
                      {row.days_behind_dataset > 0 ? (
                        <span className="text-warn">
                          {" "}
                          ({row.days_behind_dataset}d behind dataset)
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">{formatCount(row.bar_count)}</td>
                    <td
                      className={`px-4 py-2 text-right font-mono ${
                        row.missing_weekdays > 0 ? "text-warn" : "text-muted"
                      }`}
                    >
                      {formatCount(row.missing_weekdays)}
                    </td>
                    <td className="px-4 py-2">
                      <WatchButton
                        instrumentId={row.instrument.instrument_id}
                        watched={watched.has(row.instrument.instrument_id)}
                        compact
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {elsewhere.length > 0 ? (
          <p className="border-line text-muted border-t px-4 py-3 text-xs">
            Also matching, but with no bars in this dataset:{" "}
            {elsewhere.map((i) => i.symbols.at(-1)?.symbol ?? i.instrument_id).join(", ")}
          </p>
        ) : null}
      </Panel>
    </div>
  );
}
