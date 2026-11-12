import { fetchHealth } from "@/lib/api";

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
  const result = await fetchHealth();

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-muted mt-1">
          Foundation build. No market data is loaded and no research modules exist yet.
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
          Liveness of the API process only. Database and data-provider status are not checked
          yet.
        </p>
      </section>

      <section aria-labelledby="not-built" className="border-line bg-panel rounded border">
        <h2 id="not-built" className="border-line border-b px-4 py-3 font-medium">
          Not available yet
        </h2>
        <p className="text-muted px-4 py-3">
          Market snapshot, watchlists, recent experiments, data freshness and the paper
          portfolio summary arrive with their phases. Nothing is shown here until it is backed
          by real, sourced data.
        </p>
      </section>
    </div>
  );
}
