/**
 * Blind judging. The assessor sees the topic and the document — never which ranker
 * retrieved the pair, at what rank, or with what score.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { GRADE_META, GRADE_ORDER } from "@/lib/grades";
import { keys } from "@/lib/queries";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { HelpTip } from "@/components/ui/HelpTip";
import { Kbd } from "@/components/ui/Kbd";
import { LiveRegion } from "@/components/ui/LiveRegion";
import { Skeleton } from "@/components/ui/Skeleton";
import { useEvaluationContext } from "@/features/evaluation/useEvaluationContext";
import { t } from "@/lib/i18n";

const STORAGE_KEY = "irs.assessor";

export function JudgePage() {
  const ctx = useEvaluationContext();
  const queryClient = useQueryClient();
  const collectionId = ctx.collection?.id ?? 0;
  const [assessor, setAssessor] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) ?? "";
    } catch {
      return "";
    }
  });
  const [started, setStarted] = useState(false);
  const [message, setMessage] = useState("");
  const [note, setNote] = useState("");
  const shownAt = useRef<number>(Date.now());

  const pair = useQuery({
    queryKey: ["eval", "pool-next", collectionId, assessor],
    queryFn: () => api.eval.poolNext(collectionId, assessor),
    enabled: started && collectionId > 0 && assessor.trim().length > 0,
    staleTime: Infinity,
    gcTime: 0,
  });

  useEffect(() => {
    shownAt.current = Date.now();
    setNote("");
  }, [pair.data?.document.id]);

  const judge = useMutation({
    mutationFn: (grade: string) =>
      api.eval.judge({
        query_id: pair.data?.topic.id ?? 0,
        document_id: pair.data?.document.id ?? 0,
        assessor,
        grade,
        seconds_spent: (Date.now() - shownAt.current) / 1000,
        ...(note.trim() ? { note: note.trim() } : {}),
      }),
    onSuccess: async () => {
      const remaining = (pair.data?.remaining ?? 1) - 1;
      setMessage(t("Saved. {n} pair(s) remaining.", { n: remaining }));
      await pair.refetch();
      void queryClient.invalidateQueries({ queryKey: keys.eval.collections });
    },
  });

  useEffect(() => {
    if (!pair.data || judge.isPending) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
      const index = ["1", "2", "3", "4", "5"].indexOf(event.key);
      if (index === -1) return;
      const grade = GRADE_ORDER[index];
      if (grade) judge.mutate(grade);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pair.data, judge]);

  const begin = () => {
    try {
      localStorage.setItem(STORAGE_KEY, assessor.trim());
    } catch {
      // ignore
    }
    setStarted(true);
  };

  if (!ctx.collection) return <Skeleton lines={5} />;
  if (ctx.collection.is_known_item) {
    return <EmptyState title={t("The known-item collection is judged automatically")} description={t("Its judgments follow from the construction: the source document of each derived query is the one relevant answer. Switch to the topical collection to judge by hand.")} />;
  }

  if (!started) {
    return (
      <Card title={t("Judge the pool by hand")} subtitle={t("Pairs are served blind and in a shuffled order that cannot correlate with any ranker. Your grades are recorded under your name as a human assessor.")}>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (assessor.trim()) begin();
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <label className="block">
            <span className="text-caption text-text-secondary">{t("Your name")}</span>
            <input value={assessor} onChange={(event) => setAssessor(event.target.value)} required className="mt-1 block rounded-pill border border-hairline-strong bg-surface px-4 py-2 text-text" />
          </label>
          <Button type="submit" variant="primary">
            {t("Start judging")}
          </Button>
          <HelpTip anchor="help-judging">
            {t("ROMIP's five-point scale: vital, relevant+, relevant−, not relevant, cannot judge. Use the topic's narrative as the authority for borderline cases. Keys 1–5 grade without touching the mouse.")}
          </HelpTip>
        </form>
      </Card>
    );
  }

  if (pair.isPending) return <Skeleton lines={8} />;
  if (pair.isError) return <ErrorState error={pair.error} onRetry={() => void pair.refetch()} />;
  if (pair.data === null) {
    return <EmptyState title={t("Nothing left to judge")} description={t("Every pool pair of the judged topics has a grade from {assessor}. Materialise the relevance tables and run the rankers.", { assessor })} />;
  }
  const current = pair.data;

  return (
    <div className="space-y-4">
      <LiveRegion message={message} />
      <div className="flex flex-wrap items-center gap-3 text-caption text-text-secondary">
        <span>
          <strong className="tabular text-text">{current.judged_by_you}</strong> {t("judged")} · <strong className="tabular text-text">{current.remaining}</strong> {t("remaining of {total}", { total: current.total })}
        </span>
        <div className="h-2 flex-1 min-w-32 overflow-hidden rounded-pill bg-surface-sunken" aria-hidden>
          <div className="h-full rounded-pill bg-accent transition-[width]" style={{ width: `${(current.judged_by_you / Math.max(current.total, 1)) * 100}%` }} />
        </div>
        <Badge>{t("assessor")}: {assessor}</Badge>
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr_3fr]">
        <Card title={t("Topic")} subtitle={`#${current.topic.ext_id}`}>
          <p className="text-[19px] font-semibold tracking-tight">{current.topic.title}</p>
          {current.topic.description && <p className="mt-2 text-[15px] text-text-secondary">{current.topic.description}</p>}
          {current.topic.narrative && (
            <div className="mt-3 rounded-panel bg-surface-sunken p-3 text-[14px] leading-relaxed">
              <p className="mb-1 text-caption font-medium uppercase tracking-wide text-text-tertiary">{t("Narrative — what counts as relevant")}</p>
              {current.topic.narrative}
            </div>
          )}
        </Card>
        <Card title={current.document.title} subtitle={<a href={current.document.url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">{current.document.url} ↗</a>}>
          <div className="max-h-[50vh] overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed text-text">{current.document.text}</div>
        </Card>
      </div>

      <Card title={t("Your judgment")}>
        <div className="flex flex-wrap gap-2">
          {GRADE_ORDER.map((grade, index) => {
            const meta = GRADE_META[grade];
            const level = meta?.level;
            return (
              <Button key={grade} onClick={() => judge.mutate(grade)} loading={judge.isPending && judge.variables === grade} disabled={judge.isPending} className="!justify-start gap-2">
                <Kbd>{index + 1}</Kbd>
                <span aria-hidden className="size-2.5 rounded-full" style={{ background: level == null ? "var(--hairline-strong)" : `var(--relevance-${level})` }} />
                {t(meta?.label ?? grade)}
              </Button>
            );
          })}
        </div>
        <label className="mt-3 block">
          <span className="text-caption text-text-secondary">{t("Note (optional)")}</span>
          <input value={note} onChange={(event) => setNote(event.target.value)} className="mt-1 block w-full rounded-pill border border-hairline bg-surface px-3 py-1.5 text-[14px] text-text" placeholder={t("why this grade, if not obvious")} />
        </label>
        {judge.isError && (
          <div className="mt-3">
            <ErrorState error={judge.error} compact />
          </div>
        )}
      </Card>
    </div>
  );
}
