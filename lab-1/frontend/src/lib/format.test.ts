import { describe, expect, it } from "vitest";
import { fmtBytes, fmtDelta, fmtMetric, fmtMs, fmtP, fmtPct, fmtTime } from "./format";

describe("format helpers", () => {
  it("formats durations by magnitude", () => {
    expect(fmtMs(0.5)).toMatch(/µs/);
    expect(fmtMs(12)).toMatch(/ms/);
    expect(fmtMs(1500)).toMatch(/s$/);
  });
  it("formats bytes", () => {
    expect(fmtBytes(0)).toBe("0 B");
    expect(fmtBytes(1536)).toMatch(/KB/);
    expect(fmtBytes(2 ** 20)).toMatch(/MB/);
  });
  it("renders missing values as a dash", () => {
    expect(fmtMetric(null)).toBe("—");
    expect(fmtMetric(undefined)).toBe("—");
    expect(fmtTime("not a date")).toBe("—");
    expect(fmtPct(null)).toBe("—");
  });
  it("signs deltas and floors tiny p-values", () => {
    expect(fmtDelta(0.1805)).toBe("+0.1805");
    expect(fmtDelta(-0.5, 2)).toBe("-0.50");
    expect(fmtP(0.00001)).toBe("<0.0001");
    expect(fmtP(0.0312)).toBe("0.0312");
  });
});
