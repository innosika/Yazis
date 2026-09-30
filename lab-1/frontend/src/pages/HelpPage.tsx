import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { metricsQuery } from "@/lib/queries";
import { editionLabel } from "@/lib/editions";
import { Formula } from "@/components/math/Formula";
import { FORMULAS } from "@/components/math/formulas";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Table, TableFrame, Td, Th } from "@/components/ui/Table";
import { glossary, screenGuides, thirdParty } from "@/features/help/content";
import { metricDescription, metricLabel } from "@/lib/metricsRu";
import { t } from "@/lib/i18n";

const TOC = [
  { id: "help-model", label: "How the system ranks" },
  { id: "help-screens", label: "Screens" },
  { id: "help-methodology", label: "Evaluation methodology" },
  { id: "help-metrics", label: "Metrics" },
  { id: "help-glossary", label: "Glossary" },
  { id: "help-components", label: "Third-party components" },
];

const MODEL_FORMULAS = ["inverseFrequency", "rawWeight", "normalizedWeight", "queryVector", "cosine", "normReduction", "matrixL", "retrieval"] as const;

export function HelpPage() {
  const metrics = useQuery(metricsQuery);
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <PageHeader eyebrow={t("Help")} title={t("How this system works")} description={t("The vector model in the assignment's own formulas, what every screen does, how quality is measured, and what the words mean.")} />
      <div className="grid gap-8 lg:grid-cols-[14rem_1fr]">
        <nav aria-label={t("On this page")} className="lg:sticky lg:top-20 lg:self-start">
          <ul className="flex flex-wrap gap-1 lg:flex-col">
            {TOC.map((item) => (
              <li key={item.id}>
                <a href={`#${item.id}`} className="inline-block rounded-pill px-3 py-1.5 text-[14px] text-text-secondary hover:bg-surface-sunken hover:text-text">
                  {t(item.label)}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0 space-y-10">
          <section id="help-model" className="scroll-mt-24 space-y-4">
            <h2 className="text-title">{t("How the system ranks")}</h2>
            <p className="text-body text-text-secondary">
              {t("Documents and queries are turned into vectors over the dictionary of D lemmatised terms, and a document's relevance to a query is the cosine of the angle between them. Everything below is implemented directly from these formulas — no library computes the weights.")}
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              {MODEL_FORMULAS.map((key) => {
                const f = FORMULAS[key];
                return (
                  <Card key={key} padding="sm">
                    {"number" in f && (
                      <div className="mb-1">
                        <Badge tone="accent">{t("formula")} {f.number}</Badge>
                      </div>
                    )}
                    <Formula tex={f.tex} display />
                    <p className="text-caption text-text-secondary">{t(f.caption)}</p>
                  </Card>
                );
              })}
            </div>
            <Card title={t("Three consequences worth knowing")} padding="sm">
              <ul className="list-disc space-y-2 pl-5 text-[15px] text-text-secondary">
                <li>
                  <strong className="text-text">{t("Keywords and ranking use different weights.")}</strong> {t("Keywords are extracted by formula 1.6 (unnormalised A = N_dk·B_k); ranking uses the normalised w_dk. Both are derived from the same stored counts.")}
                </li>
                <li>
                  <strong className="text-text">{t("‖D‖ = 1 by construction")}</strong>{t(", so r(D, Q) = Σ w_dk / √|q| over the query's terms: the cosine is a sum of stored weights over a constant, which is what makes retrieval one scan of the inverted index.")}
                </li>
                <li>
                  <strong className="text-text">{t("The logarithm base is irrelevant to ranking")}</strong>{t(" — it cancels between numerator and denominator of w_dk — and only scales the absolute keyword weights of formula 1.6.")}
                </li>
              </ul>
            </Card>
            <Card title={t("Where the mandated model falls short, and two measured proposals")} padding="sm">
              <p className="text-[15px] text-text-secondary">
                {t("The specification fixes the query vector as binary, so a rare, informative query word and a near-ubiquitous one pull equally; and pure L2 normalisation handles long articles worse than BM25's tunable length normalisation with term-frequency saturation. Both are tested in the evaluation rather than asserted:")}
              </p>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-panel border border-hairline p-3">
                  <Badge color="var(--ranker-vector-idf)" className="mb-2 border-hairline text-text">
                    {t("Vector · IDF query")}
                  </Badge>
                  <Formula tex={FORMULAS.idfQuery.tex} display />
                  <p className="text-caption text-text-secondary">{t(FORMULAS.idfQuery.caption)}</p>
                </div>
                <div className="rounded-panel border border-hairline p-3">
                  <Badge color="var(--ranker-vector-prf)" className="mb-2 border-hairline text-text">
                    {t("Vector · Rocchio PRF")}
                  </Badge>
                  <Formula tex={FORMULAS.rocchio.tex} display />
                  <p className="text-caption text-text-secondary">{t("Pseudo-relevance feedback: the top-5 of the first pass are assumed relevant, the query is expanded to 20 terms and scored again (γ = 0).")}</p>
                </div>
              </div>
            </Card>
          </section>

          <section id="help-screens" className="scroll-mt-24 space-y-4">
            <h2 className="text-title">{t("Screens")}</h2>
            <div className="grid gap-4 md:grid-cols-2">
              {screenGuides().map((guide) => (
                <Card
                  key={guide.id}
                  id={guide.id}
                  className="scroll-mt-24"
                  title={
                    <Link to={guide.to} search={{}} className="hover:text-accent">
                      {guide.title} →
                    </Link>
                  }
                  subtitle={guide.purpose}
                  padding="sm"
                >
                  <p className="mb-1 text-caption font-medium uppercase tracking-wide text-text-tertiary">{t("Controls")}</p>
                  <ul className="mb-3 list-disc space-y-1 pl-5 text-[14px] text-text-secondary">
                    {guide.controls.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                  <p className="mb-1 text-caption font-medium uppercase tracking-wide text-text-tertiary">{t("How to read it")}</p>
                  <ul className="list-disc space-y-1 pl-5 text-[14px] text-text-secondary">
                    {guide.reading.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </Card>
              ))}
            </div>
          </section>

          <section id="help-methodology" className="scroll-mt-24 space-y-4">
            <h2 className="text-title">{t("Evaluation methodology")}</h2>
            <div className="space-y-3 text-[15px] text-text-secondary">
              <p id="help-collections" className="scroll-mt-24">
                <strong className="text-text">{t("Two test collections.")}</strong> {t("The known-item collection is built automatically: a query is derived from a document's opening text and that document is the one relevant answer. Its judgments are exact and free of any pool bias, but every topic has R = 1, so recall, bpref and set precision degenerate — the tables mark them n/a with a footnote. The topical collection has 46 hand-authored topics (navigational, topical and deliberately vocabulary-mismatched), of which 25 are selected for judging over a pool.")}
              </p>
              <p>
                <strong className="text-text">{t("Pooling with provenance.")}</strong> {t("The pool is the union of every ranker's top-10, plus an oracle synonym query run with BM25 to surface relevant documents no ranker found for the topic's wording, plus 5 random unjudged documents per topic. If almost none of the random sample is relevant, the pool is close to complete — measured, not assumed.")}
              </p>
              <p>
                <strong className="text-text">{t("Anti-tuning, as in ROMIP.")}</strong> {t("The judged topics are chosen only after the pool — that is, every ranker's output — is frozen; the API refuses to select earlier. Oracle queries stay hidden until then.")}
              </p>
              <p id="help-llm-assessor" className="scroll-mt-24">
                <strong className="text-text">{t("The assessor.")}</strong> {t("Pairs are judged on ROMIP's five-point scale by a local language model that sees only the topic (title, description, narrative) and the document — never a ranker, rank or score — and records a one-sentence reason with every verdict. Its model, digest, prompt version and decoding settings are stored. A blind human judging screen exists, but no human overlap was judged in this lab, so inter-assessor agreement is reported as not measured; this is a stated limitation.")}
              </p>
              <p id="help-judging" className="scroll-mt-24">
                <strong className="text-text">{t("Graded at collection, binary at scoring.")}</strong> {t("Grades are kept as given; every 2004 metric uses the binary table derived at threshold relevant− under the «or» and «and» aggregations. Topics with no relevant document are excluded, so num_q accompanies every number. Unjudged retrieved documents count as non-relevant; bpref, which skips them, is the robustness check.")}
              </p>
              <p>
                <strong className="text-text">{t("Macro-averaging.")}</strong> {t("Each metric is computed per topic and averaged unweighted. The 2004 appendix calls this «микроусреднение»; its micro/macro labels are swapped, which the 2010 edition corrects.")}
              </p>
              <p id="help-significance" className="scroll-mt-24">
                <strong className="text-text">{t("Significance.")}</strong> {t("Paired per-topic differences, permutation test by default (Wilcoxon and paired t also available), Holm–Bonferroni across all pairs, bootstrap intervals on the aggregates. With n ≈ 25–30, only medium-to-large effects can reach significance.")}
              </p>
              <p>
                <strong className="text-text">{t("Verified.")}</strong> {t("The metric core reproduces the appendix's own worked example and is cross-validated against NIST trec_eval (via pytrec_eval) to 10⁻⁹, including the conventions on which the documents deliberately differ.")}
              </p>
            </div>
          </section>

          <section id="help-metrics" className="scroll-mt-24 space-y-4">
            <h2 className="text-title">{t("Metrics")}</h2>
            <p className="text-[15px] text-text-secondary">{t("From the system's own registry. The official ROMIP 2004 search-track metrics are listed apart from the 2009/2010 extensions and the reconstruction of the undefined «RIRES» curve.")}</p>
            {metrics.data && (
              <TableFrame>
                <Table>
                  <thead>
                    <tr>
                      <Th>{t("metric")}</Th>
                      <Th>{t("Russian name")}</Th>
                      <Th>{t("defined in")}</Th>
                      <Th>{t("formula")}</Th>
                      <Th>{t("description")}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.data.metrics
                      .filter((m) => m.edition !== "diagnostic")
                      .map((m) => (
                        <tr key={m.key} id={`metric-${m.key}`} className="scroll-mt-24">
                          <Td>
                            <span className="font-medium">{metricLabel(m)}</span>
                            {m.kind === "curve" && <Badge className="ml-1">{t("curve")}</Badge>}
                          </Td>
                          <Td className="text-text-secondary">{m.label_ru ?? "—"}</Td>
                          <Td>
                            <Badge tone={m.edition === "official_2004" ? "accent" : "neutral"}>{editionLabel(m.edition)}</Badge>
                          </Td>
                          <Td>{m.formula_tex ? <Formula tex={m.formula_tex} /> : "—"}</Td>
                          <Td className="max-w-md text-text-secondary">{metricDescription(m)}</Td>
                        </tr>
                      ))}
                  </tbody>
                </Table>
              </TableFrame>
            )}
          </section>

          <section id="help-glossary" className="scroll-mt-24 space-y-4">
            <h2 className="text-title">{t("Glossary")}</h2>
            <dl className="grid gap-3 md:grid-cols-2">
              {glossary().map((entry) => (
                <div key={entry.id} id={entry.id} className="scroll-mt-24 rounded-panel border border-hairline bg-surface p-3">
                  <dt className="font-medium text-text">{entry.term}</dt>
                  <dd className="mt-1 text-[14px] text-text-secondary">{entry.definition}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section id="help-components" className="scroll-mt-24 space-y-4">
            <h2 className="text-title">{t("Third-party components")}</h2>
            <TableFrame>
              <Table>
                <thead>
                  <tr>
                    <Th>{t("component")}</Th>
                    <Th>{t("role")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {thirdParty().map((c) => (
                    <tr key={c.name}>
                      <Td className="font-medium">{c.name}</Td>
                      <Td className="text-text-secondary">{c.role}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableFrame>
            <p className="text-caption text-text-tertiary">
              {t("The term weights, the inverted-index scan, every ROMIP metric, the pooling, the SVD projection and Rocchio feedback are implemented in this project; the libraries above supply storage, transport, linguistics and rendering.")}
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
