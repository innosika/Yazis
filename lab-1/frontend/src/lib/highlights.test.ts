import { describe, expect, it } from "vitest";
import { normaliseRanges } from "./highlights";

describe("normaliseRanges", () => {
  it("sorts, merges overlaps and clips to the text", () => {
    const ranges = normaliseRanges(
      [
        { start: 10, end: 15, lemma: "b" },
        { start: 2, end: 6, lemma: "a" },
        { start: 5, end: 8, lemma: "c" },
        { start: 40, end: 60, lemma: "d" },
        { start: -3, end: 1, lemma: "e" },
      ],
      50,
    );
    expect(ranges.map((r) => [r.start, r.end])).toEqual([
      [0, 1],
      [2, 8],
      [10, 15],
      [40, 50],
    ]);
    expect(ranges[1]?.lemma).toBe("a, c");
  });
  it("drops empty ranges", () => {
    expect(normaliseRanges([{ start: 5, end: 5, lemma: "x" }], 10)).toEqual([]);
  });
});
