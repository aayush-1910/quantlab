/**
 * Server-side client for the QUANTLAB API. Import only from server components or
 * route handlers: API_BASE_URL is a server environment variable and is never
 * shipped to the browser.
 */

export type ApiHealth = {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  executionMode: string;
};

export type HealthResult =
  | { reachable: true; health: ApiHealth; checkedAt: string }
  | { reachable: false; reason: string; checkedAt: string };

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const HEALTH_TIMEOUT_MS = 3000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Validates the health payload instead of trusting its shape. Returns null if invalid. */
export function parseHealth(payload: unknown): ApiHealth | null {
  if (!isRecord(payload)) return null;
  const { status, service, version, environment, execution_mode } = payload;
  if (
    status !== "ok" ||
    typeof service !== "string" ||
    typeof version !== "string" ||
    typeof environment !== "string" ||
    typeof execution_mode !== "string"
  ) {
    return null;
  }
  return { status, service, version, environment, executionMode: execution_mode };
}

export async function fetchHealth(
  fetchImpl: typeof fetch = fetch,
  baseUrl: string = process.env.API_BASE_URL ?? DEFAULT_API_BASE_URL,
): Promise<HealthResult> {
  const checkedAt = new Date().toISOString();
  try {
    const response = await fetchImpl(new URL("/api/v1/health", baseUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
    });
    if (!response.ok) {
      return { reachable: false, reason: `API responded with HTTP ${response.status}`, checkedAt };
    }
    const health = parseHealth(await response.json());
    if (health === null) {
      return { reachable: false, reason: "API returned an unexpected health payload", checkedAt };
    }
    return { reachable: true, health, checkedAt };
  } catch {
    return { reachable: false, reason: "API could not be reached", checkedAt };
  }
}
