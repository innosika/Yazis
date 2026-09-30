/**
 * The glass box: the complete derivation of one document's cosine score, from raw counts
 * to the final number, typeset with the assignment's own formulas.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtInt, fmtScore } from "@/lib/format";
import { keys } from "@/lib/queries";
import { ContributionChart } from "@/components/charts/ContributionChart";
import { Formula } from "@/components/math/Formula";
import { FORMULAS } from "@/components/math/formulas";
import { Badge } from "@/components/ui/Badge";
import { Sheet } from "@/components/ui/Dialog";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Table, TableFrame, Td, Th } from "@/components/ui/Table";
import { t } from "@/lib/i18n";

interface Props {
  documentId: number | null;
  queryText: string;
  onClose: () => void;
}

export function GlassBoxSheet({ documentId, queryText, onClose }: Props) {
  const open = documentId !== null;
  const explain = useQuery({
    queryKey: keys.search.explain(documentId ?? 0, queryText),
    queryFn: () => api.search.explain(documentId ?? 0, queryText),
    enabled: open,
  });
  const data = explain.data;

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={data ? t("Why did “{title}” score {score}?", { title: data.title, score: fmtScore(data.score) }) : t("Score derivation")}
      description={t("Every number below is recomputed from the stored counts, so you can follow it with a calculator.")}
    >
      {explain.isPending && <Skeleton lines={8} />}
      {explain.isError && <ErrorState error={explain.error} onRetry={() => void explain.refetch()} />}
      {data && (
        <div className="space-y-6 text-[14px]">
          <section className="flex flex-wrap items-center gap-2 text-caption text-text-secondary">
            <Badge>{t("{n} documents", { n: fmtInt(data.document_count) })}</Badge>
            <Badge>{t("{n} terms", { n: fmtInt(data.term_count) })}</Badge>
            <Badge>{t("log base {base}", { base: data.log_base })}</Badge>
            <Badge>{t("{tokens} tokens · {distinct} distinct", { tokens: fmtInt(data.token_count), distinct: fmtInt(data.distinct_term_count) })}</Badge>
            {!data.consistent_with_index && (
              <Badge tone="caution" title={t("The recomputed norm differs from the stored one: rebuild the index.")}>
                {t("index stale")}
              </Badge>
            )}
            <a href={data.url} target="_blank" rel="noreferrer noopener" className="ml-auto text-accent hover:underline">
              {t("open document ↗")}
            </a>
          </section>

          <section>
            <h3 className="mb-2 font-semibold">{t("1 · Term weights")}</h3>
            <Formula tex={FORMULAS.normalizedWeight.tex} display />
            <TableFrame>
              <Table>
                <thead>
                  <tr>
                    <Th>{t("term k")}</Th>
                    <Th numeric>N_dk</Th>
                    <Th numeric>N_k</Th>
                    <Th numeric>N</Th>
                    <Th numeric>B_k = log(N/N_k)</Th>
                    <Th numeric>A_k = N_dk·B_k</Th>
                    <Th numeric>w_dk</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.query_terms.map((term) => (
                    <tr key={term.lemma}>
                      <Td>
                        <span className="font-medium">{term.lemma}</span>
                      </Td>
                      <Td numeric>{term.term_frequency}</Td>
                      <Td numeric>{term.document_frequency}</Td>
                      <Td numeric>{term.document_count}</Td>
                      <Td numeric>{term.inverse_frequency.toFixed(4)}</Td>
                      <Td numeric>{term.weight_raw.toFixed(4)}</Td>
                      <Td numeric strong>
                        {term.weight_norm.toFixed(4)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableFrame>
            {(data.missing_terms.length > 0 || data.unknown_terms.length > 0) && (
              <p className="mt-2 text-caption text-text-tertiary">
                {data.missing_terms.length > 0 && (
                  <>
                    {t("Not in this document: {terms}.", { terms: data.missing_terms.join(", ") })}{" "}
                  </>
                )}
                {data.unknown_terms.length > 0 && <>{t("Not in the dictionary at all: {terms}.", { terms: data.unknown_terms.join(", ") })}</>}
              </p>
            )}
          </section>

          <section>
            <h3 className="mb-2 font-semibold">{t("2 · Scalar product (D, Q), term by term")}</h3>
            <p className="mb-2 text-caption text-text-secondary">
              {t("The query vector is binary (")}<Formula tex="w_{qj} = 1" />{t("), so each matched term adds its own")} <Formula tex="w_{dk}" /> {t("to the running sum.")}
            </p>
            <TableFrame>
              <Table>
                <thead>
                  <tr>
                    <Th>{t("term")}</Th>
                    <Th numeric>w_dk</Th>
                    <Th numeric>w_qk</Th>
                    <Th numeric>{t("product")}</Th>
                    <Th numeric>{t("running Σ")}</Th>
                    <Th numeric>{t("share")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.steps.map((step) => (
                    <tr key={step.lemma}>
                      <Td>{step.lemma}</Td>
                      <Td numeric>{step.document_weight.toFixed(4)}</Td>
                      <Td numeric>{step.query_weight.toFixed(0)}</Td>
                      <Td numeric>{step.product.toFixed(4)}</Td>
                      <Td numeric strong>
                        {step.running_sum.toFixed(4)}
                      </Td>
                      <Td numeric>{(step.share * 100).toFixed(1)}%</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableFrame>
            {data.steps.length > 0 && (
              <div className="mt-3">
                <ContributionChart steps={data.steps} />
              </div>
            )}
          </section>

          <section>
            <h3 className="mb-2 font-semibold">{t("3 · Norms and the cosine")}</h3>
            <Formula tex={FORMULAS.cosine.tex} display />
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Item label="(D, Q)" value={data.scalar_product.toFixed(6)} />
              <Item
                label={t("‖D‖ recomputed")}
                value={data.document_norm.toFixed(6)}
                hint={t("stored {stored} — equals 1 by construction", { stored: data.stored_document_norm.toFixed(6) })}
              />
              <Item label="‖Q‖ = √|q|" value={data.query_norm.toFixed(6)} />
              <Item label="r(D, Q)" value={data.score.toFixed(6)} strong />
            </dl>
            <div className="mt-3 rounded-panel bg-surface-sunken p-3">
              <Formula
                display
                tex={String.raw`r(D,Q) = \frac{${data.scalar_product.toFixed(4)}}{${data.document_norm.toFixed(4)} \times ${data.query_norm.toFixed(4)}} = ${data.score.toFixed(4)}`}
              />
            </div>
            <p className="mt-2 text-caption text-text-tertiary">
              {t("Because")} <Formula tex={String.raw`\|D\| = 1`} />{t(", the score is simply the sum of the matched weights divided by")}{" "}
              <Formula tex={String.raw`\sqrt{|q|}`} />{t(". Normalisation denominator for this document:")}{" "}
              {data.normalization_denominator.toFixed(4)}.
            </p>
          </section>

          {data.document_keywords.length > 0 && (
            <section>
              <h3 className="mb-2 font-semibold">{t("Document keywords by formula 1.6")}</h3>
              <Formula tex={FORMULAS.rawWeight.tex} display />
              <div className="flex flex-wrap gap-1.5">
                {data.document_keywords.map(([lemma, weight]) => (
                  <Badge key={lemma} title={`A = ${weight.toFixed(3)}`}>
                    {lemma} <span className="tabular text-text-tertiary">{weight.toFixed(2)}</span>
                  </Badge>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </Sheet>
  );
}

function Item({ label, value, hint, strong }: { label: string; value: string; hint?: string; strong?: boolean }) {
  return (
    <div className="rounded-panel border border-hairline p-3">
      <dt className="text-caption text-text-tertiary">{label}</dt>
      <dd className={`tabular mt-0.5 ${strong ? "text-[17px] font-semibold text-accent" : "text-text"}`}>{value}</dd>
      {hint && <p className="mt-0.5 text-[11px] text-text-tertiary">{hint}</p>}
    </div>
  );
}
