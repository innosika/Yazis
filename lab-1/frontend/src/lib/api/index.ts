import { get } from "./client";
import { healthSchema } from "./common";
import { corpusApi } from "./corpus";
import { crawlApi } from "./crawl";
import { evalApi } from "./eval";
import { labApi } from "./lab";
import { searchApi } from "./search";

export { ApiError, apiUrl } from "./client";
export * from "./common";
export * from "./search";
export * from "./corpus";
export * from "./crawl";
export * from "./eval";
export * from "./lab";

export const api = {
  health: () => get("/health/ready", healthSchema),
  search: searchApi,
  corpus: corpusApi,
  crawl: crawlApi,
  eval: evalApi,
  lab: labApi,
};
