import type { SearchHit } from "@/lib/api";
import { normaliseRanges } from "@/lib/highlights";
import { t } from "@/lib/i18n";

export function HighlightedSnippet({ hit }: { hit: Pick<SearchHit, "snippet" | "highlights"> }) {
  const text = hit.snippet;
  const ranges = normaliseRanges(hit.highlights, text.length);
  if (ranges.length === 0) return <p className="text-[15px] leading-relaxed text-text-secondary">{text}</p>;

  const parts: Array<{ text: string; mark: boolean; lemma?: string }> = [];
  let cursor = 0;
  for (const range of ranges) {
    if (range.start > cursor) parts.push({ text: text.slice(cursor, range.start), mark: false });
    parts.push({ text: text.slice(range.start, range.end), mark: true, lemma: range.lemma });
    cursor = range.end;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), mark: false });

  return (
    <p className="text-[15px] leading-relaxed text-text-secondary">
      {parts.map((part, index) =>
        part.mark ? (
          <mark
            key={index}
            title={part.lemma ? t("matches query word “{lemma}”", { lemma: part.lemma }) : undefined}
            className="rounded bg-accent-soft px-0.5 text-text"
          >
            {part.text}
          </mark>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </p>
  );
}
