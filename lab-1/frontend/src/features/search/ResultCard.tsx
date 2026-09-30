import { motion } from "motion/react";
import type { SearchHit } from "@/lib/api";
import { fmtDate, fmtScore } from "@/lib/format";
import { Badge, RankerBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { HighlightedSnippet } from "./HighlightedSnippet";
import { t } from "@/lib/i18n";

interface Props {
  hit: SearchHit;
  position: number;
  ranker: string;
  queryLemmas: string[];
  canExplain: boolean;
  onExplain: (hit: SearchHit) => void;
}

export function ResultCard({ hit, position, ranker, queryLemmas, canExplain, onExplain }: Props) {
  const missing = queryLemmas.filter((lemma) => !hit.matched_lemmas.includes(lemma));
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: Math.min(position, 8) * 0.03 }}
      className="rounded-card border border-hairline bg-surface p-5 shadow-sm"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="mb-1 flex flex-wrap items-center gap-x-2 text-caption text-text-tertiary">
            <span className="tabular">#{position}</span>
            <span aria-hidden>·</span>
            <span className="truncate">{hit.source_domain || new URL(hit.url).hostname}</span>
            {hit.date && (
              <>
                <span aria-hidden>·</span>
                <time dateTime={hit.date}>{fmtDate(hit.date)}</time>
              </>
            )}
          </p>
          {/* The assignment's «активная ссылка на документ». */}
          <a
            href={hit.url}
            target="_blank"
            rel="noreferrer noopener"
            className="text-[19px] font-semibold tracking-tight text-accent hover:underline"
          >
            {hit.title || hit.url}
          </a>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <span className="tabular text-[15px] font-semibold text-text" title={t("rank (similarity score)")}>
            {fmtScore(hit.rank)}
          </span>
          <RankerBadge ranker={ranker} />
        </div>
      </div>

      <div className="mt-3">
        <HighlightedSnippet hit={hit} />
      </div>

      {/* The assignment's «список слов запроса, присутствующих в документе». */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5" aria-label={t("Query words present in this document")}>
        <span className="text-caption text-text-tertiary">{t("Query words found:")}</span>
        {hit.matched_lemmas.length === 0 && <span className="text-caption text-text-tertiary">{t("none")}</span>}
        {hit.matched_lemmas.map((lemma) => (
          <Badge key={lemma} tone="accent">
            {lemma}
          </Badge>
        ))}
        {missing.map((lemma) => (
          <Badge key={lemma} tone="neutral" title={t("not present in this document")} className="line-through opacity-70">
            {lemma}
          </Badge>
        ))}
        <span className="ml-auto">
          {canExplain ? (
            <Button variant="ghost" size="sm" onClick={() => onExplain(hit)}>
              {t("Why this score?")}
            </Button>
          ) : (
            <span className="text-caption text-text-tertiary" title={t("The derivation panel explains the vector model's cosine; this ranker scores differently.")}>
              {t("derivation available for the vector model")}
            </span>
          )}
        </span>
      </div>
    </motion.li>
  );
}
