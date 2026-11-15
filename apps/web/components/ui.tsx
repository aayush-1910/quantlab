import Link from "next/link";
import type { ReactNode } from "react";

import { daysSince, formatTimestamp } from "@/lib/format";
import type { ApiResult, Classification, SnapshotSummary } from "@/lib/market";

export function Panel({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="border-line bg-panel rounded border">
      <div className="border-line flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
        <h2 className="font-medium">{title}</h2>
        {aside ? <div className="text-muted text-xs">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function ErrorPanel({ what, result }: { what: string; result: ApiResult<unknown> }) {
  if (result.ok) return null;
  return (
    <div role="alert" className="border-bad/40 bg-panel rounded border px-4 py-3">
      <p className="text-bad font-medium">{what} could not be loaded</p>
      <p className="text-muted mt-1">
        {result.message}
        {result.status ? ` (HTTP ${result.status}, ${result.code})` : ""}
      </p>
    </div>
  );
}

const CLASSIFICATION_TEXT: Record<Classification, string> = {
  SYNTHETIC_TEST_DATA: "SYNTHETIC TEST DATA",
  USER_SUPPLIED: "User-supplied data",
  LICENSED: "Licensed data",
};

export function ClassificationBadge({ value }: { value: Classification }) {
  const synthetic = value === "SYNTHETIC_TEST_DATA";
  return (
    <span
      className={`rounded border px-1.5 py-0.5 font-mono text-[11px] ${
        synthetic ? "border-warn text-warn" : "border-line text-muted"
      }`}
    >
      {CLASSIFICATION_TEXT[value]}
    </span>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-muted text-xs">{label}</dt>
      <dd className="mt-0.5 font-mono text-xs">{children}</dd>
    </div>
  );
}

/**
 * Where the numbers on a screen come from: dataset, source, retrieval time, latest bar
 * and adjustment basis. Rendered on every market screen (spec sections 2.2 and 12.3).
 */
export function ProvenanceBar({
  datasets,
  selected,
  hrefFor,
  now,
}: {
  datasets: SnapshotSummary[];
  selected: SnapshotSummary;
  hrefFor: (datasetId: string) => string;
  now: Date;
}) {
  const age = selected.last_trading_date ? daysSince(selected.last_trading_date, now) : null;
  const synthetic = selected.data_classification === "SYNTHETIC_TEST_DATA";
  return (
    <section aria-label="Data source" className="border-line bg-panel rounded border">
      {synthetic ? (
        <p className="border-warn/40 text-warn border-b px-4 py-2 text-xs">
          This dataset is generated test data. Instruments and prices are made up and say nothing
          about any real market.
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
        <span className="text-muted text-xs">Dataset</span>
        {datasets.map((dataset) => (
          <Link
            key={dataset.dataset_id}
            href={hrefFor(dataset.dataset_id)}
            aria-current={dataset.dataset_id === selected.dataset_id ? "true" : undefined}
            className={`rounded border px-2 py-0.5 font-mono text-xs ${
              dataset.dataset_id === selected.dataset_id
                ? "border-accent text-ink"
                : "border-line text-muted hover:text-ink"
            }`}
          >
            {dataset.dataset_id}
          </Link>
        ))}
        <ClassificationBadge value={selected.data_classification} />
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 px-4 py-3 md:grid-cols-3 xl:grid-cols-6">
        <Fact label="Snapshot">{selected.snapshot_id}</Fact>
        <Fact label="Source">{selected.source_id}</Fact>
        <Fact label="Retrieved">{formatTimestamp(selected.extracted_at)}</Fact>
        <Fact label="Latest bar">
          {selected.last_trading_date ?? "none"}
          {age !== null ? (
            <span className={age > 7 ? "text-warn" : "text-muted"}>
              {" "}
              ({age} {age === 1 ? "day" : "days"} ago)
            </span>
          ) : null}
        </Fact>
        <Fact label="Frequency">Daily, end of day</Fact>
        <Fact label="Price basis">{selected.adjustment_basis}</Fact>
      </dl>
      {selected.quality_warnings.length > 0 ? (
        <ul className="border-line text-warn space-y-1 border-t px-4 py-3 text-xs">
          {selected.quality_warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="text-muted px-4 py-6">{children}</p>;
}

export function NoDatasets() {
  return (
    <div className="border-line bg-panel rounded border px-4 py-6">
      <p className="font-medium">No dataset has been ingested</p>
      <p className="text-muted mt-1">
        Load data with the ingestion commands in the README, then reload this page. Nothing is
        shown here until it comes from a published snapshot.
      </p>
    </div>
  );
}
