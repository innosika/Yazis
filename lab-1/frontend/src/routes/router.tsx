/**
 * Code-based route tree.
 *
 * Code-based rather than file-based because the file-based mode needs a Vite plugin that
 * regenerates a route file during the build; nine routes do not justify a generator.
 * Pages are lazy so the Three.js and charting chunks stay off the Search screen.
 */
import type { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  lazyRouteComponent,
  redirect,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { RootLayout } from "./RootLayout";
import { NotFound } from "./NotFound";
import { RouteError } from "./RouteError";
import {
  corpusSearchSchema,
  crawlSearchSchema,
  evaluationSearchSchema,
  labSearchSchema,
  searchSearchSchema,
  type CorpusSearch,
  type CrawlSearch,
  type EvaluationSearch,
  type LabSearch,
  type SearchSearch,
} from "./searchParams";

export interface RouterContext {
  queryClient: QueryClient;
}

export const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
  notFoundComponent: NotFound,
  errorComponent: RouteError,
});

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    redirect({ to: "/search", search: {}, throw: true });
  },
});

export const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/search",
  validateSearch: (input: Partial<SearchSearch> & SearchSchemaInput): SearchSearch =>
    searchSearchSchema.parse(input),
  component: lazyRouteComponent(() => import("@/pages/SearchPage"), "SearchPage"),
});

export const corpusRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/corpus",
  validateSearch: (input: Partial<CorpusSearch> & SearchSchemaInput): CorpusSearch =>
    corpusSearchSchema.parse(input),
  component: lazyRouteComponent(() => import("@/pages/CorpusPage"), "CorpusPage"),
});

export const documentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/corpus/$documentId",
  component: lazyRouteComponent(() => import("@/pages/DocumentPage"), "DocumentPage"),
});

export const crawlRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/crawl",
  validateSearch: (input: Partial<CrawlSearch> & SearchSchemaInput): CrawlSearch =>
    crawlSearchSchema.parse(input),
  component: lazyRouteComponent(() => import("@/pages/CrawlPage"), "CrawlPage"),
});

// The assignment's «подменю»: evaluation is a layout with one child per view, each with
// its own URL, so the browser's back button and deep links work per tab.
export const evaluationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/evaluation",
  validateSearch: (input: Partial<EvaluationSearch> & SearchSchemaInput): EvaluationSearch =>
    evaluationSearchSchema.parse(input),
  component: lazyRouteComponent(
    () => import("@/pages/evaluation/EvaluationLayout"),
    "EvaluationLayout",
  ),
});

export const evaluationOverviewRoute = createRoute({
  getParentRoute: () => evaluationRoute,
  path: "/",
  component: lazyRouteComponent(() => import("@/pages/evaluation/OverviewPage"), "OverviewPage"),
});
export const evaluationPerQueryRoute = createRoute({
  getParentRoute: () => evaluationRoute,
  path: "per-query",
  component: lazyRouteComponent(() => import("@/pages/evaluation/PerQueryPage"), "PerQueryPage"),
});
export const evaluationCurvesRoute = createRoute({
  getParentRoute: () => evaluationRoute,
  path: "curves",
  component: lazyRouteComponent(() => import("@/pages/evaluation/CurvesPage"), "CurvesPage"),
});
export const evaluationCompareRoute = createRoute({
  getParentRoute: () => evaluationRoute,
  path: "compare",
  component: lazyRouteComponent(() => import("@/pages/evaluation/ComparePage"), "ComparePage"),
});
export const evaluationSignificanceRoute = createRoute({
  getParentRoute: () => evaluationRoute,
  path: "significance",
  component: lazyRouteComponent(
    () => import("@/pages/evaluation/SignificancePage"),
    "SignificancePage",
  ),
});
export const evaluationCollectionRoute = createRoute({
  getParentRoute: () => evaluationRoute,
  path: "collection",
  component: lazyRouteComponent(
    () => import("@/pages/evaluation/CollectionPage"),
    "CollectionPage",
  ),
});
export const evaluationJudgeRoute = createRoute({
  getParentRoute: () => evaluationRoute,
  path: "judge",
  component: lazyRouteComponent(() => import("@/pages/evaluation/JudgePage"), "JudgePage"),
});

export const labRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/lab",
  validateSearch: (input: Partial<LabSearch> & SearchSchemaInput): LabSearch =>
    labSearchSchema.parse(input),
  component: lazyRouteComponent(() => import("@/pages/LabPage"), "LabPage"),
});

export const helpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/help",
  component: lazyRouteComponent(() => import("@/pages/HelpPage"), "HelpPage"),
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  searchRoute,
  corpusRoute,
  documentRoute,
  crawlRoute,
  evaluationRoute.addChildren([
    evaluationOverviewRoute,
    evaluationPerQueryRoute,
    evaluationCurvesRoute,
    evaluationCompareRoute,
    evaluationSignificanceRoute,
    evaluationCollectionRoute,
    evaluationJudgeRoute,
  ]),
  labRoute,
  helpRoute,
]);

export function createAppRouter(queryClient: QueryClient) {
  return createRouter({
    routeTree,
    context: { queryClient },
    defaultPreload: "intent",
    defaultPreloadStaleTime: 0,
    scrollRestoration: true,
    defaultPendingMs: 150,
  });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module "@tanstack/react-router" {
  interface Register {
    router: AppRouter;
  }
}
