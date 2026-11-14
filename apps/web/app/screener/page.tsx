import Link from "next/link";

import { EmptyState, ErrorPanel, NoDatasets, Panel, ProvenanceBar } from "@/components/ui";
import { formatCount, formatPercent, formatPrice, percentToRatio, ratioSign } from "@/lib/format";
import { chooseDataset, getScreener, latestPerDataset, listSnapshots } from "@/lib/market";
import { href, single, type SearchParams } from "@/lib/params";

export const dynamic = "force-dynamic";

const SORTS = [
  ["symbol", "Symbol"],
  ["close", "Close"],
  ["volume", "Volume"],
  ["return_1d", "1-session return"],
  ["return_5d", "5-session return"],
  ["return_20d", "20-session return"],
  ["avg_volume_20d", "20-session average volume"],
] as const;

const SIGN_CLASS = { up: "text-ok", down: "text-bad", flat: "text-muted" } as const;

function Field({
  name,
  label,
  defaultValue,
  type = "text",
}: {
  name: string;
  label: string;
  defaultValue: string | undefined;
  type?: "text" | "date";
}) {
  return (
    <label className="block text-xs">
      <span className="text-muted">{label}</span>
      <input
        name={name}
        type={type}
        inputMode={type === "text" ? "decimal" : undefined}
        defaultValue={defaultValue ?? ""}
        className="border-line bg-base mt-1 block w-full rounded border px-2 py-1.5 font-mono"
      />
    </label>
  );
}

function Return({ value }: { value: string | null }) {
  return (
    <td className={`px-4 py-2 text-right font-mono ${SIGN_CLASS[ratioSign(value)]}`}>
      {formatPercent(value)}
    </td>
  );
}

export default async function ScreenerPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const snapshots = await listSnapshots();
  const header = (
    <header>
      <h1 className="text-xl font-semibold">Stock Screener</h1>
      <p className="text-muted mt-1">
        Filters every instrument in one dataset on price, volume and price return, measured as of
        a date you choose. Descriptive only: a screen is not a tested strategy.
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

  const form = {
    as_of: single(params, "as_of"),
    min_close: single(params, "min_close"),
    max_close: single(params, "max_close"),
    min_avg_volume_20d: single(params, "min_avg_volume_20d"),
    min_return_20d_pct: single(params, "min_return_20d_pct"),
    max_return_20d_pct: single(params, "max_return_20d_pct"),
    sort: single(params, "sort") ?? "symbol",
    order: single(params, "order") === "desc" ? "desc" : "asc",
    fresh_only: single(params, "fresh_only") === "1",
  };
  const minReturn = form.min_return_20d_pct ? percentToRatio(form.min_return_20d_pct) : undefined;
  const maxReturn = form.max_return_20d_pct ? percentToRatio(form.max_return_20d_pct) : undefined;
  const invalidPercent = minReturn === null || maxReturn === null;

  const result = invalidPercent
    ? null
    : await getScreener(selected.dataset_id, {
        as_of: form.as_of,
        min_close: form.min_close,
        max_close: form.max_close,
        min_avg_volume_20d: form.min_avg_volume_20d,
        min_return_20d: minReturn ?? undefined,
        max_return_20d: maxReturn ?? undefined,
        include_stale: form.fresh_only ? "false" : undefined,
        sort: form.sort,
        order: form.order,
      });

  return (
    <div className="space-y-6">
      {header}
      <ProvenanceBar
        datasets={datasets}
        selected={selected}
        hrefFor={(dataset) => href("/screener", { dataset })}
        now={new Date()}
      />

      <Panel title="Filters" aside="Empty fields are not applied">
        <form action="/screener" method="get" className="space-y-4 px-4 py-3">
          <input type="hidden" name="dataset" value={selected.dataset_id} />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Field name="as_of" label="As of date" type="date" defaultValue={form.as_of} />
            <Field name="min_close" label="Min close (INR)" defaultValue={form.min_close} />
            <Field name="max_close" label="Max close (INR)" defaultValue={form.max_close} />
            <Field
              name="min_avg_volume_20d"
              label="Min 20-session avg volume (shares)"
              defaultValue={form.min_avg_volume_20d}
            />
            <Field
              name="min_return_20d_pct"
              label="Min 20-session return (%)"
              defaultValue={form.min_return_20d_pct}
            />
            <Field
              name="max_return_20d_pct"
              label="Max 20-session return (%)"
              defaultValue={form.max_return_20d_pct}
            />
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="block text-xs">
              <span className="text-muted">Sort by</span>
              <select
                name="sort"
                defaultValue={form.sort}
                className="border-line bg-base mt-1 block rounded border px-2 py-1.5"
              >
                {SORTS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs">
              <span className="text-muted">Order</span>
              <select
                name="order"
                defaultValue={form.order}
                className="border-line bg-base mt-1 block rounded border px-2 py-1.5"
              >
                <option value="asc">Ascending</option>
                <option value="desc">Descending</option>
              </select>
            </label>
            <label className="flex items-center gap-2 pb-2 text-xs">
              <input type="checkbox" name="fresh_only" value="1" defaultChecked={form.fresh_only} />
              Only instruments with a bar on the reference date
            </label>
            <button type="submit" className="border-accent rounded border px-4 py-1.5">
              Run screen
            </button>
            <Link
              href={href("/screener", { dataset: selected.dataset_id })}
              className="text-muted hover:text-ink pb-2 text-xs"
            >
              Reset
            </Link>
          </div>
        </form>
      </Panel>

      {invalidPercent ? (
        <div role="alert" className="border-bad/40 bg-panel text-bad rounded border px-4 py-3">
          Return filters must be plain numbers in percent, for example 5 or -2.5.
        </div>
      ) : result && !result.ok ? (
        <ErrorPanel what="Screen results" result={result} />
      ) : result ? (
        <Panel
          title="Results"
          aside={
            result.data.reference_date
              ? `${result.data.matched_count} of ${result.data.universe_count} instruments match · measured on ${result.data.reference_date}`
              : undefined
          }
        >
          {result.data.reference_date === null ? (
            <EmptyState>This dataset has no bars on or before {form.as_of}.</EmptyState>
          ) : (
            <>
              <p className="border-line text-muted border-b px-4 py-2 text-xs">
                Universe: every instrument in {result.data.snapshot.snapshot_id} with a bar on or
                before {result.data.reference_date}, not an index membership. Returns are price
                only on the {result.data.snapshot.adjustment_basis} basis, over each
                instrument&apos;s own sessions; n/a means not enough history, and n/a never
                passes a filter.
              </p>
              {result.data.rows.length === 0 ? (
                <EmptyState>No instrument passes these filters.</EmptyState>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="text-muted text-xs">
                      <tr className="border-line border-b">
                        <th className="px-4 py-2 text-left font-normal">Symbol</th>
                        <th className="px-4 py-2 text-left font-normal">Bar date</th>
                        <th className="px-4 py-2 text-right font-normal">
                          Close ({result.data.currency})
                        </th>
                        <th className="px-4 py-2 text-right font-normal">1 session</th>
                        <th className="px-4 py-2 text-right font-normal">5 sessions</th>
                        <th className="px-4 py-2 text-right font-normal">20 sessions</th>
                        <th className="px-4 py-2 text-right font-normal">Volume (shares)</th>
                        <th className="px-4 py-2 text-right font-normal">20-session avg volume</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.data.rows.map((row) => (
                        <tr
                          key={row.instrument.instrument_id}
                          className="border-line border-b last:border-b-0"
                        >
                          <td className="px-4 py-2">
                            <Link
                              href={href(`/markets/${row.instrument.instrument_id}`, {
                                dataset: selected.dataset_id,
                              })}
                              className="text-accent font-mono hover:underline"
                            >
                              {row.instrument.symbol ?? row.instrument.instrument_id}
                            </Link>
                            {row.instrument.name ? (
                              <span className="text-muted"> {row.instrument.name}</span>
                            ) : null}
                          </td>
                          <td className="px-4 py-2 font-mono whitespace-nowrap">
                            {row.bar_date}
                            {row.is_stale ? <span className="text-warn"> stale</span> : null}
                          </td>
                          <td className="px-4 py-2 text-right font-mono">
                            {formatPrice(row.close)}
                          </td>
                          <Return value={row.return_1d} />
                          <Return value={row.return_5d} />
                          <Return value={row.return_20d} />
                          <td className="px-4 py-2 text-right font-mono">
                            {formatCount(row.volume)}
                          </td>
                          <td className="px-4 py-2 text-right font-mono">
                            {formatCount(row.avg_volume_20d)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </Panel>
      ) : null}
    </div>
  );
}
