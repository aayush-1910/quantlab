/**
 * Display formatting. Money and ratios arrive as decimal strings; these helpers work on
 * the digits directly so a displayed value is never the product of float arithmetic.
 */

const MISSING = "n/a";

function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const head = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${head},${digits.slice(-3)}`;
}

/** Rounds a decimal string half-up to `places`. Exact: uses BigInt, not floats. */
export function roundDecimal(value: string, places: number): string {
  const negative = value.startsWith("-");
  const [whole = "0", fraction = ""] = value.replace("-", "").split(".");
  const padded = fraction.padEnd(places + 1, "0");
  let scaled = BigInt(whole + padded.slice(0, places));
  if (Number(padded[places]) >= 5) scaled += 1n;
  const text = scaled.toString().padStart(places + 1, "0");
  const cut = text.length - places;
  const result = places > 0 ? `${text.slice(0, cut)}.${text.slice(cut)}` : text;
  return negative && scaled !== 0n ? `-${result}` : result;
}

/** Price with Indian digit grouping and two decimals, e.g. "1,23,456.50". */
export function formatPrice(value: string | null): string {
  if (value === null) return MISSING;
  const rounded = roundDecimal(value, 2);
  const negative = rounded.startsWith("-");
  const [whole = "0", fraction = "00"] = rounded.replace("-", "").split(".");
  return `${negative ? "-" : ""}${groupIndian(whole)}.${fraction}`;
}

/** Whole number with Indian digit grouping. Decimal strings are rounded half-up. */
export function formatCount(value: number | string | null): string {
  if (value === null) return MISSING;
  const text = typeof value === "number" ? Math.round(value).toString() : roundDecimal(value, 0);
  const negative = text.startsWith("-");
  return `${negative ? "-" : ""}${groupIndian(text.replace("-", ""))}`;
}

/** Ratio string to a signed percentage with two decimals: "0.0525" becomes "+5.25%". */
export function formatPercent(ratio: string | null): string {
  if (ratio === null) return MISSING;
  const percent = roundDecimal(shiftDecimal(ratio, 2), 2);
  return `${percent.startsWith("-") ? "" : "+"}${percent}%`;
}

/** Multiplies a decimal string by 10^places exactly (places may be negative). */
export function shiftDecimal(value: string, places: number): string {
  const negative = value.startsWith("-");
  const [whole = "0", fraction = ""] = value.replace("-", "").split(".");
  let digits = whole + fraction;
  let point = whole.length + places;
  if (point <= 0) {
    digits = "0".repeat(1 - point) + digits;
    point = 1;
  } else if (point > digits.length) {
    digits = digits.padEnd(point, "0");
  }
  const head = digits.slice(0, point).replace(/^0+(?=\d)/, "");
  const tail = digits.slice(point).replace(/0+$/, "");
  const result = tail ? `${head}.${tail}` : head;
  return negative && /[1-9]/.test(result) ? `-${result}` : result;
}

/** A percentage typed by the user ("5.5") as the ratio the API expects ("0.055"). */
export function percentToRatio(input: string): string | null {
  const trimmed = input.trim();
  if (!/^-?\d+(\.\d+)?$/.test(trimmed)) return null;
  return shiftDecimal(trimmed, -2);
}

export function ratioSign(ratio: string | null): "up" | "down" | "flat" {
  if (ratio === null || !/[1-9]/.test(ratio)) return "flat";
  return ratio.startsWith("-") ? "down" : "up";
}

/** Whole days from an ISO date to `now` (UTC). */
export function daysSince(isoDate: string, now: Date): number {
  const then = Date.parse(`${isoDate}T00:00:00Z`);
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.round((today - then) / 86_400_000);
}

/** ISO date `days` before `isoDate`. */
export function daysBefore(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

/** "2026-11-14T07:02:11.123456Z" becomes "2026-11-14 07:02 UTC". */
export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}
