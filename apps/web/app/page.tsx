import Link from "next/link";

import { ClassificationBadge } from "@/components/ui";
import { fetchHealth } from "@/lib/api";
import { daysSince, formatCount, formatTimestamp } from "@/lib/format";
import { getWatchlist, latestPerDataset, listSnapshots } from "@/lib/market";

// Rendered per request so system status is never a build-time snapshot.
export const dynamic = "force-dynamic";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-line flex justify-between gap-4 border-t py-2 first:border-t-0">
      <dt className="text-muted">{label}</dt>
      <dd className="font-mono">{value}</dd>
    </div>
  );
}

export default async function OverviewPage() {
  const [result, snapshots, watchlist] = await Promise.all([
    fetchHealth(),
    listSnapshots(),
    getWatchlist(),
  ]);
  const datasets = snapshots.ok ? latestPerDataset(snapshots.data.snapshots) : [];
  const now = new Date();

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-muted mt-1">
          Data foundation and market explorer. No research, backtesting or trading modules exist
          yet.
        </p>
      </header>

      <section aria-labelledby="system-health" className="border-line bg-panel rounded border">
        <div className="border-line flex items-center justify-between border-b px-4 py-3">
          <h2 id="system-health" className="font-medium">
            System health
          </h2>
          <span className={result.reachable ? "text-ok" : "text-bad"}>
            {result.reachable ? "API reachable" : "API unreachable"}
          </span>
        </div>
        <dl className="px-4 py-1">
          {result.reachable ? (
            <>
              <Row label="Service" value={result.health.service} />
              <Row label="API version" value={result.health.version} />
              <Row label="Environment" value={result.health.environment} />
              <Row label="Execution mode" value={result.health.executionMode} />
            </>
          ) : (
            <Row label="Reason" value={result.reason} />
          )}
          <Row label="Checked at (UTC)" value={result.checkedAt} />
        </dl>
        <p className="text-muted border-line border-t px-4 py-3 text-xs">
          Liveness of the API process only. Database and data-provider status are not shown
          here yet.
        </p>
      </section>

      <section aria-labelledby="data-freshness" className="border-line bg-panel rounded border">
        <h2 id="data-freshness" className="border-line border-b px-4 py-3 font-medium">
          Data freshness
        </h2>
        {!snapshots.ok ? (
          <p className="text-bad px-4 py-3">Datasets could not be loaded: {snapshots.message}</p>
        ) : datasets.length === 0 ? (
          <p className="text-muted px-4 py-3">No dataset has been ingested.</p>
        ) : (
          <ul className="divide-line divide-y">
            {datasets.map((dataset) => {
              const age = dataset.last_trading_date
                ? daysSince(dataset.last_trading_date, now)
                : null;
              return (
                <li key={dataset.dataset_id} className="space-y-1 px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/markets?dataset=${encodeURIComponent(dataset.dataset_id)}`}
                      className="text-accent font-mono hover:underline"
                    >
                      {dataset.dataset_id}
                    </Link>
                    <ClassificationBadge value={dataset.data_classification} />
                  </div>
                  <p className="text-muted font-mono text-xs">
                    {formatCount(dataset.instrument_ids.length)} instruments ·{" "}
                    {formatCount(dataset.record_count)} daily bars ·{" "}
                    {formatCount(dataset.quarantined_count)} quarantined · latest bar{" "}
                    {dataset.last_trading_date ?? "none"}
                    {age !== null ? ` (${age} days ago)` : ""} · retrieved{" "}
                    {formatTimestamp(dataset.extracted_at)}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="watchlist" className="border-line bg-panel rounded border">
        <h2 id="watchlist" className="border-line border-b px-4 py-3 font-medium">
          Watchlist
        </h2>
        {!watchlist.ok ? (
          <p className="text-bad px-4 py-3">Watchlist could not be loaded: {watchlist.message}</p>
        ) : watchlist.data.items.length === 0 ? (
          <p className="text-muted px-4 py-3">Nothing watched yet.</p>
        ) : (
          <ul className="flex flex-wrap gap-2 px-4 py-3">
            {watchlist.data.items.map(({ instrument }) => (
              <li key={instrument.instrument_id}>
                <Link
                  href={`/markets/${instrument.instrument_id}`}
                  className="border-line hover:border-accent block rounded border px-2 py-1 font-mono text-xs"
                >
                  {instrument.symbols.at(-1)?.symbol ?? instrument.instrument_id}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="not-built" className="border-line bg-panel rounded border">
        <h2 id="not-built" className="border-line border-b px-4 py-3 font-medium">
          Not available yet
        </h2>
        <p className="text-muted px-4 py-3">
          Recent experiments and the paper portfolio summary arrive with their phases. Nothing
          is shown here until it is backed by real, sourced data.
        </p>
      </section>
    </div>
  );
}
