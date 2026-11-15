import { describe, expect, it } from "vitest";

import {
  breakIndices,
  compactNumber,
  labelIndices,
  linePath,
  nearestIndex,
  niceTicks,
  xPosition,
  yScale,
  type Frame,
} from "@/lib/chart";

const FRAME: Frame = { width: 120, height: 110, left: 10, right: 10, top: 5, bottom: 5 };

describe("niceTicks", () => {
  it("covers the data range with round steps", () => {
    expect(niceTicks(101, 124)).toEqual([100, 105, 110, 115, 120, 125]);
    expect(niceTicks(0, 25000, 2)).toEqual([0, 20000, 40000]);
    expect(niceTicks(0.2, 0.9)).toEqual([0.2, 0.4, 0.6, 0.8, 1]);
  });

  it("widens a flat series instead of dividing by zero", () => {
    const ticks = niceTicks(50, 50);
    expect(ticks[0]).toBeLessThan(50);
    expect(ticks.at(-1)).toBeGreaterThan(50);
    expect(niceTicks(0, 0).length).toBeGreaterThan(1);
  });
});

describe("scales", () => {
  it("spreads sessions evenly by index and centres a single one", () => {
    expect(xPosition(0, 5, FRAME)).toBe(10);
    expect(xPosition(2, 5, FRAME)).toBe(60);
    expect(xPosition(4, 5, FRAME)).toBe(110);
    expect(xPosition(0, 1, FRAME)).toBe(60);
  });

  it("maps the top tick to the top of the plot and the bottom tick to the bottom", () => {
    const toY = yScale([100, 150, 200], FRAME);
    expect(toY(200)).toBe(5);
    expect(toY(150)).toBe(55);
    expect(toY(100)).toBe(105);
  });

  it("finds the nearest session to a pointer position, clamped to the ends", () => {
    expect(nearestIndex(10, 5, FRAME)).toBe(0);
    expect(nearestIndex(47, 5, FRAME)).toBe(1);
    expect(nearestIndex(48, 5, FRAME)).toBe(2);
    expect(nearestIndex(-500, 5, FRAME)).toBe(0);
    expect(nearestIndex(500, 5, FRAME)).toBe(4);
    expect(nearestIndex(60, 1, FRAME)).toBe(0);
  });
});

describe("linePath", () => {
  const toY = yScale([0, 100], FRAME);

  it("draws one connected path when there are no gaps", () => {
    expect(linePath([0, 50, 100], new Set(), FRAME, toY)).toBe(
      "M10.00,105.00 L60.00,55.00 L110.00,5.00",
    );
  });

  it("starts a new sub-path at each break so missing data is not drawn over", () => {
    const path = linePath([0, 50, 100, 50, 0], new Set([2]), FRAME, toY);
    expect(path).toBe("M10.00,105.00 L35.00,55.00 M60.00,5.00 L85.00,55.00 L110.00,105.00");
  });
});

describe("breakIndices", () => {
  const dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-10", "2024-01-11"];

  it("marks the first bar after each gap", () => {
    expect([...breakIndices(dates, [{ end: "2024-01-09" }])]).toEqual([3]);
  });

  it("ignores gaps outside the plotted dates", () => {
    expect(breakIndices(dates, [{ end: "2023-12-29" }]).size).toBe(0);
    expect(breakIndices(dates, [{ end: "2024-02-01" }]).size).toBe(0);
    expect(breakIndices([], [{ end: "2024-01-09" }]).size).toBe(0);
  });
});

describe("labels", () => {
  it("always labels the first and last session", () => {
    expect(labelIndices(0)).toEqual([]);
    expect(labelIndices(3)).toEqual([0, 1, 2]);
    expect(labelIndices(101)).toEqual([0, 20, 40, 60, 80, 100]);
  });

  it("abbreviates large axis numbers", () => {
    expect(compactNumber(950)).toBe("950");
    expect(compactNumber(1500)).toBe("1.5K");
    expect(compactNumber(25000)).toBe("25K");
    expect(compactNumber(2_500_000)).toBe("2.5M");
    expect(compactNumber(3_000_000_000)).toBe("3B");
    expect(compactNumber(102.5)).toBe("102.5");
  });
});
