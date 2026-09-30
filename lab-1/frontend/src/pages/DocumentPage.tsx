import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtBytes, fmtDate, fmtDateTime, fmtInt } from "@/lib/format";
import { keys } from "@/lib/queries";
import { documentRoute } from "@/routes/router";
import { Formula } from "@/components/math/Formula";
import { FORMULAS } from "@/components/math/formulas";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { ErrorState } from "@/components/ui/ErrorState";
import { HelpTip } from "@/components/ui/HelpTip";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { Table, TableFrame, Td, Th } from "@/components/ui/Table";
import { Toggle } from "@/components/ui/Toggle";
import { t } from "@/lib/i18n";

export function DocumentPage() {
  const { documentId } = documentRoute.useParams();
  const id = Number(documentId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const [reindex, setReindex] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const document = useQuery({
    queryKey: keys.corpus.document(id),
    queryFn: () => api.corpus.document(id),
    enabled: Number.isFinite(id),
  });
  const remove = useMutation({
    mutationFn: () => api.corpus.remove(id, reindex),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: keys.corpus.all });
      await navigate({ to: "/corpus", search: {} });
    },
  });

  const doc = document.data;

  // Rank by the normalised weight to show how the two weightings disagree.
  const byNorm = doc ? [...doc.keywords].sort((a, b) => b.weight_norm - a.weight_norm).map((k) => k.lemma) : [];

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <p className="mb-4 text-caption">
        <Link to="/corpus" search={{}} className="text-accent hover:underline">
          ← {t("Corpus")}
        </Link>
      </p>
      {document.isPending && <Skeleton lines={8} />}
      {document.isError && <ErrorState error={document.error} onRetry={() => void document.refetch()} />}
      {doc && (
        <>
          <PageHeader
            eyebrow={t("Document {id}", { id: doc.id })}
            title={doc.title || doc.url}
            description={
              <span className="flex flex-wrap items-center gap-2">
                <a href={doc.url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
                  {doc.url} ↗
                </a>
                {doc.language && <Badge>{doc.language}</Badge>}
                {doc.published_at && <Badge>{t("published {date}", { date: fmtDate(doc.published_at) })}</Badge>}
                {doc.fetched_at && <Badge>{t("fetched {date}", { date: fmtDateTime(doc.fetched_at) })}</Badge>}
                {doc.byte_size != null && <Badge>{fmtBytes(doc.byte_size)}</Badge>}
                {doc.http_status != null && <Badge>HTTP {doc.http_status}</Badge>}
              </span>
            }
            actions={
              <Button variant="danger" onClick={() => setConfirm(true)}>
                {t("Delete")}
              </Button>
            }
          />

          <div className="grid gap-6 lg:grid-cols-[2fr_3fr]">
            <Card title={t("Text")} subtitle={t("{tokens} tokens · {distinct} distinct terms", { tokens: fmtInt(doc.token_count), distinct: fmtInt(doc.distinct_term_count) })}>
              {doc.description && <p className="mb-3 text-[15px] italic text-text-secondary">{doc.description}</p>}
              <p className={`whitespace-pre-line text-[15px] leading-relaxed text-text ${expanded ? "" : "line-clamp-[14]"}`}>
                {doc.text}
              </p>
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => setExpanded((v) => !v)}>
                {expanded ? t("Show less") : t("Show full text")}
              </Button>
            </Card>

            <Card
              title={t("Keywords by formula 1.6")}
              subtitle={
                <span>
                  {t("Terms ranked by the raw weight A = N_dk · B_k, next to the normalised weight the ranker uses.")}{" "}
                  <HelpTip anchor="help-corpus">
                    {t("Keyword extraction uses the unnormalised weight (formula 1.6). Ranking uses w_dk, which divides by the document's norm. Their orders differ, which the rank column shows.")}
                  </HelpTip>
                </span>
              }
            >
              <Formula tex={FORMULAS.rawWeight.tex} display />
              <TableFrame>
                <Table>
                  <thead>
                    <tr>
                      <Th numeric>#</Th>
                      <Th>{t("lemma")}</Th>
                      <Th numeric>N_dk</Th>
                      <Th numeric>N_k</Th>
                      <Th numeric>B_k</Th>
                      <Th numeric>A (1.6)</Th>
                      <Th numeric>w_dk</Th>
                      <Th numeric>{t("rank by w_dk")}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.keywords.map((k, index) => {
                      const normRank = byNorm.indexOf(k.lemma) + 1;
                      const shift = normRank - (index + 1);
                      return (
                        <tr key={k.lemma}>
                          <Td numeric>{index + 1}</Td>
                          <Td>
                            <span className="font-medium">{k.lemma}</span>
                          </Td>
                          <Td numeric>{k.term_frequency}</Td>
                          <Td numeric>{k.document_frequency}</Td>
                          <Td numeric>{k.inverse_frequency.toFixed(3)}</Td>
                          <Td numeric strong>
                            {k.weight_raw.toFixed(3)}
                          </Td>
                          <Td numeric>{k.weight_norm.toFixed(4)}</Td>
                          <Td numeric>
                            {normRank}
                            {shift !== 0 && (
                              <span className={`ml-1 ${shift < 0 ? "text-positive" : "text-caution"}`}>
                                {shift < 0 ? `↑${-shift}` : `↓${shift}`}
                              </span>
                            )}
                          </Td>
                        </tr>
                      );
                    })}
                  </tbody>
                </Table>
              </TableFrame>
              <p className="mt-3 text-caption text-text-tertiary">
                {t("The logarithm base scales A but cancels in w_dk, so it changes these absolute keyword weights and never the ranking.")}
              </p>
            </Card>
          </div>

          <Dialog
            open={confirm}
            onClose={() => setConfirm(false)}
            title={t("Delete this document?")}
            description={t("Removing a document changes N, so every inverse frequency B_i in the collection changes with it.")}
          >
            <div className="space-y-4">
              <Toggle
                checked={reindex}
                onChange={setReindex}
                label={t("Recompute all weights now")}
                description={t("Recommended. Otherwise the index is marked stale until the next rebuild.")}
              />
              {remove.isError && <ErrorState error={remove.error} compact />}
              <div className="flex justify-end gap-2">
                <Button onClick={() => setConfirm(false)}>{t("Cancel")}</Button>
                <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
                  {t("Delete document")}
                </Button>
              </div>
            </div>
          </Dialog>
        </>
      )}
    </div>
  );
}
