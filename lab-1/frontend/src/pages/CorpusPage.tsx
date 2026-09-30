import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtInt, fmtMs, fmtScore } from "@/lib/format";
import { corpusStatsQuery, keys } from "@/lib/queries";
import { corpusRoute } from "@/routes/router";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { HelpTip } from "@/components/ui/HelpTip";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { Stat } from "@/components/ui/Stat";
import { Table, TableFrame, Td, Th } from "@/components/ui/Table";
import { t } from "@/lib/i18n";

const PAGE_SIZE = 50;

export function CorpusPage() {
  const search = corpusRoute.useSearch();
  const navigate = useNavigate({ from: corpusRoute.fullPath });
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [filter, setFilter] = useState(search.q ?? "");

  const stats = useQuery(corpusStatsQuery);
  const params = {
    limit: PAGE_SIZE,
    offset: search.page * PAGE_SIZE,
    ...(search.domain ? { domain: search.domain } : {}),
    ...(search.q ? { search: search.q } : {}),
  };
  const documents = useQuery({
    queryKey: keys.corpus.documents(params),
    queryFn: () => api.corpus.documents(params),
  });

  const rebuild = useMutation({
    mutationFn: () => api.corpus.rebuildIndex(false),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.corpus.all }),
  });
  const add = useMutation({
    mutationFn: (value: string) => api.corpus.add(value),
    onSuccess: (result) => {
      setAddOpen(false);
      setUrl("");
      void navigate({ to: "/crawl", search: { job: result.crawl_job_id } });
    },
  });

  const s = stats.data;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow={t("Collection")}
        title={t("Corpus")}
        description={t("Every indexed document with its automatically extracted keywords (formula 1.6). N and D here are the N and N_k of every weight in the system.")}
        helpAnchor="help-corpus"
        actions={
          <>
            <Button onClick={() => setAddOpen(true)} variant="primary">
              {t("Add document")}
            </Button>
            <Button onClick={() => rebuild.mutate()} loading={rebuild.isPending} title={t("Re-analyse every document and recompute all weights")}>
              {t("Rebuild index")}
            </Button>
          </>
        }
      />

      {s?.is_stale && (
        <div role="status" className="mb-6 rounded-card border border-caution/40 bg-caution/10 p-4 text-[15px]">
          <strong className="text-caution">{t("The index is stale.")}</strong> {t("Documents were added or removed since the last build, so every B_i = log(N / N_k) is off. Rebuild the index to restore correct weights.")}
        </div>
      )}

      <dl className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label={t("Documents N")} value={s ? fmtInt(s.document_count) : "—"} />
        <Stat label={t("Dictionary D")} value={s ? fmtInt(s.term_count) : "—"} hint={t("distinct lemmas")} />
        <Stat label={t("Postings")} value={s ? fmtInt(s.posting_count) : "—"} hint={t("non-zero matrix cells")} />
        <Stat label={t("Avg. length")} value={s ? fmtInt(Math.round(s.average_document_length)) : "—"} hint={t("tokens per document")} />
        <Stat label={t("Embedded")} value={s ? fmtInt(s.embedded_document_count) : "—"} hint={t("for the semantic ranker")} />
        <Stat
          label={t("Index v{v}", { v: s?.index_version ?? "?" })}
          value={s?.build_duration_ms ? fmtMs(s.build_duration_ms) : "—"}
          hint={s?.built_at ? t("built {when} · log base {base}", { when: fmtDateTime(s.built_at), base: s.log_base }) : t("not built")}
        />
      </dl>

      <Card
        title={t("Documents")}
        subtitle={
          <span>
            {t("‖D‖ is the stored Euclidean norm of each document vector — 1 by construction.")}{" "}
            <HelpTip anchor="glossary-norm">
              {t("Weights w_dk are L2-normalised over each document, so every document vector has unit length and the cosine reduces to a sum of weights.")}
            </HelpTip>
          </span>
        }
        actions={
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void navigate({ search: { ...search, page: 0, q: filter || undefined } });
            }}
            className="flex items-center gap-2"
          >
            <input
              type="search"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder={t("Filter by title or URL")}
              aria-label={t("Filter documents")}
              className="rounded-pill border border-hairline bg-surface px-3 py-1.5 text-caption text-text"
            />
            <Button size="sm" type="submit">
              {t("Filter")}
            </Button>
          </form>
        }
      >
        {documents.isPending && <Skeleton lines={8} />}
        {documents.isError && <ErrorState error={documents.error} onRetry={() => void documents.refetch()} />}
        {documents.data && documents.data.length === 0 && (
          <EmptyState title={t("No documents")} description={t("Crawl some pages or add one by URL.")} />
        )}
        {documents.data && documents.data.length > 0 && (
          <TableFrame>
            <Table>
              <thead>
                <tr>
                  <Th numeric>id</Th>
                  <Th>{t("Title")}</Th>
                  <Th>{t("Domain")}</Th>
                  <Th>{t("Published")}</Th>
                  <Th numeric>{t("Tokens")}</Th>
                  <Th numeric>{t("Distinct")}</Th>
                  <Th numeric>‖D‖</Th>
                  <Th>{t("Embedding")}</Th>
                </tr>
              </thead>
              <tbody>
                {documents.data.map((doc) => (
                  <tr key={doc.id} className="hover:bg-surface-sunken/60">
                    <Td numeric>{doc.id}</Td>
                    <Td>
                      <Link
                        to="/corpus/$documentId"
                        params={{ documentId: String(doc.id) }}
                        className="font-medium text-accent hover:underline"
                      >
                        {doc.title || doc.url}
                      </Link>
                    </Td>
                    <Td>
                      <button
                        type="button"
                        className="text-text-secondary hover:text-accent"
                        onClick={() => void navigate({ search: { ...search, page: 0, domain: doc.source_domain } })}
                        title={t("Filter by this domain")}
                      >
                        {doc.source_domain}
                      </button>
                    </Td>
                    <Td>{fmtDate(doc.published_at)}</Td>
                    <Td numeric>{fmtInt(doc.token_count)}</Td>
                    <Td numeric>{fmtInt(doc.distinct_term_count)}</Td>
                    <Td numeric>{fmtScore(doc.vector_norm, 3)}</Td>
                    <Td>{doc.has_embedding ? <Badge tone="positive">{t("yes")}</Badge> : <Badge>{t("no")}</Badge>}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableFrame>
        )}
        <div className="mt-4 flex items-center justify-between text-caption text-text-secondary">
          <span>
            {search.domain && (
              <button
                type="button"
                className="mr-2 text-accent hover:underline"
                onClick={() => void navigate({ search: { ...search, page: 0, domain: undefined } })}
              >
                {t("clear domain filter ({domain})", { domain: search.domain })}
              </button>
            )}
            {t("page {n}", { n: search.page + 1 })}
            {s && <> {t("of about {n}", { n: Math.max(1, Math.ceil(s.document_count / PAGE_SIZE)) })}</>}
          </span>
          <span className="flex gap-2">
            <Button
              size="sm"
              disabled={search.page === 0}
              onClick={() => void navigate({ search: { ...search, page: Math.max(0, search.page - 1) } })}
            >
              {t("Previous")}
            </Button>
            <Button
              size="sm"
              disabled={(documents.data?.length ?? 0) < PAGE_SIZE}
              onClick={() => void navigate({ search: { ...search, page: search.page + 1 } })}
            >
              {t("Next")}
            </Button>
          </span>
        </div>
      </Card>

      <Dialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title={t("Add a document by URL")}
        description={t("The page goes through the same pipeline as the crawl: robots.txt, boilerplate removal, near-duplicate check, indexing.")}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (url.trim()) add.mutate(url.trim());
          }}
          className="space-y-3"
        >
          <input
            type="url"
            required
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://en.wikipedia.org/wiki/Okapi_BM25"
            aria-label={t("Document URL")}
            className="w-full rounded-pill border border-hairline-strong bg-surface px-4 py-2 text-[15px] text-text"
          />
          {add.isError && <ErrorState error={add.error} compact />}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setAddOpen(false)}>{t("Cancel")}</Button>
            <Button type="submit" variant="primary" loading={add.isPending}>
              {t("Fetch and index")}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
