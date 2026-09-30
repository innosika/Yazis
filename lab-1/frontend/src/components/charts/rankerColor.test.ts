import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { RANKER_COLOR, RANKER_KEYS, rankerColor, rankerOrder } from "./rankerColor";

const css = readFileSync(resolve(__dirname, "../../styles/theme.css"), "utf8");

describe("ranker colours", () => {
  it("match the --ranker-* tokens declared in theme.css exactly", () => {
    const declared = new Set([...css.matchAll(/^\s*--ranker-([a-z0-9-]+):/gm)].map((m) => (m[1] ?? "").replace(/-/g, "_")));
    expect(declared).toEqual(new Set(RANKER_KEYS));
  });
  it("expose every token through @theme inline", () => {
    for (const key of RANKER_KEYS) {
      expect(css).toContain(`--color-ranker-${key.replace(/_/g, "-")}: var(--ranker-${key.replace(/_/g, "-")})`);
      expect(RANKER_COLOR[key]).toBe(`var(--ranker-${key.replace(/_/g, "-")})`);
    }
  });
  it("fall back for unknown rankers and order the vector family first", () => {
    expect(rankerColor("mystery")).toBe("var(--text-tertiary)");
    expect(["hybrid", "vector_idf", "vector", "zzz"].sort(rankerOrder)).toEqual(["vector", "vector_idf", "hybrid", "zzz"]);
  });
});
