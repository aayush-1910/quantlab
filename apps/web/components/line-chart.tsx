"use client";

import { useMemo, useState, type PointerEvent } from "react";

import {
  compactNumber,
  labelIndices,
  linePath,
  nearestIndex,
  niceTicks,
  xPosition,
  yScale,
  type Frame,
} from "@/lib/chart";

export type ChartSeries = {
  key: string;
  label: string;
  color: string;
  /** Plot positions only. `display` carries the exact values shown to the reader. */
  values: number[];
  display: string[];
};

export type ReadoutField = { label: string; values: string[] };

type Props = {
  title: string;
  /** One ISO date per session, oldest first. */
  dates: string[];
  series: ChartSeries[];
  /** Indices whose point must not be joined to the one before it (data gaps). */
  breaks?: number[];
  yLabel: string;
  /** Extra per-session values for the readout, e.g. open/high/low. */
  fields?: ReadoutField[];
  /** Optional second panel of bars on its own scale, e.g. volume. */
  bars?: { label: string; values: number[]; display: string[] };
};

const WIDTH = 880;
const LINE: Frame = { width: WIDTH, height: 300, left: 12, right: 64, top: 12, bottom: 24 };
const BARS: Frame = { width: WIDTH, height: 96, left: 12, right: 64, top: 8, bottom: 20 };

export function LineChart({ title, dates, series, breaks = [], yLabel, fields = [], bars }: Props) {
  const count = dates.length;
  const [hovered, setHovered] = useState<number | null>(null);
  const active = hovered ?? count - 1;

  const geometry = useMemo(() => {
    const all = series.flatMap((s) => s.values);
    const ticks = niceTicks(Math.min(...all), Math.max(...all));
    const toY = yScale(ticks, LINE);
    const breakSet = new Set(breaks);
    const barTicks = bars ? niceTicks(0, Math.max(...bars.values, 1), 2) : [];
    return {
      ticks,
      toY,
      paths: series.map((s) => linePath(s.values, breakSet, LINE, toY)),
      barTicks,
      barY: yScale(barTicks, BARS),
    };
  }, [series, breaks, bars]);

  if (count === 0) return null;

  const track = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * WIDTH;
    setHovered(nearestIndex(x, count, LINE));
  };
  const step = (delta: number) => setHovered(Math.min(count - 1, Math.max(0, active + delta)));

  const activeX = xPosition(active, count, LINE);
  const barWidth = Math.max(1, Math.min(10, ((WIDTH - BARS.left - BARS.right) / count) * 0.7));
  const xLabels = labelIndices(count);

  return (
    <figure className="px-4 py-3">
      <figcaption className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
        <span className="text-muted text-xs">{title}</span>
        <span className="font-mono text-xs" aria-live="polite">
          <span className="text-muted">{hovered === null ? "Latest " : ""}</span>
          {dates[active]}
        </span>
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5 text-xs">
            <svg width="14" height="6" aria-hidden="true">
              <line x1="0" y1="3" x2="14" y2="3" stroke={s.color} strokeWidth="2" />
            </svg>
            <span className="text-muted">{s.label}</span>
            <span className="font-mono">{s.display[active]}</span>
          </span>
        ))}
        {fields.map((field) => (
          <span key={field.label} className="text-xs">
            <span className="text-muted">{field.label} </span>
            <span className="font-mono">{field.values[active]}</span>
          </span>
        ))}
        {bars ? (
          <span className="text-xs">
            <span className="text-muted">{bars.label} </span>
            <span className="font-mono">{bars.display[active]}</span>
          </span>
        ) : null}
      </figcaption>

      <svg
        viewBox={`0 0 ${WIDTH} ${LINE.height}`}
        className="mt-2 h-auto w-full touch-none"
        role="img"
        aria-label={`${title}. ${count} sessions from ${dates[0]} to ${dates[count - 1]}. Use the left and right arrow keys to read values.`}
        tabIndex={0}
        onPointerMove={track}
        onPointerLeave={() => setHovered(null)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") step(-1);
          if (event.key === "ArrowRight") step(1);
          if (event.key === "Escape") setHovered(null);
        }}
      >
        {geometry.ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={LINE.left}
              x2={WIDTH - LINE.right}
              y1={geometry.toY(tick)}
              y2={geometry.toY(tick)}
              stroke="var(--color-line)"
              strokeWidth="1"
            />
            <text
              x={WIDTH - LINE.right + 8}
              y={geometry.toY(tick) + 4}
              fill="var(--color-muted)"
              fontSize="11"
              fontFamily="var(--font-mono)"
            >
              {compactNumber(tick)}
            </text>
          </g>
        ))}
        {breaks.map((index) => {
          const x = (xPosition(index - 1, count, LINE) + xPosition(index, count, LINE)) / 2;
          return (
            <line
              key={index}
              x1={x}
              x2={x}
              y1={LINE.top}
              y2={LINE.height - LINE.bottom}
              stroke="var(--color-warn)"
              strokeWidth="1"
              strokeDasharray="3 4"
            >
              <title>{`No bars between ${dates[index - 1]} and ${dates[index]}`}</title>
            </line>
          );
        })}
        {geometry.paths.map((path, index) => (
          <path
            key={series[index]?.key}
            d={path}
            fill="none"
            stroke={series[index]?.color}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}
        <line
          x1={activeX}
          x2={activeX}
          y1={LINE.top}
          y2={LINE.height - LINE.bottom}
          stroke="var(--color-muted)"
          strokeWidth="1"
          opacity={hovered === null ? 0 : 0.6}
        />
        {series.map((s) => (
          <circle
            key={s.key}
            cx={activeX}
            cy={geometry.toY(s.values[active] ?? 0)}
            r="4"
            fill={s.color}
            stroke="var(--color-panel)"
            strokeWidth="2"
          />
        ))}
        {xLabels.map((index) => (
          <text
            key={index}
            x={xPosition(index, count, LINE)}
            y={LINE.height - 6}
            fill="var(--color-muted)"
            fontSize="11"
            fontFamily="var(--font-mono)"
            textAnchor={index === 0 ? "start" : index === count - 1 ? "end" : "middle"}
          >
            {dates[index]}
          </text>
        ))}
      </svg>
      <p className="text-muted text-[11px]">{yLabel}</p>

      {bars ? (
        <>
          <svg
            viewBox={`0 0 ${WIDTH} ${BARS.height}`}
            className="mt-2 h-auto w-full"
            aria-hidden="true"
          >
            {geometry.barTicks.map((tick) => (
              <g key={tick}>
                <line
                  x1={BARS.left}
                  x2={WIDTH - BARS.right}
                  y1={geometry.barY(tick)}
                  y2={geometry.barY(tick)}
                  stroke="var(--color-line)"
                  strokeWidth="1"
                />
                <text
                  x={WIDTH - BARS.right + 8}
                  y={geometry.barY(tick) + 4}
                  fill="var(--color-muted)"
                  fontSize="11"
                  fontFamily="var(--font-mono)"
                >
                  {compactNumber(tick)}
                </text>
              </g>
            ))}
            {bars.values.map((value, index) => {
              const top = geometry.barY(value);
              const base = geometry.barY(0);
              return (
                <rect
                  key={dates[index]}
                  x={xPosition(index, count, BARS) - barWidth / 2}
                  y={top}
                  width={barWidth}
                  height={Math.max(0, base - top)}
                  fill="var(--color-muted)"
                  opacity={index === active ? 1 : 0.45}
                />
              );
            })}
          </svg>
          <p className="text-muted text-[11px]">{bars.label}</p>
        </>
      ) : null}
    </figure>
  );
}
