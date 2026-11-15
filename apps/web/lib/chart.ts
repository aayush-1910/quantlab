/**
 * Chart geometry: pure functions from numbers to SVG coordinates. Sessions are placed by
 * index, not by calendar date, so weekends take no space; real gaps in the data are
 * passed in as `breaks` and the line is cut there instead of being drawn across them.
 */

export type Frame = { width: number; height: number; left: number; right: number; top: number; bottom: number };

export type Tick = { position: number; value: number };

/** About `target` round-numbered ticks covering [min, max]. */
export function niceTicks(min: number, max: number, target = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) {
    const pad = min === 0 ? 1 : Math.abs(min) * 0.05;
    return niceTicks(min - pad, max + pad, target);
  }
  const rawStep = (max - min) / Math.max(target, 1);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rawStep) ?? rawStep;
  const first = Math.floor(min / step) * step;
  const ticks: number[] = [];
  for (let value = first; value < max + step; value += step) {
    ticks.push(Number(value.toPrecision(12)));
    if (value >= max) break;
  }
  return ticks;
}

export function xPosition(index: number, count: number, frame: Frame): number {
  const span = frame.width - frame.left - frame.right;
  return count <= 1 ? frame.left + span / 2 : frame.left + (index / (count - 1)) * span;
}

export function yScale(ticks: number[], frame: Frame): (value: number) => number {
  const low = ticks[0] ?? 0;
  const high = ticks[ticks.length - 1] ?? 1;
  const span = frame.height - frame.top - frame.bottom;
  return (value) => frame.top + (1 - (value - low) / (high - low || 1)) * span;
}

/**
 * SVG path data for one series, cut into separate sub-paths at each break. `breaks`
 * holds indices whose point must not be joined to the previous point.
 */
export function linePath(
  values: number[],
  breaks: ReadonlySet<number>,
  frame: Frame,
  toY: (value: number) => number,
): string {
  return values
    .map((value, index) => {
      const command = index === 0 || breaks.has(index) ? "M" : "L";
      return `${command}${xPosition(index, values.length, frame).toFixed(2)},${toY(value).toFixed(2)}`;
    })
    .join(" ");
}

/** Indices of the first bar after each gap. Dates and gap bounds are ISO strings. */
export function breakIndices(dates: string[], gaps: { end: string }[]): Set<number> {
  const breaks = new Set<number>();
  for (const gap of gaps) {
    const index = dates.findIndex((date) => date > gap.end);
    if (index > 0) breaks.add(index);
  }
  return breaks;
}

/** Up to `target` evenly spaced indices, always including the first and last. */
export function labelIndices(count: number, target = 6): number[] {
  if (count <= 0) return [];
  if (count <= target) return Array.from({ length: count }, (_, index) => index);
  const indices = new Set<number>();
  for (let step = 0; step < target; step += 1) {
    indices.add(Math.round((step / (target - 1)) * (count - 1)));
  }
  return [...indices].sort((a, b) => a - b);
}

/** Index of the session nearest to a horizontal position in chart coordinates. */
export function nearestIndex(x: number, count: number, frame: Frame): number {
  if (count <= 1) return 0;
  const span = frame.width - frame.left - frame.right;
  const index = Math.round(((x - frame.left) / span) * (count - 1));
  return Math.min(count - 1, Math.max(0, index));
}

/** Compact axis number: 1500 becomes "1.5K", 2500000 becomes "2.5M". */
export function compactNumber(value: number): string {
  const abs = Math.abs(value);
  const trim = (n: number) => n.toFixed(2).replace(/\.?0+$/, "");
  if (abs >= 1e9) return `${trim(value / 1e9)}B`;
  if (abs >= 1e6) return `${trim(value / 1e6)}M`;
  if (abs >= 1e3) return `${trim(value / 1e3)}K`;
  return trim(value);
}
