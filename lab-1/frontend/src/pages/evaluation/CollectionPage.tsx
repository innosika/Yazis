import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ACTIVE_RUN_STATUSES, api, apiUrl, type JudgingJob } from "@/lib/api";
import { fmtDateTime, fmtInt, fmtMs, fmtPct } from "@/lib/format";
import { keys, pollWhileActive } from "@/lib/queries";
import { GradeDistribution } from "@/components/charts/GradeDistribution";
import { PoolCoverageChart } from "@/components/charts/PoolCoverageChart";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { HelpTip } from "@/components/ui/HelpTip";
import { LiveRegion } from "@/components/ui/LiveRegion";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { Stat } from "@/components/ui/Stat";
import { Table, TableFrame, Td, Th } from "@/components/ui/Table";
import { useEvalProgress } from "@/features/evaluation/useEvalProgress";
import { useEvaluationContext } from "@/features/evaluation/useEvaluationContext";
import { t } from "@/lib/i18n";
import { rankerLabel } from "@/components/charts/rankerColor";

const SOURCE_LABEL: Record<string, string> = {
  run_union: "rankers' top-k",
  oracle: "oracle query only",
  random_sample: "random sample",
  manual_seed: "manual",
};

export function CollectionPage() {
  const ctx = useEvaluationContext();
  const queryClient = useQueryClient();
  const collection = ctx.collection;
  const id = collection?.id ?? 0;
  const [mode, setMode] = useState<"source" | "ranker">("source");

  const topics = useQuery({ queryKey: keys.eval.topics(id), queryFn: () => api.eval.topics(id), enabled: id > 0 });
  const pool = useQuery({ queryKey: keys.eval.pool(id), queryFn: () => api.eval.poolStats(id), enabled: id > 0 });
  const jobs = useQuery({
    queryKey: keys.eval.judgingJobs(id),
    queryFn: () => api.eval.judgingJobs(id),
    enabled: id > 0,
    refetchInterval: pollWhileActive<JudgingJob>(ACTIVE_RUN_STATUSES, 5_000),
  });
  const assessor = useQuery({ queryKey: keys.eval.assessorStatus, queryFn: api.eval.assessorStatus, staleTime: 60_000 });
  const progress = useEvalProgress("judging");
  const latestEvent = progress.records[progress.records.length - 1];

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: keys.eval.all });
  const buildPool = useMutation({ mutationFn: () => api.eval.buildPool(id, {}), onSuccess: invalidate });
  const selectTopics = useMutation({ mutationFn: () => api.eval.selectTopics(id), onSuccess: invalidate });
  const startJudging = useMutation({ mutationFn: () => api.eval.startJudging(id), onSuccess: invalidate });
  const seedTopical = useMutation({ mutationFn: () => api.eval.seedTopical(false), onSuccess: invalidate });
  const buildKnownItem = useMutation({ mutationFn: () => api.eval.buildKnownItem(30, false), onSuccess: invalidate });

  if (!collection) {
    return (
      <EmptyState
        title={t("No test collection yet")}
        description={t("Seed the hand-authored topical collection, or build the automatic known-item one.")}
        action={
          <div className="flex gap-2">
            <Button variant="primary" loading={seedTopical.isPending} onClick={() => seedTopical.mutate()}>
              {t("Seed topical collection")}
            </Button>
            <Button loading={buildKnownItem.isPending} onClick={() => buildKnownItem.mutate()}>
              {t("Build known-item collection")}
            </Button>
          </div>
        }
      />
    );
  }

  const activeJob = (jobs.data ?? []).find((j) => ACTIVE_RUN_STATUSES.has(j.status));
  const byCategory = Object.entries(collection.topics_by_category);
  const pooled = topics.data?.filter((t) => t.pool_size > 0).length ?? 0;

  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label={t("Topics authored")} value={fmtInt(collection.summary.queries ?? 0)} hint={byCategory.map(([c, v]) => `${v.total} ${t(c)}`).join(" · ")} />
        <Stat label={t("Topics judged")} value={fmtInt(collection.summary.judged_queries ?? 0)} hint={t("selected after the runs were frozen")} />
        <Stat label={t("Pool pairs")} value={fmtInt(collection.summary.pool_entries ?? 0)} hint={pool.data ? t("{n} distinct documents", { n: pool.data.unique_documents }) : undefined} />
        <Stat label={t("Judgments")} value={fmtInt(collection.summary.judgments ?? 0)} hint={t("{n} assessor(s)", { n: collection.assessors.length })} />
        <Stat label={t("Runs frozen")} value={collection.frozen_at ? t("yes") : t("no")} hint={collection.frozen_at ? fmtDateTime(collection.frozen_at) : t("select judged topics to freeze")} />
        <Stat label={t("Pool depth")} value={collection.pool_depth} hint={t("per ranker, plus oracle and random sample")} />
      </dl>

      {!collection.is_known_item && (
        <Card
          title={t("Pipeline")}
          subtitle={t("ROMIP's order, enforced by the API: build the pool (this freezes every ranker's output) → select the judged subset → judge → evaluate.")}
        >
          <ol className="grid gap-3 md:grid-cols-3">
            <Step
              n={1}
              title={t("Build the judgment pool")}
              done={pooled > 0}
              detail={pool.data ? `${t("{n} pairs", { n: pool.data.total_entries })} · ${Object.entries(pool.data.by_source).map(([s, b]) => `${b.entries ?? 0} ${t(SOURCE_LABEL[s] ?? s)}`).join(", ")}` : t("union of every ranker's top-k + oracle query + random sample")}
              action={
                <Button size="sm" loading={buildPool.isPending} onClick={() => buildPool.mutate()} disabled={collection.frozen_at !== null && collection.frozen_at !== undefined}>
                  {pooled > 0 ? t("Rebuild pool") : t("Build pool")}
                </Button>
              }
            />
            <Step
              n={2}
              title={t("Select the judged subset")}
              done={Boolean(collection.frozen_at)}
              detail={collection.frozen_at ? t("{n} topics, stratified by category, chosen {when}", { n: collection.summary.judged_queries ?? 0, when: fmtDateTime(collection.frozen_at) }) : t("refused until the pool exists — the anti-tuning rule")}
              action={
                <Button size="sm" loading={selectTopics.isPending} onClick={() => selectTopics.mutate()} disabled={pooled === 0 || Boolean(collection.frozen_at)}>
                  {t("Select topics")}
                </Button>
              }
            />
            <Step
              n={3}
              title={t("Judge with the LLM assessor")}
              done={(collection.summary.judgments ?? 0) > 0 && !activeJob}
              detail={
                assessor.data
                  ? `${assessor.data.name} · ${assessor.data.reachable ? t("reachable") : `${t("unreachable")}: ${assessor.data.problem ?? ""}`}`
                  : t("checking the assessor endpoint…")
              }
              action={
                <Button size="sm" variant="primary" loading={startJudging.isPending} onClick={() => startJudging.mutate()} disabled={!collection.frozen_at || Boolean(activeJob) || assessor.data?.reachable === false}>
                  {activeJob ? t("Judging…") : t("Start judging")}
                </Button>
              }
            />
          </ol>
          {(buildPool.isError || selectTopics.isError || startJudging.isError) && (
            <div className="mt-3">
              <ErrorState error={buildPool.error ?? selectTopics.error ?? startJudging.error} compact />
            </div>
          )}
        </Card>
      )}

      {(jobs.data?.length ?? 0) > 0 && (
        <Card
          title={t("Judging jobs")}
          subtitle={
            <span className="flex items-center gap-2">
              {t("The assessor sees the topic and the document only — never a ranker, rank or score.")}
              <HelpTip anchor="help-llm-assessor">
                {t("Verdicts are on ROMIP's five-point scale and each carries the model's one-sentence reason. The assessor's model, digest and prompt version are recorded. No human overlap was judged in this lab, so agreement is reported as not measured.")}
              </HelpTip>
            </span>
          }
          padding="sm"
        >
          <LiveRegion message={latestEvent?.event === "judged" ? t("Judged {n} of {total}", { n: latestEvent.judged ?? 0, total: latestEvent.total ?? 0 }) : ""} />
          <TableFrame>
            <Table>
              <thead>
                <tr>
                  <Th numeric>#</Th>
                  <Th>{t("assessor")}</Th>
                  <Th>{t("status")}</Th>
                  <Th>{t("progress")}</Th>
                  <Th numeric>{t("judged")}</Th>
                  <Th numeric>{t("failed")}</Th>
                  <Th numeric>{t("pending")}</Th>
                  <Th>{t("started")}</Th>
                </tr>
              </thead>
              <tbody>
                {jobs.data?.map((job) => {
                  const live = latestEvent?.job_id === job.id && latestEvent.event === "judged" ? latestEvent : null;
                  const judged = live?.judged ?? job.judged_pairs;
                  const total = live?.total ?? job.total_pairs;
                  return (
                    <tr key={job.id}>
                      <Td numeric>{job.id}</Td>
                      <Td>
                        <span className="font-mono text-[12px]">{job.assessor}</span>
                      </Td>
                      <Td>
                        <Badge tone={job.status === "done" ? "positive" : job.status === "failed" ? "negative" : job.status === "running" ? "accent" : "neutral"}>{t(job.status)}</Badge>
                      </Td>
                      <Td className="min-w-40">
                        <div className="h-2 overflow-hidden rounded-pill bg-surface-sunken" aria-hidden>
                          <div className="h-full rounded-pill bg-accent transition-[width]" style={{ width: `${total ? Math.min(100, (judged / total) * 100) : 0}%` }} />
                        </div>
                        <span className="tabular text-caption text-text-tertiary">
                          {judged} / {total}
                          {live?.elapsed_ms !== undefined && typeof live.elapsed_ms === "number" && judged > 0 && (
                            <> · ~{fmtMs(((live.elapsed_ms as number) / judged) * (total - judged))} {t("left")}</>
                          )}
                        </span>
                      </Td>
                      <Td numeric>{job.judged_pairs}</Td>
                      <Td numeric className={job.failed_pairs > 0 ? "text-caution" : ""}>
                        {job.failed_pairs}
                      </Td>
                      <Td numeric>{job.pending_pairs}</Td>
                      <Td>
                        {fmtDateTime(job.started_at)}
                        {job.error && <span className="block text-caption text-negative">{job.error}</span>}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </TableFrame>
        </Card>
      )}

      {pool.data && pool.data.total_entries > 0 && (
        <>
          <Card
            title={t("Pool provenance")}
            subtitle={t("How relevant each class of pool entry turned out. A random-sample relevance rate near 0% is empirical evidence that the pool is close to complete.")}
            padding="sm"
          >
            <TableFrame>
              <Table>
                <thead>
                  <tr>
                    <Th>{t("source")}</Th>
                    <Th numeric>{t("entries")}</Th>
                    <Th numeric>{t("judged")}</Th>
                    <Th numeric>{t("relevant")}</Th>
                    <Th numeric>{t("relevant rate")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(pool.data.by_source).map(([source, bucket]) => (
                    <tr key={source}>
                      <Td>{t(SOURCE_LABEL[source] ?? source)}</Td>
                      <Td numeric>{bucket.entries}</Td>
                      <Td numeric>{bucket.judged}</Td>
                      <Td numeric>{bucket.relevant}</Td>
                      <Td numeric strong>
                        {bucket.judged ? fmtPct(bucket.relevant_rate) : "—"}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableFrame>
          </Card>
          <div className="flex items-center gap-2">
            <span className="text-caption text-text-secondary">{t("Colour by")}</span>
            <SegmentedControl ariaLabel={t("Pool chart mode")} size="sm" options={[{ value: "source", label: t("provenance") }, { value: "ranker", label: t("ranker") }]} value={mode} onChange={setMode} />
          </div>
          <PoolCoverageChart topics={pool.data.per_topic.filter((t) => t.is_judged)} mode={mode} />
          <GradeDistribution counts={collection.grade_counts} />
        </>
      )}

      <Card
        title={t("Topics")}
        subtitle={collection.frozen_at ? t("Oracle queries are visible because the runs are frozen.") : t("Oracle queries stay hidden until the runs are frozen.")}
        padding="sm"
        actions={
          ctx.qrelSets.length > 0 ? (
            <span className="flex flex-wrap gap-2">
              {ctx.qrelSets.map((q) => (
                <a key={q.id} href={apiUrl(`/eval/qrel-sets/${q.id}/trec`)} target="_blank" rel="noreferrer" className="text-caption text-accent hover:underline">
                  {t("TREC qrels")} ({q.aggregation}) ↗
                </a>
              ))}
              {ctx.latestRuns.map((r) => (
                <a key={r.id} href={apiUrl(`/eval/runs/${r.id}/trec`)} target="_blank" rel="noreferrer" className="text-caption text-accent hover:underline">
                  {t("run")} {rankerLabel(r.ranker)} ↗
                </a>
              ))}
            </span>
          ) : undefined
        }
      >
        {topics.isPending && <Skeleton lines={6} />}
        {topics.isError && <ErrorState error={topics.error} compact />}
        {topics.data && (
          <TableFrame>
            <Table>
              <thead>
                <tr>
                  <Th numeric>#</Th>
                  <Th>{t("title")}</Th>
                  <Th>{t("category")}</Th>
                  <Th>{t("judged")}</Th>
                  <Th numeric>{t("pool")}</Th>
                  <Th numeric>{t("judged pairs")}</Th>
                  <Th>{t("oracle query")}</Th>
                </tr>
              </thead>
              <tbody>
                {topics.data.map((topic) => (
                  <tr key={topic.id} className={topic.is_judged ? "" : "opacity-60"}>
                    <Td numeric>{topic.ext_id}</Td>
                    <Td>
                      <span className="font-medium">{topic.title}</span>
                      {topic.description && <span className="block text-caption text-text-tertiary">{topic.description}</span>}
                    </Td>
                    <Td>{topic.category && <Badge>{t(topic.category)}</Badge>}</Td>
                    <Td>{topic.is_judged ? <Badge tone="accent">{t("judged set")}</Badge> : <Badge>{t("held out")}</Badge>}</Td>
                    <Td numeric>{topic.pool_size}</Td>
                    <Td numeric>{topic.judged_pairs}</Td>
                    <Td className="text-text-secondary">{topic.oracle_query ?? <span className="text-text-tertiary">{t("hidden")}</span>}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableFrame>
        )}
      </Card>
    </div>
  );
}

function Step({ n, title, done, detail, action }: { n: number; title: string; done: boolean; detail: string; action: React.ReactNode }) {
  return (
    <li className="flex flex-col gap-2 rounded-panel border border-hairline p-4">
      <div className="flex items-center gap-2">
        <span className={`inline-flex size-6 items-center justify-center rounded-full text-caption font-semibold ${done ? "bg-positive text-on-accent" : "bg-surface-sunken text-text-secondary"}`} aria-hidden>
          {done ? "✓" : n}
        </span>
        <span className="font-medium">{title}</span>
      </div>
      <p className="flex-1 text-caption text-text-secondary">{detail}</p>
      <div>{action}</div>
    </li>
  );
}
