import { describe, expect, it } from "vitest";

import { fetchHealth, parseHealth } from "@/lib/api";
import { NAV_ITEMS } from "@/lib/navigation";

const validPayload = {
  status: "ok",
  service: "QUANTLAB",
  version: "0.0.1",
  environment: "development",
  execution_mode: "RESEARCH_ONLY",
};

function respondWith(body: unknown, status = 200): typeof fetch {
  return async () => new Response(JSON.stringify(body), { status });
}

describe("parseHealth", () => {
  it("maps a valid payload", () => {
    expect(parseHealth(validPayload)).toEqual({
      status: "ok",
      service: "QUANTLAB",
      version: "0.0.1",
      environment: "development",
      executionMode: "RESEARCH_ONLY",
    });
  });

  it.each([null, "ok", {}, { ...validPayload, status: "down" }, { ...validPayload, version: 1 }])(
    "rejects malformed payload %j",
    (payload) => {
      expect(parseHealth(payload)).toBeNull();
    },
  );
});

describe("fetchHealth", () => {
  it("requests the versioned health route on the configured base URL", async () => {
    let requested = "";
    const fetchImpl: typeof fetch = async (input) => {
      requested = String(input);
      return new Response(JSON.stringify(validPayload));
    };

    const result = await fetchHealth(fetchImpl, "http://api.test:8000");

    expect(requested).toBe("http://api.test:8000/api/v1/health");
    expect(result.reachable).toBe(true);
  });

  it("reports an HTTP error as unreachable", async () => {
    const result = await fetchHealth(respondWith({}, 503), "http://api.test");

    expect(result).toMatchObject({ reachable: false, reason: "API responded with HTTP 503" });
  });

  it("reports an unexpected payload as unreachable rather than showing it", async () => {
    const result = await fetchHealth(respondWith({ status: "ok" }), "http://api.test");

    expect(result).toMatchObject({ reachable: false });
  });

  it("reports a network failure as unreachable", async () => {
    const failing: typeof fetch = async () => {
      throw new TypeError("fetch failed");
    };

    const result = await fetchHealth(failing, "http://api.test");

    expect(result).toMatchObject({ reachable: false, reason: "API could not be reached" });
  });
});

describe("navigation", () => {
  it("does not expose an Execution entry", () => {
    expect(NAV_ITEMS.some((item) => /execution/i.test(item.label))).toBe(false);
  });

  it("links only to implemented screens", () => {
    expect(NAV_ITEMS.filter((item) => item.href).map((item) => item.href)).toEqual(["/"]);
  });
});
