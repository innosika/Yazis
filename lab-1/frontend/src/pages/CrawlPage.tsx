import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ACTIVE_JOB_STATUSES, api, type CrawlJob } from "@/lib/api";
import { fmtBytes, fmtDateTime, fmtInt, fmtMs } from "@/lib/format";
import { keys, pollWhileActive } from "@/lib/queries";
import { crawlRoute } from "@/routes/router";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { HelpTip } from "@/components/ui/HelpTip";
import { LiveRegion } from "@/components/ui/LiveRegion";
import { LogConsole } from "@/components/ui/LogConsole";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { Table, TableFrame, Td, Th } from "@/components/ui/Table";
import { Toggle } from "@/components/ui/Toggle";
import { useCrawlProgress } from "@/features/crawl/progress";
import { t } from "@/lib/i18n";

const STATUS_TONE: Record<string, "neutral" | "accent" | "positive" | "caution" | "negative"> = {
  pending: "neutral",
  running: "accent",
  done: "positive",
  failed: "negative",
  cancelled: "caution",
  indexed: "positive",
  skipped: "caution",
  fetched: "accent",
  in_progress: "accent",
};

const STAGE_COLORS = ["var(--accent)", "var(--ranker-fts)", "var(--ranker-bm25)", "var(--ranker-semantic)", "var(--ranker-hybrid)"];

export function CrawlPage() {
  const search = crawlRoute.useSearch();
  const navigate = useNavigate({ from: crawlRoute.fullPath });
  const queryClient = useQueryClient();

  const [seeds, setSeeds] = useState(search.seed ?? "https://en.wikipedia.org/wiki/Okapi_BM25");
  const [maxPages, setMaxPages] = useState(5);
  const [maxDepth, setMaxDepth] = useState(1);
  const [sameDomain, setSameDomain] = useState(true);
  const [urlStatus, setUrlStatus] = useState<string | undefined>(undefined);

  const jobs = useQuery({
    queryKey: keys.crawl.jobs,
    queryFn: () => api.crawl.jobs(20),
    refetchInterval: pollWhileActive<CrawlJob>(ACTIVE_JOB_STATUSES),
  });
  const selectedId = search.job ?? jobs.data?.[0]?.id;
  const job = useQuery({
    queryKey: keys.crawl.job(selectedId ?? 0),
    queryFn: () => api.crawl.job(selectedId ?? 0),
    enabled: selectedId !== undefined,
    refetchInterval: pollWhileActive<CrawlJob>(ACTIVE_JOB_STATUSES),
  });
  const urlParams = { limit: 200, ...(urlStatus ? { status: urlStatus } : {}) };
  const urls = useQuery({
    queryKey: keys.crawl.urls(selectedId ?? 0, urlParams),
    queryFn: () => api.crawl.urls(selectedId ?? 0, urlParams),
    enabled: selectedId !== undefined,
    refetchInterval: job.data && ACTIVE_JOB_STATUSES.has(job.data.status) ? 3_000 : false,
  });

  const progress = useCrawlProgress(selectedId);
  const lastAnnouncedRef = useRef(0);
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => {
    const count = progress.records.length;
    if (count - lastAnnouncedRef.current >= 10) {
      lastAnnouncedRef.current = count;
      const last = progress.records[count - 1];
      if (last) setAnnouncement(`${count} crawl events; latest: ${last.event} ${last.url ?? ""}`);
    }
  }, [progress.records]);

  const start = useMutation({
    mutationFn: () =>
      api.crawl.start({
        seed_urls: seeds
          .split(/\s+/)
          .map((s) => s.trim())
          .filter(Boolean),
        max_pages: maxPages,
        max_depth: maxDepth,
        same_domain_only: sameDomain,
      }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: keys.crawl.all });
      await navigate({ search: { ...search, job: created.id } });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    start.mutate();
  };

  const j = job.data;
  const budget = j ? Math.max(j.max_pages, 1) : 1;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow={t("Acquisition")}
        title={t("Crawl")}
        description={t("Collect documents from the web: robots.txt-aware fetching, boilerplate removal, SimHash near-duplicate rejection, then indexing. Progress streams live from the worker.")}
        helpAnchor="help-crawl"
      />

      <div className="grid gap-6 lg:grid-cols-[2fr_3fr]">
        <div className="space-y-6">
          <Card title={t("New crawl")}>
            <form onSubmit={submit} className="space-y-4">
              <label className="block">
                <span className="text-caption text-text-secondary">{t("Seed URLs, one per line (max 20)")}</span>
                <textarea
                  value={seeds}
                  onChange={(event) => setSeeds(event.target.value)}
                  rows={3}
                  required
                  className="mt-1 w-full rounded-panel border border-hairline-strong bg-surface px-3 py-2 font-mono text-[13px] text-text"
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-caption text-text-secondary">{t("Max pages")}</span>
                  <input
                    type="number"
                    min={1}
                    max={500}
                    value={maxPages}
                    onChange={(event) => setMaxPages(Number(event.target.value))}
                    className="mt-1 w-full rounded-pill border border-hairline-strong bg-surface px-3 py-1.5 text-text"
                  />
                </label>
                <label className="block">
                  <span className="text-caption text-text-secondary">{t("Max depth")}</span>
                  <input
                    type="number"
                    min={0}
                    max={3}
                    value={maxDepth}
                    onChange={(event) => setMaxDepth(Number(event.target.value))}
                    className="mt-1 w-full rounded-pill border border-hairline-strong bg-surface px-3 py-1.5 text-text"
                  />
                </label>
              </div>
              <Toggle
                checked={sameDomain}
                onChange={setSameDomain}
                label={t("Stay on the seed's domain")}
                description={t("Off-domain crawling wanders the whole web; keep it on for a bounded crawl.")}
              />
              {start.isError && <ErrorState error={start.error} compact />}
              <Button type="submit" variant="primary" loading={start.isPending}>
                {t("Start crawl")}
              </Button>
            </form>
          </Card>

          <Card title={t("Recent jobs")}>
            {jobs.isPending && <Skeleton lines={4} />}
            {jobs.isError && <ErrorState error={jobs.error} compact />}
            {jobs.data && jobs.data.length === 0 && <EmptyState title={t("No crawl yet")} description={t("Start one above.")} />}
            {jobs.data && jobs.data.length > 0 && (
              <ul className="divide-y divide-hairline">
                {jobs.data.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => void navigate({ search: { ...search, job: item.id } })}
                      aria-current={item.id === selectedId || undefined}
                      className={`flex w-full items-center justify-between gap-3 py-2 text-left hover:text-accent ${
                        item.id === selectedId ? "text-accent" : "text-text"
                      }`}
                    >
                      <span className="min-w-0 truncate text-[14px]">
                        <span className="tabular text-text-tertiary">#{item.id}</span> {item.seed_urls[0]}
                        {item.seed_urls.length > 1 && ` +${item.seed_urls.length - 1}`}
                      </span>
                      <span className="flex shrink-0 items-center gap-2 text-caption">
                        <span className="tabular text-text-secondary">{item.pages_indexed} {t("indexed")}</span>
                        <Badge tone={STATUS_TONE[item.status] ?? "neutral"}>{t(item.status)}</Badge>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          {j ? (
            <Card
              title={
                <span className="flex items-center gap-2">
                  {t("Job")} #{j.id} <Badge tone={STATUS_TONE[j.status] ?? "neutral"}>{t(j.status)}</Badge>
                </span>
              }
              subtitle={`${j.seed_urls.join(", ")} · ${t("depth ≤ {d}", { d: j.max_depth })} · ${t("{n} pages", { n: j.max_pages })} · ${
                j.started_at ? t("started {when}", { when: fmtDateTime(j.started_at) }) : t("queued")
              }`}
            >
              <div className="mb-3 h-2 overflow-hidden rounded-pill bg-surface-sunken" aria-hidden>
                <div
                  className="h-full rounded-pill bg-accent transition-[width]"
                  style={{ width: `${Math.min(100, (j.pages_indexed / budget) * 100)}%` }}
                />
              </div>
              <dl className="grid grid-cols-3 gap-3 text-caption sm:grid-cols-6">
                <Counter label={t("pages fetched")} value={j.pages_fetched} />
                <Counter label={t("pages indexed")} value={j.pages_indexed} />
                <Counter label={t("pages skipped")} value={j.pages_skipped} />
                <Counter label={t("pages failed")} value={j.pages_failed} />
                <Counter label={t("links found")} value={j.urls_discovered} />
                <Counter label={t("queued")} value={j.pending_urls} />
              </dl>
              <p className="mt-2 text-caption text-text-tertiary">
                {fmtBytes(j.bytes_downloaded)} {t("downloaded")}
                {j.error && <span className="text-negative"> · {j.error}</span>}
              </p>
              {Object.keys(j.skip_breakdown).length > 0 && (
                <div className="mt-3">
                  <p className="mb-1 flex items-center gap-1 text-caption text-text-secondary">
                    {t("Why pages were skipped")}
                    <HelpTip anchor="help-crawl">
                      {t("Every skipped URL carries a reason: robots.txt, exact or near duplicate (SimHash), too short after boilerplate removal, wrong content type, HTTP errors.")}
                    </HelpTip>
                  </p>
                  <div className="flex h-3 overflow-hidden rounded-pill" role="img" aria-label={t("Skip reasons")}>
                    {Object.entries(j.skip_breakdown).map(([reason, count], index) => (
                      <span
                        key={reason}
                        title={`${t(reason)}: ${count}`}
                        style={{ flex: count, background: STAGE_COLORS[index % STAGE_COLORS.length] }}
                      />
                    ))}
                  </div>
                  <ul className="mt-1 flex flex-wrap gap-x-3 text-caption text-text-secondary">
                    {Object.entries(j.skip_breakdown).map(([reason, count], index) => (
                      <li key={reason} className="flex items-center gap-1">
                        <span className="size-2 rounded-full" style={{ background: STAGE_COLORS[index % STAGE_COLORS.length] }} />
                        {t(reason)} <span className="tabular">{count}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          ) : (
            <EmptyState title={t("Select a job")} description={t("Progress, the frontier and the live feed appear here.")} />
          )}

          <Card
            title={t("Live feed")}
            subtitle={
              <span className="flex items-center gap-2">
                <span
                  aria-hidden
                  className={`size-2 rounded-full ${
                    progress.state === "open" ? "bg-positive" : progress.state === "connecting" ? "bg-caution" : "bg-text-tertiary"
                  }`}
                />
                {progress.state === "open" ? t("streaming") : t(progress.state)}
                {progress.state === "error" && (
                  <Button size="sm" variant="ghost" onClick={progress.reconnect}>
                    {t("reconnect")}
                  </Button>
                )}
              </span>
            }
            actions={
              <Button size="sm" onClick={progress.clear}>
                {t("Clear")}
              </Button>
            }
          >
            <LiveRegion message={announcement} />
            {progress.records.length === 0 ? (
              <p className="text-caption text-text-tertiary">{t("Events appear here as the worker fetches pages.")}</p>
            ) : (
              <ul className="max-h-64 space-y-1 overflow-y-auto font-mono text-[12px]">
                {progress.records.slice(-60).reverse().map((event, index) => (
                  <li key={`${event.job_id ?? 0}-${index}`} className="flex gap-2">
                    <Badge tone={STATUS_TONE[event.event] ?? "neutral"}>{t(event.event)}</Badge>
                    <span className="min-w-0 truncate text-text-secondary">
                      {event.url ?? (event.event === "finished" ? t("{n} indexed in {time}", { n: event.indexed ?? 0, time: fmtMs(event.duration_ms ?? 0) }) : "")}
                      {event.reason && <span className="text-caution"> {t(event.reason)}</span>}
                      {event.chars !== undefined && <span className="text-text-tertiary"> {fmtInt(event.chars)} {t("chars")}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {selectedId !== undefined && (
        <Card
          className="mt-6"
          title={t("Frontier")}
          subtitle={t("Every URL the job saw, with its decision and per-stage timings.")}
          actions={
            <select
              aria-label={t("Filter by URL status")}
              value={urlStatus ?? ""}
              onChange={(event) => setUrlStatus(event.target.value || undefined)}
              className="rounded-pill border border-hairline bg-surface px-3 py-1 text-caption text-text"
            >
              <option value="">{t("all statuses")}</option>
              {["pending", "in_progress", "fetched", "indexed", "skipped", "failed"].map((s) => (
                <option key={s} value={s}>
                  {t(s)}
                </option>
              ))}
            </select>
          }
        >
          {urls.isPending && <Skeleton lines={5} />}
          {urls.isError && <ErrorState error={urls.error} compact />}
          {urls.data && (
            <TableFrame>
              <Table>
                <thead>
                  <tr>
                    <Th>URL</Th>
                    <Th numeric>{t("depth")}</Th>
                    <Th>{t("status")}</Th>
                    <Th>{t("reason")}</Th>
                    <Th numeric>HTTP</Th>
                    <Th numeric>{t("chars")}</Th>
                    <Th numeric>{t("bytes")}</Th>
                    <Th>{t("stage timings")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {urls.data.map((task) => (
                    <tr key={task.id}>
                      <Td>
                        <a href={task.url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
                          {task.url.length > 70 ? `${task.url.slice(0, 70)}…` : task.url}
                        </a>
                      </Td>
                      <Td numeric>{task.depth}</Td>
                      <Td>
                        <Badge tone={STATUS_TONE[task.status] ?? "neutral"}>{t(task.status)}</Badge>
                      </Td>
                      <Td className="text-text-secondary">{task.skip_reason ? t(task.skip_reason) : (task.error ?? "")}</Td>
                      <Td numeric>{task.http_status ?? ""}</Td>
                      <Td numeric>{task.extracted_chars != null ? fmtInt(task.extracted_chars) : ""}</Td>
                      <Td numeric>{task.content_bytes != null ? fmtBytes(task.content_bytes) : ""}</Td>
                      <Td>
                        <StageBar timings={task.stage_timings_ms ?? undefined} />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableFrame>
          )}
        </Card>
      )}

      <section className="mt-6">
        <h2 className="mb-2 text-[17px] font-semibold tracking-tight">{t("Crawler log")}</h2>
        <LogConsole loggerPrefix="irs.crawler" minLevel="info" height="18rem" />
      </section>
    </div>
  );
}

function Counter({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt className="text-text-tertiary">{label}</dt>
      <dd className="tabular text-[17px] font-semibold text-text">{fmtInt(value)}</dd>
    </div>
  );
}

function StageBar({ timings }: { timings?: Record<string, unknown> | undefined }) {
  if (!timings) return null;
  const entries = Object.entries(timings).filter((entry): entry is [string, number] => typeof entry[1] === "number");
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  if (total <= 0) return null;
  return (
    <span className="flex w-40 items-center gap-2" title={entries.map(([k, v]) => `${k}: ${fmtMs(v)}`).join("\n")}>
      <span className="flex h-2 flex-1 overflow-hidden rounded-pill bg-surface-sunken" aria-hidden>
        {entries.map(([stage, ms], index) => (
          <span key={stage} style={{ flex: ms, background: STAGE_COLORS[index % STAGE_COLORS.length] }} />
        ))}
      </span>
      <span className="tabular text-caption text-text-tertiary">{fmtMs(total)}</span>
    </span>
  );
}
