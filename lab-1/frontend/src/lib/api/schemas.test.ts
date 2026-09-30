import { describe, expect, it } from "vitest";
import { runDetailSchema } from "./eval";
import { searchResponseSchema } from "./search";

const SEARCH_FIXTURE = {
  query: "vector space model",
  ranker: "vector_prf",
  hits: [
    {
      document_id: 24,
      title: "Vector space model - Wikipedia",
      url: "https://en.wikipedia.org/wiki/Vector_space_model",
      snippet: "…by this model are element-wise nonnegative…",
      rank: 0.4847,
      date: "2004-12-08",
      matched_lemmas: ["vector", "space", "model"],
      highlights: [{ start: 9, end: 14, lemma: "model" }],
      source_domain: "en.wikipedia.org",
      token_count: 760,
      detail: { scalar_product: 0.83, document_norm: 1, query_norm: 1.73 },
      snippet_is_query_biased: true,
    },
  ],
  total_candidates: 149,
  query_lemmas: ["vector", "space", "model"],
  unknown_lemmas: [],
  filters_applied: false,
  duration_ms: 853.3,
  stage_timings_ms: { parse: 10 },
  document_count: 208,
  term_count: 44054,
  index_version: 4,
};

describe("search response schema", () => {
  it("parses the real wire shape", () => {
    const parsed = searchResponseSchema.parse(SEARCH_FIXTURE);
    expect(parsed.hits[0]?.rank).toBe(0.4847);
    expect(parsed.hits[0]?.matched_lemmas).toEqual(["vector", "space", "model"]);
  });
  it("accepts ranker keys it has never seen", () => {
    expect(searchResponseSchema.parse({ ...SEARCH_FIXTURE, ranker: "something_new" }).ranker).toBe("something_new");
  });
  it("defaults missing highlight arrays", () => {
    const hit = { ...SEARCH_FIXTURE.hits[0] } as Record<string, unknown>;
    delete hit.highlights;
    const parsed = searchResponseSchema.parse({ ...SEARCH_FIXTURE, hits: [hit] });
    expect(parsed.hits[0]?.highlights).toEqual([]);
  });
});

describe("run detail schema", () => {
  it("tolerates absent optional fields", () => {
    const parsed = runDetailSchema.parse({
      id: 1,
      collection_id: 1,
      qrel_set_id: 1,
      ranker: "vector",
      top_k: 100,
      status: "done",
      index_version: 4,
    });
    expect(parsed.aggregate).toEqual([]);
    expect(parsed.caveats).toEqual([]);
    expect(parsed.params_snapshot).toEqual({});
  });
});
