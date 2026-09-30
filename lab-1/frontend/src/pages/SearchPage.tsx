import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { AnimatePresence } from "motion/react";
import { useState } from "react";
import type { SearchHit } from "@/lib/api";
import { fmtInt, fmtMs } from "@/lib/format";
import { rankersQuery, searchQuery } from "@/lib/queries";
import { searchRoute } from "@/routes/router";
import type { SearchSearch } from "@/routes/searchParams";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LiveRegion } from "@/components/ui/LiveRegion";
import { Skeleton } from "@/components/ui/Skeleton";
import { GlassBoxSheet } from "@/features/search/GlassBoxSheet";
import { ResultCard } from "@/features/search/ResultCard";
import { SearchForm } from "@/features/search/SearchForm";
import { t } from "@/lib/i18n";

const EXAMPLES = [
  "vector space model cosine similarity",
  "how does an inverted index store term positions",
  "the dream of a desk that holds all your books",
  "punched card tabulating machine",
];

const EXPLAINABLE = new Set(["vector"]);

export function SearchPage() {
  const search = searchRoute.useSearch();
  const navigate = useNavigate({ from: searchRoute.fullPath });
  const [explaining, setExplaining] = useState<SearchHit | null>(null);

  const rankers = useQuery(rankersQuery);
  const results = useQuery(
    searchQuery({
      query: search.q,
      ranker: search.ranker,
      limit: search.limit,
      all_words_together: search.all,
      ...(search.from ? { date_from: search.from } : {}),
      ...(search.to ? { date_to: search.to } : {}),
    }),
  );

  const update = (next: SearchSearch) => void navigate({ search: next });
  const data = results.data;
  const hasQuery = search.q.trim().length > 0;

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <header className="mb-8 text-center">
        <h1 className="text-headline text-balance sm:text-display">{t("Search the collection")}</h1>
        <p className="mx-auto mt-3 max-w-2xl text-body text-text-secondary">
          {t("A natural-language query, ranked by the vector model — TF-IDF weights and cosine similarity — or by any of the strategies it is measured against.")}
        </p>
      </header>

      <SearchForm value={search} rankers={rankers.data ?? []} onSubmit={update} busy={results.isFetching} />

      <div className="mt-8">
        {!hasQuery && (
          <EmptyState
            title={t("Type a query to begin")}
            description={
              <span>{t("Press / to focus the field. Try one of these:")}</span>
            }
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {EXAMPLES.map((example) => (
                  <Button key={example} size="sm" onClick={() => update({ ...search, q: example })}>
                    {example}
                  </Button>
                ))}
              </div>
            }
          />
        )}

        {hasQuery && results.isPending && <Skeleton lines={10} />}
        {hasQuery && results.isError && (
          <ErrorState error={results.error} onRetry={() => void results.refetch()} />
        )}

        {hasQuery && data && (
          <>
            <LiveRegion
              message={t("{n} documents matched; showing {shown}.", { n: fmtInt(data.total_candidates), shown: data.hits.length })}
            />
            <div className="mb-4 flex flex-wrap items-center gap-2 text-caption text-text-secondary">
              <span>
                <strong className="tabular text-text">{fmtInt(data.total_candidates)}</strong> {t("candidates in")}{" "}
                <span className="tabular">{fmtMs(data.duration_ms)}</span>
              </span>
              <span aria-hidden>·</span>
              <span>{t("searched for")}</span>
              {data.query_lemmas.map((lemma) => (
                <Badge key={lemma} tone="accent">
                  {lemma}
                </Badge>
              ))}
              {data.unknown_lemmas.map((lemma) => (
                <Badge key={lemma} title={t("not in the dictionary — appears in no document")} className="line-through">
                  {lemma}
                </Badge>
              ))}
              {data.filters_applied && <Badge tone="caution">{t("filters on")}</Badge>}
            </div>

            {data.hits.length === 0 ? (
              <EmptyState
                title={t("No document matches")}
                description={
                  search.all
                    ? t("“All words together” requires every query word; try turning it off, or removing the date filter.")
                    : data.unknown_lemmas.length === data.query_lemmas.length + data.unknown_lemmas.length
                      ? t("None of the query words occurs in the collection.")
                      : t("Try fewer or different words, or another ranker.")
                }
              />
            ) : (
              <ul className={`space-y-3 ${results.isFetching ? "opacity-60 transition-opacity" : ""}`}>
                <AnimatePresence initial={false}>
                  {data.hits.map((hit, index) => (
                    <ResultCard
                      key={hit.document_id}
                      hit={hit}
                      position={index + 1}
                      ranker={data.ranker}
                      queryLemmas={data.query_lemmas}
                      canExplain={EXPLAINABLE.has(data.ranker)}
                      onExplain={setExplaining}
                    />
                  ))}
                </AnimatePresence>
              </ul>
            )}

            {data.hits.length < data.total_candidates && data.hits.length >= search.limit && (
              <div className="mt-6 text-center">
                <Button onClick={() => update({ ...search, limit: Math.min(100, search.limit + 10) })}>
                  {t("Show more")}
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      <GlassBoxSheet
        documentId={explaining?.document_id ?? null}
        queryText={search.q}
        onClose={() => setExplaining(null)}
      />
    </div>
  );
}
