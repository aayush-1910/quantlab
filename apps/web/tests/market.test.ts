import { describe, expect, it } from "vitest";

import {
  chooseDataset,
  getBars,
  getScreener,
  latestPerDataset,
  listSnapshots,
  setWatched,
  type SnapshotSummary,
} from "@/lib/market";

const BASE = "http://api.test:8000";

function capture(body: unknown, status = 200) {
  const calls: { url: string; method: string }[] = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    calls.push({ url: String(input), method: init?.method ?? "GET" });
    return new Response(JSON.stringify(body), { status });
  };
  return { calls, transport: { fetchImpl, baseUrl: BASE } };
}

function snapshot(overrides: Partial<SnapshotSummary>): SnapshotSummary {
  return {
    snapshot_id: "a.daily_bars-v1",
    dataset_id: "a.daily_bars",
    version: 1,
    source_id: "a",
    provider_name: "p",
    licence_reference: "l",
    data_classification: "USER_SUPPLIED",
    adjustment_basis: "UNADJUSTED",
    extracted_at: "2026-11-14T07:00:00Z",
    first_trading_date: "2024-01-01",
    last_trading_date: "2024-02-02",
    record_count: 10,
    quarantined_count: 0,
    instrument_ids: ["x"],
    quality_warnings: [],
    ...overrides,
  };
}

const barsPayload = {
  instrument_id: "x",
  frequency: "1d",
  currency: "INR",
  adjustment_basis: "UNADJUSTED",
  snapshot_id: "a.daily_bars-v1",
  dataset_id: "a.daily_bars",
  source_id: "a",
  data_classification: "USER_SUPPLIED",
  data_as_of: "2026-11-14T07:00:00Z",
  requested_start: null,
  requested_end: null,
  count: 1,
  bars: [
    {
      trading_date: "2024-01-02",
      open: "101.000000",
      high: "103.500000",
      low: "100.500000",
      close: "103.000000",
      volume: 1500,
      turnover: null,
    },
  ],
  gaps: [],
  quality_warnings: [],
};

describe("request", () => {
  it("builds versioned URLs and leaves out empty parameters", async () => {
    const { calls, transport } = capture(barsPayload);

    const result = await getBars(
      { instrumentId: "x", datasetId: "a.daily_bars", start: "2024-01-01", end: undefined },
      transport,
    );

    expect(calls[0]?.url).toBe(
      `${BASE}/api/v1/market/bars?instrument_id=x&dataset_id=a.daily_bars&start=2024-01-01`,
    );
    expect(result.ok).toBe(true);
  });

  it("keeps prices as the exact strings the API sent", async () => {
    const result = await getBars({ instrumentId: "x", datasetId: "d" }, capture(barsPayload).transport);

    expect(result.ok && result.data.bars[0]?.high).toBe("103.500000");
    expect(result.ok && result.data.bars[0]?.turnover).toBeNull();
  });

  it("rejects a payload whose numbers are not decimal strings", async () => {
    const tampered = { ...barsPayload, bars: [{ ...barsPayload.bars[0], close: 103 }] };

    const result = await getBars({ instrumentId: "x", datasetId: "d" }, capture(tampered).transport);

    expect(result).toMatchObject({ ok: false, code: "unexpected_payload" });
  });

  it("surfaces the API error envelope", async () => {
    const body = { error: { code: "snapshot_not_resolved", message: "dataset 'd' has no snapshot" } };

    const result = await getScreener("d", {}, capture(body, 404).transport);

    expect(result).toEqual({
      ok: false,
      status: 404,
      code: "snapshot_not_resolved",
      message: "dataset 'd' has no snapshot",
    });
  });

  it("reports an error without an envelope and a network failure distinctly", async () => {
    const http = await listSnapshots(capture("oops", 502).transport);
    const failing: typeof fetch = async () => {
      throw new TypeError("fetch failed");
    };
    const network = await listSnapshots({ fetchImpl: failing, baseUrl: BASE });

    expect(http).toMatchObject({ ok: false, status: 502, code: "http_error" });
    expect(network).toMatchObject({ ok: false, status: null, code: "unreachable" });
  });

  it("uses PUT to watch and DELETE to unwatch, with the ID escaped", async () => {
    const { calls, transport } = capture({ items: [] });

    await setWatched("a/b", true, transport);
    await setWatched("a/b", false, transport);

    expect(calls).toEqual([
      { url: `${BASE}/api/v1/watchlist/a%2Fb`, method: "PUT" },
      { url: `${BASE}/api/v1/watchlist/a%2Fb`, method: "DELETE" },
    ]);
  });
});

describe("dataset selection", () => {
  const synthetic = snapshot({
    dataset_id: "synthetic_fixture.daily_bars",
    snapshot_id: "synthetic_fixture.daily_bars-v1",
    data_classification: "SYNTHETIC_TEST_DATA",
  });
  const real1 = snapshot({ dataset_id: "vendor.daily_bars", snapshot_id: "vendor.daily_bars-v1" });
  const real2 = snapshot({
    dataset_id: "vendor.daily_bars",
    snapshot_id: "vendor.daily_bars-v2",
    version: 2,
  });

  it("keeps only the latest version of each dataset", () => {
    expect(latestPerDataset([real1, synthetic, real2]).map((s) => s.snapshot_id)).toEqual([
      "synthetic_fixture.daily_bars-v1",
      "vendor.daily_bars-v2",
    ]);
  });

  it("honours an explicit choice, including synthetic data", () => {
    expect(chooseDataset([synthetic, real2], "synthetic_fixture.daily_bars")).toBe(synthetic);
  });

  it("never defaults to synthetic data when anything else exists", () => {
    expect(chooseDataset([synthetic, real2], undefined)).toBe(real2);
    expect(chooseDataset([synthetic, real2], "missing")).toBe(real2);
  });

  it("falls back to synthetic data only when it is all there is", () => {
    expect(chooseDataset([synthetic], undefined)).toBe(synthetic);
    expect(chooseDataset([], undefined)).toBeNull();
  });
});
