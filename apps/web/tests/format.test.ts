import { describe, expect, it } from "vitest";

import {
  daysBefore,
  daysSince,
  formatCount,
  formatPercent,
  formatPrice,
  formatTimestamp,
  percentToRatio,
  ratioSign,
  roundDecimal,
  shiftDecimal,
} from "@/lib/format";

describe("roundDecimal", () => {
  it.each([
    ["101.500000", 2, "101.50"],
    ["0.125", 2, "0.13"],
    ["0.124999", 2, "0.12"],
    ["99.995", 2, "100.00"],
    ["7", 2, "7.00"],
    ["15500.50", 0, "15501"],
    ["-0.125", 2, "-0.13"],
    ["-0.001", 2, "0.00"],
    // Would be 1.00 with float arithmetic (1.005 is stored as 1.00499...).
    ["1.005", 2, "1.01"],
    ["123456789012345678.995", 2, "123456789012345679.00"],
  ])("rounds %s to %i places as %s", (value, places, expected) => {
    expect(roundDecimal(value, places)).toBe(expected);
  });
});

describe("formatPrice and formatCount", () => {
  it("uses Indian digit grouping", () => {
    expect(formatPrice("123456.5")).toBe("1,23,456.50");
    expect(formatPrice("12345678.126")).toBe("1,23,45,678.13");
    expect(formatPrice("999.000000")).toBe("999.00");
    expect(formatCount(25000)).toBe("25,000");
    expect(formatCount(1234567)).toBe("12,34,567");
    expect(formatCount("15500.00")).toBe("15,500");
    expect(formatCount(0)).toBe("0");
  });

  it("shows missing values as n/a, never as zero", () => {
    expect(formatPrice(null)).toBe("n/a");
    expect(formatCount(null)).toBe("n/a");
    expect(formatPercent(null)).toBe("n/a");
  });
});

describe("percent handling", () => {
  it.each([
    ["0.19230769", "+19.23%"],
    ["-0.20000000", "-20.00%"],
    ["0.00813008", "+0.81%"],
    ["0.00000000", "+0.00%"],
    ["-0.00001", "+0.00%"],
    ["32.33333333", "+3233.33%"],
  ])("formats ratio %s as %s", (ratio, expected) => {
    expect(formatPercent(ratio)).toBe(expected);
  });

  it.each([
    ["5", "0.05"],
    ["5.5", "0.055"],
    ["-2.5", "-0.025"],
    ["100", "1"],
    ["0", "0"],
    ["0.07", "0.0007"],
    [" 12 ", "0.12"],
  ])("converts typed percent %s to ratio %s exactly", (input, expected) => {
    expect(percentToRatio(input)).toBe(expected);
  });

  it("rejects anything that is not a plain number", () => {
    expect(percentToRatio("5%")).toBeNull();
    expect(percentToRatio("abc")).toBeNull();
    expect(percentToRatio("1e3")).toBeNull();
    expect(percentToRatio("")).toBeNull();
  });

  it("shifts the decimal point both ways", () => {
    expect(shiftDecimal("0.0525", 2)).toBe("5.25");
    expect(shiftDecimal("1.5", 3)).toBe("1500");
    expect(shiftDecimal("-12.5", -1)).toBe("-1.25");
    expect(shiftDecimal("0.000", 2)).toBe("0");
  });

  it("classifies the sign of a ratio", () => {
    expect(ratioSign("0.01")).toBe("up");
    expect(ratioSign("-0.01")).toBe("down");
    expect(ratioSign("0.00000000")).toBe("flat");
    expect(ratioSign("-0.00000000")).toBe("flat");
    expect(ratioSign(null)).toBe("flat");
  });
});

describe("dates", () => {
  it("counts whole days and steps back across month and year ends", () => {
    const now = new Date("2026-11-14T18:30:00Z");
    expect(daysSince("2026-11-14", now)).toBe(0);
    expect(daysSince("2026-11-13", now)).toBe(1);
    expect(daysSince("2024-03-29", now)).toBe(960);
    expect(daysBefore("2024-03-29", 92)).toBe("2023-12-28");
    expect(daysBefore("2024-03-01", 1)).toBe("2024-02-29");
  });

  it("formats timestamps in UTC and labels them", () => {
    expect(formatTimestamp("2026-11-14T07:02:11.123456Z")).toBe("2026-11-14 07:02 UTC");
    expect(formatTimestamp("2026-11-14T12:32:11+05:30")).toBe("2026-11-14 07:02 UTC");
    expect(formatTimestamp("not a date")).toBe("not a date");
  });
});
