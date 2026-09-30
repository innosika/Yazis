import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { ApiError, query, request } from "./client";

const respond = (status: number, body: unknown) =>
  vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })));

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("builds query strings and skips undefined", () => {
    expect(query({ a: 1, b: "x", c: undefined, d: null, e: false })).toBe("?a=1&b=x&e=false");
    expect(query({})).toBe("");
  });

  it("reads the project's error envelope", async () => {
    vi.stubGlobal("fetch", respond(404, { error: { code: 404, message: "run 9 not found" } }));
    await expect(request("/x", z.unknown())).rejects.toMatchObject({ status: 404, message: "run 9 not found" });
  });

  it("reads FastAPI's detail envelope, string and array forms", async () => {
    vi.stubGlobal("fetch", respond(409, { detail: "pool not built" }));
    await expect(request("/x", z.unknown())).rejects.toMatchObject({ message: "pool not built" });
    vi.stubGlobal("fetch", respond(422, { detail: [{ loc: ["body", "count"], msg: "must be positive" }] }));
    await expect(request("/x", z.unknown())).rejects.toMatchObject({ message: "body.count: must be positive" });
  });

  it("turns a shape mismatch into an ApiError", async () => {
    vi.stubGlobal("fetch", respond(200, { wrong: true }));
    const error = await request("/x", z.object({ right: z.boolean() })).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toMatch(/expected shape/);
  });
});
