/**
 * Typed HTTP client.
 *
 * Every response is validated with Zod at the boundary rather than trusted via a cast, so
 * a backend contract change surfaces as a clear error here instead of an
 * `undefined is not a function` deep inside a chart component.
 */
import { z } from "zod";

const BASE: string = import.meta.env.VITE_API_BASE ?? "/api";

/** Zod schema whose *input* may differ from its output (defaults, coercions). */
export type Schema<T> = z.ZodType<T, z.ZodTypeDef, unknown>;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True for "nothing here yet" answers the UI should render as an empty state. */
  get isNotFound(): boolean {
    return this.status === 404;
  }
}

// The API wraps errors as {error:{code,message,details}}; FastAPI's own validation
// answers as {detail: string | issue[]}. Both are accepted.
const errorEnvelope = z.union([
  z.object({
    error: z.object({
      code: z.number(),
      message: z.string(),
      details: z.unknown().optional(),
    }),
  }),
  z.object({
    detail: z.union([
      z.string(),
      z.array(z.object({ msg: z.string(), loc: z.array(z.unknown()).optional() }).passthrough()),
    ]),
  }),
]);

function errorMessage(payload: unknown, fallback: string): { message: string; details: unknown } {
  const parsed = errorEnvelope.safeParse(payload);
  if (!parsed.success) return { message: fallback, details: payload };
  if ("error" in parsed.data) {
    return { message: parsed.data.error.message, details: parsed.data.error.details };
  }
  const detail = parsed.data.detail;
  if (typeof detail === "string") return { message: detail, details: undefined };
  return {
    message: detail.map((issue) => `${(issue.loc ?? []).join(".")}: ${issue.msg}`).join("; "),
    details: detail,
  };
}

/** Build `?a=1&b=2` from primitive fields, skipping undefined/null values. */
export function query(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
    if (value === undefined || value === null) continue;
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export async function request<T>(path: string, schema: Schema<T>, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  const text = await response.text();
  let payload: unknown = null;
  if (text.length > 0) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const { message, details } = errorMessage(payload, response.statusText || `HTTP ${response.status}`);
    throw new ApiError(response.status, message, details);
  }

  const result = schema.safeParse(payload);
  if (!result.success) {
    throw new ApiError(
      response.status,
      `Response did not match the expected shape for ${path}`,
      result.error.format(),
    );
  }
  return result.data;
}

export const get = <T>(path: string, schema: Schema<T>): Promise<T> =>
  request(path, schema, { method: "GET" });

export const post = <T>(path: string, schema: Schema<T>, body?: unknown): Promise<T> =>
  request(path, schema, {
    method: "POST",
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });

export const del = <T>(path: string, schema: Schema<T>): Promise<T> =>
  request(path, schema, { method: "DELETE" });

/** Plain-text endpoints (TREC exports). */
export async function getText(path: string): Promise<string> {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  return response.text();
}

/** Absolute URL for links the browser opens itself (downloads). */
export const apiUrl = (path: string): string => `${BASE}${path}`;
