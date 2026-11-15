/**
 * Server-side client for the market-data routes of the QUANTLAB API. Import only from
 * server components and server actions: API_BASE_URL never reaches the browser.
 *
 * Every payload is validated before use. Prices, turnover, returns and index values
 * arrive as decimal strings and stay strings; they are converted to numbers only to
 * position marks on a chart, never to compute a displayed value.
 */

import { z } from "zod";

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const TIMEOUT_MS = 10_000;

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number | null; code: string; message: string };

const errorEnvelope = z.object({
  error: z.object({ code: z.string(), message: z.string() }),
});

const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

const classification = z.enum(["SYNTHETIC_TEST_DATA", "USER_SUPPLIED", "LICENSED"]);

const symbolPeriod = z.object({
  symbol: z.string(),
  name: z.string().nullable(),
  isin: z.string().nullable(),
  valid_from: isoDate,
  valid_to: isoDate.nullable(),
  source_id: z.string(),
});

const instrument = z.object({
  instrument_id: z.string(),
  exchange: z.string(),
  instrument_type: z.string(),
  currency: z.string(),
  symbols: z.array(symbolPeriod),
});

const snapshotContext = z.object({
  snapshot_id: z.string(),
  dataset_id: z.string(),
  source_id: z.string(),
  data_classification: classification,
  adjustment_basis: z.string(),
  data_as_of: z.string(),
  first_trading_date: isoDate.nullable(),
  last_trading_date: isoDate.nullable(),
  quality_warnings: z.array(z.string()),
});

const label = z.object({
  instrument_id: z.string(),
  symbol: z.string().nullable(),
  name: z.string().nullable(),
  symbol_as_of: isoDate,
});

const bar = z.object({
  trading_date: isoDate,
  open: decimal,
  high: decimal,
  low: decimal,
  close: decimal,
  volume: z.number().int().nonnegative(),
  turnover: decimal.nullable(),
});

const gap = z.object({ start: isoDate, end: isoDate, missing_weekdays: z.number().int() });

const schemas = {
  snapshots: z.object({
    snapshots: z.array(
      z.object({
        snapshot_id: z.string(),
        dataset_id: z.string(),
        version: z.number().int(),
        source_id: z.string(),
        provider_name: z.string(),
        licence_reference: z.string(),
        data_classification: classification,
        adjustment_basis: z.string(),
        extracted_at: z.string(),
        first_trading_date: isoDate.nullable(),
        last_trading_date: isoDate.nullable(),
        record_count: z.number().int(),
        quarantined_count: z.number().int(),
        instrument_ids: z.array(z.string()),
        quality_warnings: z.array(z.string()),
      }),
    ),
  }),
  coverage: z.object({
    snapshot: snapshotContext,
    instruments: z.array(
      z.object({
        instrument: label,
        first_trading_date: isoDate,
        last_trading_date: isoDate,
        bar_count: z.number().int(),
        missing_weekdays: z.number().int(),
        days_behind_dataset: z.number().int(),
      }),
    ),
  }),
  instrumentList: z.object({ instruments: z.array(instrument) }),
  instrument,
  bars: z.object({
    instrument_id: z.string(),
    frequency: z.literal("1d"),
    currency: z.string(),
    adjustment_basis: z.string(),
    snapshot_id: z.string(),
    dataset_id: z.string(),
    source_id: z.string(),
    data_classification: classification,
    data_as_of: z.string(),
    count: z.number().int(),
    bars: z.array(bar),
    gaps: z.array(gap),
    quality_warnings: z.array(z.string()),
  }),
  comparison: z.object({
    snapshot: snapshotContext,
    base: label,
    comparison: label,
    base_date: isoDate.nullable(),
    base_only_sessions: z.number().int(),
    comparison_only_sessions: z.number().int(),
    points: z.array(
      z.object({ trading_date: isoDate, base_index: decimal, comparison_index: decimal }),
    ),
  }),
  screener: z.object({
    snapshot: snapshotContext,
    currency: z.string(),
    requested_as_of: isoDate.nullable(),
    reference_date: isoDate.nullable(),
    universe: z.string(),
    universe_count: z.number().int(),
    matched_count: z.number().int(),
    rows: z.array(
      z.object({
        instrument: label,
        bar_date: isoDate,
        is_stale: z.boolean(),
        sessions_available: z.number().int(),
        close: decimal,
        volume: z.number().int(),
        return_1d: decimal.nullable(),
        return_5d: decimal.nullable(),
        return_20d: decimal.nullable(),
        avg_volume_20d: decimal.nullable(),
      }),
    ),
  }),
  watchlist: z.object({
    items: z.array(z.object({ instrument, added_at: z.string() })),
  }),
};

export type Classification = z.infer<typeof classification>;
export type SnapshotContext = z.infer<typeof snapshotContext>;
export type SnapshotSummary = z.infer<typeof schemas.snapshots>["snapshots"][number];
export type Coverage = z.infer<typeof schemas.coverage>;
export type CoverageRow = Coverage["instruments"][number];
export type Instrument = z.infer<typeof instrument>;
export type Bars = z.infer<typeof schemas.bars>;
export type Bar = z.infer<typeof bar>;
export type Gap = z.infer<typeof gap>;
export type Comparison = z.infer<typeof schemas.comparison>;
export type Screener = z.infer<typeof schemas.screener>;
export type ScreenerRow = Screener["rows"][number];
export type Watchlist = z.infer<typeof schemas.watchlist>;

type Params = Record<string, string | undefined>;

export type Transport = { fetchImpl?: typeof fetch; baseUrl?: string };

export async function request<S extends z.ZodType>(
  schema: S,
  path: string,
  params: Params = {},
  method: "GET" | "PUT" | "DELETE" = "GET",
  transport: Transport = {},
): Promise<ApiResult<z.infer<S>>> {
  const fetchImpl = transport.fetchImpl ?? fetch;
  const url = new URL(path, transport.baseUrl ?? process.env.API_BASE_URL ?? DEFAULT_API_BASE_URL);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") url.searchParams.set(key, value);
  }
  let response: Response;
  let payload: unknown;
  try {
    response = await fetchImpl(url, {
      method,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    payload = await response.json();
  } catch {
    return { ok: false, status: null, code: "unreachable", message: "API could not be reached" };
  }
  if (!response.ok) {
    const envelope = errorEnvelope.safeParse(payload);
    return envelope.success
      ? { ok: false, status: response.status, ...envelope.data.error }
      : {
          ok: false,
          status: response.status,
          code: "http_error",
          message: `API responded with HTTP ${response.status}`,
        };
  }
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    return {
      ok: false,
      status: response.status,
      code: "unexpected_payload",
      message: "API returned a payload this app does not understand",
    };
  }
  return { ok: true, data: parsed.data };
}

const v1 = (path: string) => `/api/v1${path}`;
const segment = encodeURIComponent;

export const listSnapshots = (t?: Transport) =>
  request(schemas.snapshots, v1("/datasets/snapshots"), {}, "GET", t);

export const getCoverage = (datasetId: string, t?: Transport) =>
  request(schemas.coverage, v1("/market/coverage"), { dataset_id: datasetId }, "GET", t);

export const searchInstruments = (q: string, t?: Transport) =>
  request(schemas.instrumentList, v1("/instruments"), { q, limit: "200" }, "GET", t);

export const getInstrument = (instrumentId: string, t?: Transport) =>
  request(schemas.instrument, v1(`/instruments/${segment(instrumentId)}`), {}, "GET", t);

export const getBars = (
  query: { instrumentId: string; datasetId: string; start?: string; end?: string },
  t?: Transport,
) =>
  request(
    schemas.bars,
    v1("/market/bars"),
    {
      instrument_id: query.instrumentId,
      dataset_id: query.datasetId,
      start: query.start,
      end: query.end,
    },
    "GET",
    t,
  );

export const getComparison = (
  query: {
    instrumentId: string;
    comparisonInstrumentId: string;
    datasetId: string;
    start?: string;
  },
  t?: Transport,
) =>
  request(
    schemas.comparison,
    v1("/market/compare"),
    {
      instrument_id: query.instrumentId,
      comparison_instrument_id: query.comparisonInstrumentId,
      dataset_id: query.datasetId,
      start: query.start,
    },
    "GET",
    t,
  );

export const getScreener = (datasetId: string, filters: Params, t?: Transport) =>
  request(schemas.screener, v1("/market/screener"), { ...filters, dataset_id: datasetId }, "GET", t);

export const getWatchlist = (t?: Transport) =>
  request(schemas.watchlist, v1("/watchlist"), {}, "GET", t);

export const setWatched = (instrumentId: string, watched: boolean, t?: Transport) =>
  request(
    schemas.watchlist,
    v1(`/watchlist/${segment(instrumentId)}`),
    {},
    watched ? "PUT" : "DELETE",
    t,
  );

/** Latest snapshot of each dataset, in the API's order (dataset ID ascending). */
export function latestPerDataset(snapshots: SnapshotSummary[]): SnapshotSummary[] {
  const latest = new Map<string, SnapshotSummary>();
  for (const snapshot of snapshots) {
    const current = latest.get(snapshot.dataset_id);
    if (!current || snapshot.version > current.version) latest.set(snapshot.dataset_id, snapshot);
  }
  return [...latest.values()].sort((a, b) => a.dataset_id.localeCompare(b.dataset_id));
}

/**
 * The dataset a screen shows: the requested one if it exists, otherwise the first dataset
 * that is not synthetic test data, otherwise the first. The choice is always displayed.
 */
export function chooseDataset(
  datasets: SnapshotSummary[],
  requested: string | undefined,
): SnapshotSummary | null {
  return (
    datasets.find((d) => d.dataset_id === requested) ??
    datasets.find((d) => d.data_classification !== "SYNTHETIC_TEST_DATA") ??
    datasets[0] ??
    null
  );
}
